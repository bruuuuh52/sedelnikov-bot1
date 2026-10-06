import asyncio
from bot.database import init_db
from bot.config_loader import load_config

async def test():
    await init_db()
    config = load_config()
    print('Config loaded OK')
    print('Vacancy:', config.vacancy_title)
    print('Description:', config.vacancy_description[:200])
    print('---')
    print('Final message:', config.final_message[:300])

asyncio.run(test())