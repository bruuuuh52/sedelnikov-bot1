from typing import Any
from aiogram.fsm.state import StatesGroup, State


class ScreeningStates(StatesGroup):
    """Динамические состояния на основе конфига вопросов."""
    choose_vacancy = State()      # Выбор вакансии (если несколько)
    consent = State()             # Согласие на обработку персональных данных
    answering = State()           # Прохождение вопросов (текущий вопрос в FSM data)
    confirm = State()             # Подтверждение перед отправкой


# Вспомогательные функции для работы с FSM data

QUESTION_INDEX_KEY = "q_index"
SCREENING_ID_KEY = "screening_id"
VACANCY_ID_KEY = "vacancy_id"
CANDIDATE_ID_KEY = "candidate_id"
ANSWERS_KEY = "answers"  # dict: question_id -> value


def get_current_question_index(data: dict) -> int:
    return data.get(QUESTION_INDEX_KEY, 0)


def set_current_question_index(data: dict, index: int):
    data[QUESTION_INDEX_KEY] = index


def get_answers(data: dict) -> dict:
    return data.get(ANSWERS_KEY, {})


def set_answer(data: dict, question_id: str, value: Any):
    answers = get_answers(data)
    answers[question_id] = value
    data[ANSWERS_KEY] = answers


def get_answer(data: dict, question_id: str) -> Any:
    return get_answers(data).get(question_id)