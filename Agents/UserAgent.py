from spade import agent
import spade.behaviour as behaviour
from spade.message import Message
import json
import jsonpickle
import asyncio


class UserAgent(agent.Agent):
    class SendRequestBehaviour(behaviour.OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1)
            loop = asyncio.get_event_loop()

            texto = await loop.run_in_executor(
                None, lambda: input("Digite o seu pedido inicial: ").strip()
            )

            # ---- MODO TESTE: se começar por /horarios, manda direto para o HorariosAgent ----
            # Exemplos:
            #   /horarios check L-EI SO1 ALGEBRA
            #   /horarios find  L-EI SO1 ALGEBRA
            if texto.startswith("/horarios"):
                parts = texto.split()
                if len(parts) < 4:
                    print("Uso: /horarios (check|find) CURSO DISC1 DISC2 ...")
                    return

                modo = parts[1].lower()  # check | find
                curso = parts[2]
                discs = parts[3:]

                acao = "check_schedule" if modo == "check" else "find_feasible"

                msg = Message(to="horarios@localhost")
                msg.set_metadata("performative", "request")
                msg.body = jsonpickle.encode(
                    {"acao": acao, "curso": curso, "disciplinas": discs}
                )
                await self.send(msg)
                print("[UserAgent] Pedido enviado ao HorariosAgent.")
                return

            # ---- Fluxo normal: envia para o Assistente (JSON) ----
            pedido = {"texto": texto}
            msg = Message(to="assistente@localhost")
            msg.set_metadata("performative", "request")
            msg.body = json.dumps(pedido, ensure_ascii=False)
            await self.send(msg)
            print("[UserAgent] Pedido enviado ao Assistente!")

    class ReceiveMessageBehaviour(behaviour.CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if not msg:
                return

            perf = msg.get_metadata("performative")

            # tentar JSON primeiro (fluxo do Assistente)
            try:
                corpo = json.loads(msg.body) if msg.body else {}
            except Exception:
                # fallback para jsonpickle (p.ex. Horários direto)
                try:
                    corpo = jsonpickle.decode(msg.body)
                except Exception:
                    corpo = msg.body

            sender = str(msg.sender).split("/")[0]

            # Resposta do HorariosAgent (quando o user enviou /horarios ...)
            if sender == "horarios@localhost":
                print("\n[Horários respondeu]:")
                print(corpo)
                return

            # Perguntas do Assistente (slot filling)
            if perf == "request" and isinstance(corpo, dict) and corpo.get("type") == "ask":
                prompt = corpo.get("prompt") or f"Indique: {corpo.get('slot')}"
                print(f"\n[Assistente pergunta]: {prompt}")

                loop = asyncio.get_event_loop()
                valor = await loop.run_in_executor(None, lambda: input("> ").strip())

                reply = msg.make_reply()
                reply.set_metadata("performative", "inform")
                reply.body = json.dumps({"type": "answer", "value": valor}, ensure_ascii=False)
                await self.send(reply)
                print(f"[UserAgent] Resposta '{valor}' enviada.")
                return

            # Mensagens normais do Assistente
            print(f"\n[Assistente diz]: {corpo}")

    async def setup(self):
        print(f"UserAgent {str(self.jid)} iniciado.")
        self.add_behaviour(self.SendRequestBehaviour())
        self.add_behaviour(self.ReceiveMessageBehaviour())
