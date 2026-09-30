from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from bot.config import settings
from bot.config_loader import get_config
from bot.database import get_session, get_active_vacancies, get_or_create_candidate
from bot.database.models import Screening, ScreeningStatus
from bot.keyboards.builders import vacancy_choice_keyboard
from bot.keyboards.dynamic import build_question_keyboard, build_consent_keyboard
from bot.states.dynamic import ScreeningStates, QUESTION_INDEX_KEY, ANSWERS_KEY, SCREENING_ID_KEY, VACANCY_ID_KEY, CANDIDATE_ID_KEY
from sqlalchemy import select

router = Router(name="dynamic_start")


async def _get_or_create_screening(session, candidate_id: int, vacancy_id: int):
    """Возвращает существующий незавершённый скрининг или создаёт новый."""
    result = await session.execute(
        select(Screening).where(
            Screening.candidate_id == candidate_id,
            Screening.vacancy_id == vacancy_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.status == ScreeningStatus.IN_PROGRESS:
            return existing, True
        elif existing.status in (ScreeningStatus.COMPLETED, ScreeningStatus.REJECTED):
            await session.delete(existing)
            await session.flush()

    screening = Screening(candidate_id=candidate_id, vacancy_id=vacancy_id)
    session.add(screening)
    await session.flush()
    return screening, False


async def _show_consent(message: Message, state: FSMContext, vacancy, candidate):
    """Показывает экран согласия на обработку персональных данных."""
    config = get_config()
    
    # Получаем текст согласия из описания вакансии
    consent_text = config.vacancy_description
    
    await message.answer(
        f"👋 Привет, {message.from_user.full_name or 'друг'}!\n\n"
        f"Ты хочешь откликнуться на вакансию: <b>{vacancy.title}</b>\n\n"
        f"{config.vacancy_description}",
        parse_mode="HTML",
        reply_markup=build_consent_keyboard(),
    )
    await state.set_state(ScreeningStates.consent)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка /start — приветствие, согласие и выбор вакансии."""
    await state.clear()

    config = get_config()

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
        vacancy = vacancies[0]
        async with get_session() as session:
            screening, is_resumed = await _get_or_create_screening(session, candidate.id, vacancy.id)
            await session.commit()

        # Инициализация FSM data
        await state.update_data({
            SCREENING_ID_KEY: screening.id,
            VACANCY_ID_KEY: vacancy.id,
            CANDIDATE_ID_KEY: candidate.id,
            QUESTION_INDEX_KEY: 0,
            ANSWERS_KEY: {},
        })

        if is_resumed:
            # Если уже проходил — показываем сразу первый вопрос
            config = get_config()
            first_question = config.questions[0]
            await state.set_state(ScreeningStates.answering)
            async with get_session() as session:
                candidate = await get_or_create_candidate(session, telegram_id=message.from_user.id)
            await _send_question(message, state, first_question, candidate)
        else:
            # Новый пользователь — показываем согласие
            await _show_consent(message, state, vacancy, candidate)
        return

    # Несколько вакансий
    vacancy_list = "\n".join(f"• {v.title}" for v in vacancies)
    await message.answer(
        f"👋 Привет, {message.from_user.full_name or 'друг'}!\n\n"
        f"У нас есть несколько активных вакансий:\n{vacancy_list}\n\n"
        f"Выбери, на какую хочешь откликнуться:",
        reply_markup=vacancy_choice_keyboard([(v.id, v.title) for v in vacancies]),
    )
    await state.set_state(ScreeningStates.choose_vacancy)


async def _send_question(message: Message, state: FSMContext, question, candidate):
    """Отправляет вопрос пользователю."""
    from bot.utils.dynamic_validators import get_question_prompt
    prompt = get_question_prompt(question)
    keyboard = build_question_keyboard(question)
    await message.answer(prompt, parse_mode="HTML", reply_markup=keyboard)


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
    config = get_config()

    async with get_session() as session:
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

    await state.update_data({
        SCREENING_ID_KEY: screening.id,
        VACANCY_ID_KEY: vacancy.id,
        CANDIDATE_ID_KEY: candidate.id,
        QUESTION_INDEX_KEY: 0,
        ANSWERS_KEY: {},
    })

    if is_resumed:
        await callback.message.edit_text(
            f"✅ Выбрана вакансия: <b>{vacancy.title}</b>\n\n"
            f"Ты уже начинал анкету для этой вакансии.\n"
            f"Продолжим с места, где остановились.",
            parse_mode="HTML",
        )
        first_question = config.questions[0]
        await state.set_state(ScreeningStates.answering)
        await _send_question(callback.message, state, first_question, candidate)
    else:
        # Новый пользователь — показываем согласие
        await callback.message.edit_text(
            f"✅ Выбрана вакансия: <b>{vacancy.title}</b>",
            parse_mode="HTML",
        )
        await _show_consent(callback.message, state, vacancy, candidate)
    await callback.answer()


# --- Обработчики согласия ---

@router.message(ScreeningStates.consent, F.text == "✅ Согласен, продолжить")
async def process_consent_agree(message: Message, state: FSMContext):
    """Пользователь согласился — переходим к первому вопросу."""
    data = await state.get_data()
    vacancy_id = data.get(VACANCY_ID_KEY)
    
    async with get_session() as session:
        vacancies = await get_active_vacancies(session)
        vacancy = next((v for v in vacancies if v.id == vacancy_id), None)
        
        if not vacancy:
            await message.answer("❌ Вакансия не найдена. Нажми /start")
            await state.clear()
            return
        
        config = get_config()
        first_question = config.questions[0]
        async with get_session() as session:
            candidate = await get_or_create_candidate(session, telegram_id=message.from_user.id)
        await state.set_state(ScreeningStates.answering)
        await _send_question(message, state, first_question, candidate)


@router.message(ScreeningStates.consent, F.text == "❌ Не согласен")
async def process_consent_disagree(message: Message, state: FSMContext):
    """Пользователь не согласился — отменяем анкету."""
    data = await state.get_data()
    screening_id = data.get(SCREENING_ID_KEY)
    
    if screening_id:
        async with get_session() as session:
            result = await session.execute(select(Screening).where(Screening.id == screening_id))
            screening = result.scalar_one_or_none()
            if screening:
                await session.delete(screening)
                await session.commit()
    
    await state.clear()
    await message.answer(
        "❌ Вы не дали согласие на обработку персональных данных. Анкета отменена.\n"
        "Если передумаете — нажмите /start",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Команда /cancel — полный сброс FSM."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять.")
        return

    data = await state.get_data()
    screening_id = data.get(SCREENING_ID_KEY)

    if screening_id:
        async with get_session() as session:
            result = await session.execute(select(Screening).where(Screening.id == screening_id))
            screening = result.scalar_one_or_none()
            if screening:
                await session.delete(screening)
                await session.commit()

    await state.clear()
    await message.answer("❌ Анкета отменена. Чтобы начать заново, нажми /start")