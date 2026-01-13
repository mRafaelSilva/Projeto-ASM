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
                p = msg.get_metadata('performative')
                if p == 'inscricao':
                    request = self.decode_message(msg.body)
                    student_id = request.get('student_id')
                    class_id = request.get('class_id')
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
        curso_id = student['curso_id']
        
        # Verificar se ja esta inscrito
        if class_id in student['inscricoes_ativas']:
             return {"status": "error", "msg": f"Já está inscrito em {class_id}."}

        # Verificar disponibilidade da disciplina
        availability = self.check_class_availability(class_id, curso_id)
        if availability['status'] != 'available':
            return availability

        # Verificar creditos
        if self.exceeds_max_credits(student_id, class_id, curso_id):
             return {"status": "error", "msg": "Limite de créditos excedido."}

        # Inscrever
        self.enroll_student(student_id, class_id, curso_id)
        return {"status": "success", "msg": f"Inscrito com sucesso em {class_id}."}

    def check_class_availability(self, class_id, curso_id):
        if curso_id not in self.disciplinas:
            return {"status": "error", "msg": "Curso não encontrado."}
            
        for d in self.disciplinas[curso_id]:
            if d['id'] == class_id:
                if d['vagas_ocupadas'] < d['vagas_totais']:
                    return {"status": "available"}
                else:
                    return {"status": "error", "msg": "Turma cheia."}
        
        return {"status": "error", "msg": "Disciplina não encontrada."}
    
    def exceeds_max_credits(self, student_id, new_class_id, curso_id):
        creds = 0
        student = self.estudantes[student_id]
        inscricoes = student['inscricoes_ativas']
        
        course_classes = {d['id']: d['ects'] for d in self.disciplinas[curso_id]}

        for insc in inscricoes:
            if insc in course_classes:
                creds += course_classes[insc]
        
        # Adicionar creditos da nova disciplina
        if new_class_id in course_classes:
            creds += course_classes[new_class_id]
            
        if creds > 30:
            return True
        
        return False
    
    def enroll_student(self, student_id, class_id, curso_id):
        # Atualizar estudante
        self.estudantes[student_id]['inscricoes_ativas'].append(class_id)
        
        # Atualizar vagas da disciplina
        for d in self.disciplinas[curso_id]:
            if d['id'] == class_id:
                d['vagas_ocupadas'] += 1
                break
                
        self.save_data()

    async def setup(self):
        print("Academic Agent started")
        self.estudantes = {}
        self.disciplinas = {}
        self.load_data()
        self.add_behaviour(self.ReceiveRequestBehaviour())



