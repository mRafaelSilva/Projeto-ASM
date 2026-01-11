from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import jsonpickle
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.template import Template


def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    # intervalos [start, end)
    return a_start < b_end and b_start < a_end


class HorariosAgent(Agent):
    """
    Agente Horários
      - Carrega Database/disciplinas.json
      - Verifica conflitos (overlap, capacidade, inputs inválidos)
      - Pode encontrar combinação viável (backtracking simples)

    Contrato (preferência jsonpickle; fallback JSON):
      REQUEST:
        {
          "acao": "check_schedule" | "find_feasible" | "suggest_alternatives",
          "curso": "L-EI",
          "disciplinas": ["SO1","PF",...],
          "escolhas": {"SO1":"T1", ...},       # opcional
          "to_user": "user@localhost"         # opcional (para encaminhamento no Assistente)
        }

      INFORM/PROPOSE/REFUSE/FAILURE:
        {
          "ok": bool,
          "acao": "...",
          "curso": "...",
          "disciplinas": [...],
          "escolhas": {...},
          "conflitos": [...],
          "detalhes": [...],                   # no check_schedule
          "sugestao": {...},                   # opcional (no check_schedule quando falha)
          "to_user": "..."                     # se veio no request
        }
    """

    def __init__(self, jid: str, password: str):
        super().__init__(jid, password)
        self.data_path: str = ""
        self.disciplinas_por_curso: Dict[str, List[dict]] = {}

    async def setup(self):
        print(f"[Horarios] {str(self.jid)} ativo.")

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = os.path.join(base_dir, "Database", "disciplinas.json")
        self._load_data()

        t_req = Template()
        t_req.set_metadata("performative", "request")
        self.add_behaviour(self.HandleRequestsBehaviour(), t_req)

        print("[Horarios] ready")

    # -------------------- DATA --------------------

    def _load_data(self) -> None:
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                self.disciplinas_por_curso = json.load(f)
        except Exception as e:
            print(f"[Horarios] Erro ao carregar disciplinas.json: {e}")
            self.disciplinas_por_curso = {}

    def _safe_decode_body(self, body: Optional[str]) -> dict:
        if not body:
            return {}

        # 1) jsonpickle
        try:
            decoded = jsonpickle.decode(body)
            if isinstance(decoded, dict):
                return decoded
        except Exception:
            pass

        # 2) json
        try:
            decoded = json.loads(body)
            return decoded if isinstance(decoded, dict) else {}
        except Exception:
            return {}

    def _get_disciplina(self, curso: str, disc_id: str) -> Optional[dict]:
        for d in self.disciplinas_por_curso.get(curso, []):
            if d.get("id") == disc_id:
                return d
        return None

    def _get_turno(self, disciplina_obj: dict, turno_id: str) -> Optional[dict]:
        for t in disciplina_obj.get("turnos", []):
            if t.get("id") == turno_id:
                return t
        return None

    # -------------------- CORE LOGIC --------------------

    def _build_schedule_items(self, curso: str, escolhas: Dict[str, str]) -> List[dict]:
        items: List[dict] = []

        for disc_id, turno_id in escolhas.items():
            disc = self._get_disciplina(curso, disc_id)
            if not disc:
                items.append({"disciplina": disc_id, "turno": turno_id, "erro": "disciplina_inexistente"})
                continue

            turno = self._get_turno(disc, turno_id)
            if not turno:
                items.append({"disciplina": disc_id, "turno": turno_id, "erro": "turno_inexistente"})
                continue

            try:
                ini = _hhmm_to_minutes(turno.get("inicio"))
                fim = _hhmm_to_minutes(turno.get("fim"))
            except Exception:
                items.append({"disciplina": disc_id, "turno": turno_id, "erro": "hora_invalida"})
                continue

            items.append(
                {
                    "disciplina": disc_id,
                    "turno": turno_id,
                    "dia": turno.get("dia"),
                    "inicio_min": ini,
                    "fim_min": fim,
                    "inicio": turno.get("inicio"),
                    "fim": turno.get("fim"),
                    "sala": turno.get("sala"),
                    "vagas_totais": turno.get("vagas_totais", 0),
                    "vagas_ocupadas": turno.get("vagas_ocupadas", 0),
                }
            )

        return items

    def _check_capacity(self, item: dict) -> bool:
        vt = int(item.get("vagas_totais", 0) or 0)
        vo = int(item.get("vagas_ocupadas", 0) or 0)
        # vt<=0 => sem limite definido
        return (vt <= 0) or (vo < vt)

    def _detect_conflicts(self, schedule_items: List[dict]) -> List[dict]:
        conflitos: List[dict] = []

        # inválidos
        for it in schedule_items:
            if it.get("erro"):
                conflitos.append(
                    {
                        "tipo": "invalid",
                        "disciplina": it.get("disciplina"),
                        "turno": it.get("turno"),
                        "desc": it.get("erro"),
                    }
                )

        # capacidade
        for it in schedule_items:
            if it.get("erro"):
                continue
            if not self._check_capacity(it):
                conflitos.append(
                    {
                        "tipo": "capacity",
                        "disciplina": it["disciplina"],
                        "turno": it["turno"],
                        "dia": it.get("dia"),
                        "desc": "sem_vagas",
                    }
                )

        # overlaps (mesmo dia)
        valids = [it for it in schedule_items if not it.get("erro")]
        for i in range(len(valids)):
            for j in range(i + 1, len(valids)):
                a, b = valids[i], valids[j]
                if a.get("dia") != b.get("dia"):
                    continue
                if _overlap(a["inicio_min"], a["fim_min"], b["inicio_min"], b["fim_min"]):
                    conflitos.append(
                        {
                            "tipo": "overlap",
                            "a": {
                                "disciplina": a["disciplina"],
                                "turno": a["turno"],
                                "inicio": a["inicio"],
                                "fim": a["fim"],
                                "dia": a.get("dia"),
                            },
                            "b": {
                                "disciplina": b["disciplina"],
                                "turno": b["turno"],
                                "inicio": b["inicio"],
                                "fim": b["fim"],
                                "dia": b.get("dia"),
                            },
                            "desc": "conflito_horario",
                        }
                    )

        return conflitos

    def _default_choice_per_disciplina(self, curso: str, disciplinas: List[str]) -> Dict[str, str]:
        escolhas: Dict[str, str] = {}

        for disc_id in disciplinas:
            disc = self._get_disciplina(curso, disc_id)
            if not disc:
                escolhas[disc_id] = "T?"
                continue

            turnos = disc.get("turnos", [])
            if not turnos:
                escolhas[disc_id] = "T?"
                continue

            chosen = None
            for t in turnos:
                vt = t.get("vagas_totais", 0)
                vo = t.get("vagas_ocupadas", 0)
                if vt <= 0 or vo < vt:
                    chosen = t.get("id")
                    break

            escolhas[disc_id] = chosen if chosen else (turnos[0].get("id") or "T?")
        return escolhas

    def _find_feasible_combination(
        self, curso: str, disciplinas: List[str]
    ) -> Tuple[bool, Dict[str, str], List[dict]]:
        """
        Backtracking simples:
          - tenta turnos com vagas primeiro
          - valida incrementalmente (overlap/capacity/invalid)
        Retorna: (ok, escolhas, conflitos)
        """
        options: List[Tuple[str, List[str]]] = []

        for disc_id in disciplinas:
            disc = self._get_disciplina(curso, disc_id)
            if not disc:
                options.append((disc_id, ["T?"]))
                continue

            turnos = disc.get("turnos", [])
            if not turnos:
                options.append((disc_id, ["T?"]))
                continue

            def score(t: dict) -> int:
                vt = t.get("vagas_totais", 0)
                vo = t.get("vagas_ocupadas", 0)
                has_space = (vt <= 0) or (vo < vt)
                return 0 if has_space else 1

            turnos_sorted = sorted(turnos, key=score)
            options.append((disc_id, [t.get("id") for t in turnos_sorted if t.get("id")]))

        escolhas: Dict[str, str] = {}

        def is_partial_ok() -> bool:
            items = self._build_schedule_items(curso, escolhas)
            conflitos = self._detect_conflicts(items)
            hard = [c for c in conflitos if c["tipo"] in ("invalid", "capacity", "overlap")]
            return len(hard) == 0

        def backtrack(idx: int) -> bool:
            if idx == len(options):
                return True

            disc_id, turnos_list = options[idx]
            for turno_id in turnos_list:
                escolhas[disc_id] = turno_id
                if is_partial_ok() and backtrack(idx + 1):
                    return True
                escolhas.pop(disc_id, None)

            return False

        ok = backtrack(0)
        items = self._build_schedule_items(curso, escolhas)
        conflitos = self._detect_conflicts(items)
        hard = [c for c in conflitos if c["tipo"] in ("invalid", "capacity", "overlap")]
        return (ok and len(hard) == 0), escolhas, conflitos

    # -------------------- BEHAVIOUR --------------------

    class HandleRequestsBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if not msg:
                return

            req = self.agent._safe_decode_body(msg.body)
            acao = req.get("acao")
            curso = req.get("curso")
            disciplinas = req.get("disciplinas", [])
            escolhas = req.get("escolhas")
            to_user = req.get("to_user")

            # ✅ responder SEMPRE ao JID "bare" do Assistente (evita problemas com resource)
            sender_bare = str(msg.sender).split("/")[0]

            from spade.message import Message  # import local para evitar mexer no topo
            reply = Message(to=sender_bare)

            # manter thread para correlação (útil quando houver várias conversas)
            if getattr(msg, "thread", None):
                reply.thread = msg.thread

            reply.set_metadata("performative", "inform")

            # validações mínimas
            if not acao or not curso or not isinstance(disciplinas, list) or len(disciplinas) == 0:
                reply.set_metadata("performative", "failure")
                payload = {
                    "ok": False,
                    "erro": "campos_invalidos",
                    "esperado": {
                        "acao": "check_schedule|find_feasible|suggest_alternatives",
                        "curso": "L-EI",
                        "disciplinas": ["SO1", "PF"],
                        "escolhas": {"SO1": "T1"},
                        "to_user": "user@localhost",
                    },
                }
                if to_user:
                    payload["to_user"] = to_user
                reply.body = jsonpickle.encode(payload)
                await self.send(reply)
                return

            if curso not in self.agent.disciplinas_por_curso:
                reply.set_metadata("performative", "refuse")
                payload = {"ok": False, "erro": "curso_desconhecido", "curso": curso}
                if to_user:
                    payload["to_user"] = to_user
                reply.body = jsonpickle.encode(payload)
                await self.send(reply)
                return

            # check_schedule
            if acao == "check_schedule":
                if not isinstance(escolhas, dict) or not escolhas:
                    escolhas = self.agent._default_choice_per_disciplina(curso, disciplinas)

                items = self.agent._build_schedule_items(curso, escolhas)
                conflitos = self.agent._detect_conflicts(items)
                hard = [c for c in conflitos if c["tipo"] in ("invalid", "capacity", "overlap")]
                ok = len(hard) == 0

                payload: Dict[str, Any] = {
                    "ok": ok,
                    "acao": "check_schedule",
                    "curso": curso,
                    "disciplinas": disciplinas,
                    "escolhas": escolhas,
                    "conflitos": conflitos,
                    "detalhes": items,
                }

                if not ok:
                    ok2, best, conflitos2 = self.agent._find_feasible_combination(curso, disciplinas)
                    payload["sugestao"] = {"ok": ok2, "escolhas": best, "conflitos": conflitos2}

                if to_user:
                    payload["to_user"] = to_user

                reply.body = jsonpickle.encode(payload)
                await self.send(reply)
                return

            # find_feasible
            if acao == "find_feasible":
                ok, best, conflitos = self.agent._find_feasible_combination(curso, disciplinas)
                payload = {
                    "ok": ok,
                    "acao": "find_feasible",
                    "curso": curso,
                    "disciplinas": disciplinas,
                    "escolhas": best,
                    "conflitos": conflitos,
                }
                if to_user:
                    payload["to_user"] = to_user
                reply.body = jsonpickle.encode(payload)
                await self.send(reply)
                return

            # suggest_alternatives
            if acao == "suggest_alternatives":
                ok, best, conflitos = self.agent._find_feasible_combination(curso, disciplinas)
                reply.set_metadata("performative", "propose" if ok else "inform")
                payload = {
                    "ok": ok,
                    "acao": "suggest_alternatives",
                    "curso": curso,
                    "disciplinas": disciplinas,
                    "escolhas": best,
                    "conflitos": conflitos,
                }
                if to_user:
                    payload["to_user"] = to_user
                reply.body = jsonpickle.encode(payload)
                await self.send(reply)
                return

            # ação desconhecida
            reply.set_metadata("performative", "not-understood")
            payload = {
                "ok": False,
                "erro": "acao_desconhecida",
                "acao_recebida": acao,
                "acoes_suportadas": ["check_schedule", "find_feasible", "suggest_alternatives"],
            }
            if to_user:
                payload["to_user"] = to_user
            reply.body = jsonpickle.encode(payload)
            await self.send(reply)

