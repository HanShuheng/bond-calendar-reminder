from __future__ import annotations

import re
import uuid
from datetime import datetime, time as clock_time, timedelta
from typing import Any

from .config import (
    load_listing_limit_up_reminder_config, load_listing_reminder_schedule,
    load_listing_tracking_max_days,
)
from .adapters import fetch_bond_quote
from .formatters import (
    event_label, format_error, format_expired_listing_message,
    format_listing_message, format_multiple_matches, format_no_alert,
    format_not_found, format_scheduled_listing_message,
    format_status_message, format_tracking_message,
)
from .queries import find_listing_events, matches_query
from .scheduler import (
    disable_task_ids, local_naive, parse_local_datetime, save_tasks, task_run_at,
    upsert_once_message_task,
)
from .settings import TIMEZONE, WATCHLIST_FILE, now_local, today_local
from .storage import read_json, write_json

def watch_key(query: str) -> str:
    compact = re.sub(r"\s+", "", query)
    safe = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "-", compact)
    return safe[:80] or uuid.uuid4().hex[:8]

def canonical_watch_key(event: dict[str, Any], fallback_query: str) -> str:
    bond_code = str(event.get("bond_code") or "").strip()
    if bond_code:
        return bond_code
    name = str(event.get("name") or "").strip()
    if name:
        return watch_key(name)
    return watch_key(fallback_query)

def load_watchlist() -> dict[str, Any]:
    data = read_json(WATCHLIST_FILE, {"version": 1, "items": {}})
    if not isinstance(data, dict):
        data = {"version": 1, "items": {}}
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    return data

def save_watchlist(data: dict[str, Any]) -> None:
    data["version"] = 1
    data["updated_at"] = now_local().isoformat()
    write_json(WATCHLIST_FILE, data)

def parse_item_created_at(item: dict[str, Any]) -> datetime | None:
    return parse_local_datetime(item.get("created_at"))

def is_tracking_expired(item: dict[str, Any], max_days: int) -> bool:
    created_at = parse_item_created_at(item)
    if created_at is None:
        return False
    return now_local() >= created_at + timedelta(days=max_days)

def schedule_listing_tasks(event: dict[str, Any]) -> dict[str, Any]:
    listing_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
    identifier = event.get("bond_code") or watch_key(event["name"])
    created: list[str] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in load_listing_reminder_schedule():
        hour, minute = map(int, item["time"].split(":"))
        day = listing_date + timedelta(days=item["days_offset"])
        tm = clock_time(hour, minute)
        run_at = datetime.combine(day, tm, tzinfo=TIMEZONE)
        label = item["label"]
        task_id = f"bond-listing-{identifier}-{event['date'].replace('-', '')}-{item['tag']}"
        if run_at < now_local():
            skipped.append({
                "label": label,
                "run_at": local_naive(run_at),
                "reason": "past",
            })
            continue
        content = format_listing_message(event, label)
        if upsert_once_message_task(task_id, f"{event['name']}上市提醒 {label}", run_at, content):
            created.append(task_id)
        else:
            failed.append({
                "label": label,
                "run_at": local_naive(run_at),
                "task_id": task_id,
                "reason": "create_failed",
            })
    return {"task_ids": created, "skipped_reminders": skipped, "failed_reminders": failed}

def remember_alias(item: dict[str, Any], query: str) -> None:
    aliases = item.get("aliases")
    if not isinstance(aliases, list):
        aliases = []
    if query not in aliases:
        aliases.append(query)
    item["aliases"] = aliases

def merge_watch_items(data: dict[str, Any], target_key: str, source_key: str) -> dict[str, Any]:
    items = data["items"]
    source = items.pop(source_key, {}) if source_key != target_key else items.get(source_key, {})
    target = items.get(target_key, {})
    if not isinstance(source, dict):
        source = {}
    if not isinstance(target, dict):
        target = {}
    merged = {**source, **target}
    source_created = parse_local_datetime(source.get("created_at"))
    target_created = parse_local_datetime(target.get("created_at"))
    if source_created and target_created:
        merged["created_at"] = min(source_created, target_created).isoformat()
    elif source.get("created_at") or target.get("created_at"):
        merged["created_at"] = source.get("created_at") or target.get("created_at")
    else:
        merged["created_at"] = now_local().isoformat()
    source_aliases = source.get("aliases") if isinstance(source.get("aliases"), list) else []
    target_aliases = target.get("aliases") if isinstance(target.get("aliases"), list) else []
    merged["aliases"] = sorted(set(str(value) for value in [*source_aliases, *target_aliases] if value))
    items[target_key] = merged
    return merged

def update_item_with_listing(
    item: dict[str, Any],
    query: str,
    event: dict[str, Any],
    scheduled: dict[str, Any],
) -> None:
    remember_alias(item, query)
    task_ids = scheduled.get("task_ids", [])
    skipped = scheduled.get("skipped_reminders", [])
    failed = scheduled.get("failed_reminders", [])
    item.update({
        "query": query,
        "event": event,
        "task_ids": task_ids,
        "skipped_reminders": skipped,
        "failed_reminders": failed,
        "updated_at": now_local().isoformat(),
    })
    item.pop("last_error", None)
    item.pop("candidates", None)
    if task_ids:
        item["status"] = "scheduled"
    elif failed:
        item["status"] = "pending"
        item["last_error"] = "上市提醒任务创建失败，等待下次检查重试"
    else:
        item["status"] = "expired"
        item["expired_at"] = now_local().isoformat()
        item["expired_reason"] = "no_future_listing_reminders"

def limit_up_reminder_content(event: dict[str, Any], quote: dict[str, Any], threshold: float) -> str:
    name = event.get("name") or quote.get("name") or "可转债"
    code = event.get("bond_code") or quote.get("bond_code") or ""
    details = [
        f"- 最新价：{quote['last_price']}",
        f"- 涨跌幅：{quote['change_percent']}%",
        f"- 触发阈值：{threshold}%",
    ]
    if quote.get("prev_close") is not None:
        details.append(f"- 昨收：{quote['prev_close']}")
    if quote.get("quote_time"):
        details.append(f"- 行情时间：{quote['quote_time']}")
    return format_status_message(
        "ALERT",
        f"{name}（{code}）上市日涨幅达到提醒阈值",
        [
            ("事项", [f"- {name}（{code}）"]),
            ("详情", details),
            ("建议", ["请以交易软件和交易所实际行情为准。"]),
        ],
    )

def listing_limit_up_candidates(data: dict[str, Any], query: str | None = None) -> list[dict[str, Any]]:
    items = data.get("items", {})
    today = today_local().isoformat()
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, item in items.items():
        if not isinstance(item, dict) or item.get("status") != "scheduled":
            continue
        event = item.get("event")
        if not isinstance(event, dict) or event.get("date") != today:
            continue
        if query and not watch_item_matches_query(str(key), item, query):
            continue
        bond_code = str(event.get("bond_code") or "").strip()
        if not bond_code or bond_code in seen:
            continue
        events.append(event)
        seen.add(bond_code)
    return events

def check_listing_limit_up(query: str | None = None) -> int:
    config = load_listing_limit_up_reminder_config()
    if not config.get("enabled"):
        print(format_no_alert("上市涨停扩展提醒未启用"))
        return 0

    data = load_watchlist()
    events = listing_limit_up_candidates(data, query.strip() if isinstance(query, str) and query.strip() else None)
    if not events:
        print(format_no_alert("今日暂无需要检查涨停提醒的上市转债"))
        return 0

    threshold = float(config["threshold_percent"])
    reminder_hour, reminder_minute = map(int, str(config["reminder_time"]).split(":"))
    reminder_day = today_local()
    reminder_time = clock_time(reminder_hour, reminder_minute)
    run_at = datetime.combine(reminder_day, reminder_time, tzinfo=TIMEZONE)
    created: list[str] = []
    checked: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for event in events:
        bond_code = str(event.get("bond_code") or "").strip()
        quote = fetch_bond_quote(bond_code)
        if quote is None:
            failed.append(f"- {event_label(event)}：行情数据暂不可用")
            continue
        checked.append(
            f"- {event_label(event)}：最新价 {quote['last_price']}，涨跌幅 {quote['change_percent']}%"
        )
        if float(quote["change_percent"]) < threshold:
            continue
        task_id = f"bond-listing-limit-up-{bond_code}-{reminder_day.strftime('%Y%m%d')}-{str(config['reminder_time']).replace(':', '')}"
        if run_at < now_local():
            skipped.append(f"- {event_label(event)}：提醒时间 {local_naive(run_at)} 已过期")
            continue
        content = limit_up_reminder_content(event, quote, threshold)
        if upsert_once_message_task(task_id, f"{event.get('name')}上市涨停提醒 {config['label']}", run_at, content):
            created.append(f"- {event_label(event)}：{local_naive(run_at)}")
        else:
            failed.append(f"- {event_label(event)}：提醒任务创建失败")

    if created:
        sections: list[tuple[str, list[str]]] = [("任务", created)]
        if checked:
            sections.append(("详情", checked))
        if skipped:
            sections.append(("跳过", skipped))
        if failed:
            sections.append(("建议", failed))
        print(format_status_message("SCHEDULED", "已创建上市涨停二次提醒", sections))
        return 0

    sections = []
    if checked:
        sections.append(("详情", checked))
    if skipped:
        sections.append(("跳过", skipped))
    if failed:
        sections.append(("建议", failed))
    print(format_status_message("NO_ALERT", "未发现达到涨停提醒阈值的上市转债", sections))
    return 0

def track_listing(query: str) -> int:
    matches = find_listing_events(query)
    data = load_watchlist()
    key = watch_key(query)
    item = data["items"].get(key, {"query": query, "created_at": now_local().isoformat()})
    item["updated_at"] = now_local().isoformat()

    if matches is None:
        item["status"] = "pending"
        item["last_error"] = "数据源暂时不可用"
        data["items"][key] = item
        save_watchlist(data)
        print(format_error(
            "数据源暂时不可用",
            f"已记录 {query}，数据源恢复后会继续追踪上市日期。",
        ))
        return 1
    if not matches:
        item["status"] = "pending"
        data["items"][key] = item
        save_watchlist(data)
        print(format_tracking_message(query, f"暂未查到 {query} 的上市日期，已加入每日追踪"))
        return 0
    if len(matches) > 1:
        item["status"] = "needs_confirmation"
        item["candidates"] = matches
        data["items"][key] = item
        save_watchlist(data)
        print(format_multiple_matches(
            "找到多个候选，暂时不能确定是哪一只",
            matches,
            "请用更准确的转债代码重新添加。",
        ))
        return 0

    event = matches[0]
    canonical_key = canonical_watch_key(event, query)
    item = merge_watch_items(data, canonical_key, key)
    scheduled = schedule_listing_tasks(event)
    update_item_with_listing(item, query, event, scheduled)
    save_watchlist(data)
    if item["status"] == "scheduled":
        print(format_scheduled_listing_message(event, item))
    elif item["status"] == "expired":
        print(format_expired_listing_message(event, item))
    else:
        print(format_tracking_message(
            event_label(event),
            "已查到上市日期，但提醒任务创建失败，已保留追踪等待下次重试",
            "可以先和机器人发一条消息，再重新查看提醒目标状态。",
        ))
    return 0

def check_tracked_listings() -> int:
    data = load_watchlist()
    items = data.get("items", {})
    max_days = load_listing_tracking_max_days()
    pending: list[tuple[str, dict[str, Any]]] = []
    changed = False
    for key, item in list(items.items()):
        if item.get("status") not in {"pending", "needs_confirmation"} or not item.get("query"):
            continue
        item["updated_at"] = now_local().isoformat()
        if is_tracking_expired(item, max_days):
            item["status"] = "expired"
            item["expired_at"] = now_local().isoformat()
            item["expired_reason"] = f"tracking_over_{max_days}_days"
            changed = True
            continue
        pending.append((key, item))
    if not pending:
        if changed:
            save_watchlist(data)
        print(format_no_alert("暂无待追踪上市转债"))
        return 0

    scheduled_messages: list[str] = []
    for key, item in pending:
        query = item["query"]
        matches = find_listing_events(query)
        item["updated_at"] = now_local().isoformat()
        if matches is None:
            item["last_error"] = "数据源暂时不可用"
            changed = True
            continue
        if not matches:
            changed = True
            continue
        if len(matches) > 1:
            item["status"] = "needs_confirmation"
            item["candidates"] = matches
            changed = True
            continue
        event = matches[0]
        canonical_key = canonical_watch_key(event, query)
        target = merge_watch_items(data, canonical_key, key)
        scheduled = schedule_listing_tasks(event)
        update_item_with_listing(target, query, event, scheduled)
        scheduled_messages.append(f"{event['name']}（{event.get('bond_code') or query}）")
        changed = True

    if changed:
        save_watchlist(data)
    if scheduled_messages:
        print(format_status_message(
            "ALERT",
            "已为以下转债创建上市提醒",
            [("事项", [f"- {message}" for message in scheduled_messages])],
        ))
    else:
        print(format_no_alert("暂未查到新的上市日期"))
    return 0

def watch_item_matches_query(key: str, item: dict[str, Any], query: str) -> bool:
    if key == watch_key(query) or key == query.strip():
        return True
    if item.get("query") == query:
        return True
    aliases = item.get("aliases")
    if isinstance(aliases, list) and query in aliases:
        return True
    event = item.get("event")
    if isinstance(event, dict) and matches_query(event, query):
        return True
    candidates = item.get("candidates")
    if isinstance(candidates, list):
        return any(isinstance(candidate, dict) and matches_query(candidate, query) for candidate in candidates)
    return False

def cancel_listing(query: str) -> int:
    data = load_watchlist()
    items = data.get("items", {})
    matches = [
        (key, item) for key, item in items.items()
        if isinstance(item, dict)
        and item.get("status") in {"pending", "needs_confirmation", "scheduled"}
        and watch_item_matches_query(key, item, query)
    ]
    if not matches:
        print(format_not_found(
            f"暂未找到 {query} 的上市提醒或追踪记录",
            "可以用 list-reminders 查看当前提醒和追踪状态。",
        ))
        return 0
    if len(matches) > 1:
        candidates = []
        for key, item in matches:
            event = item.get("event") if isinstance(item.get("event"), dict) else {}
            candidates.append({
                "date": event.get("date") or "",
                "name": event.get("name") or item.get("query") or key,
                "bond_code": event.get("bond_code") or key,
            })
        print(format_multiple_matches(
            "找到多个提醒记录，暂时不能确定要取消哪一个",
            candidates,
            "请用更准确的转债代码取消。",
        ))
        return 0

    key, item = matches[0]
    disabled_count = disable_task_ids(item.get("task_ids") if isinstance(item.get("task_ids"), list) else [])
    item["status"] = "canceled"
    item["canceled_at"] = now_local().isoformat()
    item["updated_at"] = now_local().isoformat()
    save_watchlist(data)
    sections = [("任务", [f"- 已禁用 {disabled_count} 个待执行提醒任务"])] if disabled_count else []
    print(format_status_message("CANCELED", f"已取消 {query} 的上市提醒/追踪", sections))
    return 0
