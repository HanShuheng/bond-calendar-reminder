from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Shanghai")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}
DEFAULT_EASTMONEY_API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
DEFAULT_EASTMONEY_QUOTE_API_URL = "https://push2.eastmoney.com/api/qt/stock/get"
DEFAULT_EASTMONEY_QUOTE_FIELDS = "f57,f58,f43,f60,f169,f170,f86"
DEFAULT_EASTMONEY_PARAMS = {
    "reportName": "RPT_BOND_CB_LIST",
    "columns": "ALL",
    "source": "WEB",
    "client": "WEB",
    "pageNumber": "1",
    "pageSize": "2000",
    "sortColumns": "PUBLIC_START_DATE,SECURITY_CODE",
    "sortTypes": "-1,1",
}
DEFAULT_EASTMONEY_REFERER = "https://data.eastmoney.com/xg/xg/?mkt=kzz"
DEFAULT_JISILU_CALENDAR_URL = "https://www.jisilu.cn/data/calendar/get_calendar_data/?qtype=CNV"
DEFAULT_JISILU_BASE_URL = "https://www.jisilu.cn"
DEFAULT_JISILU_DETAIL_URL_TEMPLATE = "https://www.jisilu.cn/data/convert_bond_detail/{code}"
DEFAULT_JISILU_REFERER = "https://www.jisilu.cn/data/calendar/"

WORKSPACE = Path(os.environ.get("COW_WORKSPACE", "~/cow")).expanduser()
DATA_DIR = WORKSPACE / "bond_reminders"
CONFIG_FILE = DATA_DIR / "config.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
DAILY_SUBSCRIBE_FILE = DATA_DIR / "daily_subscribe.json"
DAILY_WINNING_FILE = DATA_DIR / "daily_winning.json"
TASKS_FILE = WORKSPACE / "scheduler" / "tasks.json"
WEIXIN_CREDS_FILE = Path("~/.weixin_cow_credentials.json").expanduser()

DEFAULT_SUBSCRIBE_REMINDER_SCHEDULE = (
    {"time": "10:00", "label": "10:00 申购提醒"},
    {"time": "12:30", "label": "12:30 申购提醒"},
)
DEFAULT_WINNING_REMINDER_SCHEDULE = (
    {"time": "10:30", "label": "10:30 中签结果公布提醒"},
    {"time": "13:00", "label": "13:00 中签结果公布提醒"},
)
DEFAULT_LISTING_TRACKING_MAX_DAYS = 180
DEFAULT_LISTING_REMINDER_SCHEDULE = (
    {"days_offset": -1, "time": "12:00", "label": "上市前一天提醒"},
    {"days_offset": 0, "time": "09:25", "label": "上市当天 09:25，开盘前提醒"},
    {"days_offset": 0, "time": "13:30", "label": "上市当天 13:30"},
)
DEFAULT_LISTING_LIMIT_UP_REMINDER = {
    "enabled": True,
    "check_time": "14:50",
    "reminder_time": "14:55",
    "threshold_percent": 30,
    "label": "上市当天 30% 涨停 14:55 提醒",
}
DEFAULT_CRON_SCHEDULE = {
    "prepare-daily-reminders": "07:00",
    "check-tracked-listings": "07:05",
    "check-listing-limit-up": "14:50",
}
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
SENSITIVE_KEY_PATTERN = re.compile(r"(authorization|cookie|token|key|secret|password)", re.IGNORECASE)
BOND_TASK_PREFIXES = ("bond-subscribe-", "bond-winning-", "bond-listing-")
DEFAULT_UPDATE_CHECK_URL = (
    "https://raw.githubusercontent.com/HanShuheng/bond-calendar-reminder-skill/main/SKILL.md"
)

def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def today_local() -> date:
    return now_local().date()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
