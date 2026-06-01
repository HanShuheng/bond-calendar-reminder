from __future__ import annotations

from datetime import date
from typing import Any

from .scheduler import local_naive, task_run_at

VALID_STATUSES = {
    "ALERT",
    "SCHEDULED",
    "TRACKING",
    "NO_ALERT",
    "NOT_FOUND",
    "MULTIPLE_MATCHES",
    "CANCELED",
    "EXPIRED",
    "ERROR",
    "INFO",
}


def format_status_message(
    status: str,
    summary: str,
    sections: list[tuple[str, list[str] | tuple[str, ...]]] | None = None,
) -> str:
    if status not in VALID_STATUSES:
        raise ValueError(f"unsupported status: {status}")
    lines = [f"{status}: {summary}"]
    for title, raw_items in sections or []:
        items = [str(item) for item in raw_items if str(item).strip()]
        if not items:
            continue
        lines.extend(["", f"{title}：", *items])
    return "\n".join(lines).strip()


def date_range_text(start: date | None, end: date | None) -> str:
    if start is None or end is None:
        return "数据源可见范围内"
    if start == end:
        return start.isoformat()
    return f"{start.isoformat()} 至 {end.isoformat()}"


def event_label(event: dict[str, Any]) -> str:
    name = str(event.get("name") or event.get("title") or "未命名事项")
    code = str(event.get("bond_code") or "").strip()
    return f"{name}（{code}）" if code else name


def format_code_lines(event: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if event.get("bond_code"):
        lines.append(f"  转债代码：{event['bond_code']}")
    if event.get("subscribe_code"):
        lines.append(f"  申购代码：{event['subscribe_code']}")
    if event.get("allotment_code"):
        lines.append(f"  配售代码：{event['allotment_code']}")
    return lines


def format_event_item(event: dict[str, Any], date_label: str | None = None) -> list[str]:
    lines = [f"- {event_label(event)}"]
    if date_label and event.get("date"):
        lines.append(f"  {date_label}：{event['date']}")
    lines.extend(format_code_lines(event))
    if event.get("url"):
        lines.append(f"  详情：{event['url']}")
    return lines


def format_event_items(events: list[dict[str, Any]], date_label: str | None = None) -> list[str]:
    lines: list[str] = []
    for event in events:
        lines.extend(format_event_item(event, date_label))
    return lines


def format_candidate_items(events: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {event.get('date', '')} {event_label(event)}".strip()
        for event in events
    ]


def format_task_line(task_id: str, task: dict[str, Any]) -> str:
    run_at = task_run_at(task)
    run_at_text = local_naive(run_at) if run_at else "未知时间"
    name = task.get("name") or task_id
    return f"- {run_at_text} {name}（{task_id}）"


def format_reminder_items(reminders: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in reminders:
        run_at = item.get("run_at")
        label = item.get("label") or item.get("task_id") or "提醒"
        if run_at:
            lines.append(f"- {run_at}：{label}")
        else:
            lines.append(f"- {label}")
    return lines


def format_subscribe_message(events: list[dict[str, Any]], slot: str | None = None) -> str:
    summary = "今日可转债申购提醒" if not slot or slot == "query" else f"今日可转债申购提醒（{slot}）"
    return format_status_message(
        "ALERT",
        summary,
        [("事项", format_event_items(events, "申购日期"))],
    )


def format_subscribe_query_message(
    events: list[dict[str, Any]],
    start: date | None,
    end: date | None,
    query: str | None = None,
) -> str:
    period = date_range_text(start, end)
    suffix = f"（{query}）" if query else ""
    return format_status_message(
        "ALERT",
        f"{period} 可转债申购查询结果{suffix}",
        [("事项", format_event_items(events, "申购日期"))],
    )


def format_winning_message(events: list[dict[str, Any]], slot: str | None = None) -> str:
    summary = "今日可转债中签结果公布提醒" if not slot or slot == "query" else f"今日可转债中签结果公布提醒（{slot}）"
    return format_status_message(
        "ALERT",
        summary,
        [("事项", format_event_items(events, "中签结果公布日期"))],
    )


def format_no_alert(message: str, suggestion: str | None = None) -> str:
    sections = [("建议", [suggestion])] if suggestion else []
    return format_status_message("NO_ALERT", message, sections)


def format_error(message: str, suggestion: str | None = None) -> str:
    sections = [("建议", [suggestion])] if suggestion else []
    return format_status_message("ERROR", message, sections)


def format_not_found(message: str, suggestion: str | None = None) -> str:
    sections = [("建议", [suggestion])] if suggestion else []
    return format_status_message("NOT_FOUND", message, sections)


def format_multiple_matches(summary: str, candidates: list[dict[str, Any]], suggestion: str) -> str:
    return format_status_message(
        "MULTIPLE_MATCHES",
        summary,
        [
            ("候选", format_candidate_items(candidates)),
            ("建议", [suggestion]),
        ],
    )


def format_listing_message(event: dict[str, Any], label: str) -> str:
    return format_status_message(
        "ALERT",
        f"{event_label(event)}上市提醒",
        [
            ("事项", format_event_item(event, "上市日期")),
            ("提醒计划", [f"- 当前提醒：{label}"]),
        ],
    )


def format_listing_query_message(event: dict[str, Any]) -> str:
    return format_status_message(
        "ALERT",
        f"已查到 {event_label(event)} 的上市日期",
        [("事项", format_event_item(event, "上市日期"))],
    )


def format_scheduled_listing_message(event: dict[str, Any], item: dict[str, Any]) -> str:
    sections: list[tuple[str, list[str]]] = [
        ("事项", format_event_item(event, "上市日期")),
    ]
    task_ids = item.get("task_ids") if isinstance(item.get("task_ids"), list) else []
    if task_ids:
        sections.append(("任务", [f"- {task_id}" for task_id in task_ids]))
    skipped = item.get("skipped_reminders") if isinstance(item.get("skipped_reminders"), list) else []
    if skipped:
        sections.append(("跳过", format_reminder_items(skipped)))
    return format_status_message("SCHEDULED", f"已创建 {event_label(event)} 上市提醒", sections)


def format_tracking_message(query: str, message: str, suggestion: str | None = None) -> str:
    sections = [("事项", [f"- {query}"])]
    if suggestion:
        sections.append(("建议", [suggestion]))
    return format_status_message("TRACKING", message, sections)


def format_expired_listing_message(event: dict[str, Any], item: dict[str, Any]) -> str:
    skipped = item.get("skipped_reminders") if isinstance(item.get("skipped_reminders"), list) else []
    sections: list[tuple[str, list[str]]] = [("事项", format_event_item(event, "上市日期"))]
    if skipped:
        sections.append(("跳过", format_reminder_items(skipped)))
    return format_status_message("EXPIRED", "上市提醒时间均已过期", sections)


def task_target_summary(task: dict[str, Any]) -> str:
    action = task.get("action")
    if not isinstance(action, dict):
        return "目标：未记录"
    channel_type = action.get("channel_type") or "unknown"
    receiver_name = action.get("receiver_name") or "默认会话"
    group_label = "群聊" if action.get("is_group") else "单聊"
    return f"目标：{receiver_name} / {channel_type} / {group_label}"


def format_info_task_line(task_id: str, task: dict[str, Any]) -> str:
    run_at = task_run_at(task)
    run_at_text = local_naive(run_at) if run_at else "未知时间"
    name = task.get("name") or task_id
    return f"- {run_at_text} {name}（{task_id}，{task_target_summary(task)}）"


def format_tracking_item(key: str, item: dict[str, Any]) -> str:
    query = item.get("query") or key
    created_at = item.get("created_at") or "未知"
    updated_at = item.get("updated_at") or "未知"
    line = f"- {query}（{item.get('status')}，创建：{created_at}，更新：{updated_at}）"
    candidates = item.get("candidates")
    if item.get("status") == "needs_confirmation" and isinstance(candidates, list):
        line += f"，候选：{len(candidates)} 个"
    if item.get("last_error"):
        line += f"，最近错误：{item['last_error']}"
    return line


def format_list_reminders_message(
    subscribe_tasks: list[tuple[str, dict[str, Any]]],
    winning_tasks: list[tuple[str, dict[str, Any]]],
    listing_tasks: list[tuple[str, dict[str, Any]]],
    tracking: list[tuple[str, dict[str, Any]]],
) -> str:
    sections: list[tuple[str, list[str]]] = [
        ("申购提醒", [format_task_line(task_id, task) for task_id, task in subscribe_tasks] or ["- 暂无"]),
        ("中签结果公布提醒", [format_task_line(task_id, task) for task_id, task in winning_tasks] or ["- 暂无"]),
        ("上市提醒", [format_task_line(task_id, task) for task_id, task in listing_tasks] or ["- 暂无"]),
        (
            "待追踪上市",
            [
                f"- {item.get('query') or key}（{item.get('status')}，创建于 {item.get('created_at') or '未知时间'}）"
                for key, item in tracking
            ] or ["- 暂无"],
        ),
        ("配置摘要", ["- 中签结果公布提醒计划：10:30 中签结果公布提醒, 13:00 中签结果公布提醒"]),
        (
            "状态计数",
            [
                f"- 申购提醒：{len(subscribe_tasks)} 个",
                f"- 中签结果公布提醒：{len(winning_tasks)} 个",
                f"- 上市提醒：{len(listing_tasks)} 个",
                f"- 待追踪上市：{len(tracking)} 个",
            ],
        ),
    ]
    if not subscribe_tasks and not winning_tasks and not listing_tasks and not tracking:
        return format_status_message("NO_ALERT", "当前暂无债券相关提醒事项", sections)
    return format_status_message("ALERT", "当前债券相关提醒事项", sections)
