from aiogram import Router, F
from aiogram.types import Message, Contact, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.config import settings
from bot.database import get_session, update_screening_step, complete_screening, get_screening_with_candidate, update_candidate_contacts
from bot.database.models import Screening, Candidate, Vacancy, ScreeningStatus
from bot.keyboards import (
    experience_keyboard,
    relocation_keyboard,
    confirm_keyboard,
    skip_keyboard,
    cancel_keyboard,
    admin_candidate_keyboard,
    EXPERIENCE_BUTTON_MAP,
    RELOCATION_BUTTON_MAP,
)
from bot.states import ScreeningStates
from bot.utils import (
    validate_phone,
    validate_email,
    validate_experience_years,
    validate_stack,
    validate_salary,
    validate_portfolio,
    parse_relocation_choice,
)

router = Router(name="screening")


# --- Вспомогательные функции ---

async def _get_screening_and_check(state: FSMContext) -> tuple[int, int] | None:
    """Получает screening_id и candidate_id из состояния."""
    data = await state.get_data()
    screening_id = data.get("screening_id")
    candidate_id = data.get("candidate_id")
    if not screening_id or not candidate_id:
        return None
    return screening_id, candidate_id


def _format_confirmation(data: dict) -> str:
    """Формирует текст подтверждения из данных FSM."""
    lines = ["📋 <b>Проверь свои данные:</b>\n"]
    if data.get("phone"):
        lines.append(f"📞 Телефон: <code>{data['phone']}</code>")
    if data.get("email"):
        lines.append(f"📧 Email: <code>{data['email']}</code>")
    if data.get("experience_years") is not None:
        lines.append(f"💼 Опыт: {data['experience_years']} лет")
    if data.get("stack"):
        lines.append(f"🛠 Стек: {data['stack']}")
    if data.get("salary_expectation"):
        lines.append(f"💰 Зарплата: {data['salary_expectation']:,} ₽".replace(",", " "))
    if data.get("relocation"):
        reloc_map = {"ready": "✅ Готов к релокации", "remote_only": "🏠 Только remote", "not_ready": "🤔 Не готов"}
        lines.append(f"🌍 Релокация: {reloc_map.get(data['relocation'], data['relocation'])}")
    if data.get("portfolio_url"):
        lines.append(f"🔗 Портфолио: {data['portfolio_url']}")
    lines.append("\nВсё верно?")
    return "\n".join(lines)


# --- Шаг 1: Контакт (телефон/email) ---

@router.message(ScreeningStates.contact, F.contact)
async def process_contact_via_button(message: Message, state: FSMContext):
    """Получен контакт через кнопку 'Поделиться контактом'."""
    contact: Contact = message.contact
    phone = contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    await _save_contact_and_next(message, state, phone=phone, email=None)


@router.message(ScreeningStates.contact, F.text == "✍️ Ввести вручную")
async def process_contact_manual_request(message: Message, state: FSMContext):
    """Пользователь хочет ввести контакт вручную."""
    await message.answer(
        "Введи телефон в формате +79991234567 или email:\n"
        "(можно оба через пробел или запятую)",
        reply_markup=cancel_keyboard(),
    )


@router.message(ScreeningStates.contact, F.text)
async def process_contact_manual(message: Message, state: FSMContext):
    """Ручной ввод контакта."""
    text = message.text.strip()

    # Попробуем распарсить как телефон
    phone = validate_phone(text)
    if phone:
        await _save_contact_and_next(message, state, phone=phone, email=None)
        return

    # Попробуем как email
    email = validate_email(text)
    if email:
        await _save_contact_and_next(message, state, phone=None, email=email)
        return

    # Попробуем оба через разделитель
    for sep in [",", " ", ";"]:
        if sep in text:
            parts = [p.strip() for p in text.split(sep)]
            phone = validate_phone(parts[0]) if parts else None
            email = validate_email(parts[1]) if len(parts) > 1 else None
            if phone or email:
                await _save_contact_and_next(message, state, phone=phone, email=email)
                return

    await message.answer(
        "❌ Не удалось распознать контакт.\n"
        "Примеры: <code>+79991234567</code>, <code>test@example.com</code>, "
        "<code>+79991234567, test@example.com</code>",
        parse_mode="HTML",
        reply_markup=contact_keyboard(),
    )


async def _save_contact_and_next(message: Message, state: FSMContext, phone: str | None, email: str | None):
    """Сохраняет контакт в БД и переходит к следующему шагу."""
    data = await state.get_data()
    screening_id = data.get("screening_id")
    candidate_id = data.get("candidate_id")

    if not screening_id:
        await message.answer("❌ Ошибка сессии. Начни заново: /start")
        await state.clear()
        return

    async with get_session() as session:
        # Обновляем контакты кандидата
        from bot.database import update_candidate_contacts
        await update_candidate_contacts(session, message.from_user.id, phone=phone, email=email)

        # Сохраняем в скрининге (для истории)
        await update_screening_step(session, screening_id, phone=phone, email=email)
        await session.commit()

    await state.update_data(phone=phone, email=email)
    await state.set_state(ScreeningStates.experience_years)

    await message.answer(
        "✅ Контакт сохранён!\n\n"
        "📋 <b>Шаг 2/7:</b> сколько лет опыта у тебя в разработке?\n"
        "Выбери диапазон или введи число вручную.",
        parse_mode="HTML",
        reply_markup=experience_keyboard(),
    )


# --- Шаг 2: Опыт работы ---

@router.message(ScreeningStates.experience_years, F.text.in_(EXPERIENCE_BUTTON_MAP))
async def process_experience_button(message: Message, state: FSMContext):
    """Выбрано значение из кнопок опыта."""
    years = EXPERIENCE_BUTTON_MAP[message.text]
    await _save_experience_and_next(message, state, years)


@router.message(ScreeningStates.experience_years, F.text == "✍️ Ввести вручную")
async def process_experience_manual_request(message: Message, state: FSMContext):
    await message.answer(
        "Введи количество лет опыта числом (например: 3):",
        reply_markup=cancel_keyboard(),
    )


@router.message(ScreeningStates.experience_years, F.text)
async def process_experience_manual(message: Message, state: FSMContext):
    """Ручной ввод лет опыта."""
    years = validate_experience_years(message.text)
    if years is None:
        await message.answer(
            "❌ Некорректное значение. Введи число от 0 до 50 (например: 3).",
            reply_markup=experience_keyboard(),
        )
        return
    await _save_experience_and_next(message, state, years)


async def _save_experience_and_next(message: Message, state: FSMContext, years: int):
    screening_id = (await state.get_data()).get("screening_id")
    async with get_session() as session:
        await update_screening_step(session, screening_id, experience_years=years)
        await session.commit()

    await state.update_data(experience_years=years)
    await state.set_state(ScreeningStates.stack)

    await message.answer(
        f"✅ Опыт: {years} лет.\n\n"
        "📋 <b>Шаг 3/7:</b> укажи свой стек технологий.\n"
        "Пример: <code>Python, FastAPI, PostgreSQL, Docker, Redis</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


# --- Шаг 3: Стек технологий ---

@router.message(ScreeningStates.stack, F.text)
async def process_stack(message: Message, state: FSMContext):
    stack = validate_stack(message.text)
    if not stack:
        await message.answer(
            "❌ Стек слишком короткий или длинный (3–1000 символов). Попробуй ещё раз.",
            reply_markup=cancel_keyboard(),
        )
        return

    screening_id = (await state.get_data()).get("screening_id")
    async with get_session() as session:
        await update_screening_step(session, screening_id, stack=stack)
        await session.commit()

    await state.update_data(stack=stack)
    await state.set_state(ScreeningStates.salary_expectation)

    await message.answer(
        f"✅ Стек сохранён.\n\n"
        "📋 <b>Шаг 4/7:</b> какая зарплата тебя интересует (в рублях на руки)?\n"
        "Введи число, например: <code>150000</code> или <code>150 000</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


# --- Шаг 4: Зарплата ---

@router.message(ScreeningStates.salary_expectation, F.text)
async def process_salary(message: Message, state: FSMContext):
    salary = validate_salary(message.text)
    if salary is None:
        await message.answer(
            "❌ Некорректная сумма. Введи число от 1000 до 9999999 (например: 150000).",
            reply_markup=cancel_keyboard(),
        )
        return

    screening_id = (await state.get_data()).get("screening_id")
    async with get_session() as session:
        await update_screening_step(session, screening_id, salary_expectation=salary)
        await session.commit()

    await state.update_data(salary_expectation=salary)
    await state.set_state(ScreeningStates.relocation)

    await message.answer(
        f"✅ Зарплата: {salary:,} ₽".replace(",", " ") + ".\n\n"
        "📋 <b>Шаг 5/7:</b> готов ли ты к релокации или ищешь remote?",
        parse_mode="HTML",
        reply_markup=relocation_keyboard(),
    )


# --- Шаг 5: Релокация ---

@router.message(ScreeningStates.relocation, F.text.in_(RELOCATION_BUTTON_MAP))
async def process_relocation_button(message: Message, state: FSMContext):
    relocation = RELOCATION_BUTTON_MAP[message.text]
    await _save_relocation_and_next(message, state, relocation)


@router.message(ScreeningStates.relocation, F.text)
async def process_relocation_manual(message: Message, state: FSMContext):
    relocation = parse_relocation_choice(message.text)
    if not relocation:
        await message.answer(
            "❌ Не понял. Выбери кнопку или введи: «готов к релокации», «только remote», «не готов».",
            reply_markup=relocation_keyboard(),
        )
        return
    await _save_relocation_and_next(message, state, relocation)


async def _save_relocation_and_next(message: Message, state: FSMContext, relocation: str):
    screening_id = (await state.get_data()).get("screening_id")
    async with get_session() as session:
        await update_screening_step(session, screening_id, relocation=relocation)
        await session.commit()

    await state.update_data(relocation=relocation)
    await state.set_state(ScreeningStates.portfolio)

    await message.answer(
        f"✅ Релокация: {relocation}.\n\n"
        "📋 <b>Шаг 6/7 (опционально):</b> ссылка на портфолио / GitHub / GitLab.\n"
        "Можешь пропустить.",
        parse_mode="HTML",
        reply_markup=skip_keyboard(),
    )


# --- Шаг 6: Портфолио (опционально) ---

@router.message(ScreeningStates.portfolio, F.text == "⏭️ Пропустить")
async def process_portfolio_skip(message: Message, state: FSMContext):
    await _show_confirmation(message, state)


@router.message(ScreeningStates.portfolio, F.text)
async def process_portfolio(message: Message, state: FSMContext):
    portfolio = validate_portfolio(message.text)
    if portfolio is None:
        await message.answer(
            "❌ Некорректная ссылка. Пример: <code>https://github.com/user</code> или <code>github.com/user</code>.\n"
            "Или нажми «Пропустить».",
            parse_mode="HTML",
            reply_markup=skip_keyboard(),
        )
        return

    screening_id = (await state.get_data()).get("screening_id")
    async with get_session() as session:
        await update_screening_step(session, screening_id, portfolio_url=portfolio)
        await session.commit()

    await state.update_data(portfolio_url=portfolio)
    await _show_confirmation(message, state)


# --- Шаг 7: Подтверждение ---

async def _show_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    text = _format_confirmation(data)
    await state.set_state(ScreeningStates.confirm)
    await message.answer(text, parse_mode="HTML", reply_markup=confirm_keyboard())


@router.message(ScreeningStates.confirm, F.text == "✅ Всё верно, отправить")
async def process_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    screening_id = data.get("screening_id")
    candidate_id = data.get("candidate_id")
    vacancy_id = data.get("vacancy_id")

    async with get_session() as session:
        screening = await complete_screening(session, screening_id)
        await session.commit()

        # Получаем данные для уведомления админов
        from sqlalchemy import select
        result = await session.execute(
            select(Screening, Candidate, Vacancy)
            .join(Candidate, Screening.candidate_id == Candidate.id)
            .join(Vacancy, Screening.vacancy_id == Vacancy.id)
            .where(Screening.id == screening_id)
        )
        row = result.first()

    # Уведомляем админов
    from aiogram import Bot
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    try:
        if row:
            scr, cand, vac = row
            admin_text = (
                f"🆕 <b>Новый кандидат!</b>\n\n"
                f"👤 <b>Имя:</b> {cand.full_name or '—'}\n"
                f"🔗 <b>Username:</b> @{cand.username or '—'}\n"
                f"🆔 <b>TG ID:</b> <code>{cand.telegram_id}</code>\n"
                f"📞 <b>Телефон:</b> {data.get('phone') or '—'}\n"
                f"📧 <b>Email:</b> {data.get('email') or '—'}\n"
                f"💼 <b>Опыт:</b> {data.get('experience_years')} лет\n"
                f"🛠 <b>Стек:</b> {data.get('stack')}\n"
                f"💰 <b>Зарплата:</b> {data.get('salary_expectation'):,} ₽\n".replace(",", " ") +
                f"🌍 <b>Релокация:</b> {data.get('relocation')}\n"
                f"🔗 <b>Портфолио:</b> {data.get('portfolio_url') or '—'}\n"
                f"📋 <b>Вакансия:</b> {vac.title}"
            )
            for admin_id in settings.ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        admin_text,
                        parse_mode="HTML",
                        reply_markup=admin_candidate_keyboard(screening_id),
                    )
                except Exception:
                    pass  # админ мог заблокировать бота
    finally:
        await bot.session.close()

    await state.clear()
    await message.answer(
        "✅ <b>Анкета отправлена!</b>\n\n"
        "Спасибо за уделенное время. Наши рекрутеры рассмотрят твою заявку "
        "и свяжутся с тобой в ближайшее время.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ScreeningStates.confirm, F.text == "🔄 Начать заново")
async def process_restart(message: Message, state: FSMContext):
    data = await state.get_data()
    screening_id = data.get("screening_id")

    if screening_id:
        async with get_session() as session:
            from bot.database.models import Screening
            from sqlalchemy import select
            result = await session.execute(select(Screening).where(Screening.id == screening_id))
            screening = result.scalar_one_or_none()
            if screening:
                await session.delete(screening)
                await session.commit()

    await state.clear()
    await message.answer("🔄 Начинаем заново. Нажми /start", reply_markup=ReplyKeyboardRemove())


@router.message(ScreeningStates.confirm, F.text == "❌ Отмена")
async def process_cancel_confirm(message: Message, state: FSMContext):
    await cmd_cancel(message, state)


# --- Универсальная отмена на любом шаге ---

# Список всех состояний кроме confirm
ALL_SCREENING_STATES = [
    ScreeningStates.choose_vacancy,
    ScreeningStates.contact,
    ScreeningStates.experience_years,
    ScreeningStates.stack,
    ScreeningStates.salary_expectation,
    ScreeningStates.relocation,
    ScreeningStates.portfolio,
]

@router.message(StateFilter(*ALL_SCREENING_STATES), F.text == "❌ Отмена")
async def process_cancel_any_step(message: Message, state: FSMContext):
    await cmd_cancel(message, state)


# Импорт для отмены (в конце чтобы избежать циклических импортов)
from bot.handlers.start import cmd_cancel