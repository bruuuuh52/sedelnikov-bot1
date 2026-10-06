import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.config import settings
from bot.database import get_session, get_all_completed_screenings, get_screening_with_candidate, update_screening_step, get_all_slots, create_interview_slot
from bot.keyboards import admin_candidate_keyboard
from bot.database.models import ScreeningStatus, InterviewSlot
from sqlalchemy import select

logger = logging.getLogger(__name__)


router = Router(name="admin")


def _is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Список завершённых скринингов с пагинацией."""
    if not _is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа.")
        return

    await _send_screenings_page(message, page=0)


async def _send_screenings_page(message: Message, page: int = 0, limit: int = 10):
    offset = page * limit
    async with get_session() as session:
        screenings = await get_all_completed_screenings(session, limit=limit + 1, offset=offset)

    if not screenings:
        await message.answer("📭 Нет завершённых скринингов.")
        return

    has_next = len(screenings) > limit
    screenings = screenings[:limit]

    lines = [f"📋 <b>Завершённые скрининги</b> (стр. {page + 1}):\n"]
    for scr, cand, vac in screenings:
        vacancy_title = vac.title if vac else "—"
        lines.append(
            f"• <b>ID:</b> {scr.id} | "
            f"<b>Кандидат:</b> {cand.full_name or cand.username or '—'} "
            f"(<code>{cand.telegram_id}</code>) | "
            f"<b>Вакансия:</b> {vacancy_title} | "
            f"<b>Статус:</b> {scr.status.value}"
        )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ Назад", callback_data=f"admin:page:{page - 1}")
    if has_next:
        builder.button(text="Вперёд ➡️", callback_data=f"admin:page:{page + 1}")
    builder.adjust(2)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin:page:"))
async def process_admin_page(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    page = int(callback.data.split(":")[2])
    await callback.message.delete()
    await _send_screenings_page(callback.message, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:detail:"))
async def process_admin_detail(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    screening_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        row = await get_screening_with_candidate(session, screening_id)

    if not row:
        await callback.answer("❌ Не найдено", show_alert=True)
        return

    scr, cand = row
    text = (
        f"📄 <b>Детали скрининга #{scr.id}</b>\n\n"
        f"👤 <b>Кандидат:</b> {cand.full_name or '—'}\n"
        f"🔗 <b>Username:</b> @{cand.username or '—'}\n"
        f"🆔 <b>TG ID:</b> <code>{cand.telegram_id}</code>\n"
        f"📞 <b>Телефон:</b> {cand.phone or '—'}\n"
        f"📧 <b>Email:</b> {cand.email or '—'}\n"
        f"💼 <b>Опыт:</b> {scr.experience_years or '—'} лет\n"
        f"🛠 <b>Стек:</b> {scr.stack or '—'}\n"
        f"💰 <b>Зарплата:</b> {f'{scr.salary_expectation:,} ₽'.replace(',', ' ') if scr.salary_expectation else '—'}\n"
        f"🌍 <b>Релокация:</b> {scr.relocation or '—'}\n"
        f"🔗 <b>Портфолио:</b> {scr.portfolio_url or '—'}\n"
        f"📋 <b>Статус:</b> {scr.status.value}\n"
        f"📅 <b>Создан:</b> {scr.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"✅ <b>Завершён:</b> {scr.completed_at.strftime('%d.%m.%Y %H:%M') if scr.completed_at else '—'}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_candidate_keyboard(screening_id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:accept:"))
async def process_admin_accept(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    screening_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        await update_screening_step(session, screening_id, status=ScreeningStatus.COMPLETED)
        await session.commit()

    await callback.answer("✅ Принят", show_alert=True)
    await callback.message.edit_text(
        callback.message.html_text + "\n\n✅ <b>Статус изменён на: COMPLETED</b>",
        parse_mode="HTML",
        reply_markup=admin_candidate_keyboard(screening_id),
    )


@router.callback_query(F.data.startswith("admin:reject:"))
async def process_admin_reject(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    screening_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        from bot.database.crud import get_slot_by_id
        from bot.database.models import InterviewSlot
        
        # Получаем скрининг с кандидатом и слотом
        result = await session.execute(
            select(Screening, Candidate, InterviewSlot)
            .outerjoin(Candidate, Screening.candidate_id == Candidate.id)
            .outerjoin(InterviewSlot, Screening.interview_slot_id == InterviewSlot.id)
            .where(Screening.id == screening_id)
        )
        row = result.first()
        
        if not row:
            await callback.answer("❌ Скрининг не найден", show_alert=True)
            return
        
        screening, candidate, slot = row
        
        # Освобождаем слот, если он был забронирован
        if slot and screening.interview_slot_id:
            slot_result = await session.execute(select(InterviewSlot).where(InterviewSlot.id == screening.interview_slot_id))
            slot = slot_result.scalar_one_or_none()
            if slot and slot.booked_slots > 0:
                slot.booked_slots -= 1
                await session.flush()
        
        # Обновляем статус на REJECTED
        await update_screening_step(session, screening_id, status=ScreeningStatus.REJECTED)
        await session.commit()

    # Отправляем уведомление кандидату
    try:
        from aiogram import Bot
        from bot.config import settings
        bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
        try:
            await bot.send_message(
                candidate.telegram_id,
                "❌ <b>К сожалению, вам отказали в собеседовании.</b>\n\n"
                "Спасибо за уделенное время и интерес к вакансии.\n"
                "Если захотите попробовать снова — нажмите /start",
                parse_mode="HTML",
            )
        finally:
            await bot.session.close()
    except Exception as e:
        logger.error(f"Failed to send rejection notification to candidate {candidate.telegram_id}: {e}")

    await callback.answer("❌ Отклонён. Уведомление отправлено кандидату, слот освобожден.", show_alert=True)
    await callback.message.edit_text(
        callback.message.html_text + "\n\n❌ <b>Статус изменён на: REJECTED</b>\n✅ Уведомление отправлено, слот освобожден",
        parse_mode="HTML",
        reply_markup=admin_candidate_keyboard(screening_id),
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Быстрая статистика."""
    if not _is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа.")
        return

    async with get_session() as session:
        from sqlalchemy import select, func
        from bot.database.models import Candidate, Screening, Vacancy

        total_candidates = await session.scalar(select(func.count(Candidate.id)))
        total_screenings = await session.scalar(select(func.count(Screening.id)))
        completed = await session.scalar(
            select(func.count(Screening.id)).where(Screening.status == ScreeningStatus.COMPLETED)
        )
        in_progress = await session.scalar(
            select(func.count(Screening.id)).where(Screening.status == ScreeningStatus.IN_PROGRESS)
        )
        rejected = await session.scalar(
            select(func.count(Screening.id)).where(Screening.status == ScreeningStatus.REJECTED)
        )
        active_vacancies = await session.scalar(
            select(func.count(Vacancy.id)).where(Vacancy.is_active == True)
        )

    text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Кандидатов: {total_candidates}\n"
        f"📋 Всего скринингов: {total_screenings}\n"
        f"   ✅ Завершено: {completed}\n"
        f"   ⏳ В процессе: {in_progress}\n"
        f"   ❌ Отклонено: {rejected}\n"
        f"📝 Активных вакансий: {active_vacancies}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("slots"))
async def cmd_slots(message: Message):
    """Просмотр и управление слотами собеседований."""
    if not _is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа.")
        return

    async with get_session() as session:
        slots = await get_all_slots(session)

    if not slots:
        await message.answer("📭 Слотов нет.")
        return

    lines = ["📅 <b>Слоты собеседований:</b>\n"]
    for slot in slots:
        status = "🟢" if slot.is_active and not slot.is_full else ("🔴" if slot.is_full else "⚪")
        date_str = slot.date.strftime("%d %B, %A, %H:%M")
        lines.append(
            f"{status} <b>ID:</b> {slot.id} | <b>{date_str}</b> | "
            f"<b>Места:</b> {slot.booked_slots}/{slot.max_slots} | "
            f"<b>Активен:</b> {'Да' if slot.is_active else 'Нет'}"
        )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for slot in slots:
        action = "🔴 Деактивировать" if slot.is_active else "🟢 Активировать"
        builder.button(text=f"{action} ID:{slot.id}", callback_data=f"admin:slot:toggle:{slot.id}")
    builder.button(text="➕ Добавить слот", callback_data="admin:slot:add")
    builder.adjust(1)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin:slot:toggle:"))
async def process_slot_toggle(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    slot_id = int(callback.data.split(":")[3])
    async with get_session() as session:
        from bot.database.crud import get_slot_by_id
        slot = await get_slot_by_id(session, slot_id)
        if slot:
            slot.is_active = not slot.is_active
            await session.commit()
            await callback.answer(f"{'Активирован' if slot.is_active else 'Деактивирован'}")
            # Refresh the list
            await cmd_slots(callback.message)
        else:
            await callback.answer("❌ Слот не найден", show_alert=True)


@router.callback_query(F.data == "admin:slot:add")
async def process_slot_add(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state("admin:slot:add:date")
    await callback.message.answer(
        "Введите дату и время нового слота в формате: <code>ГГГГ-ММ-ДД ЧЧ:ММ</code>\n"
        "Например: <code>2026-10-20 17:30</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(F.text.regexp(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"))
async def process_slot_date_input(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != "admin:slot:add:date":
        return

    try:
        slot_date = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: <code>ГГГГ-ММ-ДД ЧЧ:ММ</code>", parse_mode="HTML")
        return

    await state.update_data(slot_date=slot_date)
    await state.set_state("admin:slot:add:max")
    await message.answer("Введите максимальное количество мест для этого слота (число):")


@router.message(F.text.regexp(r"^\d+$"))
async def process_slot_max_input(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != "admin:slot:add:max":
        return

    try:
        max_slots = int(message.text.strip())
        if max_slots <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return

    data = await state.get_data()
    slot_date = data.get("slot_date")

    async with get_session() as session:
        from bot.database.crud import create_interview_slot
        await create_interview_slot(session, slot_date, max_slots)
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Слот создан: {slot_date.strftime('%d.%m.%Y %H:%M')} — {max_slots} мест")
    await cmd_slots(message)