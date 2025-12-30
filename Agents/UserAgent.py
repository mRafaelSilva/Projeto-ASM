from spade import agent
import spade.behaviour as behaviour
from spade.message import Message
import jsonpickle
import asyncio

class UserAgent(agent.Agent):
    class SendRequestBehaviour(behaviour.OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1)
            loop = asyncio.get_event_loop()
            
            # Primeiro pedido inicial
            texto = await loop.run_in_executor(None, lambda: input("Digite o seu pedido inicial: "))
            
            pedido = {"texto": texto}
            msg = Message(to="assistente@localhost")  
            msg.set_metadata("performative", "request")
            msg.body = jsonpickle.encode(pedido)
            await self.send(msg)
            print("[UserAgent] Pedido enviado!")

    class ReceiveMessageBehaviour(behaviour.CyclicBehaviour):
        async def run(self):
            # O timeout permite que o loop não fique preso para sempre
            msg = await self.receive(timeout=10)
            if msg:
                corpo = jsonpickle.decode(msg.body)
                perf = msg.get_metadata("performative")

                # Se o assistente enviar uma pergunta (query-ref)
                if perf == "query-ref":
                    print(f"\n[Assistente pergunta]: {corpo}")
                    
                    # Usa executor para o input não bloquear a receção de próximas mensagens
                    loop = asyncio.get_event_loop()
                    valor = await loop.run_in_executor(None, lambda: input("> "))
                    
                    reply = msg.make_reply()
                    reply.set_metadata("performative", "inform")
                    reply.body = jsonpickle.encode(valor)
                    await self.send(reply)
                    print(f"[UserAgent] Resposta '{valor}' enviada.")
                else:
                    print(f"\n[Assistente diz]: {corpo}")

    async def setup(self):
        print(f"UserAgent {str(self.jid)} iniciado.")
        # Comportamento para o primeiro input
        self.add_behaviour(self.SendRequestBehaviour())
        # Comportamento contínuo para ouvir o assistente
        self.add_behaviour(self.ReceiveMessageBehaviour())