"""Клавиатуры (inline и reply) для интерфейса бота."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config


# --- Главное меню владельца (reply-клавиатура снизу) ---
def owner_main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📁 Дела"), KeyboardButton(text="➕ Новое дело")],
        [KeyboardButton(text="👥 Клиенты"), KeyboardButton(text="🧑‍💼 Ассистенты")],
        [KeyboardButton(text="🔗 Ссылки на суды"), KeyboardButton(text="💰 Оплаты")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def assistant_main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📁 Мои дела")],
        [KeyboardButton(text="🔗 Ссылки на суды")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# --- Inline-кнопки ---
def court_links_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for name, url in config.COURT_LINKS.items():
        b.row(InlineKeyboardButton(text=name, url=url))
    return b.as_markup()


def case_card_kb(case_id: int, fee_paid: bool) -> InlineKeyboardMarkup:
    """Кнопки под карточкой дела (для владельца)."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📝 Стадии", callback_data=f"stages:{case_id}"),
        InlineKeyboardButton(text="✅ Задачи", callback_data=f"tasks:{case_id}"),
    )
    b.row(
        InlineKeyboardButton(text="➕ Стадия", callback_data=f"addstage:{case_id}"),
        InlineKeyboardButton(text="➕ Задача", callback_data=f"addtask:{case_id}"),
    )
    paid_label = "💸 Снять отметку оплаты" if fee_paid else "💵 Отметить: оплачено"
    b.row(InlineKeyboardButton(text=paid_label, callback_data=f"togglepaid:{case_id}"))
    b.row(
        InlineKeyboardButton(text="🧑‍💼 Назначить ассистента", callback_data=f"assign:{case_id}"),
        InlineKeyboardButton(text="📨 Запросить отчёт", callback_data=f"askreport:{case_id}"),
    )
    b.row(InlineKeyboardButton(text="🗄 Закрыть дело", callback_data=f"close:{case_id}"))
    return b.as_markup()


def case_card_kb_assistant(case_id: int) -> InlineKeyboardMarkup:
    """Кнопки под карточкой дела (для ассистента)."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📝 Стадии", callback_data=f"stages:{case_id}"),
        InlineKeyboardButton(text="✅ Мои задачи", callback_data=f"tasks:{case_id}"),
    )
    b.row(InlineKeyboardButton(text="📨 Отправить отчёт", callback_data=f"report:{case_id}"))
    return b.as_markup()


def task_done_kb(task_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Выполнено", callback_data=f"taskdone:{task_id}"))
    return b.as_markup()


def assistants_pick_kb(assistants, case_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in assistants:
        b.row(
            InlineKeyboardButton(
                text=a["full_name"], callback_data=f"setassist:{case_id}:{a['id']}"
            )
        )
    b.row(InlineKeyboardButton(text="— Снять ассистента —", callback_data=f"setassist:{case_id}:0"))
    return b.as_markup()


def cases_list_kb(cases, prefix: str = "case") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in cases:
        label = f"#{c['id']} {c['title']} — {c['client_name']}"
        b.row(InlineKeyboardButton(text=label[:60], callback_data=f"{prefix}:{c['id']}"))
    return b.as_markup()


def remind_before_kb() -> InlineKeyboardMarkup:
    """Выбор, за сколько напомнить о дедлайне."""
    b = InlineKeyboardBuilder()
    for hours, label in [(2, "2 часа"), (6, "6 часов"), (24, "1 день"), (48, "2 дня"), (72, "3 дня")]:
        b.button(text=label, callback_data=f"remind:{hours}")
    b.adjust(3, 2)
    return b.as_markup()


def confirm_skip_kb(skip_cb: str = "skip") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Пропустить", callback_data=skip_cb))
    return b.as_markup()
