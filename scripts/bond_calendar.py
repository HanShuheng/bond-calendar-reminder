#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

try:
    import requests
except ModuleNotFoundError:
    requests = None  # type: ignore[assignment]
    RequestException = Exception
else:
    RequestException = requests.RequestException


TIMEZONE = ZoneInfo("Asia/Shanghai")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}

WORKSPACE = Path(os.environ.get("COW_WORKSPACE", "~/cow")).expanduser()
DATA_DIR = WORKSPACE / "bond_reminders"
CONFIG_FILE = DATA_DIR / "config.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
DAILY_SUBSCRIBE_FILE = DATA_DIR / "daily_subscribe.json"
TASKS_FILE = WORKSPACE / "scheduler" / "tasks.json"
WEIXIN_CREDS_FILE = Path("~/.weixin_cow_credentials.json").expanduser()

DEFAULT_SUBSCRIBE_REMINDER_SCHEDULE = (
    {"time": "10:00", "label": "10:00 申购提醒"},
    {"time": "13:00", "label": "13:00 申购提醒"},
)
DEFAULT_LISTING_TRACKING_MAX_DAYS = 180
DEFAULT_LISTING_REMINDER_SCHEDULE = (
    {"days_offset": -1, "time": "12:00", "label": "上市前一天 12:00"},
    {"days_offset": 0, "time": "08:30", "label": "上市当天 08:30，开盘前 1 小时"},
    {"days_offset": 0, "time": "13:00", "label": "上市当天 13:00"},
)
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
SENSITIVE_KEY_PATTERN = re.compile(r"(authorization|cookie|token|key|secret|password)", re.IGNORECASE)
BOND_TASK_PREFIXES = ("bond-subscribe-", "bond-listing-")
DEFAULT_UPDATE_CHECK_URL = (
    "https://raw.githubusercontent.com/HanShuheng/bond-calendar-reminder/main/SKILL.md"
)


def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def today_local() -> date:
    return now_local().date()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Warning: failed to read {path}: {exc}", file=sys.stderr)
    return default


def write_json(path: Path, data: Any) -> None:
    ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def extract_skill_version(text: str) -> str | None:
    in_metadata = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == "metadata:":
            in_metadata = True
            continue
        if in_metadata and line and not line.startswith((" ", "\t")):
            in_metadata = False
        if in_metadata:
            match = re.match(r"^\s+version:\s*['\"]?([^'\"\s]+)", line)
            if match:
                return match.group(1)
    match = re.search(r"(?m)^version:\s*['\"]?([^'\"\s]+)", text)
    return match.group(1) if match else None


def local_skill_version() -> str:
    skill_file = Path(__file__).resolve().parents[1] / "SKILL.md"
    try:
        version = extract_skill_version(skill_file.read_text(encoding="utf-8"))
    except Exception:
        version = None
    return version or "unknown"


def version_key(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version)
    return tuple(int(part) for part in parts) if parts else (0,)


def compare_versions(current: str, latest: str) -> int:
    current_parts = list(version_key(current))
    latest_parts = list(version_key(latest))
    width = max(len(current_parts), len(latest_parts))
    current_parts.extend([0] * (width - len(current_parts)))
    latest_parts.extend([0] * (width - len(latest_parts)))
    if current_parts < latest_parts:
        return -1
    if current_parts > latest_parts:
        return 1
    return 0


def show_version() -> int:
    print(f"INFO 当前版本：{local_skill_version()}")
    return 0


def check_update(remote_url: str = DEFAULT_UPDATE_CHECK_URL) -> int:
    current = local_skill_version()
    print(f"INFO 当前版本：{current}")
    if requests is None:
        print("ERROR: 缺少 requests 依赖，无法检查远端版本")
        return 1
    try:
        response = requests.get(remote_url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
    except RequestException as exc:
        print(f"ERROR: 检查远端版本失败：{exc}")
        return 1

    latest = extract_skill_version(response.text)
    if not latest:
        print("ERROR: 远端 SKILL.md 中未找到版本号")
        return 1

    print(f"INFO 最新版本：{latest}")
    comparison = compare_versions(current, latest)
    if comparison < 0:
        print("INFO 建议更新：cd ~/cow/skills/bond-calendar-reminder && git pull")
    elif comparison == 0:
        print("INFO 当前已是最新版本")
    else:
        print("INFO 当前版本高于远端版本，可能正在使用本地开发版")
    return 0


def load_config() -> dict[str, Any]:
    config = read_json(CONFIG_FILE, {})
    return config if isinstance(config, dict) else {}


def load_data_source_config() -> dict[str, Any]:
    config = load_config()
    data_source = config.get("data_source")
    if not isinstance(data_source, dict):
        data_source = {}

    calendar_url = os.environ.get("BOND_CALENDAR_URL") or data_source.get("calendar_url")
    if not isinstance(calendar_url, str) or not calendar_url.strip():
        raise ValueError(
            f"缺少数据源配置：请在 {CONFIG_FILE} 中设置 data_source.calendar_url"
        )

    headers = dict(DEFAULT_HEADERS)
    custom_headers = data_source.get("headers")
    if isinstance(custom_headers, dict):
        headers.update({str(key): str(value) for key, value in custom_headers.items()})

    return {
        "calendar_url": calendar_url.strip(),
        "base_url": data_source.get("base_url") if isinstance(data_source.get("base_url"), str) else "",
        "detail_url_template": (
            data_source.get("detail_url_template")
            if isinstance(data_source.get("detail_url_template"), str)
            else ""
        ),
        "headers": headers,
    }


def load_subscribe_reminder_schedule() -> list[dict[str, Any]]:
    config = load_config()
    raw_schedule = config.get("subscribe_reminder_schedule")
    if raw_schedule is None:
        raw_schedule = config.get("subscribe_reminder_times", list(DEFAULT_SUBSCRIBE_REMINDER_SCHEDULE))
    if not isinstance(raw_schedule, (list, tuple)):
        print("Warning: subscribe reminder schedule must be a list; using defaults", file=sys.stderr)
        raw_schedule = list(DEFAULT_SUBSCRIBE_REMINDER_SCHEDULE)

    schedule: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_schedule):
        if isinstance(item, str):
            reminder_time = item.strip()
            label = f"{reminder_time} 申购提醒"
        elif isinstance(item, dict):
            raw_time = item.get("time")
            if not isinstance(raw_time, str):
                print(f"Warning: ignore invalid subscribe reminder item: {item!r}", file=sys.stderr)
                continue
            reminder_time = raw_time.strip()
            raw_label = item.get("label")
            label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else f"{reminder_time} 申购提醒"
        else:
            print(f"Warning: ignore invalid subscribe reminder item: {item!r}", file=sys.stderr)
            continue
        if not TIME_PATTERN.fullmatch(reminder_time):
            print(f"Warning: ignore invalid subscribe reminder time: {reminder_time}", file=sys.stderr)
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
    print("Warning: no valid subscribe reminder schedule configured; using defaults", file=sys.stderr)
    return [
        {
            "time": item["time"],
            "label": item["label"],
            "tag": f"{item['time'].replace(':', '')}_{index}",
        }
        for index, item in enumerate(DEFAULT_SUBSCRIBE_REMINDER_SCHEDULE)
    ]


def load_subscribe_reminder_times() -> tuple[str, ...]:
    return tuple(item["time"] for item in load_subscribe_reminder_schedule())


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


def fetch_calendar_data(
    data_source: dict[str, Any] | None = None,
    retries: int = 3,
    timeout: int = 15,
) -> list[dict[str, Any]] | None:
    if requests is None:
        print("ERROR: 缺少 Python 依赖 requests，请先安装 requirements.txt")
        return None
    if data_source is None:
        try:
            data_source = load_data_source_config()
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return None

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                data_source["calendar_url"],
                headers=data_source["headers"],
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(f"Expected JSON list, got {type(data).__name__}")
            return [item for item in data if isinstance(item, dict)]
        except (RequestException, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            print(f"Warning: fetch attempt {attempt}/{retries} failed: {exc}", file=sys.stderr)
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
    print(f"ERROR: 数据源暂时不可用: {last_error}")
    return None


def clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def parse_event_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def event_keyword(title: str) -> str | None:
    if "申购日" in title:
        return "申购日"
    if "上市日" in title:
        return "上市日"
    return None


def strip_event_prefix(title: str) -> str:
    name = re.sub(r"^【[^】]+】", "", title).strip()
    return name or title.strip()


def extract_code(label: str, text: str) -> str:
    pattern = rf"{label}\s*[:：]?\s*(\d{{6}})"
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def all_six_digit_codes(text: str) -> list[str]:
    return sorted(set(re.findall(r"(?<!\d)(\d{6})(?!\d)", text)))


def detail_url_for(code: str, raw_url: Any, data_source: dict[str, Any]) -> str:
    if isinstance(raw_url, str) and raw_url.startswith("http"):
        return raw_url
    base_url = data_source.get("base_url") or ""
    if isinstance(raw_url, str) and raw_url and base_url:
        return urljoin(base_url, raw_url)
    detail_url_template = data_source.get("detail_url_template") or ""
    if detail_url_template:
        return detail_url_template.format(code=code)
    return raw_url if isinstance(raw_url, str) else ""


def normalize_event(item: dict[str, Any], data_source: dict[str, Any]) -> dict[str, Any] | None:
    title = item.get("title")
    start = item.get("start")
    raw_code = item.get("code")
    if not isinstance(title, str) or not start:
        return None
    keyword = event_keyword(title)
    if keyword is None:
        return None
    event_date = parse_event_date(start)
    if event_date is None:
        return None

    description = clean_text(item.get("description"))
    text_blob = "\n".join(str(part) for part in [title, raw_code or "", description, item.get("url") or ""])
    bond_code = extract_code("转债代码", text_blob)
    subscribe_code = extract_code("申购代码", text_blob)
    allotment_code = extract_code("(?:配售代码|配债代码)", text_blob)
    if not bond_code and isinstance(raw_code, str) and re.fullmatch(r"\d{6}", raw_code):
        bond_code = raw_code

    codes = all_six_digit_codes(text_blob)
    return {
        "id": item.get("id") or "",
        "title": title.strip(),
        "name": strip_event_prefix(title),
        "keyword": keyword,
        "date": event_date.isoformat(),
        "bond_code": bond_code,
        "subscribe_code": subscribe_code,
        "allotment_code": allotment_code,
        "all_codes": codes,
        "description": description,
        "url": detail_url_for(bond_code or (codes[0] if codes else ""), item.get("url"), data_source),
    }


def load_events() -> list[dict[str, Any]] | None:
    try:
        data_source = load_data_source_config()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return None
    raw = fetch_calendar_data(data_source)
    if raw is None:
        return None
    events = [event for item in raw if (event := normalize_event(item, data_source))]
    return sorted(events, key=lambda e: (e["date"], e.get("bond_code") or "", e["title"]))


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


def format_code_lines(event: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if event.get("bond_code"):
        lines.append(f"转债代码：{event['bond_code']}")
    if event.get("subscribe_code"):
        lines.append(f"申购代码：{event['subscribe_code']}")
    if event.get("allotment_code"):
        lines.append(f"配售代码：{event['allotment_code']}")
    return lines


def format_subscribe_message(events: list[dict[str, Any]], slot: str | None = None) -> str:
    header = "今日可转债申购提醒"
    if slot and slot != "query":
        header += f"（{slot}）"
    lines = [header, ""]
    for event in events:
        lines.append(f"- {event['name']}")
        lines.extend(f"  {line}" for line in format_code_lines(event))
        if event.get("url"):
            lines.append(f"  详情：{event['url']}")
    return "\n".join(lines).strip()


def format_subscribe_query_message(
    events: list[dict[str, Any]],
    start: date | None,
    end: date | None,
    query: str | None = None,
) -> str:
    if start is None or end is None:
        header = "可转债申购查询结果"
    elif start == end:
        header = f"{start.isoformat()} 可转债申购查询结果"
    else:
        header = f"{start.isoformat()} 至 {end.isoformat()} 可转债申购查询结果"
    if query:
        header += f"（{query}）"

    lines = [header, ""]
    current_date = ""
    for event in events:
        if event["date"] != current_date:
            current_date = event["date"]
            lines.append(f"{current_date}")
        lines.append(f"- {event['name']}")
        lines.extend(f"  {line}" for line in format_code_lines(event))
        if event.get("url"):
            lines.append(f"  详情：{event['url']}")
    return "\n".join(lines).strip()


def format_listing_message(event: dict[str, Any], label: str) -> str:
    lines = [
        f"{event['name']}上市提醒",
        "",
        *format_code_lines(event),
        f"上市日期：{event['date']}",
        f"当前提醒：{label}",
    ]
    if event.get("url"):
        lines.append(f"详情：{event['url']}")
    return "\n".join(lines).strip()


def load_tasks() -> dict[str, Any]:
    data = read_json(TASKS_FILE, {"version": 1, "tasks": {}})
    if not isinstance(data, dict):
        data = {"version": 1, "tasks": {}}
    if not isinstance(data.get("tasks"), dict):
        data["tasks"] = {}
    return data


def save_tasks(data: dict[str, Any]) -> None:
    ensure_dirs()
    if TASKS_FILE.exists():
        backup = TASKS_FILE.with_suffix(TASKS_FILE.suffix + ".bak")
        try:
            backup.write_text(TASKS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    data["version"] = 1
    data["updated_at"] = datetime.now().isoformat()
    write_json(TASKS_FILE, data)


def local_naive(dt: datetime) -> str:
    return dt.astimezone(TIMEZONE).replace(tzinfo=None).isoformat()


def resolve_notify_target() -> dict[str, Any] | None:
    config = load_config()
    receiver = config.get("receiver")
    if isinstance(receiver, str) and receiver.strip():
        return {
            "receiver": receiver.strip(),
            "receiver_name": config.get("receiver_name", "微信用户"),
            "is_group": bool(config.get("is_group", False)),
            "channel_type": config.get("channel_type", "weixin"),
            "notify_session_id": config.get("notify_session_id") or receiver.strip(),
            "_source": "legacy_config",
        }

    creds = read_json(WEIXIN_CREDS_FILE, {})
    tokens = creds.get("context_tokens") if isinstance(creds, dict) else {}
    if isinstance(tokens, dict) and tokens:
        receivers = sorted(str(key) for key in tokens.keys() if str(key).strip())
        if receivers:
            if len(receivers) > 1:
                print(
                    "Warning: multiple weixin context tokens found; using the first one",
                    file=sys.stderr,
                )
            receiver = receivers[0]
            return {
                "receiver": receiver,
                "receiver_name": "微信用户",
                "is_group": False,
                "channel_type": "weixin",
                "notify_session_id": receiver,
                "_source": "auto_weixin",
            }
    return None


def task_receiver_fields() -> dict[str, Any] | None:
    target = resolve_notify_target()
    if target is None:
        return None
    return {key: value for key, value in target.items() if not key.startswith("_")}


def upsert_once_message_task(task_id: str, name: str, run_at: datetime, content: str) -> bool:
    if run_at < now_local():
        return False
    receiver_fields = task_receiver_fields()
    if receiver_fields is None:
        print(
            "Warning: notify target not found; cannot create scheduler task",
            file=sys.stderr,
        )
        return False
    data = load_tasks()
    tasks = data["tasks"]
    timestamp = datetime.now().isoformat()
    task = tasks.get(task_id, {})
    created_at = task.get("created_at", timestamp)
    tasks[task_id] = {
        "id": task_id,
        "name": name,
        "enabled": True,
        "created_at": created_at,
        "updated_at": timestamp,
        "schedule": {"type": "once", "run_at": local_naive(run_at)},
        "action": {
            "type": "send_message",
            "content": content,
            **receiver_fields,
        },
        "next_run_at": local_naive(run_at),
    }
    save_tasks(data)
    return True


def prepare_subscribe_today(create_tasks: bool = True) -> int:
    events = load_events()
    today = today_local().isoformat()
    if events is None:
        snapshot = {
            "date": today,
            "generated_at": now_local().isoformat(),
            "status": "error",
            "events": [],
        }
        write_json(DAILY_SUBSCRIBE_FILE, snapshot)
        print("ERROR: 数据源暂时不可用")
        return 1

    subscribe_events = [
        event for event in events if event["keyword"] == "申购日" and event["date"] == today
    ]
    snapshot = {
        "date": today,
        "generated_at": now_local().isoformat(),
        "status": "ok",
        "events": subscribe_events,
    }
    write_json(DAILY_SUBSCRIBE_FILE, snapshot)

    if not subscribe_events:
        print("NO_ALERT: 今日暂无可转债申购事项")
        return 0

    print(format_subscribe_message(subscribe_events))
    if create_tasks:
        for reminder in load_subscribe_reminder_schedule():
            slot = reminder["time"]
            label = reminder["label"]
            hour, minute = map(int, slot.split(":"))
            run_at = datetime.combine(today_local(), clock_time(hour, minute), tzinfo=TIMEZONE)
            task_id = f"bond-subscribe-{today.replace('-', '')}-{slot.replace(':', '')}"
            upsert_once_message_task(
                task_id,
                f"可转债申购提醒 {today} {label}",
                run_at,
                format_subscribe_message(subscribe_events, label),
            )
    return 0


def send_prepared_subscribe(slot: str) -> int:
    snapshot = read_json(DAILY_SUBSCRIBE_FILE, {})
    if snapshot.get("date") != today_local().isoformat():
        result = prepare_subscribe_today(create_tasks=False)
        snapshot = read_json(DAILY_SUBSCRIBE_FILE, {})
        if result != 0:
            print("ERROR: 今日申购缓存缺失，且自动补查失败")
            return result
    if snapshot.get("status") == "error":
        print("ERROR: 今日申购缓存处于错误状态，请稍后重试")
        return 1
    events = snapshot.get("events") if isinstance(snapshot, dict) else []
    if not events:
        print("NO_ALERT: 今日暂无可转债申购事项")
        return 0
    print(format_subscribe_message(events, None if slot == "query" else slot))
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
            print(f"ERROR: {exc}")
            return 2
    elif query:
        start = None
        end = None
    else:
        start, end = resolve_subscribe_period("今天", None, None, None)

    matches = find_subscribe_events(start, end, query)
    if matches is None:
        print("ERROR: 数据源暂时不可用")
        return 1
    if not matches:
        if start is None or end is None:
            period = "数据源可见范围内"
        elif start == end:
            period = start.isoformat()
        else:
            period = f"{start.isoformat()} 至 {end.isoformat()}"
        suffix = f"（{query}）" if query else ""
        print(f"NO_ALERT: {period}{suffix} 暂无匹配的可转债申购事项")
        return 0
    print("ALERT: 已查到可转债申购事项")
    print(format_subscribe_query_message(matches, start, end, query))
    return 0


def print_listing_result(event: dict[str, Any]) -> None:
    print(f"ALERT: 已查到上市日期")
    print(format_listing_message(event, "上市日期查询"))


def find_listing(query: str) -> int:
    matches = find_listing_events(query)
    if matches is None:
        print("ERROR: 数据源暂时不可用")
        return 1
    if not matches:
        print(f"NOT_FOUND: 暂未查到 {query} 的上市日期")
        return 0
    if len(matches) > 1:
        print("MULTIPLE_MATCHES: 找到多个候选，请用转债代码确认")
        for event in matches:
            print(f"- {event['date']} {event['name']} {event.get('bond_code') or ''} {event['url']}")
        return 0
    print_listing_result(matches[0])
    return 0


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


def parse_local_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TIMEZONE)
    return parsed.astimezone(TIMEZONE)


def parse_item_created_at(item: dict[str, Any]) -> datetime | None:
    return parse_local_datetime(item.get("created_at"))


def is_tracking_expired(item: dict[str, Any], max_days: int) -> bool:
    created_at = parse_item_created_at(item)
    if created_at is None:
        return False
    return now_local() >= created_at + timedelta(days=max_days)


def task_run_at(task: dict[str, Any]) -> datetime | None:
    run_at = parse_local_datetime(task.get("next_run_at"))
    if run_at is not None:
        return run_at
    schedule = task.get("schedule")
    if isinstance(schedule, dict):
        return parse_local_datetime(schedule.get("run_at"))
    return None


def is_active_bond_task(task_id: str, task: dict[str, Any], prefix: str | None = None) -> bool:
    if prefix and not task_id.startswith(prefix):
        return False
    if not prefix and not task_id.startswith(BOND_TASK_PREFIXES):
        return False
    if task.get("enabled") is False:
        return False
    run_at = task_run_at(task)
    return run_at is not None and run_at >= now_local()


def disable_task_ids(task_ids: list[str]) -> int:
    if not task_ids:
        return 0
    data = load_tasks()
    tasks = data.get("tasks", {})
    changed = 0
    timestamp = now_local().isoformat()
    for task_id in task_ids:
        task = tasks.get(task_id)
        if isinstance(task, dict) and task.get("enabled") is not False:
            task["enabled"] = False
            task["updated_at"] = timestamp
            changed += 1
    if changed:
        save_tasks(data)
    return changed


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
        print(f"ERROR: 数据源暂时不可用；已记录 {query}，数据源恢复后会继续追踪上市日期")
        return 1
    if not matches:
        item["status"] = "pending"
        data["items"][key] = item
        save_watchlist(data)
        print(f"TRACKING: 暂未查到 {query} 的上市日期，已加入每日追踪")
        return 0
    if len(matches) > 1:
        item["status"] = "needs_confirmation"
        item["candidates"] = matches
        data["items"][key] = item
        save_watchlist(data)
        print("MULTIPLE_MATCHES: 找到多个候选，请用转债代码重新添加")
        for event in matches:
            print(f"- {event['date']} {event['name']} {event.get('bond_code') or ''} {event['url']}")
        return 0

    event = matches[0]
    canonical_key = canonical_watch_key(event, query)
    item = merge_watch_items(data, canonical_key, key)
    scheduled = schedule_listing_tasks(event)
    update_item_with_listing(item, query, event, scheduled)
    save_watchlist(data)
    if item["status"] == "scheduled":
        print("SCHEDULED: 已创建上市提醒")
    elif item["status"] == "expired":
        print("EXPIRED: 已查到上市日期，但所有提醒时间均已过期")
    else:
        print("TRACKING: 已查到上市日期，但提醒任务创建失败，已保留追踪等待下次重试")
    print(format_listing_message(event, "上市提醒计划已创建"))
    if item.get("task_ids"):
        print("任务ID：" + ", ".join(item["task_ids"]))
    else:
        print("Warning: 上市提醒任务未创建，请检查提醒目标或提醒时间配置")
    if item.get("skipped_reminders"):
        print("已跳过过期提醒：" + str(len(item["skipped_reminders"])))
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
        print("NO_ALERT: 暂无待追踪上市转债")
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
        print("ALERT: 已为以下转债创建上市提醒")
        for message in scheduled_messages:
            print(f"- {message}")
    else:
        print("NO_ALERT: 暂未查到新的上市日期")
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
        print(f"NOT_FOUND: 暂未找到 {query} 的上市提醒或追踪记录")
        return 0
    if len(matches) > 1:
        print("MULTIPLE_MATCHES: 找到多个提醒记录，请用转债代码取消")
        for key, item in matches:
            event = item.get("event") if isinstance(item.get("event"), dict) else {}
            print(f"- {key} {event.get('name') or item.get('query') or ''} {item.get('status')}")
        return 0

    key, item = matches[0]
    disabled_count = disable_task_ids(item.get("task_ids") if isinstance(item.get("task_ids"), list) else [])
    item["status"] = "canceled"
    item["canceled_at"] = now_local().isoformat()
    item["updated_at"] = now_local().isoformat()
    save_watchlist(data)
    print(f"CANCELED: 已取消 {query} 的上市提醒/追踪")
    if disabled_count:
        print(f"已禁用 scheduler 任务：{disabled_count} 个")
    return 0


def format_task_line(task_id: str, task: dict[str, Any]) -> str:
    run_at = task_run_at(task)
    run_at_text = local_naive(run_at) if run_at else "未知时间"
    name = task.get("name") or task_id
    return f"- {run_at_text} {name}（{task_id}）"


def list_reminders() -> int:
    tasks = load_tasks().get("tasks", {})
    subscribe_tasks: list[tuple[str, dict[str, Any]]] = []
    listing_tasks: list[tuple[str, dict[str, Any]]] = []
    for task_id, task in tasks.items():
        if not isinstance(task, dict):
            continue
        if is_active_bond_task(task_id, task, "bond-subscribe-"):
            subscribe_tasks.append((task_id, task))
        elif is_active_bond_task(task_id, task, "bond-listing-"):
            listing_tasks.append((task_id, task))
    subscribe_tasks.sort(key=lambda pair: task_run_at(pair[1]) or datetime.max.replace(tzinfo=TIMEZONE))
    listing_tasks.sort(key=lambda pair: task_run_at(pair[1]) or datetime.max.replace(tzinfo=TIMEZONE))

    watchlist = load_watchlist().get("items", {})
    tracking = [
        (key, item) for key, item in watchlist.items()
        if isinstance(item, dict) and item.get("status") in {"pending", "needs_confirmation"}
    ]
    tracking.sort(key=lambda pair: str(pair[1].get("created_at") or ""))

    if not subscribe_tasks and not listing_tasks and not tracking:
        print("NO_ALERT: 当前暂无债券相关提醒事项")
        return 0

    print("ALERT: 当前债券相关提醒事项")
    if subscribe_tasks:
        print("\n申购提醒")
        for task_id, task in subscribe_tasks:
            print(format_task_line(task_id, task))
    if listing_tasks:
        print("\n上市提醒")
        for task_id, task in listing_tasks:
            print(format_task_line(task_id, task))
    if tracking:
        print("\n待追踪上市")
        for key, item in tracking:
            query = item.get("query") or key
            created_at = item.get("created_at") or "未知时间"
            print(f"- {query}（{item.get('status')}，创建于 {created_at}）")
    return 0


def sanitize_value(key: str, value: Any) -> Any:
    if SENSITIVE_KEY_PATTERN.search(key):
        if value in (None, "", [], {}):
            return value
        return "***"
    if isinstance(value, dict):
        return {str(k): sanitize_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_value(key, item) for item in value]
    return value


def read_crontab_lines() -> list[str]:
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    lines: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "bond_calendar.py" in line:
            lines.append(raw_line)
    return lines


def count_active_tasks_by_prefix(tasks: dict[str, Any], prefix: str) -> int:
    return sum(
        1 for task_id, task in tasks.items()
        if isinstance(task, dict) and is_active_bond_task(task_id, task, prefix)
    )


def collect_active_bond_tasks(tasks: dict[str, Any], prefix: str) -> list[tuple[str, dict[str, Any]]]:
    result = [
        (task_id, task) for task_id, task in tasks.items()
        if isinstance(task, dict) and is_active_bond_task(task_id, task, prefix)
    ]
    return sorted(
        result,
        key=lambda pair: task_run_at(pair[1]) or datetime.max.replace(tzinfo=TIMEZONE),
    )


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


def notify_target_status() -> str:
    target = resolve_notify_target()
    if target is None:
        return "未识别，自动提醒任务无法创建"
    if target.get("_source") == "legacy_config":
        return "使用兼容配置"
    if target.get("_source") == "auto_weixin":
        return "已自动识别（weixin）"
    return "已识别"


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
    crontab_lines = read_crontab_lines()
    data_source = config.get("data_source") if isinstance(config.get("data_source"), dict) else {}
    subscribe_tasks = collect_active_bond_tasks(tasks, "bond-subscribe-")
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

    print("INFO: bond-calendar-reminder 待执行任务")
    print(f"生成时间：{now_local().isoformat()}")
    print("时区：Asia/Shanghai")
    print("")
    print("scheduler 待执行申购提醒")
    if subscribe_tasks:
        for task_id, task in subscribe_tasks:
            print(format_info_task_line(task_id, task))
    else:
        print("- 暂无")
    print("")
    print("scheduler 待执行上市提醒")
    if listing_tasks:
        for task_id, task in listing_tasks:
            print(format_info_task_line(task_id, task))
    else:
        print("- 暂无")
    print("")
    print("crontab 自动触发任务")
    if crontab_lines:
        for line in crontab_lines:
            print(f"- {line}")
    else:
        print("- 未发现包含 bond_calendar.py 的 crontab 任务")
    print("")
    print("待追踪上市事项")
    if tracking_items:
        for key, item in tracking_items:
            print(format_tracking_item(key, item))
    else:
        print("- 暂无")
    print("")
    print("今日申购缓存")
    if isinstance(daily, dict) and daily:
        print(f"- 日期：{daily.get('date', '未知')}")
        print(f"- 状态：{daily.get('status', '未知')}")
        print(f"- 生成时间：{daily.get('generated_at', '未知')}")
        events = daily.get("events")
        print(f"- 事项数：{len(events) if isinstance(events, list) else 0}")
    else:
        print("- 未生成")
    print("")
    print("配置摘要")
    print(f"- 数据源：{'已配置' if data_source.get('calendar_url') else '未配置'}")
    print(f"- 提醒目标：{notify_target_status()}")
    subscribe_schedule_text = ", ".join(
        str(item["label"])
        if str(item["label"]).startswith(str(item["time"]))
        else f"{item['time']} {item['label']}"
        for item in subscribe_schedule
    )
    print(f"- 申购提醒计划：{subscribe_schedule_text}")
    print(f"- 上市提醒计划：{len(listing_schedule)} 个提醒点")
    print(f"- 上市最长追踪天数：{load_listing_tracking_max_days()}")
    print(f"- 配置文件：{CONFIG_FILE}")
    print(f"- 运行数据目录：{DATA_DIR}")
    print(f"- scheduler 文件：{TASKS_FILE}")
    print(f"- 今日申购缓存：{DAILY_SUBSCRIBE_FILE}")
    print(f"- 上市追踪列表：{WATCHLIST_FILE}")
    print("")
    print("状态计数")
    print(f"- scheduler 待执行申购提醒：{len(subscribe_tasks)} 个")
    print(f"- scheduler 待执行上市提醒：{len(listing_tasks)} 个")
    for status in ("pending", "needs_confirmation", "scheduled", "expired", "canceled"):
        print(f"- watchlist {status}：{status_counts.get(status, 0)} 个")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="可转债申购与上市提醒")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare-subscribe-today")
    p_prepare.add_argument("--no-create-tasks", action="store_true")

    p_send = sub.add_parser("send-prepared-subscribe")
    p_send.add_argument("--slot", required=True)

    p_find_subscribe = sub.add_parser("find-subscribe")
    p_find_subscribe.add_argument("--date", help="日期或日期范围，例如：今天、昨天、3月4号、3月5号-3月10号、今天开始5天内")
    p_find_subscribe.add_argument("--start", help="开始日期，支持 YYYY-MM-DD、M月D号、今天、昨天")
    p_find_subscribe.add_argument("--end", help="结束日期，左右闭区间")
    p_find_subscribe.add_argument("--days", type=int, help="从 --start 或今天开始的天数，包含起始日期")
    p_find_subscribe.add_argument("--query", help="债券名、转债代码、申购代码或配售代码")

    p_find = sub.add_parser("find-listing")
    p_find.add_argument("--query", required=True)

    p_track = sub.add_parser("track-listing")
    p_track.add_argument("--query", required=True)

    p_cancel = sub.add_parser("cancel-listing")
    p_cancel.add_argument("--query", required=True)

    sub.add_parser("check-tracked-listings")
    sub.add_parser("list-reminders")
    sub.add_parser("info")
    sub.add_parser("version")
    p_check_update = sub.add_parser("check-update")
    p_check_update.add_argument(
        "--remote-url",
        default=DEFAULT_UPDATE_CHECK_URL,
        help="远端 SKILL.md 地址，默认检查 GitHub main 分支",
    )

    args = parser.parse_args()
    if args.command == "version":
        return show_version()
    if args.command == "check-update":
        return check_update(args.remote_url)

    ensure_dirs()
    if args.command == "prepare-subscribe-today":
        return prepare_subscribe_today(create_tasks=not args.no_create_tasks)
    if args.command == "send-prepared-subscribe":
        return send_prepared_subscribe(args.slot)
    if args.command == "find-subscribe":
        return find_subscribe(args.date, args.start, args.end, args.days, args.query)
    if args.command == "find-listing":
        return find_listing(args.query)
    if args.command == "track-listing":
        return track_listing(args.query)
    if args.command == "cancel-listing":
        return cancel_listing(args.query)
    if args.command == "check-tracked-listings":
        return check_tracked_listings()
    if args.command == "list-reminders":
        return list_reminders()
    if args.command == "info":
        return plugin_info()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
