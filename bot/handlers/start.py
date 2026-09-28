from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.config import settings
from bot.database import get_session, get_active_vacancies, create_screening, get_or_create_candidate, get_candidate_screenings
from bot.database.models import Screening, ScreeningStatus
from bot.keyboards import (
    vacancy_choice_keyboard,
    contact_keyboard,
    cancel_keyboard,
    experience_keyboard,
    relocation_keyboard,
    confirm_keyboard,
    skip_keyboard,
)
from bot.states import ScreeningStates
from bot.utils import validate_phone, validate_email
from sqlalchemy import select


router = Router(name="start")


async def _get_or_create_screening(session, candidate_id: int, vacancy_id: int):
    """Возвращает существующий незавершённый скрининг или создаёт новый."""
    # Ищем существующий скрининг для этой пары кандидат+вакансия
    result = await session.execute(
        select(Screening).where(
            Screening.candidate_id == candidate_id,
            Screening.vacancy_id == vacancy_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.status == ScreeningStatus.IN_PROGRESS:
            return existing, True  # resumed
        elif existing.status == ScreeningStatus.COMPLETED:
            # Завершённый — удаляем и создаём новый
            await session.delete(existing)
            await session.flush()
        elif existing.status == ScreeningStatus.REJECTED:
            # Отклонённый — удаляем и создаём новый
            await session.delete(existing)
            await session.flush()

    # Создаём новый
    screening = Screening(candidate_id=candidate_id, vacancy_id=vacancy_id)
    session.add(screening)
    await session.flush()
    return screening, False  # new


def _determine_next_state(screening: Screening, candidate) -> ScreeningStates:
    """Определяет следующий шаг на основе заполненных полей скрининга и кандидата."""
    if not candidate.phone and not candidate.email:
        return ScreeningStates.contact
    if screening.experience_years is None:
        return ScreeningStates.experience_years
    if not screening.stack:
        return ScreeningStates.stack
    if screening.salary_expectation is None:
        return ScreeningStates.salary_expectation
    if not screening.relocation:
        return ScreeningStates.relocation
    if screening.portfolio_url is None:
        return ScreeningStates.portfolio
    return ScreeningStates.confirm


def _get_step_message(state: ScreeningStates, screening: Screening, candidate) -> str:
    """Возвращает текст сообщения для шага."""
    step_names = {
        ScreeningStates.contact: "📋 <b>Шаг 1/7:</b> укажи контакт для связи.\nМожешь нажать кнопку «Поделиться контактом» или ввести телефон/email вручную.",
        ScreeningStates.experience_years: "📋 <b>Шаг 2/7:</b> сколько лет опыта у тебя в разработке?\nВыбери диапазон или введи число вручную.",
        ScreeningStates.stack: "📋 <b>Шаг 3/7:</b> укажи свой стек технологий.\nПример: <code>Python, FastAPI, PostgreSQL, Docker, Redis</code>",
        ScreeningStates.salary_expectation: "📋 <b>Шаг 4/7:</b> какая зарплата тебя интересует (в рублях на руки)?\nВведи число, например: <code>150000</code> или <code>150 000</code>",
        ScreeningStates.relocation: "📋 <b>Шаг 5/7:</b> готов ли ты к релокации или ищешь remote?",
        ScreeningStates.portfolio: "📋 <b>Шаг 6/7 (опционально):</b> ссылка на портфолио / GitHub / GitLab.\nМожешь пропустить.",
        ScreeningStates.confirm: _format_confirmation(screening, candidate),
    }
    return step_names.get(state, "Неизвестный шаг")


def _format_confirmation(screening: Screening, candidate) -> str:
    """Формирует текст подтверждения из данных скрининга и кандидата."""
    lines = ["📋 <b>Проверь свои данные:</b>\n"]
    if candidate.phone:
        lines.append(f"📞 Телефон: <code>{candidate.phone}</code>")
    if candidate.email:
        lines.append(f"📧 Email: <code>{candidate.email}</code>")
    if screening.experience_years is not None:
        lines.append(f"💼 Опыт: {screening.experience_years} лет")
    if screening.stack:
        lines.append(f"🛠 Стек: {screening.stack}")
    if screening.salary_expectation:
        lines.append(f"💰 Зарплата: {screening.salary_expectation:,} ₽".replace(",", " "))
    if screening.relocation:
        reloc_map = {"ready": "✅ Готов к релокации", "remote_only": "🏠 Только remote", "not_ready": "🤔 Не готов"}
        lines.append(f"🌍 Релокация: {reloc_map.get(screening.relocation, screening.relocation)}")
    if screening.portfolio_url:
        lines.append(f"🔗 Портфолио: {screening.portfolio_url}")
    lines.append("\nВсё верно?")
    return "\n".join(lines)


def _get_step_keyboard(state: ScreeningStates):
    """Возвращает клавиатуру для шага."""
    keyboards = {
        ScreeningStates.contact: contact_keyboard(),
        ScreeningStates.experience_years: experience_keyboard(),
        ScreeningStates.stack: cancel_keyboard(),
        ScreeningStates.salary_expectation: cancel_keyboard(),
        ScreeningStates.relocation: relocation_keyboard(),
        ScreeningStates.portfolio: skip_keyboard(),
        ScreeningStates.confirm: confirm_keyboard(),
    }
    return keyboards.get(state, cancel_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка /start — приветствие и выбор вакансии."""
    await state.clear()

    async with get_session() as session:
        candidate = await get_or_create_candidate(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        vacancies = await get_active_vacancies(session)

    if not vacancies:
        await message.answer(
            "👋 Привет! К сожалению, сейчас нет активных вакансий.\n"
            "Подпишись на обновления или попробуй позже."
        )
        return

    if len(vacancies) == 1:
        # Только одна вакансия — проверяем/создаём скрининг
        vacancy = vacancies[0]
        async with get_session() as session:
            screening, is_resumed = await _get_or_create_screening(session, candidate.id, vacancy.id)
            await session.commit()

        await state.update_data(
            screening_id=screening.id,
            vacancy_id=vacancy.id,
            candidate_id=candidate.id,
        )

        # Определяем следующий шаг на основе заполненных полей
        next_state = _determine_next_state(screening, candidate)
        await state.set_state(next_state)

        if is_resumed:
            await message.answer(
                f"👋 Привет, {message.from_user.full_name or 'друг'}!\n\n"
                f"Ты уже начинал анкету для вакансии <b>{vacancy.title}</b>.\n"
                f"Продолжим с места, где остановились.",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"👋 Привет, {message.from_user.full_name or 'друг'}!\n\n"
                f"Ты хочешь откликнуться на вакансию: <b>{vacancy.title}</b>",
                parse_mode="HTML",
            )

        await message.answer(
            _get_step_message(next_state, screening, candidate),
            parse_mode="HTML",
            reply_markup=_get_step_keyboard(next_state),
        )
        return

    # Несколько вакансий — показываем выбор
    vacancy_list = "\n".join(f"• {v.title}" for v in vacancies)
    await message.answer(
        f"👋 Привет, {message.from_user.full_name or 'друг'}!\n\n"
        f"У нас есть несколько активных вакансий:\n{vacancy_list}\n\n"
        f"Выбери, на какую хочешь откликнуться:",
        reply_markup=vacancy_choice_keyboard([(v.id, v.title) for v in vacancies]),
    )
    await state.set_state(ScreeningStates.choose_vacancy)


@router.callback_query(ScreeningStates.choose_vacancy, F.data.startswith("vacancy:"))
async def process_vacancy_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор вакансии из inline-клавиатуры."""
    _, vac_id_str = callback.data.split(":", 1)

    if vac_id_str == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Отменено. Чтобы начать заново, нажми /start")
        await callback.answer()
        return

    vacancy_id = int(vac_id_str)

    async with get_session() as session:
        # Проверяем, что вакансия существует и активна
        vacancies = await get_active_vacancies(session)
        vacancy = next((v for v in vacancies if v.id == vacancy_id), None)

        if not vacancy:
            await callback.answer("❌ Вакансия не найдена или неактивна", show_alert=True)
            return

        candidate = await get_or_create_candidate(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )
        screening, is_resumed = await _get_or_create_screening(session, candidate.id, vacancy.id)
        await session.commit()

    await state.update_data(
        screening_id=screening.id,
        vacancy_id=vacancy.id,
        candidate_id=candidate.id,
    )

    next_state = _determine_next_state(screening, candidate)
    await state.set_state(next_state)

    if is_resumed:
        await callback.message.edit_text(
            f"✅ Выбрана вакансия: <b>{vacancy.title}</b>\n\n"
            f"Ты уже начинал анкету для этой вакансии.\n"
            f"Продолжим с места, где остановились.",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            f"✅ Выбрана вакансия: <b>{vacancy.title}</b>",
            parse_mode="HTML",
        )

    await callback.message.answer(
        _get_step_message(next_state, screening, candidate),
        parse_mode="HTML",
        reply_markup=_get_step_keyboard(next_state),
    )
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Команда /cancel — полный сброс FSM."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять.", reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    screening_id = data.get("screening_id")

    if screening_id:
        async with get_session() as session:
            result = await session.execute(select(Screening).where(Screening.id == screening_id))
            screening = result.scalar_one_or_none()
            if screening:
                await session.delete(screening)
                await session.commit()

    await state.clear()
    await message.answer("❌ Анкета отменена. Чтобы начать заново, нажми /start", reply_markup=cancel_keyboard())