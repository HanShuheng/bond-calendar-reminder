from __future__ import annotations

import re
from pathlib import Path

try:
    import requests
except ModuleNotFoundError:
    requests = None  # type: ignore[assignment]
    RequestException = Exception
else:
    RequestException = requests.RequestException

from .settings import DEFAULT_HEADERS, DEFAULT_UPDATE_CHECK_URL, PROJECT_ROOT
from .formatters import format_error, format_status_message

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
    skill_file = PROJECT_ROOT / "SKILL.md"
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
    print(format_status_message(
        "INFO",
        "当前 Skill 版本",
        [("详情", [f"- 当前版本：{local_skill_version()}"])],
    ))
    return 0

def check_update(remote_url: str = DEFAULT_UPDATE_CHECK_URL) -> int:
    current = local_skill_version()
    if requests is None:
        print(format_error(
            "缺少 requests 依赖，无法检查远端版本",
            "请先安装 requirements.txt 后再重试。",
        ))
        return 1
    try:
        response = requests.get(remote_url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
    except RequestException as exc:
        print(format_error(f"检查远端版本失败：{exc}"))
        return 1

    latest = extract_skill_version(response.text)
    if not latest:
        print(format_error("远端 SKILL.md 中未找到版本号"))
        return 1

    comparison = compare_versions(current, latest)
    if comparison < 0:
        summary = "建议更新可转债提醒 Skill"
        suggestion = "cd ~/cow/skills/bond-calendar-reminder-skill && git pull"
    elif comparison == 0:
        summary = "当前已是最新版本"
        suggestion = None
    else:
        summary = "当前版本高于远端版本，可能正在使用本地开发版"
        suggestion = None
    sections = [("详情", [f"- 当前版本：{current}", f"- 最新版本：{latest}"])]
    if suggestion:
        sections.append(("建议", [suggestion]))
    print(format_status_message("INFO", summary, sections))
    return 0
