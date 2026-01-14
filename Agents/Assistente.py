import json
import os
import jsonpickle
from typing import Any, Dict, Set
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import utils.utilsLLM as llm
import utils.utilsAssistente as utils
from Agents.Strategies.IntentionsStrategy import IntentionsStrategy

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
    INTENTS_REGULATION: Set[str] = {"listar_regulamentos", "ver_regulamento", "inscrever_regulamento", "remover_inscricao_regulamento", "verificar_inscricao_regulamento"}
    INTENTS_GENERAL: Set[str] = {"saudacao", "ajuda", "desconhecida"}
    INTENTS_ACADEMIC: Set[str] = {"inscricao", "horarios"}
    INTENTS_FINANCIAL: Set[str] = {"fazer_pagamento", "ver_saldo"}
    # Ações que NÃO precisam de login (informações públicas)
    INTENTS_NO_LOGIN: Set[str] = {"saudacao", "ajuda", "desconhecida", "horarios", "listar_regulamentos", "ver_regulamento"}

    def __init__(self, jid, password):
        super().__init__(jid, password)
        self._contexts: Dict[str, Dict[str, Any]] = {}

    async def setup(self):
        print(f"[Assistente] {str(self.jid)} ativo.")
        self.strategy = IntentionsStrategy()
        self.add_behaviour(self.ReceiveUserRequestBehaviour())
        self.add_behaviour(self.ReceiveInformBehaviour())

    def _get_ctx(self, user_jid: str) -> Dict[str, Any]:
        return self._contexts.setdefault(user_jid, {
            "user_jid": user_jid, "intencao": None, "slots": {}, "pendente": None, "awaiting": None, "sessao_aluno": None
        })
    

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
                    await utils.reply(self, user_jid, {
                        "type": "login_response",
                        "success": True,
                        "numero_aluno": numero,
                        "nome": estudante.get("nome", ""),
                        "curso": estudante.get("curso_id", ""),
                        "estatuto": estudante.get("estatuto", "")
                    })
                else:
                    await utils.reply(self, user_jid, {
                        "type": "login_response",
                        "success": False,
                        "msg": f"Estudante {numero} não encontrado na base de dados."
                    })
                return

            # Tratar logout
            if data.get("type") == "logout":
                ctx["sessao_aluno"] = None
                ctx["slots"] = {}
                ctx["intencao"] = None
                ctx["pendente"] = None
                ctx["awaiting"] = None
                return

            texto = data.get("texto", "")
            if not texto: return

            # Atualizar sessão se enviada
            sessao_aluno = data.get("sessao_aluno")
            if sessao_aluno:
                ctx["sessao_aluno"] = sessao_aluno

            # Limpar slots do pedido anterior
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

            # 1. GENERAL
            if intencao in self.agent.INTENTS_GENERAL:
                await self.agent.strategy.processar_geral(self, user_jid, intencao, ctx)
                return

            # 2. Check Login for Privileged Actions
            if intencao not in self.agent.INTENTS_NO_LOGIN:
                if not ctx.get("sessao_aluno"):
                    await utils.reply(self, user_jid, {
                        "msg": "Esta ação requer login! Use 'login <numero_aluno>' primeiro."
                    })
                    return

            # 3. ACADEMIC
            if intencao in self.agent.INTENTS_ACADEMIC:
                await self.agent.strategy.processar_academico(self, user_jid, intencao, ctx["slots"], ctx)
                return

            # 4. FINANCIAL
            if intencao in self.agent.INTENTS_FINANCIAL:
                await self.agent.strategy.processar_financeiro(self, user_jid, intencao, ctx["slots"], ctx)
                return

            # 5. REGULATION
            if intencao in self.agent.INTENTS_REGULATION:
                await self.agent.strategy.processar_regulamentos(self, user_jid, intencao, ctx["slots"], ctx)
                return
            
            await utils.reply(self, user_jid, {"msg": f"Comando '{intencao}' não reconhecido ou não suportado."})


    class ReceiveInformBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg: return
            
            # Ignorar mensagens de request (tratadas pelo outro behaviour)
            performative = msg.get_metadata("performative")
            if performative == "request":
                return

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
                    ctx["slots"][slot_faltava] = valor_recebido
                    ctx["awaiting"] = None

                    pendente = ctx.get("pendente")
                    intencao_atual = ctx.get("intencao")

                    if intencao_atual == "fazer_pagamento":
                        if not ctx["slots"].get("valor"):
                            ctx["awaiting"] = "valor"
                            await utils.ask_slot(self, user_jid, "valor")
                            return
                        val = float(ctx["slots"].get("valor", 0))
                        payload = {"acao": "pay_debt", "estudante_id": ctx["slots"]["numero_aluno"], "valor": val, "to_user": user_jid}
                        await utils.forward_request(self, "financeiro@localhost", payload)
                        return

                    if pendente and slot_faltava == "numero_aluno":
                        f_msg = Message(to="financeiro@localhost")
                        f_msg.set_metadata("performative", "query-if")
                        f_msg.body = jsonpickle.encode({"acao": "has_debt", "estudante_id": ctx["slots"]["numero_aluno"], "to_user": user_jid})
                        await self.send(f_msg)
                        return

                    target = pendente if pendente else intencao_atual
                    
                    if target in self.agent.INTENTS_ACADEMIC:
                        await self.agent.strategy.processar_academico(self, user_jid, target, ctx["slots"], ctx)
                    elif target in self.agent.INTENTS_FINANCIAL:
                        await self.agent.strategy.processar_financeiro(self, user_jid, target, ctx["slots"], ctx)
                    elif target in self.agent.INTENTS_REGULATION:
                        await self.agent.strategy.processar_regulamentos(self, user_jid, target, ctx["slots"], ctx)
                    else:
                        await self.agent.strategy.processar_geral(self, user_jid, target, ctx)
                return

            # --- Resposta do HORARIOS ---
            if sender.startswith("horarios@"):
                to_user = data.get("to_user")
                if not to_user: return
                
                ok = data.get("ok", False)
                acao = data.get("acao", "")
                
                if acao == "check_schedule":
                    # Ver horários - sempre mostra os detalhes (capacidade é só para inscrição)
                    detalhes = data.get("detalhes", [])
                    if detalhes:
                        texto = "Horário encontrado:\n"
                        for item in detalhes:
                            if not item.get("erro"):
                                texto += f"  • {item.get('disciplina')} ({item.get('turno')}): {item.get('dia')} {item.get('inicio')}-{item.get('fim')} | Sala: {item.get('sala')}\n"
                            else:
                                texto += f"  • {item.get('disciplina')}: {item.get('erro')}\n"
                        await utils.reply(self, to_user, {"msg": texto})
                    else:
                        await utils.reply(self, to_user, {"msg": "Não foi possível encontrar horário para esta disciplina."})
                else:
                    # Outros tipos de resposta do horários
                    erro = data.get("erro", "")
                    if erro:
                        await utils.reply(self, to_user, {"msg": f"Erro nos horários: {erro}"})
                    else:
                        await utils.reply(self, to_user, {"msg": "Resposta do agente de horários recebida."})
                return

            if sender.startswith("financeiro@"):
                to_user = data.get("to_user")
                if not to_user: return
                ctx = self.agent._get_ctx(to_user)

                if "debt" in data:
                    if ctx.get("pendente") == "ver_saldo":
                        saldo_msg = f"Saldo: {data.get('saldo')}€. Dívida: {data.get('valor')}€."
                        await utils.reply(self, to_user, {"msg": saldo_msg})
                        ctx["pendente"] = None
                        return

                    if data["debt"] == "yes":
                        if ctx.get("pendente") == "fazer_pagamento":
                            op = ctx.get("pendente")
                            await self.agent.strategy.processar_financeiro(self, to_user, op, ctx["slots"], ctx)
                            ctx["pendente"] = None
                            return

                        await utils.reply(self, to_user, {"ok": False, "msg": f"Operação bloqueada! Regularize a dívida de {data.get('valor')}€."})
                        ctx["pendente"] = None
                    else:
                        op = ctx.get("pendente")
                        if op:
                            # Se for inscrição, usar função direta (já validou dados)
                            if op == "inscricao":
                                await self.agent.strategy._enviar_inscricao(self, to_user, ctx["slots"], ctx)
                            elif op in self.agent.INTENTS_ACADEMIC:
                                await self.agent.strategy.processar_academico(self, to_user, op, ctx["slots"], ctx)
                            elif op in self.agent.INTENTS_FINANCIAL:
                                await self.agent.strategy.processar_financeiro(self, to_user, op, ctx["slots"], ctx)
                            elif op in self.agent.INTENTS_REGULATION:
                                await self.agent.strategy.processar_regulamentos(self, to_user, op, ctx["slots"], ctx)
                            else:
                                await self.agent.strategy.processar_geral(self, to_user, op, ctx)
                            ctx["pendente"] = None
                    return
                
                if "paid" in data:
                    res = "Sucesso" if data["paid"] else "Recusado"
                    await utils.reply(self, to_user, {"msg": f"Pagamento: {res}. Novo Saldo: {data.get('saldo_novo')}€"})
                    ctx["slots"] = {}
                    ctx["intencao"] = None
                    return

            if sender.startswith("academico@"):
                to_user = data.get("to_user")
                if not to_user: return

                status = data.get("status")
                msg_txt = data.get("msg", "")

                if status == "success":
                    await utils.reply(self, to_user, {"ok": True, "msg": f"Inscrição realizada: {msg_txt}"})
                else:
                    await utils.reply(self, to_user, {"ok": False, "msg": f"Erro na inscrição: {msg_txt}"})
                return


            if sender.startswith("regulamentos@"):
                to_user = data.get("to_user")
                if not to_user:
                    return

                action = data.get("action")
                
                erro = data.get("erro") or data.get("error")
                regulamento = data.get("regulamento")
                regs_disponiveis = data.get("regulamentos_disponiveis", [])

               
                if erro:
                    if erro == "unknown_action":
                        esperadas = data.get("expected", [])
                        recebida = data.get("got")
                    
                        if esperadas:
                            texto = (
                                "A ação pedida não é suportada.\n"
                                "Ações disponíveis:\n" +
                                "\n".join(f"- {a}" for a in esperadas)
                            )
                        else:
                            texto = "A ação pedida não é suportada."
                    
                        if recebida:
                            texto += f"\nAção recebida: {recebida}"
                    
                        await utils.reply(self, to_user, {"msg": texto})
                        return

                    if erro == "regulamento_inexistente":
                        if regs_disponiveis:
                            texto = (
                                f"O regulamento '{regulamento}' não existe.\n"
                                "Regulamentos disponíveis:\n" +
                                "\n".join(f"- {r}" for r in regs_disponiveis)
                            )
                        else:
                            texto = f"O regulamento '{regulamento}' não existe."
                        await utils.reply(self, to_user, {"msg": texto})
                        return

                    if erro == "aluno_inexistente":
                        texto = "O número de aluno indicado não existe."
                        await utils.reply(self, to_user, {"msg": texto})
                        return

                    if erro == "ja_tem_estatuto":
                        estatuto_atual = data.get("estatuto_atual", "desconhecido")
                        texto = (
                            "Não é possível atribuir novo estatuto.\n"
                            f"Estatuto atual: {estatuto_atual}."
                        )
                        await utils.reply(self, to_user, {"msg": texto})
                        return

                    if erro == "nao_tem_estatuto_especial":
                        texto = "O estudante não tem nenhum estatuto especial para remover."
                        await utils.reply(self, to_user, {"msg": texto})
                        return

                    # fallback genérico
                    texto = f"Ocorreu um erro: {erro}"
                    await utils.reply(self, to_user, {"msg": texto})
                    return

                # ---------------- SUCESSO ----------------
                if action == "listar_regulamentos":
                    regs = data.get("regulamentos", [])

                    if not regs:
                        texto = "Não existem regulamentos disponíveis."
                    else:
                        texto = "Regulamentos disponíveis:\n"
                        texto += "\n".join(f"- {r}" for r in regs)

                    await utils.reply(self, to_user, {"msg": texto})
                    return

                if action == "ver_regulamento":
                    nome = data.get("regulamento")
                    dados = data.get("dados", {})

                    if not dados:
                        texto = f"O regulamento '{nome}' não foi encontrado."
                    else:
                        texto = (
                            f"Regulamento: {nome}\n"
                            f"Descrição: {dados.get('descricao', '—')}\n"
                            f"ECTS máximos/ano: {dados.get('ects_max_ano', '—')}\n"
                        )

                        regras = dados.get("regras", [])
                        if regras:
                            texto += "Regras:\n" + "\n".join(f"- {r}" for r in regras)

                    await utils.reply(self, to_user, {"msg": texto})
                    return

                if action == "inscrever_regulamento":
                    texto = f"Inscrição no regulamento '{regulamento}' efetuada com sucesso."
                    await utils.reply(self, to_user, {"msg": texto})
                    return

                if action == "remover_inscricao_regulamento":
                    texto = "O estatuto especial foi removido com sucesso."
                    await utils.reply(self, to_user, {"msg": texto})
                    return

                if action == "verificar_inscricao_regulamento":
                    inscrito = data.get("inscrito", False)
                    if inscrito:
                        texto = f"O estudante está inscrito no regulamento '{regulamento}'."
                    else:
                        texto = f"O estudante não está inscrito no regulamento '{regulamento}'."
                    await utils.reply(self, to_user, {"msg": texto})
                    return



