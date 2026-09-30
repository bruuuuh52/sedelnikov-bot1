from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from typing import Any

from bot.config_loader import get_config, Question


def build_question_keyboard(question: Question) -> ReplyKeyboardMarkup:
    """Строит клавиатуру для конкретного вопроса на основе конфига."""
    builder = ReplyKeyboardBuilder()

    if question.type == "contact":
        builder.button(text="📱 Поделиться контактом", request_contact=True)
        builder.button(text="✍️ Ввести вручную")

    elif question.type == "choice":
        for label in question.options.keys():
            builder.button(text=label)
        if question.allow_custom:
            builder.button(text="✍️ Ввести вручную")

    elif question.type in ("text", "number", "url"):
        # Для текстовых типов — только кнопка отмены (и пропуска если url)
        pass

    # Кнопка отмены всегда
    builder.button(text="❌ Отмена")

    # Кнопка пропуска для необязательных url/text
    if question.type == "url" and question.skip_button:
        builder.button(text="⏭️ Пропустить")

    # Раскладка: по 2 кнопки в ряд для choice, остальное по 1
    if question.type == "choice":
        cols = 2
        buttons_count = len(question.options) + (1 if question.allow_custom else 0) + 1  # + отмена
        if question.skip_button:
            buttons_count += 1
        # Просто adjust(2) для choice, остальное вертикально
        builder.adjust(2, *[1] * (buttons_count - 2))
    else:
        builder.adjust(1)

    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def build_confirm_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура подтверждения (финальный шаг)."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Всё верно, отправить")
    builder.button(text="🔄 Начать заново")
    builder.button(text="❌ Отмена")
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def build_consent_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура согласия на обработку персональных данных."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Согласен, продолжить")
    builder.button(text="❌ Не согласен")
    builder.adjust(1, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def build_vacancy_keyboard() -> InlineKeyboardMarkup:
    """Inline клавиатура выбора вакансии (если несколько)."""
    # Пока заглушка — используется из builders.py
    from bot.keyboards.builders import vacancy_choice_keyboard
    return vacancy_choice_keyboard([])


def build_admin_keyboard(screening_id: int) -> InlineKeyboardMarkup:
    """Inline клавиатура для админа."""
    from bot.keyboards.builders import admin_candidate_keyboard
    return admin_candidate_keyboard(screening_id)


def get_option_value(question: Question, label: str) -> Any:
    """Возвращает значение варианта по тексту кнопки."""
    return question.options.get(label)


def get_option_label(question: Question, value: Any) -> str:
    """Возвращает текст кнопки по значению (обратный поиск)."""
    for label, val in question.options.items():
        if val == value:
            return label
    return str(value)