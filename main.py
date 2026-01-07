from Agents.Assistente import AssistenteAgent
from Agents.UserAgent import UserAgent
from Agents.FinanceiroAgent import FinanceiroAgent
import asyncio
import spade

async def main():
    assistente_jid = "assistente@localhost"
    user_jid = "user@localhost"
    financeiro_jid = "financeiro@localhost"
    assistente_agent = AssistenteAgent(assistente_jid, "NOPASSWORD")
    user_agent = UserAgent(user_jid, "NOPASSWORD")
    financeiro_agent = FinanceiroAgent(financeiro_jid, "NOPASSWORD")
    await assistente_agent.start(auto_register=True)
    await user_agent.start(auto_register=True)
    await financeiro_agent.start(auto_register=True)
    print("Assistente e UserAgent iniciados!")
    await asyncio.sleep(30)
    await assistente_agent.stop()
    await user_agent.stop()
    await financeiro_agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
