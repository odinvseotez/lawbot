"""
Хендлеры для ассистентов и общие (стадии/задачи/отчёты, доступные обеим ролям).
Этот роутер подключается ПОСЛЕ owner-роутера, поэтому сюда попадают только
сообщения не от владельца (его перехватил owner-роутер) — кроме общих callback'ов,
которые мы аккуратно разруливаем по факту привязки.
"""
from aiogram import F, Router
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import db
import formatting as fmt
from keyboards import (
    assistant_main_menu,
    case_card_kb_assistant,
    court_links_kb,
)
from states import SendReport

router = Router()


# ---------------------------------------------------------------------------
#  Привязка ассистента: /join КОД
# ---------------------------------------------------------------------------
@router.message(F.text.startswith("/join"))
async def assistant_join(message: Message, command: CommandObject = None):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: <code>/join КОД</code> (код выдаёт юрист).")
        return
    aid = int(parts[1])
    assistant = await db.get_assistant(aid)
    if not assistant:
        await message.answer("Код не найден. Уточните код у юриста.")
        return
    if assistant["tg_id"] and assistant["tg_id"] != message.from_user.id:
        await message.answer("Этот код уже привязан к другому пользователю.")
        return
    await db.link_assistant_tg(aid, message.from_user.id)
    await message.answer(
        f"✅ Готово, {assistant['full_name']}! Вы привязаны как ассистент.\n"
        f"Теперь вам будут приходить задачи и запросы отчётов.",
        reply_markup=assistant_main_menu(),
    )
    # Уведомим владельца
    try:
        uname = f" (@{message.from_user.username})" if message.from_user.username else ""
        await message.bot.send_message(
            config.OWNER_ID,
            f"🔔 Ассистент {assistant['full_name']}{uname} привязался к боту.",
        )
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
#  /start для не-владельца
# ---------------------------------------------------------------------------
@router.message(F.text == "/start")
async def assistant_start(message: Message, state: FSMContext):
    await state.clear()
    assistant = await db.get_assistant_by_tg(message.from_user.id)
    if assistant:
        await message.answer(
            f"👋 Здравствуйте, {assistant['full_name']}!\nИспользуйте меню снизу.",
            reply_markup=assistant_main_menu(),
        )
    else:
        await message.answer(
            "👋 Здравствуйте! Это бот для ведения дел.\n\n"
            "Если вы ассистент — попросите у юриста код привязки и отправьте "
            "<code>/join КОД</code>."
        )


@router.message(F.text == "🔗 Ссылки на суды")
async def assistant_links(message: Message):
    await message.answer("Полезные ссылки:", reply_markup=court_links_kb())


# ---------------------------------------------------------------------------
#  Мои дела (ассистент)
# ---------------------------------------------------------------------------
@router.message(F.text == "📁 Мои дела")
async def my_cases(message: Message):
    assistant = await db.get_assistant_by_tg(message.from_user.id)
    if not assistant:
        await message.answer("Вы не привязаны. Отправьте <code>/join КОД</code>.")
        return
    rows = await db.list_cases_for_assistant(assistant["id"], status="open")
    if not rows:
        await message.answer("Активных дел за вами пока нет.")
        return
    from keyboards import cases_list_kb

    await message.answer(
        f"Ваших активных дел: {len(rows)}",
        reply_markup=cases_list_kb(rows, prefix="acase"),
    )


@router.callback_query(F.data.startswith("acase:"))
async def assistant_show_case(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    assistant = await db.get_assistant_by_tg(call.from_user.id)
    case = await db.get_case(case_id)
    if not case or not assistant or case["assistant_id"] != assistant["id"]:
        await call.answer("Дело недоступно", show_alert=True)
        return
    await call.message.answer(
        fmt.case_card(dict(case), for_owner=False),
        reply_markup=case_card_kb_assistant(case_id),
        disable_web_page_preview=True,
    )
    await call.answer()


# ---------------------------------------------------------------------------
#  Общие callback'и: стадии и задачи (видны обеим ролям, но с проверкой)
#  ВАЖНО: эти обработчики ловят колбэки от ассистента; у владельца их
#  перехватывает owner-роутер выше.
# ---------------------------------------------------------------------------
async def _assistant_can_access(user_id: int, case_id: int) -> bool:
    assistant = await db.get_assistant_by_tg(user_id)
    if not assistant:
        return False
    case = await db.get_case(case_id)
    return bool(case and case["assistant_id"] == assistant["id"])


@router.callback_query(F.data.startswith("stages:"))
async def assistant_stages(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    if not await _assistant_can_access(call.from_user.id, case_id):
        await call.answer("Нет доступа", show_alert=True)
        return
    rows = await db.list_stages(case_id)
    if not rows:
        await call.message.answer("По делу пока нет записей о стадиях.")
    else:
        text = "<b>Движение дела:</b>\n" + "\n".join(fmt.stage_line(s) for s in rows)
        await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data.startswith("tasks:"))
async def assistant_tasks(call: CallbackQuery):
    case_id = int(call.data.split(":")[1])
    if not await _assistant_can_access(call.from_user.id, case_id):
        await call.answer("Нет доступа", show_alert=True)
        return
    rows = await db.list_tasks_for_case(case_id)
    if not rows:
        await call.message.answer("По делу пока нет задач.")
    else:
        text = "<b>Ваши задачи по делу:</b>\n\n" + "\n\n".join(
            fmt.task_line(t) for t in rows
        )
        await call.message.answer(text)
    await call.answer()


# ---------------------------------------------------------------------------
#  Отметка «выполнено» по задаче
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("taskdone:"))
async def task_done(call: CallbackQuery):
    task_id = int(call.data.split(":")[1])
    task = await db.get_task(task_id)
    if not task:
        await call.answer("Задача не найдена", show_alert=True)
        return

    # Доступ: владелец всегда, ассистент — только своя задача
    is_owner = call.from_user.id == config.OWNER_ID
    if not is_owner:
        assistant = await db.get_assistant_by_tg(call.from_user.id)
        if not assistant or task["assistant_id"] != assistant["id"]:
            await call.answer("Нет доступа", show_alert=True)
            return

    await db.mark_task_done(task_id)
    await call.answer("Отмечено как выполнено ✅")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass

    # Уведомим владельца (если отметил ассистент)
    if not is_owner:
        who = task["assistant_name"] or "ассистент"
        try:
            await call.bot.send_message(
                config.OWNER_ID,
                f"✅ {who} отметил(а) задачу #{task_id} выполненной:\n"
                f"«{task['description']}»\nДело: {task['case_title']}",
            )
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
#  Отправка отчёта ассистентом
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("report:"))
async def report_start(call: CallbackQuery, state: FSMContext):
    case_id = int(call.data.split(":")[1])
    if not await _assistant_can_access(call.from_user.id, case_id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(SendReport.text)
    await state.update_data(case_id=case_id)
    await call.message.answer("Напишите отчёт о проделанной работе по делу:")
    await call.answer()


@router.message(SendReport.text)
async def report_save(message: Message, state: FSMContext):
    data = await state.get_data()
    case_id = data["case_id"]
    assistant = await db.get_assistant_by_tg(message.from_user.id)
    assistant_id = assistant["id"] if assistant else None

    text = message.text.strip()
    await db.add_report(case_id, assistant_id, text)
    # Отчёт также фиксируем как стадию для истории
    author = assistant["full_name"] if assistant else "ассистент"
    await db.add_stage(case_id, f"Отчёт: {text}", author=author)
    await state.clear()
    await message.answer("✅ Отчёт отправлен юристу. Спасибо!")

    case = await db.get_case(case_id)
    try:
        await message.bot.send_message(
            config.OWNER_ID,
            f"📩 <b>Отчёт от {author}</b> по делу #{case_id} "
            f"({case['title'] if case else '—'}):\n\n{text}",
        )
    except Exception:  # noqa: BLE001
        pass
