from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path
import yaml
from datetime import datetime, timezone


@dataclass
class QuestionOption:
    """Вариант ответа для choice-вопроса: текст кнопки -> значение"""
    label: str
    value: Any


@dataclass
class Question:
    id: str
    text: str
    type: str                    # contact, choice, text, number, url
    required: bool = True
    save_to: str = "screening"   # candidate или screening
    options: dict[str, Any] = field(default_factory=dict)  # label -> value
    allow_custom: bool = False
    placeholder: str = ""
    min_length: int = 0
    max_length: int = 1000
    min_value: int = 0
    max_value: int = 10**9
    skip_button: bool = False


@dataclass
class ScreeningConfig:
    recipients: list[int]
    vacancy_title: str
    vacancy_description: str
    final_message: str
    questions: list[Question]

    @property
    def question_ids(self) -> list[str]:
        return [q.id for q in self.questions]

    @property
    def required_questions(self) -> list[Question]:
        return [q for q in self.questions if q.required]

    def get_question(self, qid: str) -> Optional[Question]:
        for q in self.questions:
            if q.id == qid:
                return q
        return None

    def get_next_question_id(self, current_id: str) -> Optional[str]:
        ids = self.question_ids
        if current_id in ids:
            idx = ids.index(current_id)
            if idx + 1 < len(ids):
                return ids[idx + 1]
        return None


def load_config(path: str | Path = "screening_config.yaml") -> ScreeningConfig:
    """Загружает и валидирует конфиг из YAML файла."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Валидация обязательных полей
    if "recipients" not in raw:
        raise ValueError("В конфиге отсутствует поле 'recipients'")
    if "vacancy" not in raw:
        raise ValueError("В конфиге отсутствует поле 'vacancy'")
    if "questions" not in raw:
        raise ValueError("В конфиге отсутствует поле 'questions'")

    recipients = raw["recipients"]
    if not isinstance(recipients, list) or not all(isinstance(x, int) for x in recipients):
        raise ValueError("recipients должен быть списком целых чисел (Telegram ID)")

    vacancy = raw["vacancy"]
    vacancy_title = vacancy.get("title", "Вакансия")
    vacancy_description = vacancy.get("description", "")
    final_message = raw.get("final_message", "")

    questions = []
    for i, q_raw in enumerate(raw["questions"]):
        if "id" not in q_raw:
            raise ValueError(f"Вопрос #{i} не имеет поля 'id'")
        if "text" not in q_raw:
            raise ValueError(f"Вопрос '{q_raw.get('id', i)}' не имеет поля 'text'")
        if "type" not in q_raw:
            raise ValueError(f"Вопрос '{q_raw['id']}' не имеет поля 'type'")

        q = Question(
            id=q_raw["id"],
            text=q_raw["text"],
            type=q_raw["type"],
            required=q_raw.get("required", True),
            save_to=q_raw.get("save_to", "screening"),
            options=q_raw.get("options", {}),
            allow_custom=q_raw.get("allow_custom", False),
            placeholder=q_raw.get("placeholder", ""),
            min_length=q_raw.get("min_length", 0),
            max_length=q_raw.get("max_length", 1000),
            min_value=q_raw.get("min_value", 0),
            max_value=q_raw.get("max_value", 10**9),
            skip_button=q_raw.get("skip_button", False),
        )
        questions.append(q)

    # Проверка уникальности id
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Найдены дублирующиеся id вопросов")

    return ScreeningConfig(
        recipients=recipients,
        vacancy_title=vacancy_title,
        vacancy_description=vacancy_description,
        final_message=final_message,
        questions=questions,
    )


# Глобальный экземпляр конфига (загружается при старте)
_config: ScreeningConfig | None = None


def get_config() -> ScreeningConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(path: str | Path = "screening_config.yaml") -> ScreeningConfig:
    global _config
    _config = load_config(path)
    return _config


def clear_config_cache() -> None:
    """Сбрасывает кэш конфига, заставляя перезагрузить при следующем вызове get_config()."""
    global _config
    _config = None


# Русские названия месяцев и дней недели (для форматирования дат без зависимости от локали)
RU_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}

RU_WEEKDAYS = {
    0: "понедельник", 1: "вторник", 2: "среда",
    3: "четверг", 4: "пятница", 5: "суббота", 6: "воскресенье"
}


def format_date_ru(dt: datetime) -> str:
    """Форматирует дату на русском: '6 октября, вторник, 17:30'"""
    day = dt.day
    month = RU_MONTHS[dt.month]
    weekday = RU_WEEKDAYS[dt.weekday()]
    time = dt.strftime("%H:%M")
    return f"{day} {month}, {weekday}, {time}"


async def update_interview_date_options():
    """
    Обновляет варианты ответа для вопроса interview_date
    актуальными слотами из БД.
    """
    from bot.database import get_session
    from bot.database.crud import get_available_slots
    
    config = get_config()
    question = config.get_question("interview_date")
    if not question:
        return
    
    async with get_session() as session:
        slots = await get_available_slots(session)
    
    # Формируем options: label -> slot_id (как строка)
    options = {}
    for slot in slots:
        # Формат: "6 октября, вторник, 17:30 (осталось 3 из 5)"
        date_str = format_date_ru(slot.date)
        available = slot.max_slots - slot.booked_slots
        label = f"{date_str} (осталось {available} из {slot.max_slots})"
        options[label] = str(slot.id)
    
    question.options = options