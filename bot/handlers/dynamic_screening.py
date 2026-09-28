from typing import Any
from aiogram import Router, F
from aiogram.types import Message, Contact, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.config import settings
from bot.config_loader import get_config, update_interview_date_options
from bot.database import (
    get_session,
    get_or_create_candidate,
    update_candidate_contacts,
    update_screening_step,
    complete_screening,
    get_screening_with_candidate,
)
from bot.database.crud import book_slot, get_slot_by_id
from bot.keyboards.dynamic import (
    build_question_keyboard,
    build_confirm_keyboard,
    get_option_value,
)
from bot.utils.dynamic_validators import (
    validate_answer,
    format_answer_for_display,
    get_question_prompt,
)
from bot.states.dynamic import (
    ScreeningStates,
    get_current_question_index,
    set_current_question_index,
    get_answers,
    set_answer,
    QUESTION_INDEX_KEY,
    ANSWERS_KEY,
    SCREENING_ID_KEY,
    VACANCY_ID_KEY,
    CANDIDATE_ID_KEY,
)
from bot.database.models import Candidate, Screening, ScreeningStatus
from sqlalchemy import select

router = Router(name="dynamic_screening")


# --- Вспомогательные функции ---

async def _send_question(message: Message, state: FSMContext, question, candidate: Candidate):
    """Отправляет вопрос пользователю с соответствующей клавиатурой."""
    # Если это вопрос выбора даты собеседования — обновляем варианты из БД
    if question.id == "interview_date":
        await update_interview_date_options()
    
    # Сохраняем индекс текущего вопроса
    config = get_config()
    q_index = config.questions.index(question)
    await state.update_data({QUESTION_INDEX_KEY: q_index})

    prompt = get_question_prompt(question)
    keyboard = build_question_keyboard(question)

    await message.answer(prompt, parse_mode="HTML", reply_markup=keyboard)


async def _show_confirmation(message: Message, state: FSMContext, screening: Screening, candidate: Candidate | None):
    """Показывает сводку ответов для подтверждения."""
    import logging
    logger = logging.getLogger(__name__)
    
    config = get_config()
    answers = get_answers(await state.get_data())

    lines = ["📋 <b>Проверь свои данные:</b>\n"]

    for q in config.questions:
        value = answers.get(q.id)
        if value is not None:
            formatted = format_answer_for_display(q, value)
            lines.append(f"• <b>{q.text}</b>\n  {formatted}")

    # Контакты кандидата (если кандидат есть)
    if candidate:
        if candidate.phone:
            lines.append(f"📞 <b>Телефон:</b> <code>{candidate.phone}</code>")
        if candidate.username:
            lines.append(f"🔗 <b>Username:</b> @{candidate.username}")
        if candidate.email:
            lines.append(f"📧 <b>Email:</b> <code>{candidate.email}</code>")

    lines.append("\nВсё верно?")

    await state.set_state(ScreeningStates.confirm)
    text = "\n".join(lines)
    try:
        await message.answer(text, parse_mode="HTML", reply_markup=build_confirm_keyboard())
        logger.info(f"Confirmation sent for screening {screening.id}")
    except Exception as e:
        logger.error(f"Failed to send confirmation: {e}")
        # Fallback без HTML
        try:
            await message.answer(text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""), reply_markup=build_confirm_keyboard())
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")


# --- Хендлеры ответов ---

@router.message(ScreeningStates.answering, F.contact)
async def process_contact_via_button(message: Message, state: FSMContext):
    """Получен контакт через кнопку 'Поделиться контактом'."""
    contact: Contact = message.contact
    phone = contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    await _save_contact_and_next(message, state, phone=phone, email=None)


@router.message(ScreeningStates.answering, F.text == "✍️ Ввести вручную")
async def process_manual_input_request(message: Message, state: FSMContext):
    """Пользователь хочет ввести ответ вручную (для contact/choice)."""
    config = get_config()
    q_index = get_current_question_index(await state.get_data())
    question = config.questions[q_index]

    if question.type == "contact":
        await message.answer(
            "Введи телефон в формате +79991234567 или email:\n(можно оба через запятую)",
            reply_markup=build_question_keyboard(question),
        )
    elif question.type == "choice":
        await message.answer(
            "Введи свой вариант:",
            reply_markup=build_question_keyboard(question),
        )


@router.message(ScreeningStates.answering, F.text == "⏭️ Пропустить")
async def process_skip(message: Message, state: FSMContext):
    """Пропуск необязательного вопроса."""
    await _next_question(message, state)


@router.message(ScreeningStates.answering, F.text == "❌ Отмена")
async def process_cancel(message: Message, state: FSMContext):
    """Отмена анкеты."""
    from bot.handlers.start import cmd_cancel
    await cmd_cancel(message, state)


@router.message(ScreeningStates.answering, F.text)
async def process_text_answer(message: Message, state: FSMContext):
    """Обработка текстового ответа для любого типа вопроса."""
    import logging
    logger = logging.getLogger(__name__)
    
    config = get_config()
    q_index = get_current_question_index(await state.get_data())
    question = config.questions[q_index]

    text = message.text.strip()
    logger.info(f"Processing answer for question {question.id}: '{text}'")

    # Валидация
    value = validate_answer(question, text)
    logger.info(f"Validation result for {question.id}: {value} (type: {type(value).__name__})")
    
    if value is None:
        await message.answer(
            f"❌ Некорректный ответ. {get_question_prompt(question)}",
            parse_mode="HTML",
            reply_markup=build_question_keyboard(question),
        )
        return

    # Сохранение ответа
    await _save_answer_and_next(message, state, question, value)


async def _save_answer_and_next(message: Message, state: FSMContext, question, value: Any):
    """Сохраняет ответ в БД и переходит к следующему вопросу."""
    import logging
    logger = logging.getLogger(__name__)
    
    data = await state.get_data()
    screening_id = data.get(SCREENING_ID_KEY)

    # Специальная обработка для interview_date — бронируем слот
    if question.id == "interview_date":
        # value — это slot_id (строка)
        slot_id = int(value)
        async with get_session() as session:
            slot = await book_slot(session, slot_id)
            if not slot:
                # Слот занят или не существует — показываем ошибку и повторно отправляем вопрос
                await message.answer(
                    "❌ К сожалению, места на это время уже закончились. Пожалуйста, выберите другую дату.",
                    parse_mode="HTML",
                )
                # Обновляем варианты и повторно отправляем вопрос
                await update_interview_date_options()
                config = get_config()
                question = config.get_question("interview_date")
                candidate = await get_or_create_candidate(session, telegram_id=message.from_user.id)
                await _send_question(message, state, question, candidate)
                return
            
            # Слот успешно забронирован — сохраняем slot_id в screening
            await update_screening_step(session, screening_id, interview_slot_id=slot_id)
            await session.commit()
            
            # Сохраняем в FSM
            set_answer(data, question.id, slot_id)
            await state.set_data(data)
            
            logger.info(f"Booked slot {slot_id} for screening {screening_id}, moving to next question")
            
            # Получаем кандидата для уведомления админам
            candidate = await get_or_create_candidate(session, telegram_id=message.from_user.id)
            
            # Отправляем уведомление админам о записи на собеседование
            await _notify_admins_about_booking(session, screening_id, slot, candidate)
            
            # Следующий вопрос
            await _next_question(message, state)
            return

    # Сохраняем в FSM
    set_answer(data, question.id, value)
    await state.set_data(data)

    # Сохраняем в БД
    async with get_session() as session:
        if question.save_to == "candidate":
            if question.id == "phone":
                await update_candidate_contacts(session, message.from_user.id, phone=value)
            elif question.id == "username":
                # username сохраняем в поле username кандидата
                candidate = await get_or_create_candidate(session, telegram_id=message.from_user.id)
                candidate.username = value
        else:
            await update_screening_step(session, screening_id, **{question.id: value})
        await session.commit()

    logger.info(f"Saved answer for {question.id} = {value}, moving to next question")

    # Следующий вопрос
    await _next_question(message, state)


async def _notify_admins_about_booking(session, screening_id: int, slot, candidate: Candidate):
    """Отправляет админам уведомление о записи на собеседование."""
    from aiogram import Bot
    from bot.config import settings
    from bot.config_loader import get_config
    
    config = get_config()
    
    # Получаем данные скрининга с кандидатом
    result = await session.execute(
        select(Screening, Candidate)
        .outerjoin(Candidate, Screening.candidate_id == Candidate.id)
        .where(Screening.id == screening_id)
    )
    row = result.first()
    
    if not row:
        return
    
    scr, cand = row
    
    # Форматируем дату
    date_str = slot.date.strftime("%d %B, %A, %H:%M")
    available = slot.max_slots - slot.booked_slots
    
    admin_text = (
        f"📅 <b>Запись на собеседование!</b>\n\n"
        f"👤 <b>Кандидат:</b> @{cand.username or '—'}\n"
        f"🆔 <b>TG ID:</b> <code>{cand.telegram_id}</code>\n"
        f"📞 <b>Телефон:</b> {cand.phone or '—'}\n"
        f"📅 <b>Дата:</b> {date_str}\n"
        f"🪑 <b>Места:</b> {slot.booked_slots} из {slot.max_slots} (осталось {available})"
    )
    
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    try:
        for admin_id in config.recipients:
            try:
                await bot.send_message(admin_id, admin_text, parse_mode="HTML")
            except Exception:
                pass
    finally:
        await bot.session.close()


# Импорты для SQLAlchemy (вынесены наверх для надежности)
from sqlalchemy import select

async def _next_question(message: Message, state: FSMContext):
    """Переходит к следующему вопросу или к подтверждению."""
    import logging
    logger = logging.getLogger(__name__)
    
    config = get_config()
    data = await state.get_data()
    q_index = get_current_question_index(data) + 1

    if q_index >= len(config.questions):
        # Все вопросы пройдены -> подтверждение
        screening_id = data.get(SCREENING_ID_KEY)
        logger.info(f"All questions answered for screening {screening_id}, fetching data for confirmation")
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Screening, Candidate)
                    .outerjoin(Candidate, Screening.candidate_id == Candidate.id)
                    .where(Screening.id == screening_id)
                )
                row = result.first()
            if row:
                screening, candidate = row
                logger.info(f"Showing confirmation for screening {screening_id}")
                await _show_confirmation(message, state, screening, candidate)
            else:
                logger.error(f"Screening {screening_id} not found for confirmation")
        except Exception as e:
            logger.exception(f"Error in confirmation flow: {e}")
        return

    # Следующий вопрос
    question = config.questions[q_index]
    async with get_session() as session:
        candidate = await get_or_create_candidate(session, telegram_id=message.from_user.id)

    set_current_question_index(data, q_index)
    await state.set_data(data)
    logger.info(f"Sending question {q_index}: {question.id}")
    await _send_question(message, state, question, candidate)


async def _save_contact_and_next(message: Message, state: FSMContext, phone: str | None, email: str | None):
    """Сохраняет контакт и переходит к следующему вопросу."""
    data = await state.get_data()
    screening_id = data.get(SCREENING_ID_KEY)

    async with get_session() as session:
        await update_candidate_contacts(session, message.from_user.id, phone=phone, email=email)
        if phone:
            await update_screening_step(session, screening_id, phone=phone)
        if email:
            await update_screening_step(session, screening_id, email=email)
        await session.commit()

    # Сохраняем в FSM
    if phone:
        set_answer(data, "contact", phone)
    if email:
        set_answer(data, "email", email)
    await state.set_data(data)

    # Следующий вопрос
    await _next_question(message, state)


# --- Подтверждение ---

@router.message(ScreeningStates.confirm, F.text == "✅ Всё верно, отправить")
async def process_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    screening_id = data.get(SCREENING_ID_KEY)

    async with get_session() as session:
        screening = await complete_screening(session, screening_id)
        await session.commit()

        # Данные для уведомления
        from sqlalchemy import select
        result = await session.execute(
            select(Screening, Candidate)
            .outerjoin(Candidate, Screening.candidate_id == Candidate.id)
            .where(Screening.id == screening_id)
        )
        row = result.first()

    # Уведомляем админов
    from aiogram import Bot
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    try:
        if row:
            scr, cand = row
            config = get_config()
            answers = get_answers(data)

            admin_lines = [
                f"🆕 <b>Новый кандидат!</b>",
                f"📋 <b>Вакансия:</b> {config.vacancy_title}\n",
            ]
            if cand:
                admin_lines.extend([
                    f"👤 <b>Имя:</b> {cand.full_name or '—'}",
                    f"🔗 <b>Username:</b> @{cand.username or '—'}",
                    f"🆔 <b>TG ID:</b> <code>{cand.telegram_id}</code>",
                ])
                if cand.phone:
                    admin_lines.append(f"📞 <b>Телефон:</b> {cand.phone}")
                if cand.email:
                    admin_lines.append(f"📧 <b>Email:</b> {cand.email}")
            else:
                admin_lines.append("👤 <b>Кандидат:</b> данные не найдены (возможно, удалён)")

            for q in config.questions:
                value = answers.get(q.id)
                if value is not None:
                    formatted = format_answer_for_display(q, value)
                    admin_lines.append(f"🔹 <b>{q.text}</b>\n  {formatted}")

            admin_text = "\n".join(admin_lines)

            for admin_id in config.recipients:
                try:
                    await bot.send_message(admin_id, admin_text, parse_mode="HTML")
                except Exception:
                    pass
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

    # Показываем финальное сообщение из конфига
    config = get_config()
    if config.final_message:
        await message.answer(config.final_message, parse_mode="HTML")


@router.message(ScreeningStates.confirm, F.text == "🔄 Начать заново")
async def process_restart(message: Message, state: FSMContext):
    data = await state.get_data()
    screening_id = data.get(SCREENING_ID_KEY)

    if screening_id:
        async with get_session() as session:
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
    from bot.handlers.start import cmd_cancel
    await cmd_cancel(message, state)