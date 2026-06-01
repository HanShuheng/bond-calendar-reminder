from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from .adapters import load_events
from .settings import today_local

def matches_query(event: dict[str, Any], query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return False
    q_compact = re.sub(r"\s+", "", q)
    code_fields = [
        event.get("bond_code", ""),
        event.get("subscribe_code", ""),
        event.get("allotment_code", ""),
        *event.get("all_codes", []),
    ]
    if q_compact.isdigit() and q_compact in code_fields:
        return True
    name_blob = "\n".join(
        str(event.get(key, "")) for key in ("name", "title", "description", "url")
    ).lower()
    name_compact = re.sub(r"\s+", "", name_blob)
    return q_compact in name_compact

def find_listing_events(query: str) -> list[dict[str, Any]] | None:
    events = load_events()
    if events is None:
        return None
    return [event for event in events if event["keyword"] == "上市日" and matches_query(event, query)]

def parse_single_date(value: str, base: date | None = None) -> date:
    base = base or today_local()
    text = value.strip()
    compact = re.sub(r"\s+", "", text)
    aliases = {
        "今天": base,
        "今日": base,
        "昨天": base - timedelta(days=1),
        "昨日": base - timedelta(days=1),
        "明天": base + timedelta(days=1),
        "明日": base + timedelta(days=1),
    }
    if compact in aliases:
        return aliases[compact]

    match = re.fullmatch(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日|号)?", compact)
    if match:
        year, month, day = map(int, match.groups())
        return date(year, month, day)

    match = re.fullmatch(r"(\d{1,2})[-/.月](\d{1,2})(?:日|号)?", compact)
    if match:
        month, day = map(int, match.groups())
        return date(base.year, month, day)

    raise ValueError(f"无法识别日期：{value}")

def parse_date_range_expression(value: str, base: date | None = None) -> tuple[date, date]:
    base = base or today_local()
    text = value.strip()
    compact = re.sub(r"\s+", "", text)

    match = re.search(r"(?:今天|今日)(?:开始|起|后)?(\d+)天内", compact)
    if match:
        days = int(match.group(1))
        if days < 1:
            raise ValueError("天数必须大于等于 1")
        return base, base + timedelta(days=days - 1)

    if compact in {"今天后一周内", "今日后一周内", "今天后一个星期内", "今日后一个星期内", "未来一周", "未来7天"}:
        return base, base + timedelta(days=6)

    separators = ("到", "至", "~", "～")
    for sep in separators:
        if sep in compact:
            left, right = compact.split(sep, 1)
            start = parse_single_date(left, base)
            end = parse_single_date(right, base)
            if end < start:
                end = date(start.year + 1, end.month, end.day)
            return start, end

    range_match = re.fullmatch(
        r"(.+?[日号]|\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}|\d{1,2}[-/.]\d{1,2})-(.+)",
        compact,
    )
    if range_match:
        start = parse_single_date(range_match.group(1), base)
        end = parse_single_date(range_match.group(2), base)
        if end < start:
            end = date(start.year + 1, end.month, end.day)
        return start, end

    single = parse_single_date(compact, base)
    return single, single

def resolve_subscribe_period(
    date_expr: str | None,
    start_expr: str | None,
    end_expr: str | None,
    days: int | None,
) -> tuple[date, date]:
    if days is not None:
        if days < 1:
            raise ValueError("--days 必须大于等于 1")
        start = parse_single_date(start_expr, today_local()) if start_expr else today_local()
        return start, start + timedelta(days=days - 1)

    if start_expr or end_expr:
        if not start_expr or not end_expr:
            raise ValueError("--start 和 --end 需要同时提供，或改用 --date/--days")
        start = parse_single_date(start_expr)
        end = parse_single_date(end_expr, start)
        if end < start:
            end = date(start.year + 1, end.month, end.day)
        return start, end

    return parse_date_range_expression(date_expr or "今天")

def find_subscribe_events(
    start: date | None,
    end: date | None,
    query: str | None = None,
) -> list[dict[str, Any]] | None:
    events = load_events()
    if events is None:
        return None
    matches: list[dict[str, Any]] = []
    for event in events:
        if event["keyword"] != "申购日":
            continue
        event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        if start is not None and event_date < start:
            continue
        if end is not None and event_date > end:
            continue
        if not query or matches_query(event, query):
            matches.append(event)
    return matches
