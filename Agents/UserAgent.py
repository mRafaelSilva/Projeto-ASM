import asyncio
from aioconsole import ainput
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import jsonpickle

class UserAgent(Agent):
    async def setup(self):
        print(f"UserAgent {str(self.jid)} iniciado.")
        self.msg_pergunta_pendente = None
        self.lock_input = asyncio.Event()
        self.lock_input.set()

        self.add_behaviour(self.InputBehaviour())
        self.add_behaviour(self.ReceiveMessageBehaviour())

    class InputBehaviour(CyclicBehaviour):
        async def on_start(self):
            await asyncio.sleep(0.5)
            print("\n" + "="*61)
            print("CHAT INICIADO")
            print("Digite o seu pedido de inscrição, pagamento, horários, etc...")
            print("="*61 + "\n")

        async def run(self):
            await self.agent.lock_input.wait()

            try:
                prompt = ">> " if self.agent.msg_pergunta_pendente else "> "
                texto = (await ainput(prompt)).strip()
            except: return

            if not texto: return

            self.agent.lock_input.clear()

            # Responder a uma pergunta do Assistente
            if self.agent.msg_pergunta_pendente:
                msg_origem = self.agent.msg_pergunta_pendente
                reply = msg_origem.make_reply()
                reply.set_metadata("performative", "inform")
                
                reply.body = jsonpickle.encode({"type": "answer", "value": texto})
                await self.send(reply)
                self.agent.msg_pergunta_pendente = None
                return

            # Novo Pedido
            msg = Message(to="assistente@localhost")
            msg.set_metadata("performative", "request")
            msg.body = jsonpickle.encode({"type": "request", "texto": texto})
            await self.send(msg)

    class ReceiveMessageBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg: return

            try:
                body = jsonpickle.decode(msg.body)
            except:
                body = {"msg": str(msg.body)}


            # Se for uma pergunta do Assistente
            if isinstance(body, dict) and body.get("type") == "ask":
                print(f"\n[Assistente]: {body.get('prompt')}")
                self.agent.msg_pergunta_pendente = msg
                self.agent.lock_input.set()
                return

            # Mensagem normal informativa
            mensagem = body.get("msg", body) if isinstance(body, dict) else body
            print(f"\n[Assistente]: {mensagem}")
            self.agent.lock_input.set()