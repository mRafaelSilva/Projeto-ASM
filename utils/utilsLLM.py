import ollama
import json
import os

MODELO = "llama3.2"
TIMEOUT = 30  # segundos
TEMPERATURE = 0.3  # 0.0 = determinístico, 1.0 = criativo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "Database")

def _carregar_validacoes():
    info = {"cursos": [], "disciplinas": []}
    
    # Carregar Cursos
    try:
        with open(os.path.join(DB_DIR, "cursos.json"), "r", encoding="utf-8") as f:
            dados = json.load(f)
            info["cursos"] = [c["id"] for c in dados]
    except: pass

    # Carregar Disciplinas
    try:
        with open(os.path.join(DB_DIR, "disciplinas.json"), "r", encoding="utf-8") as f:
            dados = json.load(f)
            todas_discs = []
            for curso, lista in dados.items():
                for disc in lista:
                    todas_discs.append(disc["id"])
            info["disciplinas"] = list(set(todas_discs))
    except: pass
    
    return info

CONTEXTO_VALIDO = _carregar_validacoes()

def interpretar_comando(texto_usuario):
    print(f"\n[LLM] A analisar: '{texto_usuario}'...")

    prompt_sistema = f"""
    És um assistente académico rigoroso. Analisa o texto e extrai dados estruturados.
    
    CONTEXTO DE DADOS VÁLIDOS (Usa apenas estes):
    - Cursos Válidos: {json.dumps(CONTEXTO_VALIDO['cursos'])}
    - Disciplinas Válidas: {json.dumps(CONTEXTO_VALIDO['disciplinas'])}

    REGRAS:
    1. Intenções: 'inscricao', 'horarios', 'fazer_pagamento', 'ver_saldo', 'saudacao', 'ajuda', 
       'listar_regulamentos', 'ver_regulamento', 'inscrever_regulamento', 'verificar_inscricao_regulamento'.
       - 'inscricao' (inscrever, matricular)
       - 'horarios' (ver horário, aulas, quando é, sala)
       - 'fazer_pagamento' (pagar, liquidar, transferir)
       - 'ver_saldo' (quanto devo, divida, saldo, propinas)
       - 'saudacao' (ola, bom dia, boas, oi)
       - 'ajuda' (o que fazes, help, ajuda)
       - 'listar_regulamentos' (quais regulamentos, listar regras, ver normas)
       - 'ver_regulamento' (ler regulamento X, detalhes do regulamento Y)
       - 'inscrever_regulamento' (aceitar regulamento, assinar regulamento, inscrever reg)
       - 'verificar_inscricao_regulamento' (estou inscrito no regulamento?, já aceitei o regulamento?)
    2. Caso o texto não seja reconhecido, devolve uma intencao 'desconhecida'.
    3. SLOTS (Campos):
       - 'curso': Tenta mapear o texto para um dos Cursos Válidos. Se não existir, null.
       - 'disciplina': Tenta mapear o texto para uma das Disciplinas Válidas. 
         Exemplo: Se user diz "sistemas operativos", e existe "SO1", devolve "SO1". 
         Se o user diz "Batatas" e não está na lista, devolve null.
       - 'numero_aluno': Extrai apenas números que identifiquem o aluno. NOTA: Se a intenção for 'fazer_pagamento', números isolados (ex: 200, 50.5) são 'valor', NÃO 'numero_aluno'.
       - 'valor': Extrai montante (float). Prioritário em 'fazer_pagamento'.
       - 'regulamento': Nome do regulamento mencionado (ex: "avaliação", "exames", "prescrições").
 
    Responde APENAS JSON neste formato:
    {{
        "intencao": "...",
        "slots": {{ "curso": "...", "disciplina": "...", "numero_aluno": "...", "valor": "...", "regulamento": "..." }}
    }}
    """

    try:
        response = ollama.chat(
            model=MODELO, 
            messages=[
                {'role': 'system', 'content': prompt_sistema},
                {'role': 'user', 'content': texto_usuario},
            ], 
            format='json',
            options={
                'temperature': TEMPERATURE,
                'num_predict': 200,
            },
            keep_alive=TIMEOUT
        )

        dados = json.loads(response['message']['content'])

        if "intencao" not in dados: dados["intencao"] = "desconhecida"
        if "slots" not in dados: dados["slots"] = {}
        
        dados["slots"] = {k: v for k, v in dados["slots"].items() if v}
        
        return dados

    except Exception as e:
        print(f"[Erro LLM]: {e}")
        return {"intencao": "desconhecida", "slots": {}}