"""Состояния конечного автомата (FSM) для пошаговых диалогов."""
from aiogram.fsm.state import State, StatesGroup


class NewClient(StatesGroup):
    name = State()
    contact = State()
    note = State()


class NewAssistant(StatesGroup):
    full_name = State()
    username = State()


class NewCase(StatesGroup):
    client = State()
    title = State()
    description = State()
    assistant = State()
    price = State()
    fee = State()
    court_link = State()


class NewTask(StatesGroup):
    description = State()
    deadline = State()
    remind = State()


class AddStage(StatesGroup):
    text = State()


class SendReport(StatesGroup):
    text = State()
