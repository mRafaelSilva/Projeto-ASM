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
                    student_name = request['student_name']
                    classes = request['class_name']
                    response = self.agent.check_class_availability(student_name, classes)
                    
                    reply = msg.make_reply()
                    reply.set_metadata('performative', 'enroll_response')
                    reply.body = jsonpickle.encode(response)
                    await self.send(reply)
            else:
                print("No message received within timeout")

    def load_data(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        estudantes_path = os.path.join(base_dir, "Database", "estudantes.json")
        disciplinas_path = os.path.join(base_dir, "Database", "disciplinas.json")
        with open(estudantes_path, "r") as f:
            self.estudantes = json.load(f)
        with open(disciplinas_path, "r") as f:
            self.disciplinas = json.load(f)
    
    def save_data(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        estudantes_path = os.path.join(base_dir, "Database", "estudantes.json")
        disciplinas_path = os.path.join(base_dir, "Database", "disciplinas.json")
        with open(estudantes_path, "w") as f:
            json.dump(self.estudantes, f, indent=4)
        with open(disciplinas_path, "w") as f:
            json.dump(self.disciplinas, f, indent=4)

    def decode_message(self, message_body):
        return jsonpickle.decode(message_body)

    def check_class_availability(self, class_id, curso_id):
        for d in self.disciplinas[curso_id]:
            if d['id'] == class_id:
                if self.check_class_capacity(class_id, curso_id):
                    if not self.exceeds_max_credits(class_id):
                        return {"status": "enrolled", "class_id": class_id}
                    else:
                        return {"status": "max_credits_exceeded", "class_id": class_id}
                else:
                    return {"status": "class_full", "class_id": class_id}
        
        return {"status": "class_not_found", "class_id": class_id}
    
    def check_class_capacity(self, class_id, curso_id):
        vagas_totais = 0
        vagas_ocupadas = 0
        for d in self.disciplinas[curso_id]:
            if d['id'] == class_id:
                vagas_totais = d['vagas_totais']
                vagas_ocupadas = d['vagas_ocupadas']
                break

        capacidade = vagas_totais - vagas_ocupadas
        
        if capacidade > 0:
            return True
        
        return False
    
    def exceeds_max_credits(self, student_id):
        creds = 0
        disciplinas_curso = []
        curso = self.estudantes[student_id]['curso_id']

        for d in self.disciplinas[curso]:
            disciplinas_curso.append(d['id'])

        inscricoes_ativas = self.estudantes[student_id]['inscricoes_ativas']
        for inscricao in inscricoes_ativas:
                if inscricao in disciplinas_curso:
                    creds += self.disciplinas[curso][inscricao]['ects']
        
        if creds >= 30:
            return True
        
        return False
    
    def enroll_student_in_class(self, student, classes_and_schedule):
        for class_id, schedule in classes_and_schedule.items():
            curso = self.estudantes[student]['curso_id']
            for d in self.disciplinas[curso]:
                if d['id'] == class_id:
                    d['vagas_ocupadas'] += 1
                    self.estudantes[student]['inscricoes_ativas'].append(class_id)
        self.save_data()



    async def setup(self):
        print("Academic Agent started")
        self.estudantes = {}
        self.disciplinas = {}
        self.load_data()
        self.add_behaviour(self.ReceiveRequestBehaviour())
        
    


