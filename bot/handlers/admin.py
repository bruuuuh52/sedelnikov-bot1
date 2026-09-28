from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.config import settings
from bot.database import get_session, get_all_completed_screenings, get_screening_with_candidate, update_screening_step
from bot.keyboards import admin_candidate_keyboard
from bot.database.models import ScreeningStatus

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
        await update_screening_step(session, screening_id, status=ScreeningStatus.REJECTED)
        await session.commit()

    await callback.answer("❌ Отклонён", show_alert=True)
    await callback.message.edit_text(
        callback.message.html_text + "\n\n❌ <b>Статус изменён на: REJECTED</b>",
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