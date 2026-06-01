from __future__ import annotations

import shlex
import subprocess
import sys
from datetime import datetime
from typing import Any

from .settings import (
    BOND_TASK_PREFIXES, DATA_DIR, DEFAULT_CRON_SCHEDULE, PROJECT_ROOT, TASKS_FILE,
    TIMEZONE, TIME_PATTERN, WEIXIN_CREDS_FILE, now_local,
)
from .storage import load_config, read_json, write_json

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
    return [
        line for line in read_crontab_raw_lines()
        if line.strip() and not line.strip().startswith("#") and "bond_calendar.py" in line
    ]

def read_crontab_raw_lines() -> list[str]:
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
    return result.stdout.splitlines()

def cron_time_fields(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value.strip()):
        raise ValueError(f"invalid cron time: {value}")
    hour, minute = value.strip().split(":", 1)
    return minute, hour

def build_cron_line(command: str, run_time: str, python_bin: str | None = None) -> str:
    minute, hour = cron_time_fields(run_time)
    python_path = python_bin or sys.executable or "python3"
    script_path = PROJECT_ROOT / "scripts" / "bond_calendar.py"
    log_path = DATA_DIR / "bond_calendar.log"
    return (
        f"{minute} {hour} * * * "
        f"{shlex.quote(str(python_path))} {shlex.quote(str(script_path))} {command} "
        f">> {shlex.quote(str(log_path))} 2>&1"
    )

def default_cron_jobs(
    daily_time: str | None = None,
    tracking_time: str | None = None,
    limit_up_time: str | None = None,
    python_bin: str | None = None,
) -> list[dict[str, str]]:
    schedule = {
        "prepare-daily-reminders": daily_time or DEFAULT_CRON_SCHEDULE["prepare-daily-reminders"],
        "check-tracked-listings": tracking_time or DEFAULT_CRON_SCHEDULE["check-tracked-listings"],
        "check-listing-limit-up": limit_up_time or DEFAULT_CRON_SCHEDULE["check-listing-limit-up"],
    }
    return [
        {
            "command": command,
            "time": run_time,
            "line": build_cron_line(command, run_time, python_bin),
        }
        for command, run_time in schedule.items()
    ]

def crontab_has_command(lines: list[str], command: str) -> bool:
    needle = f"bond_calendar.py {command}"
    return any(needle in line and not line.strip().startswith("#") for line in lines)

def install_cron_jobs(jobs: list[dict[str, str]], apply: bool = False, replace: bool = False) -> dict[str, list[str]]:
    existing = read_crontab_raw_lines()
    installed: list[str] = []
    skipped: list[str] = []
    commands = {job["command"] for job in jobs}
    new_lines = [
        line for line in existing
        if not replace or not any(crontab_has_command([line], command) for command in commands)
    ]
    for job in jobs:
        command = job["command"]
        line = job["line"]
        if not replace and (crontab_has_command(existing, command) or crontab_has_command(new_lines, command)):
            skipped.append(line)
            continue
        installed.append(line)
        new_lines.append(line)
    if apply and installed:
        content = "\n".join(new_lines).rstrip() + "\n"
        subprocess.run(
            ["crontab", "-"],
            input=content,
            text=True,
            check=True,
            timeout=5,
        )
    return {"installed": installed, "skipped": skipped}

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

def notify_target_status() -> str:
    target = resolve_notify_target()
    if target is None:
        return "未识别，自动提醒任务无法创建"
    if target.get("_source") == "legacy_config":
        return "使用兼容配置"
    if target.get("_source") == "auto_weixin":
        return "已自动识别（weixin）"
    return "已识别"
