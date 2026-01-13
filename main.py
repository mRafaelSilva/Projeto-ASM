from Agents.Assistente import AssistenteAgent
from Agents.UserAgent import UserAgent
from Agents.FinanceiroAgent import FinanceiroAgent
from Agents.HorariosAgent import HorariosAgent
from Agents.RegulamentosAgent import RegulamentosAgent
from Agents.AcademicoAgent import AcademicoAgent
import asyncio


async def main():
    assistente_jid = "assistente@localhost"
    user_jid = "user@localhost"
    financeiro_jid = "financeiro@localhost"
    horarios_jid = "horarios@localhost"
    regulamentos_jid = "regulamentos@localhost"
    academico_jid = "academico@localhost"
    
    password = "1234"

    assistente_agent = AssistenteAgent(assistente_jid, password)
    user_agent = UserAgent(user_jid, password)
    financeiro_agent = FinanceiroAgent(financeiro_jid, password)
    horarios_agent = HorariosAgent(horarios_jid, password)
    regulamentos_agent = RegulamentosAgent(regulamentos_jid, password)
    academico_agent = AcademicoAgent(academico_jid, password)

    print("A iniciar agentes! (Ctrl+C para terminar)")
    await assistente_agent.start(auto_register=True)
    await financeiro_agent.start(auto_register=True)
    await horarios_agent.start(auto_register=True)
    await regulamentos_agent.start(auto_register=True)
    await academico_agent.start(auto_register=True)
    await user_agent.start(auto_register=True)

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nA terminar agentes...")
    finally:
        await asyncio.gather(
            assistente_agent.stop(),
            user_agent.stop(),
            financeiro_agent.stop(),
            horarios_agent.stop(),
            regulamentos_agent.stop(),
            academico_agent.stop(),
            return_exceptions=True,
        )
        # dar tempo para fechar sockets/tarefas internas sem ruido
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
