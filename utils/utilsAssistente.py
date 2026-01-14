import jsonpickle
from spade.message import Message
import json
import os
import re
from typing import Any, Dict, List, Optional, Union

# --- Helpers de Comunicação ---

async def reply(behaviour, user_jid: str, payload: dict):
    msg = Message(to=user_jid)
    msg.set_metadata("performative", "inform")
    msg.body = jsonpickle.encode(payload)
    await behaviour.send(msg)

async def ask_slot(behaviour, user_jid: str, slot: str):
    msg = Message(to=user_jid)
    msg.set_metadata("performative", "request")
    msg.body = jsonpickle.encode({"type": "ask", "slot": slot, "prompt": f"Por favor, indique: {slot}"})
    await behaviour.send(msg)

async def forward_request(behaviour, to_agent: str, payload: dict):
    msg = Message(to=to_agent)
    msg.set_metadata("performative", "request")
    msg.body = jsonpickle.encode(payload)
    await behaviour.send(msg)


# Cursos suportados (aliases). Mantém isto se ainda não tiverem carga dinâmica de cursos.
_CURSO_ALIASES = {
    "L-EI": {"L-EI", "LEI", "L EI", "L_EI", "L.EI"},
    "L-G": {"L-G", "LG", "L G", "L_G", "L.G"},
    "M-IA": {"M-IA", "MIA", "M IA", "M_IA", "M.IA"},
}


def _norm_token(s: str) -> str:
    s = (s or "").strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s


# --------- disciplinas dinâmicas (Database/disciplinas.json) ---------

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DISC_PATH = os.path.join(_BASE_DIR, "Database", "disciplinas.json")


def _load_disc_ids() -> set[str]:
    try:
        with open(_DISC_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        ids = set()
        if isinstance(data, dict):
            for _, lst in data.items():
                if not isinstance(lst, list):
                    continue
                for d in lst:
                    if isinstance(d, dict) and "id" in d:
                        ids.add(str(d["id"]).upper())
        return ids
    except Exception:
        return set()


_DISC_IDS = _load_disc_ids()


def _load_cursos() -> set[str]:
    """Carrega os cursos disponíveis do ficheiro disciplinas.json"""
    try:
        with open(_DISC_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return set(data.keys())
        return set()
    except Exception:
        return set()


_CURSOS_DISPONIVEIS = _load_cursos()


def validar_curso(curso: str) -> bool:
    """Verifica se o curso existe na BD"""
    if not curso:
        return False
    curso_norm = normalizar_curso(curso)
    return curso_norm in _CURSOS_DISPONIVEIS


def validar_disciplina(disciplina: str) -> bool:
    """Verifica se a disciplina existe na BD"""
    if not disciplina:
        return False
    return disciplina.upper() in _DISC_IDS


def get_cursos_disponiveis() -> List[str]:
    """Retorna lista de cursos disponíveis"""
    return list(_CURSOS_DISPONIVEIS)


def get_disciplinas_disponiveis() -> List[str]:
    """Retorna lista de disciplinas disponíveis"""
    return list(_DISC_IDS)


def get_disciplinas_curso(curso_id: str) -> List[str]:
    """Retorna lista de disciplinas de um curso específico"""
    try:
        with open(_DISC_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and curso_id in data:
            return [d["id"] for d in data[curso_id] if isinstance(d, dict) and "id" in d]
        return []
    except Exception:
        return []


def get_estudante_by_id(numero_aluno: str) -> Optional[Dict[str, Any]]:
    """Obtém os dados de um estudante pelo número"""
    if not numero_aluno:
        return None
    try:
        estudantes_path = os.path.join(_BASE_DIR, "Database", "estudantes.json")
        with open(estudantes_path, "r", encoding="utf-8") as f:
            estudantes = json.load(f)
        for est in estudantes:
            if str(est.get("id")) == str(numero_aluno):
                return est
        return None
    except Exception:
        return None


def extrair_disciplinas(texto: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9_]+", (texto or "").upper())
    return [t for t in tokens if t in _DISC_IDS]


# --------- normalizações ---------

def normalizar_curso(curso: Optional[str]) -> Optional[str]:
    if not curso:
        return None

    c = _norm_token(curso)

    for canon, aliases in _CURSO_ALIASES.items():
        if c == canon or c in aliases:
            return canon

    c2 = re.sub(r"[^A-Z0-9 ]+", "", c)
    for canon, aliases in _CURSO_ALIASES.items():
        canon2 = re.sub(r"[^A-Z0-9 ]+", "", _norm_token(canon))
        aliases2 = {re.sub(r"[^A-Z0-9 ]+", "", _norm_token(a)) for a in aliases}
        if c2 == canon2 or c2 in aliases2:
            return canon

    return c


def normalizar_disciplinas(valor: Union[str, List[str], None]) -> List[str]:
    if valor is None:
        return []

    if isinstance(valor, list):
        items = valor
    else:
        v = (valor or "").strip()
        if not v:
            return []
        if "," in v:
            items = [x.strip() for x in v.split(",") if x.strip()]
        else:
            items = [v]

    res: List[str] = []
    for x in items:
        t = _norm_token(x)
        if t:
            res.append(t)
    return res


# --------- intenção ---------

def extrair_intencao(texto: str) -> str:
    texto = (texto or "").lower()

    if re.search(r"\b(ola|olá|oi|bom dia|boa tarde|boas)\b", texto):
        return "saudacao"

    if re.search(r"\binscrev|inscri(?:c|ç)(?:a|ã)o\b", texto):
        return "inscricao"

    if re.search(r"\bhorar|horári|schedule\b", texto):
        return "horarios"

    if re.search(r"\b(paga|liquid|transfer)", texto):
        return "fazer_pagamento"
    
    if re.search(r"\b(saldo|divida|dívida|quanto devo|propina|finance)\b", texto):
        return "ver_saldo"

    if re.search(r"\b(ver|consultar|detalhes?)\b.*\b(regulamento|estatuto)\b.*\b(de|do|da)\b", texto):
        return "ver_regulamento"

    if re.search(r"\b(regulamentos?|estatutos?)\b.*\b(existem|dispon[ií]veis|lista|todos)\b", texto):
        return "listar_regulamentos"

    if re.search(r"\b(inscrever|aderir|aceitar|assinar|pedir)\b.*\b(regulamento|estatuto)\b", texto):
        return "inscrever_regulamento"

    if re.search(r"\b(remover|cancelar|anular|desistir|retirar)\b.*\b(regulamento|estatuto)\b", texto):
        return "remover_inscricao_regulamento"

    if re.search(r"\b(estou|já)\b.*\b(inscrito|registado|aceitei)\b.*\b(regulamento|estatuto)\b", texto):
        return "verificar_inscricao_regulamento"

    return "desconhecida"


def get_intencao(texto: str) -> str:
    return extrair_intencao(texto)


# --------- slots ---------

def extrair_slots(*args) -> Dict[str, Any]:
    """
    Compatibilidade:
      - extrair_slots(texto)
      - extrair_slots(intencao, texto)
    """
    if len(args) == 1:
        texto = args[0]
    elif len(args) >= 2:
        texto = args[1]
    else:
        texto = ""

    slots: Dict[str, Any] = {}
    texto = texto or ""

    # Número de aluno (ex.: 202301)
    match_numero = re.search(r"\b(\d{1,10})\b", texto)
    if match_numero:
        slots["numero_aluno"] = match_numero.group(1)

    # Curso (aliases)
    match_curso = re.search(r"\b(l[-_.\s]?ei|lei|l[-_.\s]?g|lg)\b", texto, re.IGNORECASE)
    if match_curso:
        slots["curso"] = normalizar_curso(match_curso.group(1))

    # Disciplinas (dinâmico pelo JSON)
    disc = extrair_disciplinas(texto)
    if disc:
        slots["disciplina"] = normalizar_disciplinas(disc)

    return slots

HELP_MESSAGE = """
Sou a Secretaria Online da Universidade.

AUTENTICACAO
  - login [numero_aluno]: entra na sessao com o teu numero de estudante.
  - logout: termina a sessao atual.

ACADEMICO
  - Inscrever em disciplina: inscreve-te numa unidade curricular do teu curso.
    Exemplo: inscrever em SO1
  - Ver horario: consulta horarios de disciplinas de um curso.
    Exemplo: ver horario de ALGEBRA

FINANCEIRO
  - Ver saldo: consulta o teu saldo e divida atual.
  - Pagar divida: efetua um pagamento para liquidar divida.
    Exemplo: pagar 50 euros

REGULAMENTOS E ESTATUTOS
  - Listar regulamentos: mostra todos os regulamentos e estatutos disponiveis.
  - Ver regulamento: consulta os detalhes de um regulamento especifico.
    Exemplo: ver regulamento trabalhador-estudante
  - Inscrever em regulamento: adere a um estatuto especial.
    Exemplo: inscrever no estatuto trabalhador-estudante
  - Remover inscricao de regulamento: remove o teu estatuto especial atual.
  - Verificar inscricao em regulamento: verifica se estas inscrito num estatuto.

NOTA: Algumas operacoes requerem login. Usa 'login [numero]' primeiro. Para saír pressione 'CTRL+C'.
"""
