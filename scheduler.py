"""
Планировщик фоновых задач (APScheduler):
  1) Еженедельный опрос ассистентов — запрос отчёта по каждому активному делу.
  2) Ежечасная проверка приближающихся дедлайнов с напоминанием ассистенту
     (и дублем владельцу).
"""
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import db
import formatting as f
from keyboards import case_card_kb_assistant, task_done_kb

log = logging.getLogger(__name__)


async def weekly_poll(bot: Bot) -> None:
    """Раз в неделю просим у ассистентов отчёт по каждому открытому делу."""
    rows = await db.cases_with_active_assistant()
    if not rows:
        return

    # Группируем по ассистенту, чтобы не спамить отдельным сообщением на каждое дело.
    by_assistant: dict[int, list] = {}
    for r in rows:
        by_assistant.setdefault(r["assistant_tg"], []).append(r)

    owner_summary = ["📊 <b>Еженедельный опрос ассистентов отправлен.</b>\n"]

    for tg_id, cases in by_assistant.items():
        name = cases[0]["assistant_name"]
        owner_summary.append(f"\n<b>{name}</b>:")
        for c in cases:
            owner_summary.append(f"  • #{c['id']} {c['title']} ({c['client_name']})")
            text = (
                f"📅 <b>Еженедельный запрос отчёта</b>\n\n"
                f"Дело #{c['id']}: <b>{c['title']}</b>\n"
                f"Клиент: {c['client_name']}\n\n"
                f"Пожалуйста, опишите, что сделано за неделю. "
                f"Нажмите «📨 Отправить отчёт» под карточкой дела."
            )
            try:
                await bot.send_message(
                    tg_id, text, reply_markup=case_card_kb_assistant(c["id"])
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Не удалось написать ассистенту %s: %s", tg_id, e)
                owner_summary.append(f"    ⚠ не доставлено ({e})")

    # Дублируем владельцу сводку.
    try:
        await bot.send_message(config.OWNER_ID, "\n".join(owner_summary))
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось отправить сводку владельцу: %s", e)


async def deadline_check(bot: Bot) -> None:
    """Проверяем задачи, у которых скоро дедлайн, и шлём напоминания."""
    tasks = await db.due_tasks_for_reminder()
    for t in tasks:
        deadline = f.fmt_dt(t["deadline"])
        body = (
            f"⏰ <b>Приближается дедлайн!</b>\n\n"
            f"Задача #{t['id']}: {t['description']}\n"
            f"Дело: {t['case_title']}\n"
            f"Срок: <b>{deadline}</b>"
        )
        # Ассистенту
        if t["assistant_tg"]:
            try:
                await bot.send_message(
                    t["assistant_tg"], body, reply_markup=task_done_kb(t["id"])
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Напоминание ассистенту не доставлено: %s", e)
        # Дубль владельцу
        try:
            who = t["assistant_name"] or "никому"
            await bot.send_message(
                config.OWNER_ID,
                body + f"\n\n(ответственный: {who})",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Дубль владельцу не доставлен: %s", e)

        await db.mark_task_reminded(t["id"])


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=config.TZ)

    # Еженедельный опрос
    sched.add_job(
        weekly_poll,
        CronTrigger(
            day_of_week=config.WEEKLY_POLL_DOW,
            hour=config.WEEKLY_POLL_HOUR,
            minute=0,
            timezone=config.TZ,
        ),
        args=[bot],
        id="weekly_poll",
        replace_existing=True,
    )

    # Проверка дедлайнов — каждый час (чтобы ловить любые remind_before)
    sched.add_job(
        deadline_check,
        CronTrigger(minute=0, timezone=config.TZ),
        args=[bot],
        id="deadline_check",
        replace_existing=True,
    )

    return sched
