#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bond_calendar_lib.settings import *
from bond_calendar_lib.storage import *
from bond_calendar_lib.versioning import *
from bond_calendar_lib.config import *
from bond_calendar_lib.adapters import *
from bond_calendar_lib.queries import *
from bond_calendar_lib.formatters import *
from bond_calendar_lib.scheduler import *
from bond_calendar_lib.watchlist import *
from bond_calendar_lib.commands import *

def main() -> int:
    parser = argparse.ArgumentParser(description="可转债申购与上市提醒")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare-subscribe-today")
    p_prepare.add_argument("--no-create-tasks", action="store_true")

    p_prepare_daily = sub.add_parser("prepare-daily-reminders")
    p_prepare_daily.add_argument("--no-create-tasks", action="store_true")

    p_send = sub.add_parser("send-prepared-subscribe")
    p_send.add_argument("--slot", required=True)

    p_prepare_winning = sub.add_parser("prepare-winning-today")
    p_prepare_winning.add_argument("--no-create-tasks", action="store_true")

    p_send_winning = sub.add_parser("send-prepared-winning")
    p_send_winning.add_argument("--slot", required=True)

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
    p_limit_up = sub.add_parser("check-listing-limit-up")
    p_limit_up.add_argument("--query", help="可选。只检查指定转债代码或名称")
    p_setup = sub.add_parser("setup-schedule")
    p_setup.add_argument("--yes", action="store_true", help="确认写入 crontab；不加时只预览")
    p_setup.add_argument("--replace", action="store_true", help="替换已有 bond_calendar.py 同名定时任务")
    p_setup.add_argument("--daily-time", help="每日申购和中签结果公布检查时间，默认 07:00")
    p_setup.add_argument("--tracking-time", help="每日上市追踪检查时间，默认 07:05")
    p_setup.add_argument("--limit-up-time", help="上市日涨幅检查时间，默认 14:50")
    p_setup.add_argument("--python", dest="python_bin", help="写入 crontab 的 Python 路径，默认使用当前解释器")
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
    if args.command not in {"setup-schedule"}:
        auto_setup_schedule_if_enabled()
    if args.command == "prepare-subscribe-today":
        return prepare_subscribe_today(create_tasks=not args.no_create_tasks)
    if args.command == "prepare-daily-reminders":
        return prepare_daily_reminders(create_tasks=not args.no_create_tasks)
    if args.command == "send-prepared-subscribe":
        return send_prepared_subscribe(args.slot)
    if args.command == "prepare-winning-today":
        return prepare_winning_today(create_tasks=not args.no_create_tasks)
    if args.command == "send-prepared-winning":
        return send_prepared_winning(args.slot)
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
    if args.command == "check-listing-limit-up":
        return check_listing_limit_up(args.query)
    if args.command == "setup-schedule":
        return setup_schedule(
            apply=args.yes,
            replace=args.replace,
            daily_time=args.daily_time,
            tracking_time=args.tracking_time,
            limit_up_time=args.limit_up_time,
            python_bin=args.python_bin,
        )
    if args.command == "list-reminders":
        return list_reminders()
    if args.command == "info":
        return plugin_info()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
