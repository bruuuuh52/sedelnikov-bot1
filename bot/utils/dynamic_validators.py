import re
from typing import Optional, Any

from bot.config_loader import Question


PHONE_REGEX = re.compile(r"^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
URL_REGEX = re.compile(r"^https?://.+")
USERNAME_REGEX = re.compile(r"^@?[a-zA-Z0-9_]{3,50}$")


def validate_answer(question: Question, text: str) -> Optional[Any]:
    """
    Валидирует ответ пользователя согласно типу вопроса.
    Возвращает нормализованное значение или None если невалидно.
    """
    text = text.strip()

    # Специфичная валидация для phone
    if question.id == "phone":
        # Нормализуем телефон: убираем пробелы, скобки, дефисы
        cleaned = re.sub(r"[\s\(\)\-]", "", text)
        if PHONE_REGEX.match(cleaned):
            # Добавляем + если нет
            if not cleaned.startswith("+"):
                cleaned = "+" + cleaned
            return cleaned
        return None

    # Специфичная валидация для username
    if question.id == "username":
        # Убираем @ в начале если есть
        username = text.lstrip("@")
        if USERNAME_REGEX.match(text):
            return username
        return None

    if question.type == "contact":
        # Обрабатывается отдельно в хендлере (contact object или текст)
        return None

    if question.type == "choice":
        # Проверка: нажата кнопка или введен свой вариант
        if text in question.options:
            return question.options[text]
        if question.allow_custom:
            # Для experience_years требуем число
            if question.id == "experience_years":
                match = re.search(r"(\d+)", text)
                if match:
                    val = int(match.group(1))
                    if 0 <= val <= 50:
                        return val
                return None  # Нет цифр или вне диапазона
            # Для free_evenings и остальных - текст как есть
            return text
        return None

    if question.type == "text":
        if question.min_length <= len(text) <= question.max_length:
            return text
        return None

    if question.type == "number":
        # Убираем пробелы и непечатные символы
        cleaned = re.sub(r"[\s\.]", "", text)
        if cleaned.isdigit():
            val = int(cleaned)
            if question.min_value <= val <= question.max_value:
                return val
        return None

    if question.type == "url":
        if not text:
            return None  # Пусто = пропуск (проверяется required)
        if URL_REGEX.match(text):
            return text
        # Попытка добавить https://
        if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
            return "https://" + text
        return None

    return None


def format_answer_for_display(question: Question, value: Any) -> str:
    """Форматирует значение для отображения в подтверждении."""
    if value is None:
        return "—"

    # Для interview_date показываем label кнопки (дата на русском)
    if question.id == "interview_date":
        for label, val in question.options.items():
            if val == value:
                return label
        return str(value)

    if question.type == "choice":
        # Найти label по value
        for label, val in question.options.items():
            if val == value:
                return label
        return str(value)

    if question.type == "number":
        # Для зарплаты показываем рубль, для возраста — просто число
        if question.id == "salary_expectation":
            return f"{value:,} ₽".replace(",", " ")
        return str(value)

    if question.type == "url":
        return f"<a href='{value}'>{value}</a>"

    return str(value)


def get_question_prompt(question: Question) -> str:
    """Возвращает текст подсказки для вопроса."""
    base = f"📋 <b>Вопрос:</b> {question.text}"

    if question.type == "choice" and question.options:
        options_text = "\n".join(f"  • {label}" for label in question.options.keys())
        base += f"\n\n<b>Варианты:</b>\n{options_text}"
        if question.allow_custom:
            base += "\n  • Или введите свой вариант"

    if question.placeholder:
        base += f"\n\n<i>Пример: {question.placeholder}</i>"

    if not question.required:
        base += "\n\n<i>(необязательно — можно пропустить)</i>"

    return base