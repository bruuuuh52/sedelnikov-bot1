from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


# Константы для маппинга кнопок -> значений
RELOCATION_BUTTON_MAP = {
    "✅ Готов к релокации": "ready",
    "🏠 Только remote": "remote_only",
    "🤔 Не готов переезжать": "not_ready",
}

EXPERIENCE_BUTTON_MAP = {
    "👶 0–1 год": 0,
    "🧑 1–3 года": 2,
    "👨‍💻 3–5 лет": 4,
    "👑 5+ лет": 7,
}


# --- Reply keyboards (клавиатура под полем ввода) ---

def contact_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка 'Поделиться контактом' + отмена."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Поделиться контактом", request_contact=True)
    builder.button(text="✍️ Ввести вручную")
    builder.button(text="❌ Отмена")
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def experience_keyboard() -> ReplyKeyboardMarkup:
    """Диапазоны опыта + ручной ввод + отмена."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="👶 0–1 год")
    builder.button(text="🧑 1–3 года")
    builder.button(text="👨‍💻 3–5 лет")
    builder.button(text="👑 5+ лет")
    builder.button(text="✍️ Ввести вручную")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def relocation_keyboard() -> ReplyKeyboardMarkup:
    """Готовность к переезду/remote."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Готов к релокации")
    builder.button(text="🏠 Только remote")
    builder.button(text="🤔 Не готов переезжать")
    builder.button(text="❌ Отмена")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def confirm_keyboard() -> ReplyKeyboardMarkup:
    """Подтверждение / начать заново."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Всё верно, отправить")
    builder.button(text="🔄 Начать заново")
    builder.button(text="❌ Отмена")
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def skip_keyboard() -> ReplyKeyboardMarkup:
    """Пропустить опциональный шаг (портфолио)."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="⏭️ Пропустить")
    builder.button(text="❌ Отмена")
    builder.adjust(1, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Просто отмена."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


# --- Inline keyboards (под сообщением) ---

def vacancy_choice_keyboard(vacancies: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Выбор вакансии (если несколько активных)."""
    builder = InlineKeyboardBuilder()
    for vac_id, title in vacancies:
        builder.button(text=title, callback_data=f"vacancy:{vac_id}")
    builder.button(text="❌ Отмена", callback_data="vacancy:cancel")
    builder.adjust(1)
    return builder.as_markup()


def admin_candidate_keyboard(screening_id: int) -> InlineKeyboardMarkup:
    """Действия админа с кандидатом."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 Подробнее", callback_data=f"admin:detail:{screening_id}")
    builder.button(text="✅ Принять", callback_data=f"admin:accept:{screening_id}")
    builder.button(text="❌ Отклонить", callback_data=f"admin:reject:{screening_id}")
    builder.adjust(1, 2)
    return builder.as_markup()