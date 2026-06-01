from __future__ import annotations

import runpy
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bond_calendar.py"
STATUS_PREFIXES = (
    "ALERT:",
    "SCHEDULED:",
    "TRACKING:",
    "NO_ALERT:",
    "NOT_FOUND:",
    "MULTIPLE_MATCHES:",
    "CANCELED:",
    "EXPIRED:",
    "ERROR:",
    "INFO:",
)


def load_script() -> dict:
    for name in list(sys.modules):
        if name == "bond_calendar_lib" or name.startswith("bond_calendar_lib."):
            sys.modules.pop(name)
    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")
        requests.RequestException = Exception
        sys.modules["requests"] = requests
    return runpy.run_path(str(SCRIPT_PATH), run_name="bond_calendar_test")


class BondCalendarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ns = load_script()
        self.base = date(2026, 5, 31)

    def assert_status_prefix(self, text: str, expected: str | None = None) -> None:
        first_line = text.strip().splitlines()[0]
        if expected is not None:
            self.assertTrue(first_line.startswith(f"{expected}:"))
        self.assertTrue(first_line.startswith(STATUS_PREFIXES), first_line)

    def test_parse_single_date_aliases(self) -> None:
        parse = self.ns["parse_single_date"]
        self.assertEqual(parse("今天", self.base), date(2026, 5, 31))
        self.assertEqual(parse("昨天", self.base), date(2026, 5, 30))
        self.assertEqual(parse("3月4号", self.base), date(2026, 3, 4))
        self.assertEqual(parse("2026-03-04", self.base), date(2026, 3, 4))

    def test_parse_date_range_expression(self) -> None:
        parse = self.ns["parse_date_range_expression"]
        self.assertEqual(parse("3月5号-3月10号", self.base), (date(2026, 3, 5), date(2026, 3, 10)))
        self.assertEqual(parse("3月5号到3月10号", self.base), (date(2026, 3, 5), date(2026, 3, 10)))
        self.assertEqual(parse("今天后一个星期内", self.base), (date(2026, 5, 31), date(2026, 6, 6)))
        self.assertEqual(parse("今天开始5天内", self.base), (date(2026, 5, 31), date(2026, 6, 4)))
        self.assertEqual(parse("12月30号-1月3号", self.base), (date(2026, 12, 30), date(2027, 1, 3)))

    def test_matches_query_supports_name_and_codes(self) -> None:
        matches_query = self.ns["matches_query"]
        event = {
            "name": "阳谷转债",
            "title": "【申购日】阳谷转债",
            "description": "转债代码：123270 申购代码：370881 配售代码：380881",
            "url": "https://example.com/",
            "bond_code": "123270",
            "subscribe_code": "370881",
            "allotment_code": "380881",
            "all_codes": ["123270", "370881", "380881"],
        }
        self.assertTrue(matches_query(event, "阳谷转债"))
        self.assertTrue(matches_query(event, "123270"))
        self.assertTrue(matches_query(event, "370881"))
        self.assertTrue(matches_query(event, "380881"))
        self.assertFalse(matches_query(event, "不存在转债"))

    def test_find_subscribe_events_uses_closed_range_and_query(self) -> None:
        events = [
            {"keyword": "申购日", "date": "2026-03-05", "name": "A转债", "bond_code": "111111", "subscribe_code": "", "allotment_code": "", "all_codes": ["111111"], "title": "", "description": "", "url": ""},
            {"keyword": "申购日", "date": "2026-03-10", "name": "B转债", "bond_code": "222222", "subscribe_code": "", "allotment_code": "", "all_codes": ["222222"], "title": "", "description": "", "url": ""},
            {"keyword": "上市日", "date": "2026-03-06", "name": "C转债", "bond_code": "333333", "subscribe_code": "", "allotment_code": "", "all_codes": ["333333"], "title": "", "description": "", "url": ""},
        ]
        find_subscribe_events = self.ns["find_subscribe_events"]
        find_subscribe_events.__globals__["load_events"] = lambda: events
        result = find_subscribe_events(date(2026, 3, 5), date(2026, 3, 10))
        self.assertEqual([event["name"] for event in result], ["A转债", "B转债"])

        result = find_subscribe_events(date(2026, 3, 5), date(2026, 3, 10), "222222")
        self.assertEqual([event["name"] for event in result], ["B转债"])

        result = find_subscribe_events(None, None, "111111")
        self.assertEqual([event["name"] for event in result], ["A转债"])

    def test_python_calendar_adapter_loads_and_normalizes_events(self) -> None:
        load_calendar_adapter = self.ns["load_calendar_adapter"]
        load_calendar_adapter.__globals__["load_config"] = lambda: {
            "calendar_strategy": {
                "type": "python",
                "adapter": "tests.custom_adapters:CalendarAdapter",
            }
        }
        adapter = load_calendar_adapter()
        events = [
            event for raw in adapter.load_events()
            if (event := self.ns["normalize_bond_event"](raw))
        ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["keyword"], "申购日")
        self.assertEqual(events[0]["bond_code"], "111111")
        self.assertEqual(events[0]["source"], "custom-calendar")

    def test_normalize_bond_event_rejects_missing_required_fields(self) -> None:
        normalize = self.ns["normalize_bond_event"]
        self.assertIsNone(normalize({"event_type": "subscribe", "date": "2026-03-05", "bond_name": "缺代码"}))
        event = normalize({
            "event_type": "listing",
            "date": "2026-03-06",
            "bond_code": "123270",
            "bond_name": "阳谷转债",
        })
        self.assertEqual(event["keyword"], "上市日")

    def test_normalize_eastmoney_row_creates_standard_events(self) -> None:
        normalize = self.ns["normalize_eastmoney_row"]
        events = normalize({
            "SECURITY_CODE": "123270",
            "SECURITY_NAME_ABBR": "盛德转债",
            "CORRECODE": "370881",
            "CORRECODEO": "380881",
            "CONVERT_STOCK_CODE": "300881",
            "PUBLIC_START_DATE": "2026-06-01 00:00:00",
            "BOND_START_DATE": "2026-06-03 00:00:00",
            "LISTING_DATE": "2026-06-20 00:00:00",
            "SECURITY_START_DATE": "2026-05-29 00:00:00",
        })

        self.assertEqual([event["keyword"] for event in events], ["申购日", "中签结果公布日", "上市日"])
        self.assertEqual([event["event_type"] for event in events], ["subscribe", "winning", "listing"])
        self.assertEqual(events[0]["date"], "2026-06-01")
        self.assertEqual(events[1]["date"], "2026-06-03")
        self.assertEqual(events[2]["date"], "2026-06-20")
        self.assertEqual(events[0]["bond_code"], "123270")
        self.assertEqual(events[0]["subscribe_code"], "370881")
        self.assertEqual(events[0]["allotment_code"], "380881")
        self.assertEqual(events[0]["winning_date"], "2026-06-03")
        self.assertIn("中签号发布日:2026-06-03", events[0]["description"])
        self.assertEqual(events[0]["source"], "eastmoney")

    def test_merge_events_keeps_eastmoney_when_sources_conflict(self) -> None:
        merge_events = self.ns["merge_events"]
        primary = [{
            "keyword": "上市日",
            "date": "2026-06-20",
            "name": "盛德转债",
            "bond_code": "123270",
            "title": "【上市日】盛德转债",
        }]
        fallback = [{
            "keyword": "上市日",
            "date": "2026-06-21",
            "name": "盛德转债",
            "bond_code": "123270",
            "title": "【上市日】盛德转债",
        }]

        with redirect_stderr(StringIO()) as error:
            merged = merge_events(primary, fallback)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["date"], "2026-06-20")
        self.assertIn("日期不一致", error.getvalue())

    def test_format_subscribe_omits_missing_code_and_url(self) -> None:
        format_message = self.ns["format_subscribe_query_message"]
        events = [
            {
                "date": "2026-03-05",
                "name": "示例转债",
                "bond_code": "",
                "subscribe_code": "",
                "allotment_code": "",
                "url": "",
            }
        ]
        message = format_message(events, date(2026, 3, 5), date(2026, 3, 5))
        self.assert_status_prefix(message, "ALERT")
        self.assertIn("事项：", message)
        self.assertIn("- 示例转债", message)
        self.assertNotIn("转债代码：", message)
        self.assertNotIn("详情：", message)

    def test_subscribe_reminder_schedule_use_config_or_defaults(self) -> None:
        load_schedule = self.ns["load_subscribe_reminder_schedule"]
        load_times = self.ns["load_subscribe_reminder_times"]
        with redirect_stderr(StringIO()):
            load_schedule.__globals__["load_config"] = lambda: {}
            self.assertEqual(
                load_schedule(),
                [
                    {"time": "10:00", "label": "10:00 申购提醒", "tag": "1000_0"},
                    {"time": "12:30", "label": "12:30 申购提醒", "tag": "1230_1"},
                ],
            )
            self.assertEqual(load_times(), ("10:00", "12:30"))

            load_schedule.__globals__["load_config"] = lambda: {
                "subscribe_reminder_schedule": [
                    {"time": "09:30", "label": "上午提醒"},
                    {"time": "13:00", "label": "下午提醒"},
                    {"time": "09:30", "label": "重复提醒"},
                    {"time": "bad", "label": "错误时间"},
                    {"label": "缺少时间"},
                ]
            }
            self.assertEqual(
                load_schedule(),
                [
                    {"time": "09:30", "label": "上午提醒", "tag": "0930_0"},
                    {"time": "13:00", "label": "下午提醒", "tag": "1300_1"},
                ],
            )
            self.assertEqual(load_times(), ("09:30", "13:00"))

            load_schedule.__globals__["load_config"] = lambda: {
                "subscribe_reminder_times": ["08:45", "13:00", "08:45", "bad"]
            }
            self.assertEqual(
                load_schedule(),
                [
                    {"time": "08:45", "label": "08:45 申购提醒", "tag": "0845_0"},
                    {"time": "13:00", "label": "13:00 申购提醒", "tag": "1300_1"},
                ],
            )
            self.assertEqual(load_times(), ("08:45", "13:00"))

    def test_prepare_subscribe_today_uses_stable_task_ids(self) -> None:
        prepare = self.ns["prepare_subscribe_today"]
        created: list[tuple[str, str]] = []
        event = {
            "keyword": "申购日",
            "date": "2026-03-05",
            "name": "A转债",
            "bond_code": "111111",
            "subscribe_code": "",
            "allotment_code": "",
            "all_codes": ["111111"],
            "title": "",
            "description": "",
            "url": "",
        }

        prepare.__globals__["load_events"] = lambda: [event]
        prepare.__globals__["today_local"] = lambda: date(2026, 3, 5)
        prepare.__globals__["now_local"] = lambda: self.ns["datetime"](2026, 3, 5, 7, 0, tzinfo=self.ns["TIMEZONE"])
        prepare.__globals__["write_json"] = lambda path, data: None
        prepare.__globals__["load_subscribe_reminder_schedule"] = lambda: [
            {"time": "09:30", "label": "上午申购提醒", "tag": "0930_0"},
            {"time": "13:00", "label": "下午申购提醒", "tag": "1300_1"},
        ]
        prepare.__globals__["upsert_once_message_task"] = (
            lambda task_id, name, run_at, content: created.append((task_id, run_at.strftime("%H:%M"))) or True
        )

        with redirect_stdout(StringIO()):
            self.assertEqual(prepare(create_tasks=True), 0)
        self.assertEqual(
            created,
            [
                ("bond-subscribe-20260305-0930", "09:30"),
                ("bond-subscribe-20260305-1300", "13:00"),
            ],
        )

    def test_prepare_winning_today_creates_reminders(self) -> None:
        prepare = self.ns["prepare_winning_today"]
        created: list[tuple[str, str, str]] = []
        event = {
            "keyword": "中签结果公布日",
            "date": "2026-03-05",
            "name": "A转债",
            "bond_code": "111111",
            "subscribe_code": "371111",
            "allotment_code": "",
            "all_codes": ["111111", "371111"],
            "title": "【中签结果公布日】A转债",
            "description": "",
            "url": "",
        }

        prepare.__globals__["load_events"] = lambda: [event]
        prepare.__globals__["today_local"] = lambda: date(2026, 3, 5)
        prepare.__globals__["now_local"] = lambda: self.ns["datetime"](2026, 3, 5, 7, 0, tzinfo=self.ns["TIMEZONE"])
        prepare.__globals__["write_json"] = lambda path, data: None
        prepare.__globals__["load_winning_reminder_schedule"] = lambda: [
            {"time": "10:30", "label": "上午中签结果公布提醒", "tag": "1030_0"},
            {"time": "13:00", "label": "下午中签结果公布提醒", "tag": "1300_1"},
        ]
        prepare.__globals__["upsert_once_message_task"] = (
            lambda task_id, name, run_at, content:
            created.append((task_id, run_at.strftime("%H:%M"), content)) or True
        )

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(prepare(create_tasks=True), 0)

        self.assert_status_prefix(output.getvalue(), "ALERT")
        self.assertEqual(
            [(task_id, run_at) for task_id, run_at, _content in created],
            [
                ("bond-winning-20260305-1030", "10:30"),
                ("bond-winning-20260305-1300", "13:00"),
            ],
        )
        self.assertIn("中签结果公布日期：2026-03-05", created[0][2])

    def test_send_prepared_winning_reports_cached_events(self) -> None:
        send = self.ns["send_prepared_winning"]
        send.__globals__["today_local"] = lambda: date(2026, 3, 5)
        send.__globals__["read_json"] = lambda path, default: {
            "date": "2026-03-05",
            "status": "ok",
            "events": [
                {
                    "date": "2026-03-05",
                    "name": "A转债",
                    "bond_code": "111111",
                    "subscribe_code": "371111",
                    "allotment_code": "",
                    "url": "",
                }
            ],
        }

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(send("10:30"), 0)

        text = output.getvalue()
        self.assert_status_prefix(text, "ALERT")
        self.assertIn("今日可转债中签结果公布提醒（10:30）", text)
        self.assertIn("中签结果公布日期：2026-03-05", text)

    def test_prepare_daily_reminders_loads_once_and_creates_both_event_tasks(self) -> None:
        prepare = self.ns["prepare_daily_reminders"]
        load_calls = 0
        created: list[tuple[str, str]] = []
        events = [
            {
                "keyword": "申购日",
                "date": "2026-03-05",
                "name": "申购转债",
                "bond_code": "111111",
                "subscribe_code": "",
                "allotment_code": "",
                "all_codes": ["111111"],
                "title": "【申购日】申购转债",
                "description": "",
                "url": "",
            },
            {
                "keyword": "中签结果公布日",
                "date": "2026-03-05",
                "name": "中签转债",
                "bond_code": "222222",
                "subscribe_code": "",
                "allotment_code": "",
                "all_codes": ["222222"],
                "title": "【中签结果公布日】中签转债",
                "description": "",
                "url": "",
            },
        ]

        def fake_load_events():
            nonlocal load_calls
            load_calls += 1
            return events

        prepare.__globals__["load_events"] = fake_load_events
        prepare.__globals__["today_local"] = lambda: date(2026, 3, 5)
        prepare.__globals__["now_local"] = lambda: self.ns["datetime"](2026, 3, 5, 7, 0, tzinfo=self.ns["TIMEZONE"])
        prepare.__globals__["write_json"] = lambda path, data: None
        prepare.__globals__["load_subscribe_reminder_schedule"] = lambda: [
            {"time": "10:00", "label": "10:00 申购提醒", "tag": "1000_0"},
        ]
        prepare.__globals__["load_winning_reminder_schedule"] = lambda: [
            {"time": "10:30", "label": "10:30 中签结果公布提醒", "tag": "1030_0"},
        ]
        prepare.__globals__["upsert_once_message_task"] = (
            lambda task_id, name, run_at, content: created.append((task_id, run_at.strftime("%H:%M"))) or True
        )

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(prepare(create_tasks=True), 0)

        self.assertEqual(load_calls, 1)
        self.assertEqual(
            created,
            [
                ("bond-subscribe-20260305-1000", "10:00"),
                ("bond-winning-20260305-1030", "10:30"),
            ],
        )
        text = output.getvalue()
        self.assert_status_prefix(text, "ALERT")
        self.assertIn("申购日期：2026-03-05", text)
        self.assertIn("中签结果公布日期：2026-03-05", text)

    def test_find_subscribe_query_only_uses_visible_source_range(self) -> None:
        find_subscribe = self.ns["find_subscribe"]
        captured_args: list[tuple[date | None, date | None, str | None]] = []
        event = {
            "keyword": "申购日",
            "date": "2026-03-05",
            "name": "A转债",
            "bond_code": "111111",
            "subscribe_code": "",
            "allotment_code": "",
            "all_codes": ["111111"],
            "title": "",
            "description": "",
            "url": "",
        }

        def fake_find_subscribe_events(start: date | None, end: date | None, query: str | None):
            captured_args.append((start, end, query))
            return [event]

        find_subscribe.__globals__["find_subscribe_events"] = fake_find_subscribe_events
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(find_subscribe(None, None, None, None, "111111"), 0)

        self.assertEqual(captured_args, [(None, None, "111111")])
        text = output.getvalue()
        self.assert_status_prefix(text, "ALERT")
        self.assertIn("事项：", text)
        self.assertIn("可转债申购查询结果（111111）", text)

    def test_send_prepared_subscribe_reports_refresh_failure(self) -> None:
        send_prepared = self.ns["send_prepared_subscribe"]
        send_prepared.__globals__["today_local"] = lambda: date(2026, 3, 5)
        send_prepared.__globals__["read_json"] = lambda path, default: {}
        send_prepared.__globals__["prepare_subscribe_today"] = lambda create_tasks=False: 1

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(send_prepared("10:00"), 1)

        self.assert_status_prefix(output.getvalue(), "ERROR")

    def test_find_listing_formats_multiple_matches_and_not_found(self) -> None:
        find_listing = self.ns["find_listing"]
        find_listing.__globals__["find_listing_events"] = lambda query: []
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(find_listing("不存在"), 0)
        not_found_text = output.getvalue()
        self.assert_status_prefix(not_found_text, "NOT_FOUND")
        self.assertIn("建议：", not_found_text)

        find_listing.__globals__["find_listing_events"] = lambda query: [
            {"date": "2026-03-06", "name": "A转债", "bond_code": "111111", "url": ""},
            {"date": "2026-03-07", "name": "B转债", "bond_code": "222222", "url": ""},
        ]
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(find_listing("转债"), 0)
        multiple_text = output.getvalue()
        self.assert_status_prefix(multiple_text, "MULTIPLE_MATCHES")
        self.assertIn("候选：", multiple_text)
        self.assertIn("建议：", multiple_text)

    def test_upsert_once_message_task_skips_past_time(self) -> None:
        upsert = self.ns["upsert_once_message_task"]
        upsert.__globals__["now_local"] = lambda: self.ns["datetime"](2026, 3, 5, 10, 0, tzinfo=self.ns["TIMEZONE"])

        run_at = self.ns["datetime"](2026, 3, 5, 9, 59, tzinfo=self.ns["TIMEZONE"])
        self.assertFalse(upsert("task-id", "测试提醒", run_at, "content"))

    def test_listing_reminder_schedule_uses_config_or_defaults(self) -> None:
        load_schedule = self.ns["load_listing_reminder_schedule"]
        with redirect_stderr(StringIO()):
            load_schedule.__globals__["load_config"] = lambda: {}
            default_schedule = load_schedule()
            self.assertEqual([item["time"] for item in default_schedule], ["12:00", "09:25", "13:30"])

            load_schedule.__globals__["load_config"] = lambda: {
                "listing_reminder_schedule": [
                    {"days_offset": -2, "time": "09:00", "label": "提前两天"},
                    {"days_offset": 0, "time": "bad", "label": "bad"},
                ]
            }
            custom_schedule = load_schedule()
            self.assertEqual(len(custom_schedule), 1)
            self.assertEqual(custom_schedule[0]["days_offset"], -2)
            self.assertEqual(custom_schedule[0]["label"], "提前两天")

    def test_winning_and_limit_up_configs_use_defaults(self) -> None:
        load_winning = self.ns["load_winning_reminder_schedule"]
        load_limit_up = self.ns["load_listing_limit_up_reminder_config"]
        with redirect_stderr(StringIO()):
            load_winning.__globals__["load_config"] = lambda: {}
            self.assertEqual(
                load_winning(),
                [
                    {"time": "10:30", "label": "10:30 中签结果公布提醒", "tag": "1030_0"},
                    {"time": "13:00", "label": "13:00 中签结果公布提醒", "tag": "1300_1"},
                ],
            )

            load_limit_up.__globals__["load_config"] = lambda: {}
            limit_up = load_limit_up()
            self.assertTrue(limit_up["enabled"])
            self.assertEqual(limit_up["check_time"], "14:50")
            self.assertEqual(limit_up["reminder_time"], "14:55")
            self.assertEqual(limit_up["threshold_percent"], 30)

    def test_python_quote_adapter_loads_and_normalizes_quote(self) -> None:
        fetch_quote = self.ns["fetch_bond_quote"]
        fetch_quote.__globals__["load_config"] = lambda: {
            "quote_strategy": {
                "type": "python",
                "adapter": "tests.custom_adapters:QuoteAdapter",
            }
        }

        quote = fetch_quote("123267")

        self.assertEqual(quote["bond_code"], "123267")
        self.assertEqual(quote["change_percent"], 30.0)
        self.assertEqual(quote["source"], "custom-quote")

    def test_bond_quote_requires_change_percent(self) -> None:
        normalize = self.ns["normalize_standard_quote"]
        self.assertIsNone(normalize({"bond_code": "123267", "last_price": 120.0}))

    def test_schedule_listing_tasks_skips_past_and_creates_future(self) -> None:
        schedule = self.ns["schedule_listing_tasks"]
        event = {
            "date": "2026-03-06",
            "name": "阳谷转债",
            "bond_code": "123270",
            "subscribe_code": "",
            "allotment_code": "",
            "url": "",
        }
        created: list[tuple[str, str]] = []
        schedule.__globals__["now_local"] = lambda: self.ns["datetime"](2026, 3, 6, 9, 0, tzinfo=self.ns["TIMEZONE"])
        schedule.__globals__["load_listing_reminder_schedule"] = lambda: [
            {"days_offset": 0, "time": "08:30", "label": "上午", "tag": "morning"},
            {"days_offset": 0, "time": "13:00", "label": "下午", "tag": "afternoon"},
        ]
        schedule.__globals__["upsert_once_message_task"] = (
            lambda task_id, name, run_at, content: created.append((task_id, run_at.strftime("%H:%M"))) or True
        )

        result = schedule(event)
        self.assertEqual(result["task_ids"], ["bond-listing-123270-20260306-afternoon"])
        self.assertEqual(len(result["skipped_reminders"]), 1)
        self.assertEqual(created, [("bond-listing-123270-20260306-afternoon", "13:00")])

    def test_schedule_listing_task_failure_stays_pending_not_expired(self) -> None:
        track = self.ns["track_listing"]
        event = {
            "keyword": "上市日",
            "date": "2026-03-06",
            "name": "阳谷转债",
            "bond_code": "123270",
            "subscribe_code": "370881",
            "allotment_code": "380881",
            "all_codes": ["123270", "370881", "380881"],
            "title": "【上市日】阳谷转债",
            "description": "",
            "url": "",
        }
        saved: dict = {}
        track.__globals__["find_listing_events"] = lambda query: [event]
        track.__globals__["load_watchlist"] = lambda: {"version": 1, "items": {}}
        track.__globals__["save_watchlist"] = lambda data: saved.update(data)
        track.__globals__["now_local"] = lambda: self.ns["datetime"](2026, 3, 5, 8, 0, tzinfo=self.ns["TIMEZONE"])
        track.__globals__["load_listing_reminder_schedule"] = lambda: [
            {"days_offset": 0, "time": "13:00", "label": "下午", "tag": "afternoon"},
        ]
        track.__globals__["upsert_once_message_task"] = lambda task_id, name, run_at, content: False

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(track("370881"), 0)

        item = saved["items"]["123270"]
        self.assertEqual(item["status"], "pending")
        self.assertIn("last_error", item)
        self.assertEqual(item["failed_reminders"][0]["reason"], "create_failed")
        text = output.getvalue()
        self.assert_status_prefix(text, "TRACKING")
        self.assertIn("事项：", text)
        self.assertIn("建议：", text)

    def test_canonical_watch_key_prefers_bond_code(self) -> None:
        canonical_key = self.ns["canonical_watch_key"]
        self.assertEqual(canonical_key({"bond_code": "123270", "name": "阳谷转债"}, "370881"), "123270")
        self.assertEqual(canonical_key({"bond_code": "", "name": "阳谷转债"}, "370881"), "阳谷转债")

    def test_track_listing_writes_canonical_scheduled_item(self) -> None:
        track = self.ns["track_listing"]
        event = {
            "keyword": "上市日",
            "date": "2026-03-06",
            "name": "阳谷转债",
            "bond_code": "123270",
            "subscribe_code": "370881",
            "allotment_code": "380881",
            "all_codes": ["123270", "370881", "380881"],
            "title": "【上市日】阳谷转债",
            "description": "",
            "url": "",
        }
        saved: dict = {}
        track.__globals__["find_listing_events"] = lambda query: [event]
        track.__globals__["load_watchlist"] = lambda: {"version": 1, "items": {}}
        track.__globals__["save_watchlist"] = lambda data: saved.update(data)
        track.__globals__["schedule_listing_tasks"] = lambda event: {
            "task_ids": ["bond-listing-123270-20260306-listing_0830"],
            "skipped_reminders": [],
        }

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(track("370881"), 0)

        self.assertIn("123270", saved["items"])
        self.assertEqual(saved["items"]["123270"]["status"], "scheduled")
        self.assertIn("370881", saved["items"]["123270"]["aliases"])
        text = output.getvalue()
        self.assert_status_prefix(text, "SCHEDULED")
        self.assertIn("事项：", text)
        self.assertIn("任务：", text)

    def test_check_tracked_listings_expires_old_pending(self) -> None:
        check = self.ns["check_tracked_listings"]
        old_created = (self.ns["datetime"](2026, 3, 1, 8, 0, tzinfo=self.ns["TIMEZONE"]) - timedelta(days=181)).isoformat()
        data = {
            "version": 1,
            "items": {
                "123270": {
                    "query": "123270",
                    "status": "pending",
                    "created_at": old_created,
                }
            },
        }
        saved: dict = {}
        check.__globals__["now_local"] = lambda: self.ns["datetime"](2026, 3, 1, 8, 0, tzinfo=self.ns["TIMEZONE"])
        check.__globals__["load_watchlist"] = lambda: data
        check.__globals__["load_listing_tracking_max_days"] = lambda: 180
        check.__globals__["save_watchlist"] = lambda value: saved.update(value)
        check.__globals__["find_listing_events"] = lambda query: self.fail("expired item should not query data source")

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(check(), 0)

        self.assert_status_prefix(output.getvalue(), "NO_ALERT")
        self.assertEqual(saved["items"]["123270"]["status"], "expired")

    def test_check_listing_limit_up_creates_reminder_when_threshold_hit(self) -> None:
        check = self.ns["check_listing_limit_up"]
        now = self.ns["datetime"](2026, 3, 6, 14, 50, tzinfo=self.ns["TIMEZONE"])
        created: list[tuple[str, str, str]] = []
        check.__globals__["now_local"] = lambda: now
        check.__globals__["today_local"] = lambda: date(2026, 3, 6)
        check.__globals__["load_listing_limit_up_reminder_config"] = lambda: {
            "enabled": True,
            "check_time": "14:50",
            "reminder_time": "14:55",
            "threshold_percent": 30,
            "label": "上市当天 30% 涨停 14:55 提醒",
        }
        check.__globals__["load_watchlist"] = lambda: {
            "version": 1,
            "items": {
                "123270": {
                    "query": "123270",
                    "status": "scheduled",
                    "event": {
                        "date": "2026-03-06",
                        "name": "阳谷转债",
                        "bond_code": "123270",
                    },
                }
            },
        }
        check.__globals__["fetch_bond_quote"] = lambda code: {
            "bond_code": code,
            "name": "阳谷转债",
            "last_price": 130.0,
            "prev_close": 100.0,
            "change": 30.0,
            "change_percent": 30.0,
            "quote_time": "2026-03-06T14:50:00",
        }
        check.__globals__["upsert_once_message_task"] = (
            lambda task_id, name, run_at, content:
            created.append((task_id, run_at.strftime("%H:%M"), content)) or True
        )

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(check(), 0)

        self.assert_status_prefix(output.getvalue(), "SCHEDULED")
        self.assertEqual(created[0][0], "bond-listing-limit-up-123270-20260306-1455")
        self.assertEqual(created[0][1], "14:55")
        self.assertIn("涨跌幅：30.0%", created[0][2])

    def test_cancel_listing_disables_task_and_marks_canceled(self) -> None:
        cancel = self.ns["cancel_listing"]
        data = {
            "version": 1,
            "items": {
                "123270": {
                    "query": "370881",
                    "status": "scheduled",
                    "task_ids": ["task-a"],
                    "event": {
                        "name": "阳谷转债",
                        "title": "【上市日】阳谷转债",
                        "description": "",
                        "url": "",
                        "bond_code": "123270",
                        "subscribe_code": "370881",
                        "allotment_code": "380881",
                        "all_codes": ["123270", "370881", "380881"],
                    },
                }
            },
        }
        disabled: list[str] = []
        saved: dict = {}
        cancel.__globals__["load_watchlist"] = lambda: data
        cancel.__globals__["disable_task_ids"] = lambda task_ids: disabled.extend(task_ids) or len(task_ids)
        cancel.__globals__["save_watchlist"] = lambda value: saved.update(value)

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(cancel("123270"), 0)

        text = output.getvalue()
        self.assert_status_prefix(text, "CANCELED")
        self.assertIn("任务：", text)
        self.assertEqual(disabled, ["task-a"])
        self.assertEqual(saved["items"]["123270"]["status"], "canceled")

    def test_list_reminders_shows_only_current_effective_items(self) -> None:
        list_reminders = self.ns["list_reminders"]
        now = self.ns["datetime"](2026, 3, 5, 8, 0, tzinfo=self.ns["TIMEZONE"])
        future = "2026-03-05T10:00:00"
        past = "2026-03-05T07:00:00"
        list_reminders.__globals__["now_local"] = lambda: now
        sys.modules["bond_calendar_lib.scheduler"].now_local = lambda: now
        list_reminders.__globals__["load_tasks"] = lambda: {
            "version": 1,
                "tasks": {
                    "bond-subscribe-20260305-1000": {"enabled": True, "name": "申购", "next_run_at": future},
                    "bond-winning-20260305-1030": {"enabled": True, "name": "中签结果公布", "next_run_at": future},
                    "bond-listing-123270-20260306-a": {"enabled": True, "name": "上市", "next_run_at": future},
                "bond-listing-old": {"enabled": True, "name": "旧上市", "next_run_at": past},
                "bond-subscribe-disabled": {"enabled": False, "name": "禁用", "next_run_at": future},
            },
        }
        list_reminders.__globals__["load_watchlist"] = lambda: {
            "version": 1,
            "items": {
                "123270": {"query": "123270", "status": "pending", "created_at": "2026-03-05T07:30:00+08:00"},
                "111111": {"query": "111111", "status": "expired"},
            },
        }

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(list_reminders(), 0)

        text = output.getvalue()
        self.assert_status_prefix(text, "ALERT")
        self.assertIn("申购提醒：", text)
        self.assertIn("中签结果公布提醒：", text)
        self.assertIn("上市提醒：", text)
        self.assertIn("中签结果公布", text)
        self.assertIn("待追踪上市：", text)
        self.assertIn("配置摘要：", text)
        self.assertIn("状态计数：", text)
        self.assertIn("123270", text)
        self.assertNotIn("旧上市", text)
        self.assertNotIn("禁用", text)
        self.assertNotIn("111111", text)

    def test_plugin_info_shows_pending_dashboard_and_hides_sensitive_target(self) -> None:
        info = self.ns["plugin_info"]
        now = self.ns["datetime"](2026, 3, 5, 8, 0, tzinfo=self.ns["TIMEZONE"])
        future = "2026-03-05T10:00:00"
        past = "2026-03-05T07:00:00"
        info.__globals__["now_local"] = lambda: now
        info.__globals__["load_config"] = lambda: {
            "calendar_strategy": {
                "type": "python",
                "adapter": "tests.custom_adapters:CalendarAdapter",
            },
            "receiver": "wxid_sensitive",
            "notify_session_id": "session_sensitive",
            "subscribe_reminder_schedule": [{"time": "09:30", "label": "上午提醒"}],
            "listing_tracking_max_days": 90,
        }
        sys.modules["bond_calendar_lib.scheduler"].now_local = lambda: now
        sys.modules["bond_calendar_lib.scheduler"].load_config = info.__globals__["load_config"]
        info.__globals__["load_subscribe_reminder_schedule"] = lambda: [
            {"time": "09:30", "label": "上午提醒", "tag": "0930_0"}
        ]
        info.__globals__["load_listing_tracking_max_days"] = lambda: 90
        info.__globals__["load_listing_reminder_schedule"] = lambda: [
            {"days_offset": 0, "time": "09:00", "label": "开盘前", "tag": "open"}
        ]
        info.__globals__["load_tasks"] = lambda: {
            "version": 1,
                "tasks": {
                    "bond-subscribe-20260305-1000": {
                    "enabled": True,
                    "name": "申购提醒",
                    "next_run_at": future,
                    "action": {
                        "receiver": "wxid_sensitive",
                        "notify_session_id": "session_sensitive",
                        "receiver_name": "微信用户",
                        "channel_type": "weixin",
                        "is_group": False,
                    },
                    },
                    "bond-winning-20260305-1030": {
                        "enabled": True,
                        "name": "中签结果公布提醒",
                        "next_run_at": future,
                        "action": {
                            "receiver": "wxid_sensitive",
                            "receiver_name": "微信用户",
                            "channel_type": "weixin",
                            "is_group": False,
                        },
                    },
                    "bond-listing-123270-20260306-a": {
                    "enabled": True,
                    "name": "上市提醒",
                    "next_run_at": future,
                    "action": {
                        "receiver": "wxid_sensitive",
                        "receiver_name": "微信用户",
                        "channel_type": "weixin",
                        "is_group": False,
                    },
                },
                "bond-subscribe-old": {"enabled": True, "name": "旧任务", "next_run_at": past},
                "bond-listing-disabled": {"enabled": False, "name": "禁用任务", "next_run_at": future},
            },
        }
        info.__globals__["load_watchlist"] = lambda: {
            "version": 1,
            "items": {
                "a": {"query": "123270", "status": "pending", "created_at": "2026-03-05T07:00:00+08:00"},
                "b": {"query": "111111", "status": "expired"},
            },
        }
        info.__globals__["read_json"] = lambda path, default: {}
        info.__globals__["read_crontab_lines"] = lambda: ["0 7 * * * python bond_calendar.py prepare-subscribe-today"]

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(info(), 0)

        text = output.getvalue()
        self.assert_status_prefix(text, "INFO")
        self.assertIn("INFO: bond-calendar-reminder-skill 待执行任务", text)
        self.assertIn("详情：", text)
        self.assertIn("申购提醒：", text)
        self.assertIn("中签结果公布提醒：", text)
        self.assertIn("上市提醒：", text)
        self.assertIn("任务：", text)
        self.assertIn("待追踪上市：", text)
        self.assertIn("配置摘要：", text)
        self.assertIn("状态计数：", text)
        self.assertIn("scheduler 待执行申购提醒", text)
        self.assertIn("scheduler 待执行中签结果公布提醒", text)
        self.assertIn("scheduler 待执行上市提醒", text)
        self.assertIn("申购提醒", text)
        self.assertIn("中签结果公布提醒", text)
        self.assertIn("上市提醒", text)
        self.assertIn("python bond_calendar.py prepare-subscribe-today", text)
        self.assertIn("123270", text)
        self.assertIn("提醒目标：使用兼容配置", text)
        self.assertNotIn("旧任务", text)
        self.assertNotIn("禁用任务", text)
        self.assertNotIn("111111", text)
        self.assertNotIn("wxid_sensitive", text)
        self.assertNotIn("session_sensitive", text)
        self.assertNotIn("Authorization", text)

    def test_resolve_notify_target_supports_legacy_config_and_auto_weixin(self) -> None:
        resolve = self.ns["resolve_notify_target"]
        resolve.__globals__["load_config"] = lambda: {
            "receiver": "legacy_receiver",
            "receiver_name": "旧配置",
            "is_group": True,
            "channel_type": "weixin",
            "notify_session_id": "legacy_session",
        }
        target = resolve()
        self.assertEqual(target["receiver"], "legacy_receiver")
        self.assertEqual(target["notify_session_id"], "legacy_session")
        self.assertEqual(target["_source"], "legacy_config")

        resolve.__globals__["load_config"] = lambda: {}
        resolve.__globals__["read_json"] = lambda path, default: {
            "context_tokens": {"wxid_b": "token-b", "wxid_a": "token-a"}
        }
        with redirect_stderr(StringIO()) as error:
            target = resolve()
        self.assertEqual(target["receiver"], "wxid_a")
        self.assertEqual(target["channel_type"], "weixin")
        self.assertEqual(target["_source"], "auto_weixin")
        self.assertIn("multiple weixin context tokens", error.getvalue())

        resolve.__globals__["read_json"] = lambda path, default: {}
        self.assertIsNone(resolve())

    def test_read_crontab_lines_filters_comments(self) -> None:
        read_crontab_lines = self.ns["read_crontab_lines"]
        read_crontab_lines.__globals__["subprocess"].run = lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0,
            stdout=(
                "# 0 7 * * * python bond_calendar.py prepare-subscribe-today\n"
                "\n"
                "0 7 * * * python bond_calendar.py prepare-subscribe-today\n"
                "0 8 * * * python other.py\n"
            ),
        )

        self.assertEqual(
            read_crontab_lines(),
            ["0 7 * * * python bond_calendar.py prepare-subscribe-today"],
        )

    def test_install_cron_jobs_skips_existing_commands(self) -> None:
        install = self.ns["install_cron_jobs"]
        calls: list[dict] = []

        def fake_run(args, **kwargs):
            calls.append({"args": args, **kwargs})
            if args == ["crontab", "-l"]:
                return types.SimpleNamespace(
                    returncode=0,
                    stdout="0 7 * * * python /tmp/bond_calendar.py prepare-daily-reminders\n",
                )
            return types.SimpleNamespace(returncode=0, stdout="")

        install.__globals__["subprocess"].run = fake_run
        jobs = [
            {"command": "prepare-daily-reminders", "time": "07:00", "line": "0 7 * * * python /tmp/bond_calendar.py prepare-daily-reminders"},
            {"command": "check-tracked-listings", "time": "07:05", "line": "5 7 * * * python /tmp/bond_calendar.py check-tracked-listings"},
        ]

        result = install(jobs, apply=True)

        self.assertEqual(result["skipped"], [jobs[0]["line"]])
        self.assertEqual(result["installed"], [jobs[1]["line"]])
        self.assertEqual(calls[-1]["args"], ["crontab", "-"])
        self.assertIn("check-tracked-listings", calls[-1]["input"])
        self.assertEqual(calls[-1]["input"].count("prepare-daily-reminders"), 1)

    def test_build_cron_line_includes_workspace_env(self) -> None:
        build_cron_line = self.ns["build_cron_line"]
        build_cron_line.__globals__["WORKSPACE"] = Path("/tmp/cow-a")
        build_cron_line.__globals__["DATA_DIR"] = Path("/tmp/cow-a/bond_reminders")
        build_cron_line.__globals__["PROJECT_ROOT"] = Path("/tmp/cow-a/skills/bond-calendar-reminder-skill")

        line = build_cron_line(
            "prepare-daily-reminders",
            "07:00",
            "/root/CowAgent-A/.venv/bin/python",
        )

        self.assertTrue(line.startswith("00 07 * * * COW_WORKSPACE=/tmp/cow-a "))
        self.assertIn("/root/CowAgent-A/.venv/bin/python", line)
        self.assertIn("/tmp/cow-a/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py", line)
        self.assertIn(">> /tmp/cow-a/bond_reminders/bond_calendar.log", line)

    def test_setup_schedule_previews_without_writing_crontab(self) -> None:
        setup = self.ns["setup_schedule"]
        setup.__globals__["default_cron_jobs"] = lambda *args, **kwargs: [
            {"command": "prepare-daily-reminders", "time": "08:00", "line": "0 8 * * * python bond_calendar.py prepare-daily-reminders"}
        ]
        setup.__globals__["install_cron_jobs"] = lambda jobs, apply=False, replace=False: {"installed": [jobs[0]["line"]], "skipped": []}

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(setup(apply=False, daily_time="08:00"), 0)

        text = output.getvalue()
        self.assert_status_prefix(text, "INFO")
        self.assertIn("当前只是预览", text)
        self.assertIn("--daily-time", text)

    def test_setup_schedule_output_lists_final_cron_plan(self) -> None:
        setup = self.ns["setup_schedule"]
        jobs = [
            {"command": "prepare-daily-reminders", "time": "07:00", "line": "0 7 * * * python bond_calendar.py prepare-daily-reminders"},
            {"command": "check-tracked-listings", "time": "07:05", "line": "5 7 * * * python bond_calendar.py check-tracked-listings"},
            {"command": "check-listing-limit-up", "time": "14:50", "line": "50 14 * * * python bond_calendar.py check-listing-limit-up"},
        ]
        setup.__globals__["default_cron_jobs"] = lambda *args, **kwargs: jobs
        setup.__globals__["install_cron_jobs"] = lambda jobs, apply=False, replace=False: {
            "installed": [jobs[0]["line"], jobs[2]["line"]],
            "skipped": [jobs[1]["line"]],
        }

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(setup(apply=True), 0)

        text = output.getvalue()
        self.assert_status_prefix(text, "SCHEDULED")
        self.assertIn("新增 2 个，已存在 1 个，目标 3 个", text)
        self.assertIn("本次实际新增：2 个", text)
        self.assertIn("已存在并跳过：1 个", text)
        self.assertIn("本次检查目标：3 个系统 crontab 任务", text)
        self.assertIn("prepare-daily-reminders", text)
        self.assertIn("check-tracked-listings", text)
        self.assertIn("check-listing-limit-up", text)

    def test_setup_schedule_preview_does_not_claim_actual_install(self) -> None:
        setup = self.ns["setup_schedule"]
        jobs = [
            {"command": "prepare-daily-reminders", "time": "07:00", "line": "0 7 * * * python bond_calendar.py prepare-daily-reminders"},
            {"command": "check-tracked-listings", "time": "07:05", "line": "5 7 * * * python bond_calendar.py check-tracked-listings"},
            {"command": "check-listing-limit-up", "time": "14:50", "line": "50 14 * * * python bond_calendar.py check-listing-limit-up"},
        ]
        setup.__globals__["default_cron_jobs"] = lambda *args, **kwargs: jobs
        setup.__globals__["install_cron_jobs"] = lambda jobs, apply=False, replace=False: {
            "installed": jobs,
            "skipped": [],
        }

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(setup(apply=False), 0)

        text = output.getvalue()
        self.assert_status_prefix(text, "INFO")
        self.assertIn("预计新增（未写入）：3 个", text)
        self.assertNotIn("本次实际新增：3 个", text)

    def test_auto_setup_schedule_installs_missing_jobs(self) -> None:
        auto_setup = self.ns["auto_setup_schedule_if_enabled"]
        captured: dict = {}
        auto_setup.__globals__["load_config"] = lambda: {
            "auto_setup_schedule": {
                "daily_time": "08:00",
                "tracking_time": "08:05",
                "limit_up_time": "14:45",
            }
        }
        auto_setup.__globals__["default_cron_jobs"] = lambda daily, tracking, limit_up: [
            {"command": "prepare-daily-reminders", "time": daily, "line": f"{daily} prepare-daily-reminders"},
            {"command": "check-tracked-listings", "time": tracking, "line": f"{tracking} check-tracked-listings"},
            {"command": "check-listing-limit-up", "time": limit_up, "line": f"{limit_up} check-listing-limit-up"},
        ]
        auto_setup.__globals__["install_cron_jobs"] = (
            lambda jobs, apply=False, replace=False:
            captured.update({"jobs": jobs, "apply": apply, "replace": replace}) or {"installed": [jobs[0]["line"]], "skipped": []}
        )

        with redirect_stderr(StringIO()) as error:
            auto_setup()

        self.assertTrue(captured["apply"])
        self.assertFalse(captured["replace"])
        self.assertEqual([job["time"] for job in captured["jobs"]], ["08:00", "08:05", "14:45"])
        self.assertIn("已自动设置", error.getvalue())

    def test_load_config_does_not_write_auto_receiver(self) -> None:
        load_config = self.ns["load_config"]
        calls: list[dict] = []
        load_config.__globals__["read_json"] = lambda path, default: {}
        load_config.__globals__["write_json"] = lambda path, data: calls.append(data)

        self.assertEqual(load_config(), {})
        self.assertEqual(calls, [])

    def test_extract_skill_version_prefers_metadata_version(self) -> None:
        extract = self.ns["extract_skill_version"]
        text = """---
name: bond-calendar-reminder-skill
version: 9.9.9
metadata:
  author: xixilili
  version: 0.1.1
---
"""
        self.assertEqual(extract(text), "0.1.1")

    def test_compare_versions_handles_patch_numbers(self) -> None:
        compare = self.ns["compare_versions"]
        self.assertLess(compare("0.1.0", "0.1.1"), 0)
        self.assertEqual(compare("0.1.1", "0.1.1"), 0)
        self.assertGreater(compare("0.2.0", "0.1.9"), 0)

    def test_check_update_reports_available_update(self) -> None:
        check_update = self.ns["check_update"]

        class FakeResponse:
            text = "metadata:\n  version: 0.1.2\n"

            def raise_for_status(self) -> None:
                return None

        check_update.__globals__["local_skill_version"] = lambda: "0.1.1"
        check_update.__globals__["requests"].get = lambda *args, **kwargs: FakeResponse()

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(check_update("https://example.com/SKILL.md"), 0)

        text = output.getvalue()
        self.assert_status_prefix(text, "INFO")
        self.assertIn("详情：", text)
        self.assertIn("建议：", text)
        self.assertIn("当前版本：0.1.1", text)
        self.assertIn("最新版本：0.1.2", text)
        self.assertIn("建议更新", text)

    def test_daily_update_prompt_runs_once_per_day(self) -> None:
        maybe_prompt = self.ns["maybe_prompt_update_once_per_day"]

        class FakeResponse:
            text = "metadata:\n  version: 0.1.2\n"

            def raise_for_status(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmp:
            maybe_prompt.__globals__["UPDATE_CHECK_FILE"] = Path(tmp) / "update_check.json"
            maybe_prompt.__globals__["local_skill_version"] = lambda: "0.1.1"
            maybe_prompt.__globals__["requests"].get = lambda *args, **kwargs: FakeResponse()

            with redirect_stdout(StringIO()) as output:
                self.assertTrue(maybe_prompt("https://example.com/SKILL.md"))

            text = output.getvalue()
            self.assert_status_prefix(text, "INFO")
            self.assertIn("发现可转债提醒 Skill 新版本 0.1.2", text)
            self.assertIn("skip-update --version 0.1.2", text)

            with redirect_stdout(StringIO()) as second_output:
                self.assertFalse(maybe_prompt("https://example.com/SKILL.md"))
            self.assertEqual(second_output.getvalue(), "")

    def test_skip_update_version_suppresses_same_version_prompt(self) -> None:
        skip_update = self.ns["skip_update_version"]
        maybe_prompt = self.ns["maybe_prompt_update_once_per_day"]

        class FakeResponse:
            text = "metadata:\n  version: 0.1.2\n"

            def raise_for_status(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "update_check.json"
            skip_update.__globals__["UPDATE_CHECK_FILE"] = state_file
            maybe_prompt.__globals__["UPDATE_CHECK_FILE"] = state_file
            maybe_prompt.__globals__["local_skill_version"] = lambda: "0.1.1"
            maybe_prompt.__globals__["requests"].get = lambda *args, **kwargs: FakeResponse()

            with redirect_stdout(StringIO()) as skip_output:
                self.assertEqual(skip_update("0.1.2"), 0)
            self.assert_status_prefix(skip_output.getvalue(), "INFO")
            self.assertIn("已跳过版本 0.1.2", skip_output.getvalue())

            with redirect_stdout(StringIO()) as output:
                self.assertFalse(maybe_prompt("https://example.com/SKILL.md"))
            self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
