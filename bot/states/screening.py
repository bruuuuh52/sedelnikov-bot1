from aiogram.fsm.state import StatesGroup, State


class ScreeningStates(StatesGroup):
    # Шаг 0: выбор вакансии (если несколько активных) — опционально
    choose_vacancy = State()

    # Шаг 1: контакт (телефон/email) — кнопка "Поделиться контактом" + ручной ввод
    contact = State()

    # Шаг 2: опыт работы (года)
    experience_years = State()

    # Шаг 3: стек технологий (текст)
    stack = State()

    # Шаг 4: ожидания по зарплате (число)
    salary_expectation = State()

    # Шаг 5: релокация / remote
    relocation = State()

    # Шаг 6: портфолио / GitHub (опционально)
    portfolio = State()

    # Шаг 7: подтверждение перед отправкой
    confirm = State()