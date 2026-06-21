"""Вспомогательные функции форматирования сообщений."""
from datetime import datetime

import config


def fmt_money(value) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f} ₽".replace(",", " ")


def fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(config.TZ).strftime("%d.%m.%Y %H:%M")


def fmt_date(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(config.TZ).strftime("%d.%m.%Y")


def case_card(case, *, for_owner: bool) -> str:
    """Текст карточки дела. Для ассистента скрываем деньги."""
    lines = [
        f"<b>Дело #{case['id']}: {case['title']}</b>",
        f"👤 Клиент: {case['client_name']}",
    ]
    if case.get("description"):
        lines.append(f"📄 Суть: {case['description']}")

    assistant_name = case.get("assistant_name")
    lines.append(f"🧑‍💼 Ассистент: {assistant_name or '— не назначен —'}")

    if for_owner:
        lines.append(f"💰 Стоимость услуги: {fmt_money(case.get('price'))}")
        lines.append(f"🧾 Доля ассистента: {fmt_money(case.get('assistant_fee'))}")
        paid = "✅ оплачено" if case.get("fee_paid") else "❌ не оплачено"
        lines.append(f"💵 Оплата ассистенту: {paid}")

    if case.get("court_link"):
        lines.append(f"🔗 <a href=\"{case['court_link']}\">Ссылка на суд / КАД</a>")

    status = "🟢 открыто" if case.get("status") == "open" else "⚫ закрыто"
    lines.append(f"Статус: {status}")
    return "\n".join(lines)


def task_line(task) -> str:
    mark = "✅" if task["done"] else "🔲"
    dl = fmt_dt(task["deadline"]) if task["deadline"] else "без дедлайна"
    assigned = fmt_dt(task["assigned_at"])
    s = f"{mark} <b>#{task['id']}</b> {task['description']}\n     ⏰ дедлайн: {dl} · поставлена: {assigned}"
    if task["done"] and task["done_at"]:
        s += f"\n     ✔ выполнено: {fmt_dt(task['done_at'])}"
    return s


def stage_line(stage) -> str:
    return f"• {fmt_dt(stage['created_at'])} — {stage['text']} <i>({stage['author']})</i>"
