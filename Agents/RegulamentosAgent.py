import json
import jsonpickle
import os
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Database", "regulamentos.json")
STUDENTS_PATH = os.path.join(os.path.dirname(__file__), "..", "Database", "estudantes.json")

"""
Agente de Regulamentos

Responsabilidades:
- Carrega a definição dos regulamentos a partir de Database/regulamentos_status.json.
- Gere o estatuto dos estudantes usando Database/estudantes.json como fonte única de verdade.
- Permite:
  • listar regulamentos disponíveis  
  • consultar detalhes de um regulamento  
  • atribuir um estatuto/regulamento a um estudante  
  • remover um estatuto/regulamento  
  • verificar se um estudante está inscrito num regulamento
- Garante a regra de negócio:
  • cada estudante só pode ter UM estatuto ativo de cada vez.
- Valida pedidos e assegura consistência (existência do regulamento, aluno válido, transições permitidas).

Contrato de comunicação  
(Formato preferencial: jsonpickle; fallback: JSON)

REQUEST:
{
  "action": "listar_regulamentos"
            | "ver_regulamento"
            | "inscrever_regulamento"
            | "remover_inscricao_regulamento"
            | "verificar_inscricao_regulamento",

  "regulamento": "trabalhador-estudante" | "estatuto-especial" | ...,   // obrigatório quando aplicável
  "numero_aluno": "12345",                                              // obrigatório em inscrição, remoção e verificação

  "to_user": "user@localhost"                                           // opcional (encaminhamento da resposta)
}
"""

def load_regulamentos():
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_estudantes():
    with open(STUDENTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_estudantes(data):
    with open(STUDENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_student(estudantes, numero):
    for e in estudantes:
        if str(e.get("id")) == str(numero):
            return e
    return None

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

        if action == "inscrever_regulamento":
            await self._handle_inscrever_regulamento(msg, data)
            return

        if action == "remover_inscricao_regulamento":
            await self._handle_remover_inscricao_regulamento(msg, data)
            return

        if action == "verificar_inscricao_regulamento":
            await self._handle_verificar_inscricao(msg, data)
            return

        # ---------------- UNKNOWN ACTION ----------------
        reply = msg.make_reply()
        reply.set_metadata("performative", "failure")
        reply.body = jsonpickle.encode({
            "error": "unknown_action",
            "expected": [
                "listar_regulamentos",
                "ver_regulamento",
                "inscrever_regulamento",
                "remover_inscricao_regulamento",
                "verificar_inscricao_regulamento"
            ],
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
            reply.body = jsonpickle.encode({
                "error": "missing_regulamento",
                "to_user": to_user
            })
            await self.send(reply)
            return

        nome_normalizado = nome.lower().strip().replace(" ", "-").replace("_", "-")

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

        if nome_normalizado not in regras:
            reply = msg.make_reply()
            reply.set_metadata("performative", "refuse")
            reply.body = jsonpickle.encode({
                "ok": False,
                "action": "ver_regulamento",
                "erro": "regulamento_inexistente",
                "regulamentos_disponiveis": list(regras.keys()),
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
            "regulamento": nome_normalizado,
            "dados": regras[nome_normalizado],
            "to_user": to_user
        })
        await self.send(reply)

    async def _handle_inscrever_regulamento(self, msg, data):
        nome = data.get("regulamento")
        aluno = data.get("numero_aluno")
        to_user = data.get("to_user")

        if not nome or not aluno:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({
                "error": "missing_fields",
                "required": ["regulamento", "numero_aluno"],
                "to_user": to_user
            })
            await self.send(reply)
            return

        reg = nome.lower().strip().replace(" ", "-").replace("_", "-")

        try:
            regras = load_regulamentos()
            estudantes = load_estudantes()
        except Exception:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({
                "error": "erro_carregar_dados",
                "to_user": to_user
            })
            await self.send(reply)
            return

        if reg not in regras:
            reply = msg.make_reply()
            reply.set_metadata("performative", "refuse")
            reply.body = jsonpickle.encode({
                "erro": "regulamento_inexistente",
                "regulamentos_disponiveis": list(regras.keys()),
                "regulamento": reg,
                "to_user": to_user
            })
            await self.send(reply)
            return

        est = find_student(estudantes, aluno)
        if not est:
            reply = msg.make_reply()
            reply.set_metadata("performative", "refuse")
            reply.body = jsonpickle.encode({
                "erro": "aluno_inexistente",
                "numero_aluno": aluno,
                "to_user": to_user
            })
            await self.send(reply)
            return

        estatuto_atual = est.get("estatuto", "Regular")
        if estatuto_atual.lower() != "regular":
            reply = msg.make_reply()
            reply.set_metadata("performative", "refuse")
            reply.body = jsonpickle.encode({
                "erro": "ja_tem_estatuto",
                "estatuto_atual": estatuto_atual,
                "to_user": to_user
            })
            await self.send(reply)
            return

        # atribuir novo estatuto
        est["estatuto"] = reg.replace("-", " ").title()
        save_estudantes(estudantes)

        reply = msg.make_reply()
        reply.set_metadata("performative", "inform")
        reply.body = jsonpickle.encode({
            "ok": True,
            "action": "inscrever_regulamento",
            "status": "inscrito",
            "regulamento": reg,
            "numero_aluno": aluno,
            "to_user": to_user
        })
        await self.send(reply)

    async def _handle_remover_inscricao_regulamento(self, msg, data):
        aluno = data.get("numero_aluno")
        to_user = data.get("to_user")

        if not aluno:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({
                "error": "missing_fields",
                "required": ["numero_aluno"],
                "to_user": to_user
            })
            await self.send(reply)
            return

        try:
            estudantes = load_estudantes()
        except Exception:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({
                "error": "erro_carregar_estudantes",
                "to_user": to_user
            })
            await self.send(reply)
            return

        est = find_student(estudantes, aluno)
        if not est:
            reply = msg.make_reply()
            reply.set_metadata("performative", "refuse")
            reply.body = jsonpickle.encode({
                "erro": "aluno_inexistente",
                "numero_aluno": aluno,
                "to_user": to_user
            })
            await self.send(reply)
            return

        if est.get("estatuto", "Regular").lower() == "regular":
            reply = msg.make_reply()
            reply.set_metadata("performative", "refuse")
            reply.body = jsonpickle.encode({
                "erro": "nao_tem_estatuto_especial",
                "to_user": to_user
            })
            await self.send(reply)
            return

        est["estatuto"] = "Regular"
        save_estudantes(estudantes)

        reply = msg.make_reply()
        reply.set_metadata("performative", "inform")
        reply.body = jsonpickle.encode({
            "ok": True,
            "action": "remover_inscricao_regulamento",
            "status": "removido",
            "numero_aluno": aluno,
            "to_user": to_user
        })
        await self.send(reply)

    async def _handle_verificar_inscricao(self, msg, data):
        nome = data.get("regulamento")
        aluno = data.get("numero_aluno")
        to_user = data.get("to_user")

        if not nome or not aluno:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({
                "error": "missing_fields",
                "required": ["regulamento", "numero_aluno"],
                "to_user": to_user
            })
            await self.send(reply)
            return

        reg = nome.lower().strip().replace(" ", "-").replace("_", "-")

        try:
            estudantes = load_estudantes()
        except Exception:
            reply = msg.make_reply()
            reply.set_metadata("performative", "failure")
            reply.body = jsonpickle.encode({
                "error": "erro_carregar_estudantes",
                "to_user": to_user
            })
            await self.send(reply)
            return

        est = find_student(estudantes, aluno)
        if not est:
            reply = msg.make_reply()
            reply.set_metadata("performative", "refuse")
            reply.body = jsonpickle.encode({
                "erro": "aluno_inexistente",
                "numero_aluno": aluno,
                "to_user": to_user
            })
            await self.send(reply)
            return

        estatuto_norm = est.get("estatuto", "").lower().replace(" ", "-")
        inscrito = estatuto_norm == reg

        reply = msg.make_reply()
        reply.set_metadata("performative", "inform")
        reply.body = jsonpickle.encode({
            "ok": True,
            "action": "verificar_inscricao_regulamento",
            "regulamento": reg,
            "numero_aluno": aluno,
            "inscrito": inscrito,
            "estatuto_atual": est.get("estatuto"),
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

        self.add_behaviour(RegulamentosBehaviour())