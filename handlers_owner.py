"""
Хендлеры для владельца (главного юриста).
Доступ ограничен фильтром OwnerFilter — только OWNER_ID.
"""
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import db
import formatting as fmt
from dateparse import parse_deadline
from keyboards import (
    assistants_pick_kb,
    case_card_kb,
    cases_list_kb,
    court_links_kb,
    owner_main_menu,
    remind_before_kb,
)
from states import AddStage, NewAssistant, NewCase, NewClient, NewTask

router = Router()


class OwnerFilter(BaseFilter):
    async def __call__(self, event) -> bool:
        uid = event.from_user.id if event.from_user else None
        return uid == config.OWNER_ID


# Применяем фильтр ко всем сообщениям и колбэкам в этом роутере
router.message.filter(OwnerFilter())
router.callback_query.filter(OwnerFilter())


# ---------------------------------------------------------------------------
#  /start и главное меню
# ---------------------------------------------------------------------------
@router.message(F.text == "/start")
async def owner_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Здравствуйте! Это ваш бот для ведения дел и ассистентов.\n\n"
        "Используйте меню снизу.",
        reply_markup=owner_main_menu(),
    )


@router.message(F.text == "🔗 Ссылки на суды")
async def owner_links(message: Message):
    await message.answer("Полезные ссылки:", reply_markup=court_links_kb())


# ---------------------------------------------------------------------------
#  Ассистенты
# ---------------------------------------------------------------------------
@router.message(F.text == "🧑‍💼 Ассистенты")
async def owner_assistants(message: Message):
    rows = await db.list_assistants(active_only=False)
    if not rows:
        await message.answer(
            "Ассистентов пока нет.\nДобавьте: напишите /add_assistant"
        )
        return
    lines = ["<b>Ваши ассистенты:</b>\n"]
    for a in rows:
        status = "🟢" if a["active"] else "⚪"
        linked = "✅ привязан" if a["tg_id"] else f"⏳ код для привязки: <code>{a['id']}</code>"
        uname = f" (@{a['username']})" if a["username"] else ""
        lines.append(f"{status} #{a['id']} {a['full_name']}{uname} — {linked}")
    lines.append(
        "\nЧтобы ассистент привязался: он открывает бота и отправляет\n"
        "<code>/join КОД</code> (код — число после #)."
    )
    lines.append("Добавить нового: /add_assistant")
    await message.answer("\n".join(lines))


@router.message(F.text == "/add_assistant")
async def add_assistant_start(message: Message, state: FSMContext):
    await state.set_state(NewAssistant.full_name)
    await message.answer("Введите ФИО ассистента:")


@router.message(NewAssistant.full_name)
async def add_assistant_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(NewAssistant.username)
    await message.answer(
        "Введите @username ассистента (или «-», если нет):"
    )


@router.message(NewAssistant.username)
async def add_assistant_username(message: Message, state: FSMContext):
    data = await state.get_data()
    uname = message.text.strip().lstrip("@")
    if uname == "-":
        uname = None
    aid = await db.add_assistant(data["full_name"], uname)
    await state.clear()
    await message.answer(
        f"✅ Ассистент добавлен. Его код привязки: <code>{aid}</code>\n\n"
        f"Передайте ассистенту: пусть откроет этого бота и отправит\n"
        f"<code>/join {aid}</code>"
    )


# ---------------------------------------------------------------------------
#  Клиенты
# ---------------------------------------------------------------------------
@router.message(F.text == "👥 Клиенты")
async def owner_clients(message: Message):
    rows = await db.list_clients()
    if not rows:
        await message.answer("Клиентов пока нет.\nДобавить: /add_client")
        return
    lines = ["<b>Клиенты:</b>\n"]
    for c in rows:
        contact = f" · {c['contact']}" if c["contact"] else ""
        lines.append(f"#{c['id']} {c['name']}{contact}")
    lines.append("\nДобавить нового: /add_client")
    await message.answer("\n".join(lines))


@router.message(F.text == "/add_client")
async def add_client_start(message: Message, state: FSMContext):
    await state.set_state(NewClient.name)
    await message.answer("Имя / наименование клиента:")


@router.message(NewClient.name)
async def add_client_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(NewClient.contact)
    await message.answer("Контакт клиента (телефон/почта) или «-»:")


@router.message(NewClient.contact)
async def add_client_contact(message: Message, state: FSMContext):
    contact = message.text.strip()
    await state.update_data(contact=None if contact == "-" else contact)
    await state.set_state(NewClient.note)
    await message.answer("Примечание о клиенте или «-»:")


@router.message(NewClient.note)
async def add_client_note(message: Message, state: FSMContext):
    data = await state.get_data()
    note = message.text.strip()
    cid = await db.add_client(
        data["name"], data["contact"], None if note == "-" else note
    )
    await state.clear()
    await message.answer(f"✅ Клиент #{cid} добавлен.")


# ---------------------------------------------------------------------------
#  Новое дело (пошагово)
# ---------------------------------------------------------------------------
@router.message(F.text == "➕ Новое дело")
async def new_case_start(message: Message, state: FSMContext):
    clients = await db.list_clients()
    if not clients:
        await message.answer(
            "Сначала добавьте хотя бы одного клиента: /add_client"
        )
        return
    await state.set_state(NewCase.client)
    kb = cases_list_kb(
        [{"id": c["id"], "title": c["name"], "client_name": ""} for c in clients],
        prefix="pickclient",
    )
    await message.answer("Выберите клиента для дела:", reply_markup=kb)


@router.callback_query(NewCase.client, F.data.startswith("pickclient:"))
async def new_case_client(call: CallbackQuery, state: FSMContext):
    client_id = int(call.data.split(":")[1])
    await state.update_data(client_id=client_id)
    await state.set_state(NewCase.title)
    await call.message.answer("Краткое название дела:")
    await call.answer()


@router.message(NewCase.title)
async def new_case_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(NewCase.description)
    await message.answer("Суть дела (краткое описание) или «-»:")


@router.message(NewCase.description)
async def new_case_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(description=None if desc == "-" else desc)
    assistants = await db.list_assistants()
    await state.set_state(NewCase.assistant)
    if assistants:
        kb = cases_list_kb(
            [{"id": a["id"], "title": a["full_name"], "client_name": ""} for a in assistants],
            prefix="pickassist",
        )
        await message.answer(
            "Кому отдаёте дело? Выберите ассистента или отправьте «-», "
            "чтобы пока не назначать:",
            reply_markup=kb,
        )
    else:
        await state.update_data(assistant_id=None)
        await state.set_state(NewCase.price)
        await message.answer("Стоимость услуги для клиента (число) или «-»:")


@router.callback_query(NewCase.assistant, F.data.startswith("pickassist:"))
async def new_case_assistant(call: CallbackQuery, state: FSMContext):
    aid = int(call.data.split(":")[1])
    await state.update_data(assistant_id=aid)
    await state.set_state(NewCase.price)
    await call.message.answer("Стоимость услуги для клиента (число) или «-»:")
    await call.answer()


@router.message(NewCase.assistant, F.text == "-")
async def new_case_no_assistant(message: Message, state: FSMContext):
    await state.update_data(assistant_id=None)
    await state.set_state(NewCase.price)
    await message.answer("Стоимость услуги для клиента (число) или «-»:")


def _parse_money(text: str) -> Decimal | None:
    text = text.strip().replace(" ", "").replace(",", ".")
    if text == "-":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


@router.message(NewCase.price)
async def new_case_price(message: Message, state: FSMContext):
    price = _parse_money(message.text)
    await state.update_data(price=price)
    await state.set_state(NewCase.fee)
    await message.answer("Доля ассистента (число) или «-»:")


@router.message(NewCase.fee)
async def new_case_fee(message: Message, state: FSMContext):
    fee = _parse_money(message.text)
    await state.update_data(assistant_fee=fee)
    await state.set_state(NewCase.court_link)
    await message.answer(
        "Ссылка на дело в КАД / на сайте суда или «-»:"
    )


@router.message(NewCase.court_link)
async def new_case_link(message: Message, state: FSMContext):
    link = message.text.strip()
    data = await state.get_data()
    case_id = await db.add_case(
        client_id=data["client_id"],
        title=data["title"],
        description=data.get("description"),
        assistant_id=data.get("assistant_id"),
        price=data.get("price"),
        assistant_fee=data.get("assistant_fee"),
        court_link=None if link == "-" else link,
    )
    await state.clear()
    case = await db.get_case(case_id)
    await message.answer("✅ Дело создано!")
    await message.answer(
        fmt.case_card(dict(case), for_owner=True),
        reply_markup=case_card_kb(case_id, case["fee_paid"]),
        disable_web_page_preview=True,
    )

    # Если назначен ассистент с привязкой — уведомим его
    if case["assistant_tg"]:
        try:
            await message.bot.send_message(
                case["assistant_tg"],
                f"📬 Вам назначено новое дело #{case_id}: <b>{case['title']}</b>\n"
                f"Клиент: {case['client_name']}",
            )
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
#  Список дел и карточка
# ---------------------------------------------------------------------------
@router.message(F.text == "📁 Дела")
async def owner_cases(message: Message):
    rows = await db.list_cases(status="open")
    if not rows:
        await message.answer("Открытых дел нет. Создайте: «➕ Новое дело».")
        return
    await message.answer(
        f"Открытых дел: {len(rows)}. Выберите для просмотра:",
        reply_markup=cases_list_kb(rows, prefix="case"),
    )


@router.callback_query(F.data.startswith("case:"))
async def show_case(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    case = await db.get_case(case_id)
    if not case:
        await call.answer("Дело не найдено", show_alert=True)
        return
    await call.message.answer(
        fmt.case_card(dict(case), for_owner=True),
        reply_markup=case_card_kb(case_id, case["fee_paid"]),
        disable_web_page_preview=True,
    )
    await call.answer()


@router.callback_query(F.data.startswith("togglepaid:"))
async def toggle_paid(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    case = await db.get_case(case_id)
    new_val = not case["fee_paid"]
    await db.set_fee_paid(case_id, new_val)
    await call.answer("Отметка обновлена ✅")
    case = await db.get_case(case_id)
    try:
        await call.message.edit_text(
            fmt.case_card(dict(case), for_owner=True),
            reply_markup=case_card_kb(case_id, case["fee_paid"]),
            disable_web_page_preview=True,
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("close:"))
async def close_case_cb(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    await db.close_case(case_id)
    await call.answer("Дело закрыто 🗄")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
#  Назначение ассистента из карточки
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("assign:"))
async def assign_start(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    assistants = await db.list_assistants()
    if not assistants:
        await call.answer("Сначала добавьте ассистентов (/add_assistant)", show_alert=True)
        return
    await call.message.answer(
        "Выберите ассистента:",
        reply_markup=assistants_pick_kb(assistants, case_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("setassist:"))
async def assign_set(call: CallbackQuery):
    _, case_id, aid = call.data.split(":")
    case_id, aid = int(case_id), int(aid)
    await db.assign_case(case_id, aid if aid else None)
    await call.answer("Ассистент обновлён ✅")
    case = await db.get_case(case_id)
    await call.message.answer(
        fmt.case_card(dict(case), for_owner=True),
        reply_markup=case_card_kb(case_id, case["fee_paid"]),
        disable_web_page_preview=True,
    )
    if aid and case["assistant_tg"]:
        try:
            await call.bot.send_message(
                case["assistant_tg"],
                f"📬 Вам назначено дело #{case_id}: <b>{case['title']}</b>",
            )
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
#  Стадии
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("stages:"))
async def show_stages(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    rows = await db.list_stages(case_id)
    if not rows:
        await call.message.answer("По делу пока нет записей о стадиях.")
    else:
        text = "<b>Движение дела:</b>\n" + "\n".join(fmt.stage_line(s) for s in rows)
        await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data.startswith("addstage:"))
async def add_stage_start(call: CallbackQuery, state: FSMContext):
    case_id = int(call.data.split(":")[1])
    await state.set_state(AddStage.text)
    await state.update_data(case_id=case_id)
    await call.message.answer("Опишите новую стадию / запись о движении дела:")
    await call.answer()


@router.message(AddStage.text)
async def add_stage_save(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.add_stage(data["case_id"], message.text.strip(), author="owner")
    await state.clear()
    await message.answer("✅ Стадия добавлена.")


# ---------------------------------------------------------------------------
#  Задачи
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("tasks:"))
async def show_tasks(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    rows = await db.list_tasks_for_case(case_id)
    if not rows:
        await call.message.answer("По делу пока нет задач.")
    else:
        text = "<b>Задачи по делу:</b>\n\n" + "\n\n".join(fmt.task_line(t) for t in rows)
        await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data.startswith("addtask:"))
async def add_task_start(call: CallbackQuery, state: FSMContext):
    case_id = int(call.data.split(":")[1])
    await state.set_state(NewTask.description)
    await state.update_data(case_id=case_id)
    await call.message.answer("Опишите задачу для ассистента:")
    await call.answer()


@router.message(NewTask.description)
async def add_task_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(NewTask.deadline)
    await message.answer(
        "Дедлайн задачи. Введите дату в формате <b>ДД.ММ.ГГГГ</b> "
        "или <b>ДД.ММ.ГГГГ ЧЧ:ММ</b>.\n"
        "Если без времени — поставится 18:00. Или отправьте «-», если без дедлайна:"
    )


@router.message(NewTask.deadline)
async def add_task_deadline(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "-":
        await state.update_data(deadline=None)
        # без дедлайна — напоминания не нужны, сохраняем сразу
        data = await state.get_data()
        task_id = await db.add_task(data["case_id"], data["description"], None, 24)
        await state.clear()
        await _notify_assistant_new_task(message, data["case_id"], task_id, data["description"], None)
        await message.answer("✅ Задача добавлена (без дедлайна).")
        return

    dl = parse_deadline(text)
    if dl is None:
        await message.answer(
            "Не понял дату. Пример: <code>31.12.2026 18:00</code>. Попробуйте ещё раз:"
        )
        return
    await state.update_data(deadline=dl)
    await state.set_state(NewTask.remind)
    await message.answer(
        f"Дедлайн: <b>{fmt.fmt_dt(dl)}</b>.\nЗа сколько напомнить ассистенту?",
        reply_markup=remind_before_kb(),
    )


@router.callback_query(NewTask.remind, F.data.startswith("remind:"))
async def add_task_remind(call: CallbackQuery, state: FSMContext):
    hours = int(call.data.split(":")[1])
    data = await state.get_data()
    task_id = await db.add_task(
        data["case_id"], data["description"], data["deadline"], hours
    )
    await state.clear()
    await call.message.answer(
        f"✅ Задача добавлена. Дедлайн {fmt.fmt_dt(data['deadline'])}, "
        f"напомню за {hours} ч."
    )
    await _notify_assistant_new_task(
        call.message, data["case_id"], task_id, data["description"], data["deadline"]
    )
    await call.answer()


async def _notify_assistant_new_task(message, case_id, task_id, description, deadline):
    """Сообщить ассистенту о новой задаче."""
    case = await db.get_case(case_id)
    if not case or not case["assistant_tg"]:
        return
    dl = fmt.fmt_dt(deadline) if deadline else "без дедлайна"
    try:
        from keyboards import task_done_kb

        await message.bot.send_message(
            case["assistant_tg"],
            f"🆕 <b>Новая задача</b> по делу #{case_id} ({case['title']}):\n\n"
            f"{description}\n\n⏰ Дедлайн: {dl}",
            reply_markup=task_done_kb(task_id),
        )
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
#  Запрос отчёта вручную
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("askreport:"))
async def ask_report(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    case = await db.get_case(case_id)
    if not case or not case["assistant_tg"]:
        await call.answer("У дела нет привязанного ассистента", show_alert=True)
        return
    from keyboards import case_card_kb_assistant

    try:
        await call.bot.send_message(
            case["assistant_tg"],
            f"📨 Запрос отчёта по делу #{case_id}: <b>{case['title']}</b>\n"
            f"Опишите, что сделано. Нажмите «📨 Отправить отчёт».",
            reply_markup=case_card_kb_assistant(case_id),
        )
        await call.answer("Запрос отправлен ассистенту ✅")
    except Exception as e:  # noqa: BLE001
        await call.answer(f"Не удалось отправить: {e}", show_alert=True)


# ---------------------------------------------------------------------------
#  Оплаты — сводка по неоплаченным
# ---------------------------------------------------------------------------
@router.message(F.text == "💰 Оплаты")
async def owner_payments(message: Message):
    rows = await db.list_cases(status=None)
    unpaid = [c for c in rows if c["assistant_fee"] and not c["fee_paid"] and c["assistant_id"]]
    if not unpaid:
        await message.answer("✅ Нет дел с неоплаченной долей ассистента.")
        return
    total = sum(c["assistant_fee"] for c in unpaid)
    lines = ["<b>Неоплаченные доли ассистентов:</b>\n"]
    for c in unpaid:
        lines.append(
            f"#{c['id']} {c['title']} — {c['assistant_name']}: "
            f"{fmt.fmt_money(c['assistant_fee'])}"
        )
    lines.append(f"\n<b>Итого к выплате: {fmt.fmt_money(total)}</b>")
    lines.append("\nОтметить оплату можно в карточке дела.")
    await message.answer("\n".join(lines))
