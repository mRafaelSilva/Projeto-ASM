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

    async def processar_academico(self, behaviour, user_jid, intencao, slots, ctx):
        if intencao == "inscricao":
            if not slots.get("curso"):
                ctx["awaiting"] = "curso"
                await utils.ask_slot(behaviour, user_jid, "curso")
                return
            if not slots.get("disciplina"):
                ctx["awaiting"] = "disciplina"
                await utils.reply(behaviour, user_jid, {"type": "ask", "prompt": "Qual a disciplina? (Indique uma válida, ex: SO1)"})
                return
            
            student_id = ctx["slots"].get("numero_aluno")
            class_id = ctx["slots"].get("disciplina")
            
            # Request to AcademicoAgent
            payload = {"student_id": student_id, "class_id": class_id, "to_user": user_jid}
            req = Message(to="academico@localhost")
            req.set_metadata("performative", "inscricao")
            req.body = jsonpickle.encode(payload)
            await behaviour.send(req)
            
            await utils.reply(behaviour, user_jid, {"msg": f"A processar inscrição em {class_id}..."})
            ctx["intencao"] = None 
            return

        if intencao == "horarios":
            if not slots.get("curso"):
                ctx["awaiting"] = "curso"
                await utils.ask_slot(behaviour, user_jid, "curso")
                return
            if not slots.get("disciplina"):
                ctx["awaiting"] = "disciplina"
                await utils.ask_slot(behaviour, user_jid, "disciplina")
                return

            payload = {
                "acao": "check_schedule", 
                "curso": slots["curso"], 
                "disciplinas": [slots["disciplina"]], 
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
            payload = { "action": "listar_regulamentos", "to_user": user_jid }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return

        if intencao == "ver_regulamento":
            if not slots.get("regulamento"):
                ctx["awaiting"] = "regulamento"
                await utils.ask_slot(behaviour, user_jid, "regulamento")
                return

            payload = { "action": "ver_regulamento", "regulamento": slots.get("regulamento"), "to_user": user_jid }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return

        if intencao == "inscrever_regulamento":
            if not slots.get("regulamento"):
                ctx["awaiting"] = "regulamento"
                await utils.ask_slot(behaviour, user_jid, "regulamento")
                return
            
            payload = {"action": "inscrever_regulamento", "regulamento": slots.get("regulamento"), "numero_aluno": slots.get("numero_aluno"), "documentos": slots.get("documentos", []), "to_user": user_jid }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return

        if intencao == "verificar_inscricao_regulamento":
            if not slots.get("regulamento"):
                ctx["awaiting"] = "regulamento"
                await utils.ask_slot(behaviour, user_jid, "regulamento")
                return

            payload = { "action": "verificar_inscricao_regulamento", "regulamento": slots.get("regulamento"), "numero_aluno": slots.get("numero_aluno"), "to_user": user_jid }
            await utils.forward_request(behaviour, "regulamentos@localhost", payload)
            return
