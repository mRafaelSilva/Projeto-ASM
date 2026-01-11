from Agents.Assistente import AssistenteAgent
from Agents.UserAgent import UserAgent
from Agents.FinanceiroAgent import FinanceiroAgent
from Agents.HorariosAgent import HorariosAgent
import asyncio


async def main():
    assistente_jid = "assistente@localhost"
    user_jid = "user@localhost"
    financeiro_jid = "financeiro@localhost"
    horarios_jid = "horarios@localhost"
    password = "1234"

    assistente_agent = AssistenteAgent(assistente_jid, password)
    user_agent = UserAgent(user_jid, password)
    financeiro_agent = FinanceiroAgent(financeiro_jid, password)
    horarios_agent = HorariosAgent(horarios_jid, password)

    await assistente_agent.start(auto_register=False)
    await user_agent.start(auto_register=False)
    await financeiro_agent.start(auto_register=False)
    await horarios_agent.start(auto_register=False)

    print("Agentes iniciados! (Ctrl+C para terminar)")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nA terminar agentes...")
    finally:
        # shield para reduzir probabilidade de interrupção a meio do shutdown
        await asyncio.gather(
            asyncio.shield(assistente_agent.stop()),
            asyncio.shield(user_agent.stop()),
            asyncio.shield(financeiro_agent.stop()),
            asyncio.shield(horarios_agent.stop()),
            return_exceptions=True,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
