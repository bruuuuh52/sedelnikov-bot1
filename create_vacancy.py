#!/usr/bin/env python3
# ============================================================
# СКРИПТ ДЛЯ СОЗДАНИЯ ВАКАНСИИ В БАЗЕ ДАННЫХ
# ============================================================
# Запуск: python create_vacancy.py
# ============================================================

import asyncio
from bot.database import get_session, init_db
from bot.database.crud import create_vacancy, get_active_vacancies


async def main():
    await init_db()
    
    async with get_session() as session:
        # Проверяем, есть ли уже активные вакансии
        existing = await get_active_vacancies(session)
        if existing:
            print("[WARN] Активные вакансии уже есть:")
            for v in existing:
                print(f"  ID:{v.id} | {v.title} | active: {v.is_active}")
            return
        
        # Создаём вакансию
        vacancy = await create_vacancy(
            session,
            title="Капельдинер",
            description="Работа в театре оперетты. Свободный график, обучение, до 200₽/час + % с продаж.",
            required_stack=None,
            experience_min_years=0,
            salary_min=0,
            salary_max=200,
        )
        await session.commit()
        
        print("[OK] Вакансия создана!")
        print(f"   ID: {vacancy.id}")
        print(f"   Название: {vacancy.title}")
        print(f"   Активна: {vacancy.is_active}")


if __name__ == "__main__":
    asyncio.run(main())