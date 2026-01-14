import ollama
import json
import os

MODELO = "llama3.2"
TIMEOUT = 30  # segundos
TEMPERATURE = 0.2  # 0.0 = determinístico, 1.0 = criativo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "..", "Database")

# Aliases de cursos para normalização
CURSO_ALIASES = {
    "LG": "L-G", "L G": "L-G", "L_G": "L-G", "L.G": "L-G",
    "LEI": "L-EI", "L EI": "L-EI", "L_EI": "L-EI", "L.EI": "L-EI",
    "MIA": "M-IA", "M IA": "M-IA", "M_IA": "M-IA", "M.IA": "M-IA",
}

def _carregar_validacoes():
    info = {"cursos": [], "disciplinas": [], "regulamentos": [], "curso_aliases": CURSO_ALIASES}
    
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

    # Carregar Regulamentos
    try:
        with open(os.path.join(DB_DIR, "regulamentos.json"), "r", encoding="utf-8") as f:
            dados = json.load(f)
            info["regulamentos"] = list(dados.keys())
    except: pass
    
    return info

CONTEXTO_VALIDO = _carregar_validacoes()

def interpretar_comando(texto_usuario):
    print(f"\n[LLM] A analisar: '{texto_usuario}'...")

    prompt_sistema = f"""
Es um assistente de secretaria academica universitaria.
A tua tarefa e interpretar linguagem natural do utilizador e extrair a intencao e os dados relevantes.
Foca-te em compreender o que o utilizador quer fazer, mesmo que escreva de forma informal ou com abreviaturas.

DADOS VALIDOS (usa APENAS estes valores nos slots):
- cursos: {json.dumps(CONTEXTO_VALIDO['cursos'])}
- aliases de cursos (normaliza para o formato correto): {json.dumps(CONTEXTO_VALIDO['curso_aliases'])}
- disciplinas: {json.dumps(CONTEXTO_VALIDO['disciplinas'])}
- regulamentos: {json.dumps(CONTEXTO_VALIDO['regulamentos'])}

INTENCOES DISPONIVEIS:
- saudacao: cumprimento simples (ola, bom dia, oi)
- ajuda: pedido de ajuda ou informacao sobre o sistema (o que fazes, help)
- inscricao: matricula/inscricao em disciplina (inscrever, matricular)
- horarios: consulta de horarios, aulas, salas (ver horario, aulas, quando e, sala)
- fazer_pagamento: pagar valores/divida (pagar, liquidar, transferir)
- ver_saldo: consultar divida/saldo/propinas (quanto devo, divida, saldo)
- listar_regulamentos: ver lista de regulamentos (quais regulamentos, listar regras)
- ver_regulamento: consultar detalhes de um regulamento (ler regulamento X, detalhes do regulamento Y)
- inscrever_regulamento: aderir a um estatuto/regulamento (aceitar regulamento, assinar)
- remover_inscricao_regulamento: remover/cancelar estatuto (remover regulamento, cancelar estatuto)
- verificar_inscricao_regulamento: verificar se esta inscrito (estou inscrito no regulamento?, ja aceitei?)
- desconhecida: quando nao conseguires identificar a intencao

REGRAS DE DECISAO (aplica por ordem, usa a PRIMEIRA que encaixar):
1. Se houver valor monetario + verbo pagar -> fazer_pagamento
2. Se mencionar saldo, divida ou propinas -> ver_saldo
3. Se mencionar horario, aula, sala ou data -> horarios
4. Se mencionar inscrever/matricular curso ou disciplina -> inscricao
5. Se mencionar regulamento ou estatuto:
   a) verbo aceitar/aderir/assinar -> inscrever_regulamento
   b) verbo remover/cancelar/desistir -> remover_inscricao_regulamento
   c) pergunta se ja esta inscrito/aceitou -> verificar_inscricao_regulamento
   d) pedido de detalhes de um regulamento -> ver_regulamento
   e) pedido de lista de regulamentos -> listar_regulamentos
6. Se apenas cumprimentar -> saudacao
7. Se pedir ajuda generica -> ajuda
8. Caso contrario -> desconhecida

SLOTS (Campos):
- curso: Tenta mapear o texto para um dos Cursos Validos usando aliases. Exemplo: LG -> L-G, LEI -> L-EI. Se nao existir, null.
- disciplina: Tenta mapear o texto para uma das Disciplinas Validas em MAIUSCULAS.
  Exemplo: Se user diz "sistemas operativos" e existe "SO1", devolve "SO1".
  Se user diz "economia" e existe "ECON1", devolve "ECON1".
  Se input tiver algo correspondente a uma SIGLA ou alias de disciplina, devolve a disciplina da lista correspondente.
  Se nenhum dos casos acima se aplicar, devolve o texto original.
  Exemplo: "inscrever em BATATAS" -> disciplina: BATATAS
  Exemplo: "ver horario disciplina soueu curso:LEI" -> disciplina: soueu, curso: L-EI
  Exemplo: "ver horario disciplina:arroz curso:LG" -> disciplina: arroz, curso: L-G
  Tens de descobrir se for este o caso, nao te guies APENAS pelos exemplos
- numero_aluno: Extrai apenas numeros que identifiquem o aluno. NOTA: Se intencao = fazer_pagamento, numeros sao SEMPRE valor, NAO numero_aluno.
- valor: Extrai montante (float). Prioritario em fazer_pagamento.
- regulamento: Nome do regulamento mencionado com hifens (ex: trabalhador-estudante, atleta-alta-competicao).

IMPORTANTE: Identifica SEMPRE a intencao baseada no que o utilizador QUER fazer, mesmo que os slots nao existam nas listas validas. Exemplos:
- "inscrever em BATATAS" -> intencao: inscricao, disciplina: BATATAS
- "ver horario de XPTO" -> intencao: horarios, disciplina: XPTO
- "ver horario disciplina "tomates" curso LEI" -> intencao: horarios, curso: L-EI, disciplina: tomates

REGRA FINAL (OBRIGATÓRIA):
A intenção devolvida TEM de ser EXATAMENTE UMA destas:
'inscricao', 'horarios', 'fazer_pagamento', 'ver_saldo', 'saudacao', 'ajuda',
'listar_regulamentos', 'ver_regulamento', 'inscrever_regulamento',
'remover_inscricao_regulamento', 'verificar_inscricao_regulamento', 'desconhecida'.
Se nenhuma regra acima se aplicar de forma clara, usa SEMPRE 'desconhecida'.

FORMATO JSON OBRIGATORIO:
{{
    "intencao": "...",
    "slots": {{ "curso": "...", "disciplina": "...", "numero_aluno": "...", "valor": "...", "regulamento": "..." }}
}}"""

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