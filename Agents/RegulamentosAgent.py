import json
import jsonpickle
import os
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Database", "regulamentos.json")

"""
Agente Regulamentos
  - Carrega Database/regulamentos_status.json
  - Gere inscrições em regulamentos (Database/inscricoes_regulamentos.json)
  - Valida pedidos de consulta, inscrição e verificação de estado
  - Garante consistência das regras (documentos obrigatórios, limites, etc.)

Contrato (preferência jsonpickle; fallback JSON):

  REQUEST:
    {
      "action": "listar_regulamentos"
                | "ver_regulamento"
                | #"inscrever_regulamento"
                | #"verificar_inscricao_regulamento",

      "regulamento": "trabalhador-estudante" | "estatuto-especial" | ...,   # opcional (exceto quando exigido)
      "numero_aluno": "12345",                                       # obrigatório em inscrição/verificação
      "documentos": ["comprovativo_trabalho", ...],                  # opcional (usado na inscrição)

      "to_user": "user@localhost"                                    # opcional (para encaminhamento no Assistente)
    }

  INFORM / REFUSE / FAILURE:
    {
      "ok": bool,
      "action": "...",

      "regulamento": "...",                                          # quando aplicável
      "numero_aluno": "...",                                         # quando aplicável

      "regulamentos": ["trabalhador-estudante", ...],                # no listar_regulamentos
      "dados": { ... },                                              # no ver_regulamento

      "inscrito": bool,                                              # no verificar_inscricao_regulamento
      "mensagem": "...",                                             # mensagens de sucesso

      "erro": "...",                                                 # motivo da recusa/falha
      "to_user": "..."                                               # se veio no request
    }
"""


def load_regulamentos():
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

class RegulamentosBehaviour(CyclicBehaviour):

    async def run(self):
        msg = await self.receive(timeout=10)
   
        if not msg:
            return

        data = self.agent._safe_decode_body(msg)
        action = data.get("action")

        # ---------------- DISPATCHER ----------------
        if action == "listar_regulamentos":
            await self._handle_listar_regulamentos(msg)
            return

        if action == "ver_regulamento":
            await self._handle_ver_regulamento(msg, data)
            return

        # ação desconhecida
        reply = msg.make_reply()
        reply.set_metadata("performative", "failure")
        reply.body = jsonpickle.encode({
            "error": "unknown_action",
            "expected": ["listar_regulamentos", "ver_regulamento"],
            "got": action
        })
        await self.send(reply)

    # -------------------------------------------------
    # HANDLERS
    # -------------------------------------------------

    async def _handle_listar_regulamentos(self, msg):
        data = self.agent._safe_decode_body(msg)
        to_user = data.get("to_user")   

        try:
            regras = load_regulamentos()
        except Exception:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({
                "error": "erro_carregar_regulamentos",
                "to_user": to_user          
            })
            await self.send(reply)
            return

        reply = msg.make_reply()
        reply.set_metadata("performative", "inform")
        reply.body = jsonpickle.encode({
            "ok": True,
            "action": "listar_regulamentos",
            "regulamentos": list(regras.keys()),
            "to_user": to_user              
        })
        await self.send(reply)


    async def _handle_ver_regulamento(self, msg, data):
        nome = data.get("regulamento")
        to_user = data.get("to_user")

        if not nome:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({"error": "missing_regulamento", "to_user": to_user})
            await self.send(reply)
            return

        try:
            regras = load_regulamentos()
        except Exception:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({"error": "erro_carregar_regulamentos", "to_user": to_user})
            await self.send(reply)
            return

        if nome not in regras:
            reply = msg.make_reply()
            reply.set_metadata("performative", "refuse")
            reply.body = jsonpickle.encode({
                "ok": False,
                "action": "ver_regulamento",
                "erro": "regulamento_inexistente",
                "regulamento": nome,
                "to_user": to_user
            })
            await self.send(reply)
            return

        reply = msg.make_reply()
        reply.set_metadata("performative", "inform")
        reply.body = jsonpickle.encode({
            "ok": True,
            "action": "ver_regulamento",
            "regulamento": nome,
            "dados": regras[nome],
            "to_user": to_user
        })
        await self.send(reply)


class RegulamentosAgent(Agent):

    def _safe_decode_body(self, msg):
        try:
            decoded = jsonpickle.decode(msg.body)
            return decoded if isinstance(decoded, dict) else {"value": decoded}
        except Exception:
            return {}

    async def setup(self):
        print(f"[Regulamentos] {str(self.jid)} ativo.")

        template = Template()
        template.set_metadata("performative", "request")

        self.add_behaviour(RegulamentosBehaviour(), template)