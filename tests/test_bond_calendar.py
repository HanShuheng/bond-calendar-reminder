from __future__ import annotations

import runpy
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bond_calendar.py"


def load_script() -> dict:
    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")
        requests.RequestException = Exception
        sys.modules["requests"] = requests
    return runpy.run_path(str(SCRIPT_PATH), run_name="bond_calendar_test")


class BondCalendarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ns = load_script()
        self.base = date(2026, 5, 31)

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

    def test_detail_url_uses_configured_source(self) -> None:
        detail_url_for = self.ns["detail_url_for"]
        data_source = {
            "base_url": "https://example.com",
            "detail_url_template": "https://example.com/bonds/{code}",
        }
        self.assertEqual(
            detail_url_for("123270", "/calendar/123270", data_source),
            "https://example.com/calendar/123270",
        )
        self.assertEqual(
            detail_url_for("123270", "", data_source),
            "https://example.com/bonds/123270",
        )

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
                    {"time": "13:00", "label": "13:00 申购提醒", "tag": "1300_1"},
                ],
            )
            self.assertEqual(load_times(), ("10:00", "13:00"))

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
        self.assertIn("可转债申购查询结果（111111）", output.getvalue())

    def test_send_prepared_subscribe_reports_refresh_failure(self) -> None:
        send_prepared = self.ns["send_prepared_subscribe"]
        send_prepared.__globals__["today_local"] = lambda: date(2026, 3, 5)
        send_prepared.__globals__["read_json"] = lambda path, default: {}
        send_prepared.__globals__["prepare_subscribe_today"] = lambda create_tasks=False: 1

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(send_prepared("10:00"), 1)

        self.assertIn("ERROR:", output.getvalue())

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
            self.assertEqual([item["time"] for item in default_schedule], ["12:00", "08:30", "13:00"])

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
        self.assertIn("TRACKING:", output.getvalue())

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

        with redirect_stdout(StringIO()):
            self.assertEqual(track("370881"), 0)

        self.assertIn("123270", saved["items"])
        self.assertEqual(saved["items"]["123270"]["status"], "scheduled")
        self.assertIn("370881", saved["items"]["123270"]["aliases"])

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

        self.assertIn("NO_ALERT", output.getvalue())
        self.assertEqual(saved["items"]["123270"]["status"], "expired")

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

        self.assertIn("CANCELED", output.getvalue())
        self.assertEqual(disabled, ["task-a"])
        self.assertEqual(saved["items"]["123270"]["status"], "canceled")

    def test_list_reminders_shows_only_current_effective_items(self) -> None:
        list_reminders = self.ns["list_reminders"]
        now = self.ns["datetime"](2026, 3, 5, 8, 0, tzinfo=self.ns["TIMEZONE"])
        future = "2026-03-05T10:00:00"
        past = "2026-03-05T07:00:00"
        list_reminders.__globals__["now_local"] = lambda: now
        list_reminders.__globals__["load_tasks"] = lambda: {
            "version": 1,
            "tasks": {
                "bond-subscribe-20260305-1000": {"enabled": True, "name": "申购", "next_run_at": future},
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
        self.assertIn("申购提醒", text)
        self.assertIn("上市提醒", text)
        self.assertIn("待追踪上市", text)
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
            "data_source": {
                "calendar_url": "https://example.com/calendar.json",
                "headers": {"Authorization": "Bearer secret", "Referer": "https://example.com"},
            },
            "receiver": "wxid_sensitive",
            "notify_session_id": "session_sensitive",
            "subscribe_reminder_schedule": [{"time": "09:30", "label": "上午提醒"}],
            "listing_tracking_max_days": 90,
        }
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
        self.assertIn("INFO: bond-calendar-reminder 待执行任务", text)
        self.assertIn("scheduler 待执行申购提醒", text)
        self.assertIn("scheduler 待执行上市提醒", text)
        self.assertIn("申购提醒", text)
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

    def test_load_config_does_not_write_auto_receiver(self) -> None:
        load_config = self.ns["load_config"]
        calls: list[dict] = []
        load_config.__globals__["read_json"] = lambda path, default: {}
        load_config.__globals__["write_json"] = lambda path, data: calls.append(data)

        self.assertEqual(load_config(), {})
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
