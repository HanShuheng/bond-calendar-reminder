class CalendarAdapter:
    def load_events(self):
        return [
            {
                "event_type": "subscribe",
                "date": "2026-03-05",
                "bond_code": "111111",
                "bond_name": "自定义转债",
                "subscribe_code": "371111",
                "source": "custom-calendar",
            },
            {"event_type": "subscribe", "date": "2026-03-06", "bond_name": "缺代码"},
        ]

class QuoteAdapter:
    def get_quote(self, bond_code):
        return {
            "bond_code": bond_code,
            "bond_name": "自定义转债",
            "last_price": 130.0,
            "prev_close": 100.0,
            "change": 30.0,
            "change_percent": 30.0,
            "quote_time": "2026-03-05T14:50:00",
            "source": "custom-quote",
        }
