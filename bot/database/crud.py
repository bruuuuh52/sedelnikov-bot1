from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Candidate, Vacancy, Screening, ScreeningStatus


# --- Whitelist для безопасного обновления полей скрининга ---
SCREENING_ALLOWED_FIELDS = {
    "experience_years",
    "stack",
    "salary_expectation",
    "relocation",
    "portfolio_url",
    "status",
    "vacancy_id",
}


async def _get_candidate_by_tg_id(session: AsyncSession, telegram_id: int) -> Candidate | None:
    result = await session.execute(select(Candidate).where(Candidate.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_or_create_candidate(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    full_name: str | None = None,
) -> Candidate:
    candidate = await _get_candidate_by_tg_id(session, telegram_id)
    if candidate:
        if username and candidate.username != username:
            candidate.username = username
        if full_name and candidate.full_name != full_name:
            candidate.full_name = full_name
        return candidate
    candidate = Candidate(telegram_id=telegram_id, username=username, full_name=full_name)
    session.add(candidate)
    await session.flush()
    return candidate


async def update_candidate_contacts(
    session: AsyncSession, telegram_id: int, phone: str | None = None, email: str | None = None
) -> Candidate | None:
    candidate = await _get_candidate_by_tg_id(session, telegram_id)
    if candidate:
        if phone:
            candidate.phone = phone
        if email:
            candidate.email = email
        await session.flush()
    return candidate


async def create_screening(
    session: AsyncSession,
    candidate_id: int,
    vacancy_id: int | None = None,
) -> Screening:
    screening = Screening(candidate_id=candidate_id, vacancy_id=vacancy_id)
    session.add(screening)
    await session.flush()
    return screening


async def update_screening_step(
    session: AsyncSession,
    screening_id: int,
    **kwargs,
) -> Screening | None:
    result = await session.execute(select(Screening).where(Screening.id == screening_id))
    screening = result.scalar_one_or_none()
    if screening:
        for key, value in kwargs.items():
            if key in SCREENING_ALLOWED_FIELDS:
                setattr(screening, key, value)
        await session.flush()
    return screening


async def complete_screening(session: AsyncSession, screening_id: int) -> Screening | None:
    return await update_screening_step(
        session,
        screening_id,
        status=ScreeningStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )


async def get_screening_with_candidate(session: AsyncSession, screening_id: int):
    result = await session.execute(
        select(Screening, Candidate)
        .join(Candidate, Screening.candidate_id == Candidate.id)
        .where(Screening.id == screening_id)
    )
    return result.first()


async def get_candidate_screenings(session: AsyncSession, candidate_id: int) -> list[Screening]:
    result = await session.execute(
        select(Screening).where(Screening.candidate_id == candidate_id).order_by(Screening.created_at.desc())
    )
    return list(result.scalars().all())


async def get_all_completed_screenings(session: AsyncSession, limit: int = 50, offset: int = 0):
    result = await session.execute(
        select(Screening, Candidate, Vacancy)
        .join(Candidate, Screening.candidate_id == Candidate.id)
        .outerjoin(Vacancy, Screening.vacancy_id == Vacancy.id)
        .where(Screening.status == ScreeningStatus.COMPLETED)
        .order_by(Screening.completed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.all()


async def create_vacancy(
    session: AsyncSession,
    title: str,
    description: str | None = None,
    required_stack: str | None = None,
    experience_min_years: int | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
) -> Vacancy:
    vacancy = Vacancy(
        title=title,
        description=description,
        required_stack=required_stack,
        experience_min_years=experience_min_years,
        salary_min=salary_min,
        salary_max=salary_max,
    )
    session.add(vacancy)
    await session.flush()
    return vacancy


async def get_active_vacancies(session: AsyncSession) -> list[Vacancy]:
    result = await session.execute(select(Vacancy).where(Vacancy.is_active == True))
    return list(result.scalars().all())