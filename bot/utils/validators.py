import re
from typing import Optional


PHONE_REGEX = re.compile(r"^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
SALARY_REGEX = re.compile(r"^\d{3,7}$")  # 1000 - 9999999
YEARS_REGEX = re.compile(r"^\d{1,2}$")  # 0-99
STACK_MIN_LEN = 3
STACK_MAX_LEN = 1000
PORTFOLIO_MAX_LEN = 500


def validate_phone(text: str) -> Optional[str]:
    """Возвращает нормализованный телефон или None если невалидно."""
    cleaned = re.sub(r"[\s\-\(\)]", "", text)
    if PHONE_REGEX.match(cleaned):
        return cleaned
    return None


def validate_email(text: str) -> Optional[str]:
    text = text.strip().lower()
    if EMAIL_REGEX.match(text):
        return text
    return None


def validate_salary(text: str) -> Optional[int]:
    """Возвращает зарплату в рублях или None."""
    cleaned = re.sub(r"[\s\.]", "", text)
    if SALARY_REGEX.match(cleaned):
        return int(cleaned)
    return None


def validate_experience_years(text: str) -> Optional[int]:
    """Возвращает годы опыта или None."""
    cleaned = text.strip()
    if YEARS_REGEX.match(cleaned):
        years = int(cleaned)
        if 0 <= years <= 50:
            return years
    # Попытка извлечь число из фразы "3 года", "5 лет" и т.д.
    match = re.search(r"(\d+)", cleaned)
    if match:
        years = int(match.group(1))
        if 0 <= years <= 50:
            return years
    return None


def validate_stack(text: str) -> Optional[str]:
    """Валидация стека — просто длина."""
    text = text.strip()
    if STACK_MIN_LEN <= len(text) <= STACK_MAX_LEN:
        return text
    return None


def validate_portfolio(text: str) -> Optional[str]:
    """Валидация URL портфолио."""
    text = text.strip()
    if not text:
        return None
    if len(text) > PORTFOLIO_MAX_LEN:
        return None
    # Простая проверка URL
    if text.startswith(("http://", "https://", "github.com/", "gitlab.com/")):
        return text
    # Добавим https:// если забыли
    if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
        return "https://" + text
    return None


def parse_relocation_choice(text: str) -> Optional[str]:
    """Парсит выбор релокации в стандартизированное значение."""
    text = text.strip().lower()
    if any(kw in text for kw in ("релок", "relocat", "готов", "переезж", "move")):
        return "ready"
    if any(kw in text for kw in ("remote", "удален", "дистанц", "home", "дом")):
        return "remote_only"
    if any(kw in text for kw in ("не готов", "не могу", "нет", "no", "отказ")):
        return "not_ready"
    return None