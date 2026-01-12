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
        
        # Sessão do aluno (número de aluno logado)
        self.sessao_aluno = None

        self.add_behaviour(self.InputBehaviour())
        self.add_behaviour(self.ReceiveMessageBehaviour())

    class InputBehaviour(CyclicBehaviour):
        async def on_start(self):
            await asyncio.sleep(0.5)
            print("\n" + "="*61)
            print("CHAT INICIADO")
            print("Comandos de sessão:")
            print("  login <numero_aluno>  - Iniciar sessão")
            print("  logout                - Terminar sessão")
            print("  status                - Ver sessão ativa")
            print("Depois pode fazer pedidos sem indicar o número.")
            print("="*61 + "\n")

        async def run(self):
            await self.agent.lock_input.wait()

            try:
                prompt = ">> " if self.agent.msg_pergunta_pendente else "> "
                texto = (await ainput(prompt)).strip()
            except: return

            if not texto: return

            self.agent.lock_input.clear()

            # ---- Comandos de sessão ----
            texto_lower = texto.lower().strip()
            
            # Login: login <numero_aluno>
            if texto_lower.startswith("login "):
                numero = texto[6:].strip()
                if numero.isdigit():
                    self.agent.sessao_aluno = numero
                    print(f"\n[Sessão] Login efetuado! Aluno: {numero}")
                    print("[Sessão] Agora pode fazer pedidos sem indicar o número.")
                else:
                    print("\n[Sessão] Número inválido. Use: login <numero>")
                self.agent.lock_input.set()
                return
            
            # Logout
            if texto_lower in ["logout", "sair", "terminar sessao", "terminar sessão"]:
                if self.agent.sessao_aluno:
                    # Enviar logout ao Assistente para limpar contexto
                    msg = Message(to="assistente@localhost")
                    msg.set_metadata("performative", "request")
                    msg.body = jsonpickle.encode({"type": "logout"})
                    await self.send(msg)
                    
                    print(f"\n[Sessão] Logout efetuado. Aluno {self.agent.sessao_aluno} desconectado.")
                    self.agent.sessao_aluno = None
                else:
                    print("\n[Sessão] Não existe sessão ativa.")
                self.agent.lock_input.set()
                return
            
            # Ver sessão ativa
            if texto_lower in ["quem sou", "sessao", "sessão", "status"]:
                if self.agent.sessao_aluno:
                    print(f"\n[Sessão] Sessão ativa: Aluno {self.agent.sessao_aluno}")
                else:
                    print("\n[Sessão] Nenhuma sessão ativa. Use 'login <numero>' para entrar.")
                self.agent.lock_input.set()
                return

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
            
            # Incluir número do aluno da sessão se existir
            payload = {"type": "request", "texto": texto}
            if self.agent.sessao_aluno:
                payload["sessao_aluno"] = self.agent.sessao_aluno
            
            msg.body = jsonpickle.encode(payload)
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