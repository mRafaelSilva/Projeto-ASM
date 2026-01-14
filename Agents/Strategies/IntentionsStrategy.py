import jsonpickle
from spade.message import Message
import utils.utilsAssistente as utils

class IntentionsStrategy:
    
    async def processar_geral(self, behaviour, user_jid, intencao, ctx):
        if intencao == "saudacao":
            await utils.reply(behaviour, user_jid, {"msg": "Olá! Posso ajudar com inscrições, horários ou pagamentos."})
            return

        if intencao == "desconhecida":
            await utils.reply(behaviour, user_jid, {"msg": "Não percebi. Tente 'ver saldo', 'inscrever SO1' ou 'horario LEI'."})
            return
        
        if intencao == "ajuda":
            await utils.reply(behaviour, user_jid, {"msg": utils.HELP_MESSAGE})
            return

    async def _enviar_inscricao(self, behaviour, user_jid, slots, ctx):
        """Envia pedido de inscrição ao AcademicoAgent (após verificação de dívidas)"""
        student_id = slots.get("numero_aluno")
        class_id = slots.get("disciplina")
        
        payload = {"student_id": student_id, "class_id": class_id, "to_user": user_jid}
        req = Message(to="academico@localhost")
        req.set_metadata("performative", "inscricao")
        req.body = jsonpickle.encode(payload)
        await behaviour.send(req)
        
        await utils.reply(behaviour, user_jid, {"msg": f"A processar inscrição em {class_id}..."})
        ctx["intencao"] = None
        ctx["pendente"] = None

    async def processar_academico(self, behaviour, user_jid, intencao, slots, ctx):
        if intencao == "inscricao":
            # Usar curso da sessão se disponível
            if not slots.get("curso"):
                estudante = utils.get_estudante_by_id(ctx.get("sessao_aluno"))
                if estudante and estudante.get("curso_id"):
                    ctx["slots"]["curso"] = estudante["curso_id"]
                    slots["curso"] = estudante["curso_id"]
                else:
                    ctx["awaiting"] = "curso"
                    cursos = utils.get_cursos_disponiveis()
                    await utils.reply(behaviour, user_jid, {"type": "ask", "prompt": f"Qual o curso? (Disponíveis: {', '.join(cursos)})"})
                    return
            
            # Verificar se curso existe
            if not utils.validar_curso(slots.get("curso")):
                cursos = utils.get_cursos_disponiveis()
                await utils.reply(behaviour, user_jid, {"msg": f"Curso '{slots.get('curso')}' não encontrado. Cursos disponíveis: {', '.join(cursos)}"})
                ctx["slots"]["curso"] = None
                return
            
            # Validar disciplina
            if not slots.get("disciplina"):
                ctx["awaiting"] = "disciplina"
                await utils.reply(behaviour, user_jid, {"type": "ask", "prompt": "Qual a disciplina? (ex: SO1, ALGEBRA)"})
                return
            
            # Normalizar disciplina (pode ser lista ou string)
            disc = slots.get("disciplina")
            if isinstance(disc, list):
                disc = disc[0] if disc else None
            
            if not disc or not utils.validar_disciplina(disc):
                curso = slots.get("curso")
                discs_curso = utils.get_disciplinas_curso(curso) if curso else []
                ctx["slots"]["disciplina"] = None
                ctx["awaiting"] = "disciplina"
                if disc:
                    if discs_curso:
                        prompt = f"Disciplina '{disc}' não encontrada no curso {curso}. Disponíveis: {', '.join(discs_curso)}"
                    else:
                        prompt = f"Disciplina '{disc}' não encontrada. Qual a disciplina?"
                else:
                    prompt = f"Qual a disciplina? (Disponíveis: {', '.join(discs_curso)})" if discs_curso else "Qual a disciplina? (ex: SO1, ALGEBRA)"
                await utils.reply(behaviour, user_jid, {"type": "ask", "prompt": prompt})
                return
            
            student_id = ctx["slots"].get("numero_aluno")
            class_id = disc.upper()
            
            # Guardar dados para depois da verificação de dívidas
            ctx["slots"]["disciplina"] = class_id
            ctx["pendente"] = "inscricao"
            
            # Verificar dívidas antes de inscrever
            msg = Message(to="financeiro@localhost")
            msg.set_metadata("performative", "query-if")
            msg.body = jsonpickle.encode({"acao": "has_debt", "estudante_id": student_id, "to_user": user_jid})
            await behaviour.send(msg)
            return

        if intencao == "horarios":
            # Ver horarios é público - perguntar sempre o curso
            if not slots.get("curso"):
                ctx["awaiting"] = "curso"
                cursos = utils.get_cursos_disponiveis()
                await utils.reply(behaviour, user_jid, {"type": "ask", "prompt": f"Qual o curso? (Disponíveis: {', '.join(cursos)})"})
                return
            
            # Verificar se curso existe
            curso = utils.normalizar_curso(slots.get("curso"))
            if not utils.validar_curso(curso):
                cursos = utils.get_cursos_disponiveis()
                await utils.reply(behaviour, user_jid, {"msg": f"Curso '{slots.get('curso')}' não encontrado. Cursos disponíveis: {', '.join(cursos)}"})
                ctx["slots"]["curso"] = None
                return
            
            # Validar disciplina
            discs_curso = utils.get_disciplinas_curso(curso)
            if not slots.get("disciplina"):
                ctx["awaiting"] = "disciplina"
                prompt = f"Qual a disciplina? (Disponíveis: {', '.join(discs_curso)})" if discs_curso else "Qual a disciplina? (ex: SO1, ALGEBRA)"
                await utils.reply(behaviour, user_jid, {"type": "ask", "prompt": prompt})
                return
            
            # Normalizar disciplina
            disc = slots.get("disciplina")
            if isinstance(disc, list):
                disc = disc[0] if disc else None
            
            if not disc or not utils.validar_disciplina(disc):
                ctx["slots"]["disciplina"] = None
                ctx["awaiting"] = "disciplina"
                if disc:
                    if discs_curso:
                        prompt = f"Disciplina '{disc}' não encontrada no curso {curso}. Disponíveis: {', '.join(discs_curso)}"
                    else:
                        prompt = f"Disciplina '{disc}' não encontrada. Qual a disciplina?"
                else:
                    prompt = f"Qual a disciplina? (Disponíveis: {', '.join(discs_curso)})" if discs_curso else "Qual a disciplina? (ex: SO1, ALGEBRA)"
                await utils.reply(behaviour, user_jid, {"type": "ask", "prompt": prompt})
                return

            payload = {
                "acao": "check_schedule", 
                "curso": curso, 
                "disciplinas": [disc.upper()], 
                "to_user": user_jid
            }
            await utils.forward_request(behaviour, "horarios@localhost", payload)
            return

    async def processar_financeiro(self, behaviour, user_jid, intencao, slots, ctx):
        if intencao == "fazer_pagamento":
            if not slots.get("numero_aluno"):
                ctx["awaiting"] = "numero_aluno"
                await utils.ask_slot(behaviour, user_jid, "numero_aluno")
                return
            if not slots.get("valor"):
                ctx["awaiting"] = "valor"
                await utils.ask_slot(behaviour, user_jid, "valor")
                return
            
            val = float(slots.get("valor"))
            payload = {
                "acao": "pay_debt", 
                "estudante_id": slots["numero_aluno"], 
                "valor": val, 
                "to_user": user_jid
            }
            await utils.forward_request(behaviour, "financeiro@localhost", payload)
            return

        if intencao == "ver_saldo":
            if not slots.get("numero_aluno"):
                ctx["awaiting"] = "numero_aluno"
                ctx["pendente"] = "ver_saldo"
                await utils.ask_slot(behaviour, user_jid, "numero_aluno")
                return
            
            ctx["pendente"] = "ver_saldo"
            msg = Message(to="financeiro@localhost")
            msg.set_metadata("performative", "query-if")
            msg.body = jsonpickle.encode({"acao": "has_debt", "estudante_id": slots["numero_aluno"], "to_user": user_jid})
            await behaviour.send(msg)
            return

    async def processar_regulamentos(self, behaviour, user_jid, intencao, slots, ctx):
        if intencao == "listar_regulamentos":
            payload = {
                "action": "listar_regulamentos",
                "to_user": user_jid
            }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return

        if intencao == "ver_regulamento":
            if not slots.get("regulamento"):
                ctx["awaiting"] = "regulamento"
                await utils.ask_slot(behaviour, user_jid, "regulamento")
                return

            payload = {
                "action": "ver_regulamento",
                "regulamento": slots.get("regulamento"),
                "to_user": user_jid
            }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return

        if intencao == "inscrever_regulamento":
            if not slots.get("regulamento"):
                ctx["awaiting"] = "regulamento"
                await utils.ask_slot(behaviour, user_jid, "regulamento")
                return

            if not slots.get("numero_aluno"):
                ctx["awaiting"] = "numero_aluno"
                await utils.ask_slot(behaviour, user_jid, "numero_aluno")
                return

            payload = {
                "action": "inscrever_regulamento",
                "regulamento": slots.get("regulamento"),
                "numero_aluno": slots.get("numero_aluno"),
                "to_user": user_jid
            }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return

        if intencao == "remover_inscricao_regulamento":
            if not slots.get("numero_aluno"):
                ctx["awaiting"] = "numero_aluno"
                await utils.ask_slot(behaviour, user_jid, "numero_aluno")
                return

            payload = {
                "action": "remover_inscricao_regulamento",
                "numero_aluno": slots.get("numero_aluno"),
                "to_user": user_jid
            }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return

        if intencao == "verificar_inscricao_regulamento":
            if not slots.get("regulamento"):
                ctx["awaiting"] = "regulamento"
                await utils.ask_slot(behaviour, user_jid, "regulamento")
                return

            if not slots.get("numero_aluno"):
                ctx["awaiting"] = "numero_aluno"
                await utils.ask_slot(behaviour, user_jid, "numero_aluno")
                return

            payload = {
                "action": "verificar_inscricao_regulamento",
                "regulamento": slots.get("regulamento"),
                "numero_aluno": slots.get("numero_aluno"),
                "to_user": user_jid
            }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return
