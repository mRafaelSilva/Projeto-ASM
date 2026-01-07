# FinanceiroAgent.py
from spade import agent
import spade.behaviour as behaviour
from spade.template import Template

from datetime import datetime
import jsonpickle
import json
import os


class FinanceiroAgent(agent.Agent):
    """
    Agente Financeiro (versão simplificada):
      - Só faz verificação de dívida via QUERY_IF:
            QUERY_IF(has_debt, aluno) -> INFORM(debt=yes/no, valor=..., saldo=...)
      - REQUEST é usado apenas para operações financeiras ativas, ex. liquidar dívida:
            REQUEST(pay_debt, aluno, valor) -> INFORM(paid=true/false, saldo_novo=...)
    """

    async def setup(self):
        print(f"Financeiro {str(self.jid)} ativo.")

        # Caminho do ficheiro financeiro.json
        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.data_path = os.path.join(base_dir, "Database", "financeiro.json")

        # Carrega dados financeiros
        self._load_data()

        # Templates para separar mensagens por performative
        t_query = Template()
        t_query.set_metadata("performative", "query-if")
        self.add_behaviour(self.CheckDebtBehaviour(), t_query)

        t_req = Template()
        t_req.set_metadata("performative", "request")
        self.add_behaviour(self.PayDebtBehaviour(), t_req)

    # ---------- persistência ----------
    def _load_data(self):
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception as e:
            print(f"[Financeiro] Erro ao carregar dados: {e}")
            dados = []

        # Indexa por estudante_id (mantém o tipo do JSON; normalmente int)
        self.financeiro_by_id = {rec.get("estudante_id"): rec for rec in dados if rec.get("estudante_id")}

    def _save_data(self):
        """Grava de volta o dicionário para o JSON (persistência simples)."""
        try:
            dados = list(self.financeiro_by_id.values())
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Financeiro] Erro ao guardar dados: {e}")

    # ---------- helpers ----------
    def _safe_decode_body(self, msg):
        try:
            decoded = jsonpickle.decode(msg.body)
            return decoded if isinstance(decoded, dict) else {"value": decoded}
        except Exception:
            return {}

    def _normalize_student_id(self, estudante_id):
        """
        Se o JSON usa int (como no teu exemplo), isto evita bugs quando chega "202301" como string.
        """
        try:
            return int(estudante_id)
        except (TypeError, ValueError):
            return None

    def _get_fin_record(self, estudante_id):
        return self.financeiro_by_id.get(estudante_id)

    def _compute_debt_info(self, rec):
        saldo = rec.get("saldo", 0)
        isento = bool(rec.get("isento_taxas", False))

        tem_divida = (saldo < 0) and (not isento)
        valor_divida = abs(saldo) if saldo < 0 else 0

        return {
            "tem_divida": tem_divida,
            "valor_divida": valor_divida,
            "saldo": saldo,
            "isento_taxas": isento,
        }

    # ---------- behaviours ----------
    class CheckDebtBehaviour(behaviour.CyclicBehaviour):
        """
        Recebe:
          performative = "query-if"
          body: {"acao":"has_debt", "estudante_id": ...}

        Responde:
          performative = "inform"
          body: {"debt":"yes/no/unknown", "valor":..., "saldo":..., "isento_taxas":...}
        """

        async def run(self):
            msg = await self.receive(timeout=10)
            if not msg:
                return

            conteudo = self.agent._safe_decode_body(msg)
            acao = conteudo.get("acao", "has_debt")
            estudante_id = self.agent._normalize_student_id(conteudo.get("estudante_id"))

            reply = msg.make_reply()
            reply.set_metadata("performative", "inform")

            if acao != "has_debt":
                reply.body = jsonpickle.encode({"error": "unknown_action", "acao": acao})
                await self.send(reply)
                return

            if estudante_id is None:
                reply.body = jsonpickle.encode({"error": "missing_or_invalid_estudante_id"})
                await self.send(reply)
                return

            rec = self.agent._get_fin_record(estudante_id)
            if not rec:
                reply.body = jsonpickle.encode({
                    "debt": "unknown",
                    "motivo": "estudante_nao_encontrado",
                    "estudante_id": estudante_id
                })
                await self.send(reply)
                return

            info = self.agent._compute_debt_info(rec)
            reply.body = jsonpickle.encode({
                "debt": "yes" if info["tem_divida"] else "no",
                "valor": info["valor_divida"],
                "saldo": info["saldo"],
                "isento_taxas": info["isento_taxas"],
            })
            await self.send(reply)

    class PayDebtBehaviour(behaviour.CyclicBehaviour):
        """
        Recebe:
          performative = "request"
          body: {"acao":"pay_debt", "estudante_id":..., "valor": ...}

        Responde:
          - "inform" se processou
          - "failure" se campos inválidos
          - "refuse" se aluno não existe
        """

        async def run(self):
            msg = await self.receive(timeout=10)
            if not msg:
                return

            conteudo = self.agent._safe_decode_body(msg)
            acao = conteudo.get("acao")

            # Só tratamos requests de pagamento aqui
            if acao != "pay_debt":
                reply = msg.make_reply()
                reply.set_metadata("performative", "failure")
                reply.body = jsonpickle.encode({
                    "error": "unexpected_request_action",
                    "expected": "pay_debt",
                    "got": acao
                })
                await self.send(reply)
                return

            estudante_id = self.agent._normalize_student_id(conteudo.get("estudante_id"))
            valor = conteudo.get("valor")

            if estudante_id is None or valor is None:
                reply = msg.make_reply()
                reply.set_metadata("performative", "failure")
                reply.body = jsonpickle.encode({
                    "error": "missing_fields",
                    "required": ["acao", "estudante_id", "valor"]
                })
                await self.send(reply)
                return

            # Validar valor
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                reply = msg.make_reply()
                reply.set_metadata("performative", "failure")
                reply.body = jsonpickle.encode({"error": "invalid_valor"})
                await self.send(reply)
                return

            if valor <= 0:
                reply = msg.make_reply()
                reply.set_metadata("performative", "failure")
                reply.body = jsonpickle.encode({"error": "valor_must_be_positive"})
                await self.send(reply)
                return

            rec = self.agent._get_fin_record(estudante_id)
            if not rec:
                reply = msg.make_reply()
                reply.set_metadata("performative", "refuse")
                reply.body = jsonpickle.encode({
                    "motivo": "estudante_nao_encontrado",
                    "estudante_id": estudante_id
                })
                await self.send(reply)
                return

            info_before = self.agent._compute_debt_info(rec)

            # Se está isento, não faz sentido "pagar dívida" por bloqueio (mas podes permitir por simulação)
            if info_before["isento_taxas"]:
                reply = msg.make_reply()
                reply.set_metadata("performative", "inform")
                reply.body = jsonpickle.encode({
                    "paid": False,
                    "motivo": "isento_taxas",
                    "saldo_atual": info_before["saldo"]
                })
                await self.send(reply)
                return

            # Atualiza saldo: pagar dívida aumenta o saldo (ex.: -250 + 100 = -150)
            saldo_atual = float(rec.get("saldo", 0))
            saldo_novo = saldo_atual + valor
            rec["saldo"] = round(saldo_novo, 2)

            # (Opcional) guardar no histórico
            timestamp = datetime.now().isoformat(timespec="seconds")

            hist = rec.get("historico_pagamentos")
            novo_registo = {
                "data": timestamp,
                "valor": valor,
                "tipo": "Pagamento dívida (simulado)"
            }

            if isinstance(hist, list):
                hist.append(novo_registo)
            else:
                rec["historico_pagamentos"] = [novo_registo]

            # Persistir
            self.agent._save_data()

            info_after = self.agent._compute_debt_info(rec)

            reply = msg.make_reply()
            reply.set_metadata("performative", "inform")
            reply.body = jsonpickle.encode({
                "paid": True,
                "saldo_novo": rec["saldo"],
                "debt_cleared": (not info_after["tem_divida"]),
                "debt_valor_restante": info_after["valor_divida"],
            })
            await self.send(reply)
