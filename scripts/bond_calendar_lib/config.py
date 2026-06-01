from __future__ import annotations

import re
import sys
from typing import Any

from .settings import (
    DEFAULT_LISTING_LIMIT_UP_REMINDER, DEFAULT_LISTING_REMINDER_SCHEDULE,
    DEFAULT_LISTING_TRACKING_MAX_DAYS, DEFAULT_SUBSCRIBE_REMINDER_SCHEDULE,
    DEFAULT_WINNING_REMINDER_SCHEDULE, TIME_PATTERN,
)
from .storage import load_config

def normalize_time_schedule(raw_schedule: Any, default_schedule: tuple[dict[str, str], ...], event_name: str) -> list[dict[str, Any]]:
    if not isinstance(raw_schedule, (list, tuple)):
        print(f"Warning: {event_name} reminder schedule must be a list; using defaults", file=sys.stderr)
        raw_schedule = list(default_schedule)

    schedule: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_schedule):
        if isinstance(item, str):
            reminder_time = item.strip()
            label = f"{reminder_time} {event_name}提醒"
        elif isinstance(item, dict):
            raw_time = item.get("time")
            if not isinstance(raw_time, str):
                print(f"Warning: ignore invalid {event_name} reminder item: {item!r}", file=sys.stderr)
                continue
            reminder_time = raw_time.strip()
            raw_label = item.get("label")
            label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else f"{reminder_time} {event_name}提醒"
        else:
            print(f"Warning: ignore invalid {event_name} reminder item: {item!r}", file=sys.stderr)
            continue
        if not TIME_PATTERN.fullmatch(reminder_time):
            print(f"Warning: ignore invalid {event_name} reminder time: {reminder_time}", file=sys.stderr)
            continue
        if reminder_time in seen:
            continue
        schedule.append({
            "time": reminder_time,
            "label": label,
            "tag": f"{reminder_time.replace(':', '')}_{index}",
        })
        seen.add(reminder_time)

    if schedule:
        return schedule
    print(f"Warning: no valid {event_name} reminder schedule configured; using defaults", file=sys.stderr)
    return [
        {
            "time": item["time"],
            "label": item["label"],
            "tag": f"{item['time'].replace(':', '')}_{index}",
        }
        for index, item in enumerate(default_schedule)
    ]

def load_subscribe_reminder_schedule() -> list[dict[str, Any]]:
    config = load_config()
    raw_schedule = config.get("subscribe_reminder_schedule")
    if raw_schedule is None:
        raw_schedule = config.get("subscribe_reminder_times", list(DEFAULT_SUBSCRIBE_REMINDER_SCHEDULE))
    return normalize_time_schedule(raw_schedule, DEFAULT_SUBSCRIBE_REMINDER_SCHEDULE, "申购")

def load_subscribe_reminder_times() -> tuple[str, ...]:
    return tuple(item["time"] for item in load_subscribe_reminder_schedule())

def load_winning_reminder_schedule() -> list[dict[str, Any]]:
    config = load_config()
    raw_schedule = config.get("winning_reminder_schedule", list(DEFAULT_WINNING_REMINDER_SCHEDULE))
    return normalize_time_schedule(raw_schedule, DEFAULT_WINNING_REMINDER_SCHEDULE, "中签结果公布")

def load_listing_limit_up_reminder_config() -> dict[str, Any]:
    config = load_config()
    raw_config = config.get("listing_limit_up_reminder")
    result = dict(DEFAULT_LISTING_LIMIT_UP_REMINDER)
    if isinstance(raw_config, dict):
        result.update(raw_config)
    if not isinstance(result.get("enabled"), bool):
        result["enabled"] = bool(result.get("enabled"))
    for key in ("check_time", "reminder_time"):
        value = result.get(key)
        if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value.strip()):
            print(f"Warning: invalid listing_limit_up_reminder.{key}; using default", file=sys.stderr)
            result[key] = DEFAULT_LISTING_LIMIT_UP_REMINDER[key]
        else:
            result[key] = value.strip()
    threshold = result.get("threshold_percent")
    if not isinstance(threshold, (int, float)) or threshold <= 0:
        print("Warning: invalid listing_limit_up_reminder.threshold_percent; using default", file=sys.stderr)
        result["threshold_percent"] = DEFAULT_LISTING_LIMIT_UP_REMINDER["threshold_percent"]
    label = result.get("label")
    if not isinstance(label, str) or not label.strip():
        result["label"] = DEFAULT_LISTING_LIMIT_UP_REMINDER["label"]
    else:
        result["label"] = label.strip()
    return result

def load_listing_tracking_max_days() -> int:
    config = load_config()
    value = config.get("listing_tracking_max_days", DEFAULT_LISTING_TRACKING_MAX_DAYS)
    if isinstance(value, int) and value > 0:
        return value
    print("Warning: invalid listing_tracking_max_days; using default", file=sys.stderr)
    return DEFAULT_LISTING_TRACKING_MAX_DAYS

def load_listing_reminder_schedule() -> list[dict[str, Any]]:
    config = load_config()
    raw_schedule = config.get("listing_reminder_schedule", list(DEFAULT_LISTING_REMINDER_SCHEDULE))
    if not isinstance(raw_schedule, list):
        print("Warning: listing_reminder_schedule must be a list; using defaults", file=sys.stderr)
        raw_schedule = list(DEFAULT_LISTING_REMINDER_SCHEDULE)

    schedule: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_schedule):
        if not isinstance(raw_item, dict):
            print(f"Warning: ignore invalid listing reminder item: {raw_item!r}", file=sys.stderr)
            continue
        days_offset = raw_item.get("days_offset")
        reminder_time = raw_item.get("time")
        if not isinstance(days_offset, int) or not isinstance(reminder_time, str):
            print(f"Warning: ignore invalid listing reminder item: {raw_item!r}", file=sys.stderr)
            continue
        reminder_time = reminder_time.strip()
        if not TIME_PATTERN.fullmatch(reminder_time):
            print(f"Warning: ignore invalid listing reminder time: {reminder_time}", file=sys.stderr)
            continue
        label = raw_item.get("label")
        if not isinstance(label, str) or not label.strip():
            label = f"上市日{days_offset:+d}天 {reminder_time}"
        schedule.append({
            "days_offset": days_offset,
            "time": reminder_time,
            "label": label.strip(),
            "tag": f"d{days_offset}_{reminder_time.replace(':', '')}_{index}",
        })

    if schedule:
        return schedule
    print("Warning: no valid listing reminder schedule configured; using defaults", file=sys.stderr)
    return [
        {
            "days_offset": item["days_offset"],
            "time": item["time"],
            "label": item["label"],
            "tag": f"d{item['days_offset']}_{item['time'].replace(':', '')}_{index}",
        }
        for index, item in enumerate(DEFAULT_LISTING_REMINDER_SCHEDULE)
    ]
