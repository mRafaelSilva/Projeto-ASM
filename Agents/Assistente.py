import asyncio
import json
from typing import Any, Dict, Optional, Set
import jsonpickle
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import utils.utilsAssistente as utilsAssistente


def _safe_decode_body(body: Optional[str]) -> dict:
    try:
        decoded = jsonpickle.decode(body)
        if isinstance(decoded, dict): return decoded
    except Exception: pass
    try:
        decoded = json.loads(body) if body else {}
        return decoded if isinstance(decoded, dict) else {}
    except Exception: return {}


class AssistenteAgent(Agent):
    INTENTS_NO_FINANCIAL_CHECK: Set[str] = {"horarios", "ajuda", "saudacao"}

    def __init__(self, jid, password):
        super().__init__(jid, password)
        self._contexts: Dict[str, Dict[str, Any]] = {}

    async def setup(self):
        print(f"[Assistente] {str(self.jid)} iniciado.")
        self.add_behaviour(self.ReceiveUserRequestBehaviour())
        self.add_behaviour(self.ReceiveInformBehaviour())

    def _get_ctx(self, user_jid: str) -> Dict[str, Any]:
        return self._contexts.setdefault(user_jid, {
            "user_jid": user_jid, "intencao": None, "slots": {}, "pendente": None, "awaiting": None
        })

    # --- Helpers de Envio ---
    async def _ask_for_slot(self, behaviour: CyclicBehaviour, user_jid: str, slot_name: str):
        msg = Message(to=user_jid)
        msg.set_metadata("performative", "request")
        msg.body = json.dumps({"type": "ask", "slot": slot_name, "prompt": f"Por favor, indique: {slot_name}"}, ensure_ascii=False)
        await behaviour.send(msg)

    async def _reply_to_user(self, behaviour: CyclicBehaviour, user_jid: str, payload: dict):
        msg = Message(to=user_jid)
        msg.set_metadata("performative", "inform")
        msg.body = json.dumps(payload, ensure_ascii=False)
        await behaviour.send(msg)

    async def _query_debt_status(self, behaviour: CyclicBehaviour, user_jid: str, estudante_id: Any):
        msg = Message(to="financeiro@localhost")
        msg.set_metadata("performative", "query-if")
        msg.body = jsonpickle.encode({"acao": "has_debt", "estudante_id": estudante_id, "to_user": user_jid})
        await behaviour.send(msg)

    async def _request_debt_payment(self, behaviour: CyclicBehaviour, user_jid: str, estudante_id: Any, valor: float):
        msg = Message(to="financeiro@localhost")
        msg.set_metadata("performative", "request")
        msg.body = jsonpickle.encode({"acao": "pay_debt", "estudante_id": estudante_id, "valor": valor, "to_user": user_jid})
        await behaviour.send(msg)

    async def _forward_to_horarios(self, behaviour: CyclicBehaviour, user_jid: str, curso: str, disciplinas: list):
        msg = Message(to="horarios@localhost")
        msg.set_metadata("performative", "request")
        msg.body = jsonpickle.encode({"acao": "check_schedule", "curso": curso, "disciplinas": disciplinas, "to_user": user_jid})
        await behaviour.send(msg)

    async def processar_intencao_negocio(self, behaviour: CyclicBehaviour, user_jid: str, intencao: str, ctx: dict):
        if intencao == "saudacao":
            await self._reply_to_user(behaviour, user_jid, {"msg": "Olá! Em que posso ajudar? (inscrições, horários, pagamentos)"})
            return

        if intencao == "horarios":
            required = ["curso", "disciplina"]
            missing = [k for k in required if not ctx["slots"].get(k)]
            if missing:
                ctx["awaiting"] = missing[0]
                await self._ask_for_slot(behaviour, user_jid, missing[0])
                return
            await self._forward_to_horarios(behaviour, user_jid, ctx["slots"]["curso"], ctx["slots"]["disciplina"])
        
        elif intencao == "inscricao":
            required = ["curso", "disciplina"]
            missing = [k for k in required if not ctx["slots"].get(k)]
            if missing:
                ctx["awaiting"] = missing[0]
                await self._ask_for_slot(behaviour, user_jid, missing[0])
                return
            await self._reply_to_user(behaviour, user_jid, {"ok": True, "msg": f"Inscrição realizada em {ctx['slots']['disciplina']}"})
        
        elif intencao == "desconhecida":
             await self._reply_to_user(behaviour, user_jid, {"ok": False, "msg": "Não percebi. Tente 'inscrever em LEI', 'ver horario' ou 'pagar propina'."})

        else:
            await self._reply_to_user(behaviour, user_jid, {"ok": False, "erro": "intencao_nao_implementada", "intencao": intencao})


    # --- Behaviours ---

    class ReceiveUserRequestBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg or msg.get_metadata("performative") != "request": return

            user_jid = str(msg.sender).split("/")[0]
            ctx = self.agent._get_ctx(user_jid)
            
            try: data = json.loads(msg.body) if msg.body else {}
            except: data = {}

            texto = (data.get("texto") or "").strip()
            intencao = utilsAssistente.get_intencao(texto)
            ctx["intencao"] = intencao
            ctx["slots"].update(utilsAssistente.extrair_slots(intencao, texto))

            if "curso" in ctx["slots"]: ctx["slots"]["curso"] = utilsAssistente.normalizar_curso(ctx["slots"]["curso"])
            if "disciplina" in ctx["slots"]: ctx["slots"]["disciplina"] = utilsAssistente.normalizar_disciplinas(ctx["slots"]["disciplina"])

            # Pagamentos
            if intencao == "fazer_pagamento":
                if not ctx["slots"].get("numero_aluno"):
                    ctx["awaiting"] = "numero_aluno"
                    await self.agent._ask_for_slot(self, user_jid, "numero_aluno")
                    return
                if not ctx["slots"].get("valor"):
                    ctx["awaiting"] = "valor"
                    await self.agent._ask_for_slot(self, user_jid, "valor")
                    return
                await self.agent._request_debt_payment(self, user_jid, ctx["slots"]["numero_aluno"], ctx["slots"]["valor"])
                return

            # Ver Saldo
            if intencao == "ver_saldo":
                if not ctx["slots"].get("numero_aluno"):
                    ctx["awaiting"] = "numero_aluno"
                    ctx["pendente"] = "ver_saldo"
                    await self.agent._ask_for_slot(self, user_jid, "numero_aluno")
                    return
                ctx["pendente"] = "ver_saldo"
                await self.agent._query_debt_status(self, user_jid, ctx["slots"]["numero_aluno"])
                return

            # Intents Seguros
            if intencao in self.agent.INTENTS_NO_FINANCIAL_CHECK:
                await self.agent.processar_intencao_negocio(self, user_jid, intencao, ctx)
                return

            # Intents Sensíveis -> Validar Dívida
            if not ctx["slots"].get("numero_aluno"):
                ctx["awaiting"] = "numero_aluno"
                ctx["pendente"] = intencao 
                await self.agent._ask_for_slot(self, user_jid, "numero_aluno")
                return
            
            ctx["pendente"] = intencao
            await self.agent._query_debt_status(self, user_jid, ctx["slots"]["numero_aluno"])


    class ReceiveInformBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg: return

            perf = msg.get_metadata("performative")
            sender = str(msg.sender).split("/")[0]
            data = _safe_decode_body(msg.body)

            # Resposta do User
            if sender.startswith("user@") and perf == "inform":
                if data.get("type") != "answer": return

                user_jid = sender
                ctx = self.agent._get_ctx(user_jid)
                slot = ctx.get("awaiting")
                valor = data.get("value")
                
                if slot:
                    # Normalizações
                    if slot == "curso": valor = utilsAssistente.normalizar_curso(valor)
                    if slot == "disciplina": valor = utilsAssistente.normalizar_disciplinas(valor)
                    if slot in ["numero_aluno", "valor"]: valor = str(valor).strip()
                    
                    ctx["slots"][slot] = valor
                    ctx["awaiting"] = None
                    pendente = ctx.get("pendente")
                    
                    # Se era Fazer Pagamento
                    if ctx.get("intencao") == "fazer_pagamento":
                        if not ctx["slots"].get("numero_aluno"):
                            ctx["awaiting"] = "numero_aluno"
                            await self.agent._ask_for_slot(self, user_jid, "numero_aluno")
                            return
                        
                        if not ctx["slots"].get("valor"):
                            ctx["awaiting"] = "valor"
                            await self.agent._ask_for_slot(self, user_jid, "valor")
                            return

                        try: val_float = float(ctx["slots"]["valor"])
                        except: val_float = 0.0
                        
                        await self.agent._request_debt_payment(self, user_jid, ctx["slots"]["numero_aluno"], val_float)
                        return

                    # Se era Ver Saldo
                    if pendente == "ver_saldo" and slot == "numero_aluno":
                        await self.agent._query_debt_status(self, user_jid, valor)
                        return

                    # Se preenchemos aluno e havia operação pendente sensível
                    if slot == "numero_aluno" and pendente and pendente not in self.agent.INTENTS_NO_FINANCIAL_CHECK:
                        await self.agent._query_debt_status(self, user_jid, valor)
                        return

                    target = pendente if pendente else ctx.get("intencao")
                    await self.agent.processar_intencao_negocio(self, user_jid, target, ctx)
                return

            # Resposta do Financeiro
            if sender.startswith("financeiro@"):
                to_user = data.get("to_user")
                if not to_user: return
                ctx = self.agent._get_ctx(to_user)

                if perf == "inform" and "debt" in data:
                    # Apenas Ver Saldo
                    if ctx.get("pendente") == "ver_saldo":
                        saldo = data.get("saldo", 0)
                        divida = data.get("valor", 0)
                        msg_texto = f"A sua situação financeira: Saldo = {saldo}€."
                        if data["debt"] == "yes":
                            msg_texto += f" Atenção: Tem {divida}€ em dívida!"
                        else:
                            msg_texto += " Situação regularizada."
                        
                        await self.agent._reply_to_user(self, to_user, {"msg": msg_texto})
                        ctx["pendente"] = None
                        return

                    # Bloqueio por Dívida
                    if data["debt"] == "yes":
                        ctx["pendente"] = None
                        await self.agent._reply_to_user(self, to_user, {
                            "ok": False, 
                            "msg": f"Operação bloqueada. Tem uma dívida de {data.get('valor')}€.",
                            "valor_divida": data.get("valor")
                        })
                    else:
                        op_pendente = ctx.get("pendente")
                        if op_pendente:
                            await self.agent.processar_intencao_negocio(self, to_user, op_pendente, ctx)
                            ctx["pendente"] = None
                    return

                # Resposta Pagamento
                if perf == "inform" and "paid" in data:
                    await self.agent._reply_to_user(self, to_user, {
                        "ok": data["paid"],
                        "msg": "Pagamento efetuado com sucesso." if data["paid"] else "Pagamento recusado.",
                        "saldo_novo": data.get("saldo_novo")
                    })
                    # Limpar slots para nova operação
                    ctx["slots"] = {}
                    ctx["intencao"] = None
                    return

            if to_user := data.get("to_user"):
                await self.agent._reply_to_user(self, to_user, data)