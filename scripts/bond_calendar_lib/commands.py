from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, time as clock_time
from typing import Any

from .config import (
    load_listing_limit_up_reminder_config, load_listing_reminder_schedule,
    load_listing_tracking_max_days, load_subscribe_reminder_schedule,
    load_winning_reminder_schedule,
)
from .adapters import load_calendar_adapter, load_events, load_quote_adapter
from .formatters import (
    date_range_text, format_error, format_event_items, format_info_task_line,
    format_list_reminders_message, format_listing_query_message,
    format_multiple_matches, format_no_alert, format_not_found,
    format_status_message, format_subscribe_message,
    format_subscribe_query_message, format_tracking_item, format_winning_message,
)
from .queries import find_listing_events, find_subscribe_events, resolve_subscribe_period
from .scheduler import (
    collect_active_bond_tasks, default_cron_jobs, install_cron_jobs,
    is_active_bond_task, load_tasks, notify_target_status, read_crontab_lines,
    task_run_at, upsert_once_message_task,
)
from .settings import (
    CONFIG_FILE, DAILY_SUBSCRIBE_FILE, DAILY_WINNING_FILE, DATA_DIR,
    DEFAULT_CRON_SCHEDULE, TASKS_FILE, TIME_PATTERN, TIMEZONE, WATCHLIST_FILE,
    now_local, today_local,
)
from .storage import load_config, read_json, write_json
from .watchlist import (
    cancel_listing, check_tracked_listings, load_watchlist, track_listing,
)

def prepare_subscribe_today(create_tasks: bool = True) -> int:
    events = load_events()
    today = today_local().isoformat()
    if events is None:
        write_daily_snapshot(DAILY_SUBSCRIBE_FILE, today, "error", [])
        print(format_error("数据源暂时不可用", "我没有创建新的提醒任务。可以稍后再试，或检查数据源配置和日志。"))
        return 1

    subscribe_events = today_events(events, "申购日", today)
    write_daily_snapshot(DAILY_SUBSCRIBE_FILE, today, "ok", subscribe_events)

    if not subscribe_events:
        print(format_no_alert("今日暂无可转债申购事项"))
        return 0

    print(format_subscribe_message(subscribe_events))
    if create_tasks:
        create_subscribe_tasks(today, subscribe_events)
    return 0

def send_prepared_subscribe(slot: str) -> int:
    snapshot = read_json(DAILY_SUBSCRIBE_FILE, {})
    if snapshot.get("date") != today_local().isoformat():
        result = prepare_subscribe_today(create_tasks=False)
        snapshot = read_json(DAILY_SUBSCRIBE_FILE, {})
        if result != 0:
            print(format_error("今日申购缓存缺失，且自动补查失败", "可以稍后再试，或检查数据源配置和日志。"))
            return result
    if snapshot.get("status") == "error":
        print(format_error("今日申购缓存处于错误状态，请稍后重试"))
        return 1
    events = snapshot.get("events") if isinstance(snapshot, dict) else []
    if not events:
        print(format_no_alert("今日暂无可转债申购事项"))
        return 0
    print(format_subscribe_message(events, None if slot == "query" else slot))
    return 0

def prepare_winning_today(create_tasks: bool = True) -> int:
    events = load_events()
    today = today_local().isoformat()
    if events is None:
        write_daily_snapshot(DAILY_WINNING_FILE, today, "error", [])
        print(format_error("数据源暂时不可用", "我没有创建新的提醒任务。可以稍后再试，或检查数据源配置和日志。"))
        return 1

    winning_events = today_events(events, "中签结果公布日", today)
    write_daily_snapshot(DAILY_WINNING_FILE, today, "ok", winning_events)

    if not winning_events:
        print(format_no_alert("今日暂无可转债中签结果公布事项"))
        return 0

    print(format_winning_message(winning_events))
    if create_tasks:
        create_winning_tasks(today, winning_events)
    return 0

def write_daily_snapshot(path: Any, day: str, status: str, events: list[dict[str, Any]]) -> None:
    write_json(path, {
        "date": day,
        "generated_at": now_local().isoformat(),
        "status": status,
        "events": events,
    })

def today_events(events: list[dict[str, Any]], keyword: str, day: str) -> list[dict[str, Any]]:
    return [event for event in events if event["keyword"] == keyword and event["date"] == day]

def create_subscribe_tasks(day: str, events: list[dict[str, Any]]) -> None:
    for reminder in load_subscribe_reminder_schedule():
        slot = reminder["time"]
        label = reminder["label"]
        hour, minute = map(int, slot.split(":"))
        run_at = datetime.combine(today_local(), clock_time(hour, minute), tzinfo=TIMEZONE)
        task_id = f"bond-subscribe-{day.replace('-', '')}-{slot.replace(':', '')}"
        upsert_once_message_task(
            task_id,
            f"可转债申购提醒 {day} {label}",
            run_at,
            format_subscribe_message(events, label),
        )

def create_winning_tasks(day: str, events: list[dict[str, Any]]) -> None:
    for reminder in load_winning_reminder_schedule():
        slot = reminder["time"]
        label = reminder["label"]
        hour, minute = map(int, slot.split(":"))
        run_at = datetime.combine(today_local(), clock_time(hour, minute), tzinfo=TIMEZONE)
        task_id = f"bond-winning-{day.replace('-', '')}-{slot.replace(':', '')}"
        upsert_once_message_task(
            task_id,
            f"可转债中签结果公布提醒 {day} {label}",
            run_at,
            format_winning_message(events, label),
        )

def prepare_daily_reminders(create_tasks: bool = True) -> int:
    events = load_events()
    today = today_local().isoformat()
    if events is None:
        write_daily_snapshot(DAILY_SUBSCRIBE_FILE, today, "error", [])
        write_daily_snapshot(DAILY_WINNING_FILE, today, "error", [])
        print(format_error("数据源暂时不可用", "我没有创建新的提醒任务。可以稍后再试，或检查数据源配置和日志。"))
        return 1

    subscribe_events = today_events(events, "申购日", today)
    winning_events = today_events(events, "中签结果公布日", today)
    write_daily_snapshot(DAILY_SUBSCRIBE_FILE, today, "ok", subscribe_events)
    write_daily_snapshot(DAILY_WINNING_FILE, today, "ok", winning_events)

    sections: list[tuple[str, list[str]]] = []
    if subscribe_events:
        sections.append(("事项", ["- 申购日", *format_event_items(subscribe_events, "申购日期")]))
        if create_tasks:
            create_subscribe_tasks(today, subscribe_events)
    if winning_events:
        sections.append(("详情", ["- 中签结果公布日", *format_event_items(winning_events, "中签结果公布日期")]))
        if create_tasks:
            create_winning_tasks(today, winning_events)
    if not subscribe_events and not winning_events:
        print(format_no_alert("今日暂无可转债申购和中签结果公布事项"))
        return 0
    print(format_status_message(
        "ALERT",
        "今日可转债申购和中签结果公布提醒",
        sections,
    ))
    return 0

def send_prepared_winning(slot: str) -> int:
    snapshot = read_json(DAILY_WINNING_FILE, {})
    if snapshot.get("date") != today_local().isoformat():
        result = prepare_winning_today(create_tasks=False)
        snapshot = read_json(DAILY_WINNING_FILE, {})
        if result != 0:
            print(format_error("今日中签结果公布缓存缺失，且自动补查失败", "可以稍后再试，或检查数据源配置和日志。"))
            return result
    if snapshot.get("status") == "error":
        print(format_error("今日中签结果公布缓存处于错误状态，请稍后重试"))
        return 1
    events = snapshot.get("events") if isinstance(snapshot, dict) else []
    if not events:
        print(format_no_alert("今日暂无可转债中签结果公布事项"))
        return 0
    print(format_winning_message(events, None if slot == "query" else slot))
    return 0

def find_subscribe(
    date_expr: str | None,
    start_expr: str | None,
    end_expr: str | None,
    days: int | None,
    query: str | None,
) -> int:
    query = query.strip() if isinstance(query, str) and query.strip() else None
    has_period = any(value is not None for value in (date_expr, start_expr, end_expr, days))
    if has_period:
        try:
            start, end = resolve_subscribe_period(date_expr, start_expr, end_expr, days)
        except ValueError as exc:
            print(format_error(str(exc)))
            return 2
    elif query:
        start = None
        end = None
    else:
        start, end = resolve_subscribe_period("今天", None, None, None)

    matches = find_subscribe_events(start, end, query)
    if matches is None:
        print(format_error("数据源暂时不可用", "我没有创建新的提醒任务。可以稍后再试，或检查数据源配置和日志。"))
        return 1
    if not matches:
        period = date_range_text(start, end)
        suffix = f"（{query}）" if query else ""
        suggestion = "可以换用转债代码、申购代码或配售代码再查一次。" if query else None
        print(format_no_alert(f"{period}{suffix} 暂无匹配的可转债申购事项", suggestion))
        return 0
    print(format_subscribe_query_message(matches, start, end, query))
    return 0

def setup_schedule(
    apply: bool = False,
    replace: bool = False,
    daily_time: str | None = None,
    tracking_time: str | None = None,
    limit_up_time: str | None = None,
    python_bin: str | None = None,
) -> int:
    try:
        schedule = configured_cron_schedule(daily_time, tracking_time, limit_up_time)
        jobs = default_cron_jobs(
            schedule["prepare-daily-reminders"],
            schedule["check-tracked-listings"],
            schedule["check-listing-limit-up"],
            python_bin,
        )
        result = install_cron_jobs(jobs, apply=apply, replace=replace)
    except (OSError, ValueError) as exc:
        print(format_error(f"定时任务配置失败：{exc}", "请检查 crontab 是否可用，或手动复制 README 中的 crontab 示例。"))
        return 1

    planned = [f"- {job['time']} {job['command']}：{job['line']}" for job in jobs]
    installed = [f"- {line}" for line in result["installed"]]
    skipped = [f"- {line}" for line in result["skipped"]]
    suggestions = [
        "- 如需修改时间，可重新运行 setup-schedule --replace --yes 并传入 --daily-time、--tracking-time、--limit-up-time。",
        "- 提醒发送时间请在 config.json 中修改，如 subscribe_reminder_schedule、winning_reminder_schedule、listing_reminder_schedule。",
    ]
    if not apply:
        suggestions.insert(0, "- 当前只是预览，没有写入 crontab；确认后加 --yes 执行。")
        print(format_status_message(
            "INFO",
            "定时任务安装预览",
            [
                ("任务", planned),
                ("建议", suggestions),
            ],
        ))
        return 0

    print(format_status_message(
        "SCHEDULED",
        "定时任务已检查并写入 crontab",
        [
            ("任务", installed or ["- 没有新增任务"]),
            ("跳过", skipped),
            ("建议", suggestions),
        ],
    ))
    return 0

def configured_cron_schedule(
    daily_time: str | None = None,
    tracking_time: str | None = None,
    limit_up_time: str | None = None,
) -> dict[str, str]:
    config = load_config()
    raw = config.get("auto_setup_schedule")
    raw = raw if isinstance(raw, dict) else {}
    values = {
        "prepare-daily-reminders": daily_time or raw.get("daily_time") or DEFAULT_CRON_SCHEDULE["prepare-daily-reminders"],
        "check-tracked-listings": tracking_time or raw.get("tracking_time") or DEFAULT_CRON_SCHEDULE["check-tracked-listings"],
        "check-listing-limit-up": limit_up_time or raw.get("limit_up_time") or DEFAULT_CRON_SCHEDULE["check-listing-limit-up"],
    }
    for key, value in values.items():
        if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value.strip()):
            raise ValueError(f"{key} time must be HH:MM")
        values[key] = value.strip()
    return values

def auto_setup_schedule_if_enabled() -> None:
    config = load_config()
    raw = config.get("auto_setup_schedule")
    if isinstance(raw, dict) and raw.get("enabled") is False:
        return
    try:
        schedule = configured_cron_schedule()
        jobs = default_cron_jobs(
            schedule["prepare-daily-reminders"],
            schedule["check-tracked-listings"],
            schedule["check-listing-limit-up"],
        )
        result = install_cron_jobs(jobs, apply=True, replace=False)
    except Exception as exc:
        print(f"Warning: 自动设置定时任务失败：{exc}", file=sys.stderr)
        return
    if result["installed"]:
        print(
            "Info: 已自动设置可转债每日定时任务；如需修改时间，请运行 setup-schedule --replace --yes。",
            file=sys.stderr,
        )

def print_listing_result(event: dict[str, Any]) -> None:
    print(format_listing_query_message(event))

def find_listing(query: str) -> int:
    matches = find_listing_events(query)
    if matches is None:
        print(format_error("数据源暂时不可用", "我没有创建新的提醒任务。可以稍后再试，或检查数据源配置和日志。"))
        return 1
    if not matches:
        print(format_not_found(
            f"暂未查到 {query} 的上市日期",
            f"如果你已经中签，可以输入“我中了 {query}，上市提醒我”。",
        ))
        return 0
    if len(matches) > 1:
        print(format_multiple_matches(
            "找到多个候选，暂时不能确定是哪一只",
            matches,
            "请用更准确的转债代码再查一次。",
        ))
        return 0
    print_listing_result(matches[0])
    return 0

def list_reminders() -> int:
    tasks = load_tasks().get("tasks", {})
    subscribe_tasks: list[tuple[str, dict[str, Any]]] = []
    winning_tasks: list[tuple[str, dict[str, Any]]] = []
    listing_tasks: list[tuple[str, dict[str, Any]]] = []
    for task_id, task in tasks.items():
        if not isinstance(task, dict):
            continue
        if is_active_bond_task(task_id, task, "bond-subscribe-"):
            subscribe_tasks.append((task_id, task))
        elif is_active_bond_task(task_id, task, "bond-winning-"):
            winning_tasks.append((task_id, task))
        elif is_active_bond_task(task_id, task, "bond-listing-"):
            listing_tasks.append((task_id, task))
    subscribe_tasks.sort(key=lambda pair: task_run_at(pair[1]) or datetime.max.replace(tzinfo=TIMEZONE))
    winning_tasks.sort(key=lambda pair: task_run_at(pair[1]) or datetime.max.replace(tzinfo=TIMEZONE))
    listing_tasks.sort(key=lambda pair: task_run_at(pair[1]) or datetime.max.replace(tzinfo=TIMEZONE))

    watchlist = load_watchlist().get("items", {})
    tracking = [
        (key, item) for key, item in watchlist.items()
        if isinstance(item, dict) and item.get("status") in {"pending", "needs_confirmation"}
    ]
    tracking.sort(key=lambda pair: str(pair[1].get("created_at") or ""))

    print(format_list_reminders_message(subscribe_tasks, winning_tasks, listing_tasks, tracking))
    return 0

def plugin_info() -> int:
    config = load_config()
    tasks = load_tasks().get("tasks", {})
    watch_items = load_watchlist().get("items", {})
    status_counts = Counter(
        item.get("status", "unknown")
        for item in watch_items.values()
        if isinstance(item, dict)
    )
    daily = read_json(DAILY_SUBSCRIBE_FILE, {})
    daily_winning = read_json(DAILY_WINNING_FILE, {})
    crontab_lines = read_crontab_lines()
    calendar_strategy = config.get("calendar_strategy") if isinstance(config.get("calendar_strategy"), dict) else {}
    quote_strategy = config.get("quote_strategy") if isinstance(config.get("quote_strategy"), dict) else {}
    subscribe_tasks = collect_active_bond_tasks(tasks, "bond-subscribe-")
    winning_tasks = collect_active_bond_tasks(tasks, "bond-winning-")
    listing_tasks = collect_active_bond_tasks(tasks, "bond-listing-")
    tracking_items = sorted(
        (
            (key, item) for key, item in watch_items.items()
            if isinstance(item, dict) and item.get("status") in {"pending", "needs_confirmation"}
        ),
        key=lambda pair: str(pair[1].get("created_at") or ""),
    )
    listing_schedule = load_listing_reminder_schedule()
    subscribe_schedule = load_subscribe_reminder_schedule()
    winning_schedule = load_winning_reminder_schedule()
    limit_up_reminder = load_listing_limit_up_reminder_config()
    calendar_adapter = load_calendar_adapter()
    quote_adapter = load_quote_adapter()

    daily_lines: list[str] = []
    if isinstance(daily, dict) and daily:
        daily_lines.extend([
            f"- 日期：{daily.get('date', '未知')}",
            f"- 状态：{daily.get('status', '未知')}",
            f"- 生成时间：{daily.get('generated_at', '未知')}",
        ])
        events = daily.get("events")
        daily_lines.append(f"- 事项数：{len(events) if isinstance(events, list) else 0}")
    else:
        daily_lines.append("- 未生成")

    daily_winning_lines: list[str] = []
    if isinstance(daily_winning, dict) and daily_winning:
        daily_winning_lines.extend([
            f"- 日期：{daily_winning.get('date', '未知')}",
            f"- 状态：{daily_winning.get('status', '未知')}",
            f"- 生成时间：{daily_winning.get('generated_at', '未知')}",
        ])
        events = daily_winning.get("events")
        daily_winning_lines.append(f"- 事项数：{len(events) if isinstance(events, list) else 0}")
    else:
        daily_winning_lines.append("- 未生成")

    subscribe_schedule_text = ", ".join(
        str(item["label"])
        if str(item["label"]).startswith(str(item["time"]))
        else f"{item['time']} {item['label']}"
        for item in subscribe_schedule
    )
    winning_schedule_text = ", ".join(
        str(item["label"])
        if str(item["label"]).startswith(str(item["time"]))
        else f"{item['time']} {item['label']}"
        for item in winning_schedule
    )
    limit_up_status = (
        f"启用，{limit_up_reminder['check_time']} 检查，"
        f"涨幅达到 {limit_up_reminder['threshold_percent']}% 时 "
        f"{limit_up_reminder['reminder_time']} 提醒"
        if limit_up_reminder["enabled"]
        else "未启用"
    )
    config_lines = [
        f"- 日历策略：{calendar_strategy.get('type') or type(calendar_adapter).__name__}",
        f"- 行情策略：{quote_strategy.get('type') or type(quote_adapter).__name__}",
        f"- 提醒目标：{notify_target_status()}",
        f"- 申购提醒计划：{subscribe_schedule_text}",
        f"- 中签结果公布提醒计划：{winning_schedule_text}",
        f"- 上市提醒计划：{len(listing_schedule)} 个提醒点",
        f"- 上市涨停扩展提醒：{limit_up_status}",
        f"- 上市最长追踪天数：{load_listing_tracking_max_days()}",
        f"- 配置文件：{CONFIG_FILE}",
        f"- 运行数据目录：{DATA_DIR}",
        f"- scheduler 文件：{TASKS_FILE}",
        f"- 今日申购缓存：{DAILY_SUBSCRIBE_FILE}",
        f"- 今日中签结果公布缓存：{DAILY_WINNING_FILE}",
        f"- 上市追踪列表：{WATCHLIST_FILE}",
    ]
    status_lines = [
        f"- scheduler 待执行申购提醒：{len(subscribe_tasks)} 个",
        f"- scheduler 待执行中签结果公布提醒：{len(winning_tasks)} 个",
        f"- scheduler 待执行上市提醒：{len(listing_tasks)} 个",
    ]
    status_lines.extend(
        f"- watchlist {status}：{status_counts.get(status, 0)} 个"
        for status in ("pending", "needs_confirmation", "scheduled", "expired", "canceled")
    )
    print(format_status_message(
        "INFO",
        "bond-calendar-reminder-skill 待执行任务",
        [
            ("详情", [f"- 生成时间：{now_local().isoformat()}", "- 时区：Asia/Shanghai"]),
            ("申购提醒", [format_info_task_line(task_id, task) for task_id, task in subscribe_tasks] or ["- 暂无"]),
            ("中签结果公布提醒", [format_info_task_line(task_id, task) for task_id, task in winning_tasks] or ["- 暂无"]),
            ("上市提醒", [format_info_task_line(task_id, task) for task_id, task in listing_tasks] or ["- 暂无"]),
            ("任务", [f"- {line}" for line in crontab_lines] or ["- 未发现包含 bond_calendar.py 的 crontab 任务"]),
            ("待追踪上市", [format_tracking_item(key, item) for key, item in tracking_items] or ["- 暂无"]),
            ("今日申购缓存", daily_lines),
            ("今日中签结果公布缓存", daily_winning_lines),
            ("配置摘要", config_lines),
            ("状态计数", status_lines),
        ],
    ))
    return 0
