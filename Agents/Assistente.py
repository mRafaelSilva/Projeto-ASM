import asyncio
import json
from typing import Any, Dict, Optional

import jsonpickle
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

import utils.utilsAssistente as utilsAssistente


def _safe_decode_body(body: Optional[str]) -> dict:
    # 1) jsonpickle (Horários / Financeiro)
    try:
        decoded = jsonpickle.decode(body)
        if isinstance(decoded, dict):
            return decoded
    except Exception:
        pass

    # 2) JSON normal (UserAgent <-> Assistente)
    try:
        decoded = json.loads(body) if body else {}
        return decoded if isinstance(decoded, dict) else {}
    except Exception:
        return {}


class AssistenteAgent(Agent):
    def __init__(self, jid, password):
        super().__init__(jid, password)
        self._contexts: Dict[str, Dict[str, Any]] = {}

    async def setup(self):
        self.add_behaviour(ReceiveUserRequestBehaviour())
        self.add_behaviour(ReceiveInformBehaviour())

    def _get_ctx(self, user_jid: str) -> Dict[str, Any]:
        return self._contexts.setdefault(
            user_jid,
            {
                "user_jid": user_jid,
                "intencao": None,
                "slots": {},
                "pendente": None,      # para retomar após respostas de outros agentes
                "awaiting": None,      # slot que estamos a pedir ao user
            },
        )

    async def _ask_for_slot(self, behaviour: CyclicBehaviour, user_jid: str, slot_name: str):
        msg = Message(to=user_jid)
        msg.set_metadata("performative", "request")
        msg.body = json.dumps(
            {
                "type": "ask",
                "slot": slot_name,
                "prompt": f"Por favor, indique: {slot_name}",
            },
            ensure_ascii=False,
        )
        await behaviour.send(msg)

    async def _forward_to_horarios(self, behaviour: CyclicBehaviour, user_jid: str, curso: str, disciplinas: list):
        msg = Message(to="horarios@localhost")
        msg.set_metadata("performative", "request")
        msg.body = jsonpickle.encode(
            {
                "acao": "check_schedule",
                "curso": curso,
                "disciplinas": disciplinas,
                "to_user": user_jid,
            }
        )
        await behaviour.send(msg)

    async def _query_debt_to_financeiro(self, behaviour: CyclicBehaviour, user_jid: str, estudante_id: Any):
        """
        O FinanceiroAgent do vosso projeto responde a:
          performative = "query-if"
          body: {"acao":"has_debt","estudante_id":...}
        """
        msg = Message(to="financeiro@localhost")
        msg.set_metadata("performative", "query-if")
        msg.body = jsonpickle.encode(
            {
                "acao": "has_debt",
                "estudante_id": estudante_id,
                "to_user": user_jid,
            }
        )
        await behaviour.send(msg)

    async def _reply_to_user(self, behaviour: CyclicBehaviour, user_jid: str, payload: dict):
        msg = Message(to=user_jid)
        msg.set_metadata("performative", "inform")
        msg.body = json.dumps(payload, ensure_ascii=False)
        await behaviour.send(msg)


class ReceiveUserRequestBehaviour(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=1)
        if not msg:
            return

        if msg.get_metadata("performative") != "request":
            return

        user_jid = str(msg.sender).split("/")[0]
        ctx = self.agent._get_ctx(user_jid)

        try:
            data = json.loads(msg.body) if msg.body else {}
        except Exception:
            data = {}

        texto = (data.get("texto") or "").strip()

        intencao = utilsAssistente.get_intencao(texto)
        slots_extraidos = utilsAssistente.extrair_slots(intencao, texto)

        ctx["intencao"] = intencao
        ctx["slots"].update(slots_extraidos)

        # normalizações
        if "curso" in ctx["slots"]:
            ctx["slots"]["curso"] = utilsAssistente.normalizar_curso(ctx["slots"]["curso"])
        if "disciplina" in ctx["slots"]:
            ctx["slots"]["disciplina"] = utilsAssistente.normalizar_disciplinas(ctx["slots"]["disciplina"])

        # ------------------- Fluxos -------------------

        if intencao == "inscricao":
            # precisa: numero_aluno, curso, disciplina
            required = ["numero_aluno", "curso", "disciplina"]
            missing = [k for k in required if not ctx["slots"].get(k)]
            if missing:
                ctx["awaiting"] = missing[0]
                await self.agent._ask_for_slot(self, user_jid, missing[0])
                return

            # antes de avançar: verifica dívida
            ctx["pendente"] = "inscricao_depois_divida"
            await self.agent._query_debt_to_financeiro(self, user_jid, ctx["slots"]["numero_aluno"])
            return

        if intencao == "horarios":
            required = ["curso", "disciplina"]
            missing = [k for k in required if not ctx["slots"].get(k)]
            if missing:
                ctx["awaiting"] = missing[0]
                await self.agent._ask_for_slot(self, user_jid, missing[0])
                return

            curso = utilsAssistente.normalizar_curso(ctx["slots"]["curso"])
            disciplinas = utilsAssistente.normalizar_disciplinas(ctx["slots"]["disciplina"])
            ctx["slots"]["curso"] = curso
            ctx["slots"]["disciplina"] = disciplinas

            await self.agent._forward_to_horarios(self, user_jid, curso, disciplinas)
            return

        if intencao == "pagamentos":
            required = ["numero_aluno"]
            missing = [k for k in required if not ctx["slots"].get(k)]
            if missing:
                ctx["awaiting"] = missing[0]
                await self.agent._ask_for_slot(self, user_jid, missing[0])
                return

            ctx["pendente"] = "pagamentos_depois_divida"
            await self.agent._query_debt_to_financeiro(self, user_jid, ctx["slots"]["numero_aluno"])
            return

        # fallback
        await self.agent._reply_to_user(
            self,
            user_jid,
            {"ok": False, "erro": "intencao_desconhecida", "texto": texto, "intencao": intencao},
        )


class ReceiveInformBehaviour(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=1)
        if not msg:
            return

        perf = msg.get_metadata("performative")
        sender = str(msg.sender).split("/")[0]

        # ------------------- Resposta do user (slot filling) -------------------
        if sender.startswith("user@") and perf == "inform":
            user_jid = sender
            ctx = self.agent._get_ctx(user_jid)

            try:
                data = json.loads(msg.body) if msg.body else {}
            except Exception:
                data = {}

            if data.get("type") != "answer":
                return

            slot = ctx.get("awaiting")
            valor = data.get("value")
            if not slot:
                return

            if slot == "curso":
                valor = utilsAssistente.normalizar_curso(valor)
            if slot == "disciplina":
                valor = utilsAssistente.normalizar_disciplinas(valor)

            ctx["slots"][slot] = valor
            ctx["awaiting"] = None

            intencao = ctx.get("intencao")

            if intencao == "inscricao":
                required = ["numero_aluno", "curso", "disciplina"]
                missing = [k for k in required if not ctx["slots"].get(k)]
                if missing:
                    ctx["awaiting"] = missing[0]
                    await self.agent._ask_for_slot(self, user_jid, missing[0])
                    return

                ctx["pendente"] = "inscricao_depois_divida"
                await self.agent._query_debt_to_financeiro(self, user_jid, ctx["slots"]["numero_aluno"])
                return

            if intencao == "horarios":
                required = ["curso", "disciplina"]
                missing = [k for k in required if not ctx["slots"].get(k)]
                if missing:
                    ctx["awaiting"] = missing[0]
                    await self.agent._ask_for_slot(self, user_jid, missing[0])
                    return

                curso = utilsAssistente.normalizar_curso(ctx["slots"]["curso"])
                disciplinas = utilsAssistente.normalizar_disciplinas(ctx["slots"]["disciplina"])
                ctx["slots"]["curso"] = curso
                ctx["slots"]["disciplina"] = disciplinas

                await self.agent._forward_to_horarios(self, user_jid, curso, disciplinas)
                return

            if intencao == "pagamentos":
                required = ["numero_aluno"]
                missing = [k for k in required if not ctx["slots"].get(k)]
                if missing:
                    ctx["awaiting"] = missing[0]
                    await self.agent._ask_for_slot(self, user_jid, missing[0])
                    return

                ctx["pendente"] = "pagamentos_depois_divida"
                await self.agent._query_debt_to_financeiro(self, user_jid, ctx["slots"]["numero_aluno"])
                return

            return

        # ------------------- Respostas de outros agentes -------------------
        if perf in ("inform", "propose", "failure", "refuse", "not-understood"):
            data = _safe_decode_body(msg.body)

            to_user = data.get("to_user")
            if not to_user:
                if self.agent._contexts:
                    to_user = next(iter(self.agent._contexts.keys()))
                else:
                    return

            ctx = self.agent._get_ctx(to_user)

            # Financeiro: retomar fluxo pendente
            if sender.startswith("financeiro@"):
                pendente = ctx.get("pendente")
                debt = data.get("debt")  # "yes" / "no" / "unknown"

                if pendente == "inscricao_depois_divida":
                    ctx["pendente"] = None

                    if debt == "yes":
                        await self.agent._reply_to_user(
                            self,
                            to_user,
                            {
                                "ok": False,
                                "erro": "bloqueado_por_divida",
                                "valor_divida": data.get("valor"),
                                "saldo": data.get("saldo"),
                                "isento_taxas": data.get("isento_taxas"),
                            },
                        )
                        return

                    if debt == "unknown":
                        await self.agent._reply_to_user(
                            self,
                            to_user,
                            {"ok": False, "erro": "financeiro_desconhecido", "detalhes": data},
                        )
                        return

                    # debt == "no" => prosseguir com Horários (por agora)
                    curso = utilsAssistente.normalizar_curso(ctx["slots"].get("curso"))
                    disciplinas = utilsAssistente.normalizar_disciplinas(ctx["slots"].get("disciplina"))
                    ctx["slots"]["curso"] = curso
                    ctx["slots"]["disciplina"] = disciplinas
                    await self.agent._forward_to_horarios(self, to_user, curso, disciplinas)
                    return

                if pendente == "pagamentos_depois_divida":
                    ctx["pendente"] = None
                    await self.agent._reply_to_user(self, to_user, {"ok": True, "financeiro": data})
                    return

            # default: encaminhar ao utilizador
            await self.agent._reply_to_user(self, to_user, data)
            return
