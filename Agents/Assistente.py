from spade import agent
import spade.behaviour as behaviour
from spade.message import Message
import jsonpickle
import utils.utilsAssistente as utilsAssistente

class ReceiveUserRequestBehaviour(behaviour.CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=10)
        if msg:
            corpo = jsonpickle.decode(msg.body)
            perf = msg.get_metadata("performative")
            sender_jid = str(msg.sender)
            
            # 1. Novo pedido: Cria ou reseta a sessão específica deste JID
            if perf == "request":
                print(f"[Assistente] Novo pedido de {sender_jid}: {corpo.get('texto')}")
                intencao = utilsAssistente.get_intencao(corpo.get('texto'))
                slots = utilsAssistente.extrair_slots(intencao, corpo.get('texto')) if intencao else {}
                
                # Guarda no dicionário de sessões do agente usando o JID como chave
                self.agent.sessoes[sender_jid] = {
                    'intencao': intencao,
                    'slots': slots,
                    'waiting_slot': None
                }
                # Passa o JID para o próximo comportamento saber quem tratar
                self.agent.add_behaviour(DialogueStateBehaviour(user_jid=sender_jid))

            # 2. Resposta a pergunta: Recupera a sessão do JID que respondeu
            elif perf == "inform":
                if sender_jid in self.agent.sessoes:
                    ctx = self.agent.sessoes[sender_jid]
                    slot_pendente = ctx.get('waiting_slot')
                    
                    if slot_pendente:
                        print(f"[Assistente] {sender_jid} enviou {slot_pendente}: {corpo}")
                        ctx['slots'][slot_pendente] = corpo
                        ctx['waiting_slot'] = None
                        self.agent.add_behaviour(DialogueStateBehaviour(user_jid=sender_jid))

class DialogueStateBehaviour(behaviour.OneShotBehaviour):
    def __init__(self, user_jid):
        super().__init__()
        self.user_jid = user_jid

    async def run(self):
        # Acede apenas à sessão do utilizador específico
        ctx = self.agent.sessoes.get(self.user_jid)
        if not ctx: return

        intencao = ctx.get('intencao')
        slots = ctx.get('slots', {})

        if not intencao:
            print(f"[Assistente] Intenção de {self.user_jid} não reconhecida.")
            return

        slots_necessarios = self.agent.INTENT_SLOTS.get(intencao, [])
        slots_em_falta = [s for s in slots_necessarios if s not in slots]

        if slots_em_falta:
            proximo_slot = slots_em_falta[0]
            ctx['waiting_slot'] = proximo_slot
            
            msg = Message(to=self.user_jid)
            msg.set_metadata("performative", "query-ref")
            msg.body = jsonpickle.encode(f"Por favor, indique: {proximo_slot}")
            await self.send(msg)
        else:
            print(f"[Assistente] Concluído para {self.user_jid}. Dados: {slots}")
            # Limpa a sessão após concluir para libertar memória
            del self.agent.sessoes[self.user_jid]

class AssistenteAgent(agent.Agent):
    INTENT_SLOTS = {
        "inscricao": ["numero_aluno", "curso", "disciplina"],
        "equivalencia": ["numero_aluno", "disciplina_origem", "disciplina_destino"],
    }

    async def setup(self):
        print(f"Assistente {str(self.jid)} ativo para múltiplos utilizadores.")
        # Dicionário que gere múltiplas conversas em simultâneo
        self.sessoes = {} 
        self.add_behaviour(ReceiveUserRequestBehaviour())