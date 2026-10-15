"""FSM states for multi-step admin flows."""
from aiogram.fsm.state import State, StatesGroup


class AddMovie(StatesGroup):
    code = State()
    name = State()
    description = State()
    link = State()
    file = State()


class EditMovie(StatesGroup):
    code = State()
    value = State()


class DeleteMovie(StatesGroup):
    code = State()
