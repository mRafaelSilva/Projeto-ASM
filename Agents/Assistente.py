import json
import os
import jsonpickle
from typing import Any, Dict, Set
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import utils.utilsLLM as llm
import utils.utilsAssistente as utils

# Caminho para a base de dados de estudantes
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ESTUDANTES_PATH = os.path.join(_BASE_DIR, "Database", "estudantes.json")

def verificar_estudante(numero_aluno: str) -> dict | None:
    """Verifica se o estudante existe na BD. Retorna dados ou None."""
    try:
        with open(_ESTUDANTES_PATH, "r", encoding="utf-8") as f:
            estudantes = json.load(f)
        for est in estudantes:
            if str(est.get("id")) == str(numero_aluno):
                return est
        return None
    except Exception:
        return None

class AssistenteAgent(Agent):
    INTENTS_NO_FINANCIAL_CHECK: Set[str] = {"horarios", "ajuda", "saudacao", "desconhecida"}
    INTENTS_NO_REGULAMENTOS_CHECK: Set[str] = {"listar_regulamentos", "ver_regulamento", "inscrever_regulamento", "verificar_inscricao_regulamento"}

    def __init__(self, jid, password):
        super().__init__(jid, password)
        self._contexts: Dict[str, Dict[str, Any]] = {}

    async def setup(self):
        print(f"[Assistente] {str(self.jid)} ativo (Full Pickle Mode).")
        self.add_behaviour(self.ReceiveUserRequestBehaviour())
        self.add_behaviour(self.ReceiveInformBehaviour())

    def _get_ctx(self, user_jid: str) -> Dict[str, Any]:
        return self._contexts.setdefault(user_jid, {
            "user_jid": user_jid, "intencao": None, "slots": {}, "pendente": None, "awaiting": None, "sessao_aluno": None
        })

    # --- Helpers de Envio ---
    async def _reply(self, behaviour, user_jid, payload):
        msg = Message(to=user_jid)
        msg.set_metadata("performative", "inform")
        msg.body = jsonpickle.encode(payload)
        await behaviour.send(msg)

    async def _ask_slot(self, behaviour, user_jid, slot):
        msg = Message(to=user_jid)
        msg.set_metadata("performative", "request")
        msg.body = jsonpickle.encode({"type": "ask", "slot": slot, "prompt": f"Por favor, indique: {slot}"})
        await behaviour.send(msg)

    # --- Lógica Central ---
    async def processar_intencao(self, behaviour, user_jid, intencao, ctx):
        slots = ctx["slots"]

    async def _forward_request_to_regulamentos(self, behaviour: CyclicBehaviour, payload: dict):
        msg = Message(to="regulamentos@localhost")
        msg.set_metadata("performative", "request")
        msg.body = jsonpickle.encode(payload)
        await behaviour.send(msg)

    async def processar_intencao_negocio(self, behaviour: CyclicBehaviour, user_jid: str, intencao: str, ctx: dict):
        if intencao == "saudacao":
            await self._reply(behaviour, user_jid, {"msg": "Olá! Posso ajudar com inscrições, horários ou pagamentos."})
            return

        if intencao == "desconhecida":
            await self._reply(behaviour, user_jid, {"msg": "Não percebi. Tente 'ver saldo', 'inscrever SO1' ou 'horario LEI'."})
            return
        
        if intencao == "ajuda":
            await self._reply(behaviour, user_jid, {"msg": utils.HELP_MESSAGE})
            return

        if intencao == "inscricao":
            if not slots.get("curso"):
                ctx["awaiting"] = "curso"
                await self._ask_slot(behaviour, user_jid, "curso")
                return
            if not slots.get("disciplina"):
                ctx["awaiting"] = "disciplina"
                await self._reply(behaviour, user_jid, {"type": "ask", "prompt": "Qual a disciplina? (Indique uma válida, ex: SO1)"})
                return
            
            await self._reply(behaviour, user_jid, {"ok": True, "msg": f"Inscrição registada em {slots['disciplina']} ({slots['curso']})."})
            ctx["intencao"] = None 
            return

        if intencao == "horarios":
            if not slots.get("curso"):
                ctx["awaiting"] = "curso"
                await self._ask_slot(behaviour, user_jid, "curso")
                return
            if not slots.get("disciplina"):
                ctx["awaiting"] = "disciplina"
                await self._ask_slot(behaviour, user_jid, "disciplina")
                return

            msg = Message(to="horarios@localhost")
            msg.set_metadata("performative", "request")
            msg.body = jsonpickle.encode({
                "acao": "check_schedule", 
                "curso": slots["curso"], 
                "disciplinas": [slots["disciplina"]], 
                "to_user": user_jid
            })
            await behaviour.send(msg)
            return

        await self._reply(behaviour, user_jid, {"msg": f"Comando '{intencao}' em construção."})


    async def processar_intencao_regulamentos(self,
                                          behaviour: CyclicBehaviour,
                                          user_jid: str,
                                          intencao: str,
                                          ctx: dict):

        slots = ctx.get("slots", {})

        if intencao == "listar_regulamentos":
            payload = { "action": "listar_regulamentos", "to_user": user_jid }
            await self._forward_request_to_regulamentos(behaviour, payload)
            return

        if intencao == "ver_regulamento":
            required = ["regulamento"]
            missing = [k for k in required if not slots.get(k)]

            if missing:
                ctx["awaiting"] = missing[0]
                await self._ask_for_slot(behaviour, user_jid, missing[0])
                return

            payload = {  "action": "ver_regulamento", "regulamento": slots.get("regulamento"), "to_user": user_jid }
            await self._forward_request_to_regulamentos(behaviour, payload)
            return

        if intencao == "inscrever_regulamento":
            required = ["regulamento", "numero_aluno"]
            missing = [k for k in required if not slots.get(k)]

            if missing:
                ctx["awaiting"] = missing[0]
                await self._ask_for_slot(behaviour, user_jid, missing[0])
                return

            payload = {"action": "inscrever_regulamento", "regulamento": slots.get("regulamento"), "numero_aluno": slots.get("numero_aluno"), "documentos": slots.get("documentos", []), "to_user": user_jid }
            await self._forward_request_to_regulamentos(behaviour, payload)
            return

        if intencao == "verificar_inscricao_regulamento":
            required = ["regulamento", "numero_aluno"]
            missing = [k for k in required if not slots.get(k)]

            if missing:
                ctx["awaiting"] = missing[0]
                await self._ask_for_slot(behaviour, user_jid, missing[0])
                return

            payload = { "action": "verificar_inscricao_regulamento", "regulamento": slots.get("regulamento"), "numero_aluno": slots.get("numero_aluno"), "to_user": user_jid }
            await self._forward_request_to_regulamentos(behaviour, payload)
            return

        await self._reply_to_user(behaviour, user_jid, {"ok": False, "erro": "intencao_nao_suportada", "intencao": intencao})


    # --- Behaviours ---
    class ReceiveUserRequestBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg or msg.get_metadata("performative") != "request": return

            try: data = jsonpickle.decode(msg.body)
            except: data = {}
            
            user_jid = str(msg.sender).split("/")[0]
            ctx = self.agent._get_ctx(user_jid)
            
            # Tratar login
            if data.get("type") == "login":
                numero = data.get("numero_aluno")
                estudante = verificar_estudante(numero)
                
                if estudante:
                    ctx["sessao_aluno"] = numero
                    ctx["sessao_nome"] = estudante.get("nome", "")
                    await self.agent._reply(self, user_jid, {
                        "type": "login_response",
                        "success": True,
                        "numero_aluno": numero,
                        "nome": estudante.get("nome", ""),
                        "curso": estudante.get("curso_id", ""),
                        "estatuto": estudante.get("estatuto", "")
                    })
                else:
                    await self.agent._reply(self, user_jid, {
                        "type": "login_response",
                        "success": False,
                        "msg": f"Estudante {numero} não encontrado na base de dados."
                    })
                return
            
            # Tratar logout - limpar todo o contexto
            if data.get("type") == "logout":
                ctx["sessao_aluno"] = None
                ctx["slots"] = {}
                ctx["intencao"] = None
                ctx["pendente"] = None
                ctx["awaiting"] = None
                return
            
            texto = data.get("texto", "")
            if not texto: return
            
            # Atualizar sessão do aluno se foi enviada
            sessao_aluno = data.get("sessao_aluno")
            if sessao_aluno:
                ctx["sessao_aluno"] = sessao_aluno
            
            # Limpar slots do pedido anterior (manter apenas numero_aluno se há sessão)
            numero_sessao = ctx.get("sessao_aluno")
            ctx["slots"] = {}
            if numero_sessao:
                ctx["slots"]["numero_aluno"] = numero_sessao

            # LLM
            resultado = llm.interpretar_comando(texto)
            intencao = resultado["intencao"]
            
            # Atualiza o contexto
            ctx["intencao"] = intencao
            ctx["slots"].update(resultado["slots"])

            # Ações públicas (não precisam de login)
            if intencao in self.agent.INTENTS_NO_LOGIN:
                await self.agent.processar_intencao(self, user_jid, intencao, ctx)
                return
        

            
            # Ações privadas - verificar se tem sessão ativa
            if not ctx.get("sessao_aluno"):
                await self.agent._reply(self, user_jid, {
                    "msg": "Esta ação requer login! Use 'login <numero_aluno>' primeiro."
                })
                return

            # Lógica Financeira
            if intencao in ["fazer_pagamento", "ver_saldo"]:
                if not ctx["slots"].get("numero_aluno"):
                    ctx["awaiting"] = "numero_aluno"
                    ctx["pendente"] = intencao
                    await self.agent._ask_slot(self, user_jid, "numero_aluno")
                    return
                
                ctx["pendente"] = intencao
                f_msg = Message(to="financeiro@localhost")
                f_msg.set_metadata("performative", "query-if")
                f_msg.body = jsonpickle.encode({"acao": "has_debt", "estudante_id": ctx["slots"]["numero_aluno"], "to_user": user_jid})
                await self.send(f_msg)
                return

            if intencao not in self.agent.INTENTS_NO_FINANCIAL_CHECK:
                 if not ctx["slots"].get("numero_aluno"):
                    ctx["awaiting"] = "numero_aluno"
                    ctx["pendente"] = intencao
                    await self.agent._ask_slot(self, user_jid, "numero_aluno")
                    return

            if intencao in self.agent.INTENTS_NO_REGULAMENTOS_CHECK:
                await self.agent.processar_intencao_regulamentos(self, user_jid, intencao, ctx)
                return
                 
                 # Valida dívida antes
                 ctx["pendente"] = intencao
                 f_msg = Message(to="financeiro@localhost")
                 f_msg.set_metadata("performative", "query-if")
                 f_msg.body = jsonpickle.encode({"acao": "has_debt", "estudante_id": ctx["slots"]["numero_aluno"], "to_user": user_jid})
                 await self.send(f_msg)
                 return

            await self.agent.processar_intencao(self, user_jid, intencao, ctx)


    class ReceiveInformBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg: return

            try: data = jsonpickle.decode(msg.body)
            except: return

            sender = str(msg.sender).split("/")[0]

            # --- Resposta do USER ---
            if sender.startswith("user@"):
                if data.get("type") != "answer": return
                
                user_jid = sender
                ctx = self.agent._get_ctx(user_jid)
                slot_faltava = ctx.get("awaiting")
                valor_recebido = data.get("value")

                if slot_faltava:
                    # Preenche o slot
                    ctx["slots"][slot_faltava] = valor_recebido
                    ctx["awaiting"] = None
                    
                    pendente = ctx.get("pendente")
                    intencao_atual = ctx.get("intencao")

                    if intencao_atual == "fazer_pagamento":
                        if not ctx["slots"].get("valor"):
                             ctx["awaiting"] = "valor"
                             await self.agent._ask_slot(self, user_jid, "valor")
                             return
                        val = float(ctx["slots"].get("valor", 0))
                        req = Message(to="financeiro@localhost")
                        req.set_metadata("performative", "request")
                        req.body = jsonpickle.encode({"acao": "pay_debt", "estudante_id": ctx["slots"]["numero_aluno"], "valor": val, "to_user": user_jid})
                        await self.send(req)
                        return

                    if pendente and slot_faltava == "numero_aluno":
                        f_msg = Message(to="financeiro@localhost")
                        f_msg.set_metadata("performative", "query-if")
                        f_msg.body = jsonpickle.encode({"acao": "has_debt", "estudante_id": ctx["slots"]["numero_aluno"], "to_user": user_jid})
                        await self.send(f_msg)
                        return
                    
                    target = pendente if pendente else intencao_atual
                    await self.agent.processar_intencao(self, user_jid, target, ctx)
                return

            # --- Resposta do FINANCEIRO ---
            if sender.startswith("financeiro@"):
                to_user = data.get("to_user")
                if not to_user: return
                ctx = self.agent._get_ctx(to_user)
                
                if "debt" in data:
                    # Se era só para ver saldo
                    if ctx.get("pendente") == "ver_saldo":
                        saldo_msg = f"Saldo: {data.get('saldo')}€. Dívida: {data.get('valor')}€."
                        await self.agent._reply(self, to_user, {"msg": saldo_msg})
                        ctx["pendente"] = None
                        return

                    # Se tem dívida e bloqueia
                    if data["debt"] == "yes":
                        await self.agent._reply(self, to_user, {"ok": False, "msg": f"Operação bloqueada! Regularize a dívida de {data.get('valor')}€."})
                        ctx["pendente"] = None
                    else:
                        # Sem dívida, retoma operação
                        op = ctx.get("pendente")
                        if op:
                            await self.agent.processar_intencao(self, to_user, op, ctx)
                            ctx["pendente"] = None
                    return
                
                if "paid" in data:
                    res = "Sucesso" if data["paid"] else "Recusado"
                    await self.agent._reply(self, to_user, {"msg": f"Pagamento: {res}. Novo Saldo: {data.get('saldo_novo')}€"})
                    ctx["slots"] = {}
                    ctx["intencao"] = None
                    return

            if sender.startswith("regulamentos@"):
                to_user = data.get("to_user")
                if not to_user:
                    return

                action = data.get("action")

                # LISTAR REGULAMENTOS
                if action == "listar_regulamentos":
                    regs = data.get("regulamentos", [])

                    if not regs:
                        texto = "Não existem regulamentos disponíveis."
                    else:
                        texto = "Regulamentos disponíveis:\n"
                        texto += "\n".join(f"- {r}" for r in regs)

                    await self.agent._reply_to_user(self, to_user, {"msg": texto})
                    return

                # VER REGULAMENTO
                if action == "ver_regulamento":
                    nome = data.get("regulamento")
                    dados = data.get("dados", {})

                    if not dados:
                        texto = f"O regulamento '{nome}' não foi encontrado."
                    else:
                        texto = (
                            f"Regulamento: {nome}\n"
                            f"Descrição: {dados.get('descricao')}\n"
                            f"ECTS máximos/ano: {dados.get('ects_max_ano')}\n"
                        )

                        regras = dados.get("regras", [])
                        if regras:
                            texto += "Regras:\n" + "\n".join(f"- {r}" for r in regras)

                    await self.agent._reply_to_user(self, to_user, {"msg": texto})
                    return

            target_user = data.get("to_user")
            if target_user:
                await self.agent._reply(self, target_user, data)
                return
