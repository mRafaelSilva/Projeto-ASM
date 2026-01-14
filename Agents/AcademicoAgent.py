from spade import agent
import spade.behaviour as behaviour

import jsonpickle
import json
import os

class AcademicoAgent(agent.Agent):

    class ReceiveRequestBehaviour(behaviour.CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg:
                # Recarregar dados frescos para garantir consistência com outros agentes
                self.agent.load_data()
                
                p = msg.get_metadata('performative')
                if p == 'inscricao':
                    request = self.agent.decode_message(msg.body)
                    student_id = str(request.get('student_id'))
                    class_id = str(request.get('class_id')).upper()
                    to_user = request.get('to_user')
                    
                    response = self.agent.process_enrollment(student_id, class_id)
                    
                    if to_user:
                        response['to_user'] = to_user
                    
                    reply = msg.make_reply()
                    reply.set_metadata('performative', 'inform') 
                    reply.body = jsonpickle.encode(response)
                    await self.send(reply)
            else:
               pass

    def load_data(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        estudantes_path = os.path.join(base_dir, "Database", "estudantes.json")
        disciplinas_path = os.path.join(base_dir, "Database", "disciplinas.json")
        with open(estudantes_path, "r") as f:
            est_list = json.load(f)
            self.estudantes = {str(e['id']): e for e in est_list}
            
        with open(disciplinas_path, "r") as f:
            self.disciplinas = json.load(f)
    
    def save_data(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        estudantes_path = os.path.join(base_dir, "Database", "estudantes.json")
        
        est_list = list(self.estudantes.values())
        
        with open(estudantes_path, "w") as f:
            json.dump(est_list, f, indent=4)

    def decode_message(self, message_body):
        return jsonpickle.decode(message_body)

    def process_enrollment(self, student_id, class_id):
        if student_id not in self.estudantes:
             return {"status": "error", "msg": "Estudante não encontrado."}

        student = self.estudantes[student_id]
        curso_id = student.get('curso_id')
        
        if not curso_id:
            return {"status": "error", "msg": "Estudante sem curso associado."}
        
        # Obter inscrições ativas do currículo
        curriculo = student.get('curriculo', {})
        inscricoes_ativas = curriculo.get('inscricoes_ativas', [])
        
        # Verificar se ja esta inscrito
        if class_id in inscricoes_ativas:
             return {"status": "error", "msg": f"Já está inscrito em {class_id}."}

        # Verificar disponibilidade da disciplina
        availability = self.check_class_availability(class_id, curso_id)
        if availability['status'] != 'available':
            return availability

        # Verificar creditos
        if self.exceeds_max_credits(student_id, class_id, curso_id):
             return {"status": "error", "msg": "Limite de créditos (30 ECTS) excedido."}

        # Inscrever (passar o turno disponível)
        turno_id = availability.get('turno')
        self.enroll_student(student_id, class_id, curso_id, turno_id)
        return {"status": "success", "msg": f"Inscrito com sucesso em {class_id} (turno {turno_id})."}

    def check_class_availability(self, class_id, curso_id):
        if curso_id not in self.disciplinas:
            return {"status": "error", "msg": "Curso não encontrado."}
            
        for d in self.disciplinas[curso_id]:
            if d['id'] == class_id:
                # Verificar vagas nos turnos
                turnos = d.get('turnos', [])
                if not turnos:
                    return {"status": "error", "msg": "Disciplina sem turnos disponíveis."}
                
                # Procurar pelo menos um turno com vagas
                for turno in turnos:
                    vagas_ocupadas = turno.get('vagas_ocupadas', 0)
                    vagas_totais = turno.get('vagas_totais', 0)
                    if vagas_ocupadas < vagas_totais:
                        return {"status": "available", "turno": turno.get('id')}
                
                return {"status": "error", "msg": "Todos os turnos estão cheios."}
        
        return {"status": "error", "msg": "Disciplina não encontrada."}
    
    def exceeds_max_credits(self, student_id, new_class_id, curso_id):
        creds = 0
        student = self.estudantes[student_id]
        curriculo = student.get('curriculo', {})
        inscricoes = curriculo.get('inscricoes_ativas', [])
        
        if curso_id not in self.disciplinas:
            return False
        
        course_classes = {d['id']: d.get('ects', 0) for d in self.disciplinas[curso_id]}

        for insc in inscricoes:
            if insc in course_classes:
                creds += course_classes[insc]
        
        # Adicionar creditos da nova disciplina
        if new_class_id in course_classes:
            creds += course_classes[new_class_id]
            
        return creds > 30
    
    def enroll_student(self, student_id, class_id, curso_id, turno_id=None):
        # Atualizar estudante (usar curriculo.inscricoes_ativas)
        student = self.estudantes[student_id]
        if 'curriculo' not in student:
            student['curriculo'] = {'aprovadas': [], 'inscricoes_ativas': []}
        if 'inscricoes_ativas' not in student['curriculo']:
            student['curriculo']['inscricoes_ativas'] = []
        
        student['curriculo']['inscricoes_ativas'].append(class_id)
        
        # Atualizar vagas no turno da disciplina
        if curso_id in self.disciplinas:
            for d in self.disciplinas[curso_id]:
                if d['id'] == class_id:
                    turnos = d.get('turnos', [])
                    for turno in turnos:
                        # Se turno_id especificado, usar esse; senão, usar o primeiro com vagas
                        if turno_id and turno.get('id') == turno_id:
                            turno['vagas_ocupadas'] = turno.get('vagas_ocupadas', 0) + 1
                            break
                        elif not turno_id and turno.get('vagas_ocupadas', 0) < turno.get('vagas_totais', 0):
                            turno['vagas_ocupadas'] = turno.get('vagas_ocupadas', 0) + 1
                            break
                    break
                
        self.save_data()

    async def setup(self):
        print(f"[Academico] {str(self.jid)} ativo.")
        self.estudantes = {}
        self.disciplinas = {}
        self.load_data()
        self.add_behaviour(self.ReceiveRequestBehaviour())



