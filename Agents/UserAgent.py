from spade import agent
import spade.behaviour as behaviour
from spade.message import Message
import asyncio
import json
import jsonpickle
from aioconsole import ainput


class UserAgent(agent.Agent):
    async def setup(self):
        print(f"UserAgent {str(self.jid)} iniciado.")
        
        # Variável para gerir o estado da conversa
        self.msg_pergunta_pendente = None
        
        self.add_behaviour(self.InputBehaviour())
        self.add_behaviour(self.ReceiveMessageBehaviour())

        await asyncio.sleep(0.5)
        
        print("Digite o seu pedido (ex: 'inscrever em LEI', 'olá', 'pagar', 'divida'):")

    class InputBehaviour(behaviour.CyclicBehaviour):
        async def run(self):
            await asyncio.sleep(0.1)

            try:
                prompt = ">> " if self.agent.msg_pergunta_pendente else "> "
                texto = (await ainput(prompt)).strip()
            except (EOFError, KeyboardInterrupt):
                return

            if not texto:
                return

            # Se existe uma pergunta pendente, o input é a resposta
            if self.agent.msg_pergunta_pendente:
                msg_origem = self.agent.msg_pergunta_pendente
                reply = msg_origem.make_reply()
                reply.set_metadata("performative", "inform")
                reply.body = json.dumps({"type": "answer", "value": texto}, ensure_ascii=False)
                await self.send(reply)
                
                self.agent.msg_pergunta_pendente = None
                return

            # ---- MODO TESTE: se começar por /horarios, manda direto para o HorariosAgent ----
            if texto.startswith("/horarios"):
                parts = texto.split()
                if len(parts) < 4:
                    print("Uso: /horarios (check|find) CURSO DISC1 DISC2 ...")
                    return

                msg = Message(to="horarios@localhost")
                msg.set_metadata("performative", "request")
                msg.body = jsonpickle.encode({
                    "acao": "check_schedule" if parts[1] == "check" else "find_feasible",
                    "curso": parts[2],
                    "disciplinas": parts[3:]
                })
                await self.send(msg)
                return

            # ---- Fluxo normal: envia para o Assistente (JSON) ----
            msg = Message(to="assistente@localhost")
            msg.set_metadata("performative", "request")
            msg.body = json.dumps({"texto": texto}, ensure_ascii=False)
            await self.send(msg)

    class ReceiveMessageBehaviour(behaviour.CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg:
                return

            perf = msg.get_metadata("performative")
            sender = str(msg.sender).split("/")[0]

            try:
                corpo = json.loads(msg.body) if msg.body else {}
            except Exception:
                try:
                    corpo = jsonpickle.decode(msg.body)
                except Exception:
                    corpo = msg.body

            # Resposta do HorariosAgent
            if sender == "horarios@localhost":
                print(f"\n[Horários respondeu]: {corpo}")
                return

            # Perguntas do Assistente (slot filling)
            if perf == "request" and isinstance(corpo, dict) and corpo.get("type") == "ask":
                prompt = corpo.get("prompt") or f"Indique: {corpo.get('slot')}"
                print(f"\n[Assistente pergunta]: {prompt}")
                # Apenas guardamos o estado, o InputBehaviour trata de responder
                self.agent.msg_pergunta_pendente = msg
                return

            # Mensagens informativas do Assistente
            if isinstance(corpo, dict) and "msg" in corpo:
                print(f"\n[Assistente diz]: {corpo['msg']}")
                if "saldo_novo" in corpo:
                    print(f"   Saldo Atual: {corpo['saldo_novo']}€")
                if "valor_divida" in corpo:
                    print(f"   Dívida: {corpo['valor_divida']}€")
            else:
                print(f"\n[Assistente diz]: {corpo}")