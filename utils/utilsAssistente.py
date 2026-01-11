import json
import os
import re
from typing import Any, Dict, List, Optional, Union


# Cursos suportados (aliases). Mantém isto se ainda não tiverem carga dinâmica de cursos.
_CURSO_ALIASES = {
    "L-EI": {"L-EI", "LEI", "L EI", "L_EI", "L.EI"},
    "L-G": {"L-G", "LG", "L G", "L_G", "L.G"},
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

    if re.search(r"\binscrev|inscri(?:c|ç)(?:a|ã)o\b", texto):
        return "inscricao"

    if re.search(r"\bhorar|horári|schedule\b", texto):
        return "horarios"

    if re.search(r"\bpaga|propina|saldo|divida|dívida|finance\b", texto):
        return "pagamentos"

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
