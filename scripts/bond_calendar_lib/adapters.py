from __future__ import annotations

import importlib
import inspect
import json
import re
import sys
import time
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

try:
    import requests
except ModuleNotFoundError:
    requests = None  # type: ignore[assignment]
    RequestException = Exception
else:
    RequestException = requests.RequestException

from .settings import (
    DEFAULT_EASTMONEY_API_URL, DEFAULT_EASTMONEY_PARAMS,
    DEFAULT_EASTMONEY_QUOTE_API_URL, DEFAULT_EASTMONEY_QUOTE_FIELDS,
    DEFAULT_EASTMONEY_REFERER, DEFAULT_HEADERS, DEFAULT_JISILU_BASE_URL,
    DEFAULT_JISILU_CALENDAR_URL, DEFAULT_JISILU_DETAIL_URL_TEMPLATE,
    DEFAULT_JISILU_REFERER, TIMEZONE,
)
from .storage import load_config

EVENT_TYPE_LABELS = {
    "subscribe": "申购日",
    "winning": "中签结果公布日",
    "listing": "上市日",
}


class AdapterLoadError(ValueError):
    pass

def request_json(
    url: str,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    retries: int = 3,
    timeout: int = 15,
) -> Any | None:
    if requests is None:
        print("Error: 缺少 Python 依赖 requests，请先安装 requirements.txt", file=sys.stderr)
        return None

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (RequestException, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            print(f"Warning: fetch attempt {attempt}/{retries} failed: {exc}", file=sys.stderr)
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
    print(f"Error: 数据源暂时不可用: {last_error}", file=sys.stderr)
    return None

def clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def parse_event_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

def date_text(value: Any) -> str:
    parsed = parse_event_date(value)
    return parsed.isoformat() if parsed else ""

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

def default_eastmoney_calendar_config() -> dict[str, Any]:
    headers = dict(DEFAULT_HEADERS)
    headers.setdefault("Referer", DEFAULT_EASTMONEY_REFERER)
    return {
        "api_url": DEFAULT_EASTMONEY_API_URL,
        "params": dict(DEFAULT_EASTMONEY_PARAMS),
        "headers": headers,
    }

def default_jisilu_calendar_config() -> dict[str, Any]:
    headers = dict(DEFAULT_HEADERS)
    headers.setdefault("Referer", DEFAULT_JISILU_REFERER)
    return {
        "calendar_url": DEFAULT_JISILU_CALENDAR_URL,
        "base_url": DEFAULT_JISILU_BASE_URL,
        "detail_url_template": DEFAULT_JISILU_DETAIL_URL_TEMPLATE,
        "headers": headers,
    }

def default_eastmoney_quote_config() -> dict[str, Any]:
    headers = dict(DEFAULT_HEADERS)
    headers.setdefault("Referer", DEFAULT_EASTMONEY_REFERER)
    return {
        "api_url": DEFAULT_EASTMONEY_QUOTE_API_URL,
        "params": {"secid": "{eastmoney_secid}", "fields": DEFAULT_EASTMONEY_QUOTE_FIELDS},
        "headers": headers,
        "data_path": "data",
    }

def merge_headers(default_headers: dict[str, str], custom_headers: Any) -> dict[str, str]:
    headers = dict(default_headers)
    if isinstance(custom_headers, dict):
        headers.update({str(key): str(value) for key, value in custom_headers.items()})
    return headers

def fetch_eastmoney_data(adapter_config: dict[str, Any]) -> list[dict[str, Any]] | None:
    default_config = default_eastmoney_calendar_config()
    api_url = adapter_config.get("api_url") or default_config["api_url"]
    params = adapter_config.get("params") if isinstance(adapter_config.get("params"), dict) else default_config["params"]
    headers = merge_headers(default_config["headers"], adapter_config.get("headers"))
    data = request_json(
        str(api_url),
        headers,
        {str(key): str(value) for key, value in params.items()},
    )
    if data is None:
        return None
    if not isinstance(data, dict):
        print(f"Error: 东方财富数据格式异常：Expected JSON object, got {type(data).__name__}", file=sys.stderr)
        return None
    result = data.get("result")
    rows = result.get("data") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        print("Error: 东方财富数据格式异常：缺少 result.data", file=sys.stderr)
        return None
    return [item for item in rows if isinstance(item, dict)]

def fetch_jisilu_calendar_data(adapter_config: dict[str, Any]) -> list[dict[str, Any]] | None:
    default_config = default_jisilu_calendar_config()
    calendar_url = adapter_config.get("calendar_url") or default_config["calendar_url"]
    if not isinstance(calendar_url, str) or not calendar_url.strip():
        return []
    data = request_json(calendar_url, merge_headers(default_config["headers"], adapter_config.get("headers")))
    if data is None:
        return None
    if not isinstance(data, list):
        print(f"Error: 集思录日历数据格式异常：Expected JSON list, got {type(data).__name__}", file=sys.stderr)
        return None
    return [item for item in data if isinstance(item, dict)]

def eastmoney_detail_url(code: str) -> str:
    return f"https://data.eastmoney.com/kzz/detail/{code}.html" if code else ""

def eastmoney_quote_secid(code: str) -> str:
    code = str(code or "").strip()
    if re.fullmatch(r"11\d{4}", code):
        return f"1.{code}"
    if re.fullmatch(r"12\d{4}", code):
        return f"0.{code}"
    if re.fullmatch(r"\d{6}", code):
        return f"0.{code}"
    return code

def render_template(value: str, context: dict[str, str]) -> str:
    result = value
    for key, replacement in context.items():
        result = result.replace("{" + key + "}", replacement)
    return result

def render_quote_params(params: dict[str, str], code: str) -> dict[str, str]:
    context = {
        "bond_code": code,
        "eastmoney_secid": eastmoney_quote_secid(code),
    }
    return {key: render_template(value, context) for key, value in params.items()}

def get_path(data: Any, path: str) -> Any:
    if not path:
        return data
    current = data
    for part in path.split("."):
        if not part:
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current

def numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None

def scale_eastmoney_price(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return round(float(value) / 1000, 3)

def scale_eastmoney_percent(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(float(value) / 100, 2)

def quote_time_text(value: Any) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return ""
    try:
        return datetime.fromtimestamp(value, TIMEZONE).replace(tzinfo=None).isoformat()
    except (OSError, ValueError):
        return ""

def normalize_eastmoney_quote(data: dict[str, Any]) -> dict[str, Any] | None:
    if not data:
        return None
    code = str(data.get("f57") or "").strip()
    name = str(data.get("f58") or "").strip()
    last_price = scale_eastmoney_price(data.get("f43"))
    prev_close = scale_eastmoney_price(data.get("f60"))
    change = scale_eastmoney_price(data.get("f169"))
    change_percent = scale_eastmoney_percent(data.get("f170"))
    if not code or last_price is None or change_percent is None:
        return None
    return {
        "bond_code": code,
        "bond_name": name,
        "name": name,
        "last_price": last_price,
        "prev_close": prev_close,
        "change": change,
        "change_percent": change_percent,
        "quote_time": quote_time_text(data.get("f86")),
        "source": "eastmoney_push2",
        "raw": data,
    }

def normalize_standard_quote(data: dict[str, Any]) -> dict[str, Any] | None:
    code = str(data.get("bond_code") or data.get("code") or "").strip()
    name = str(data.get("bond_name") or data.get("name") or "").strip()
    last_price = numeric(data.get("last_price"))
    prev_close = numeric(data.get("prev_close"))
    change = numeric(data.get("change"))
    change_percent = numeric(data.get("change_percent"))
    if not code or last_price is None or change_percent is None:
        return None
    return {
        "bond_code": code,
        "bond_name": name,
        "name": name,
        "last_price": round(last_price, 3),
        "prev_close": round(prev_close, 3) if prev_close is not None else None,
        "change": round(change, 3) if change is not None else None,
        "change_percent": round(change_percent, 2),
        "quote_time": str(data.get("quote_time") or ""),
        "source": str(data.get("source") or "custom"),
        "raw": data,
    }

def normalize_bond_event(data: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(data.get("event_type") or "").strip()
    keyword = EVENT_TYPE_LABELS.get(event_type)
    event_date = date_text(data.get("date"))
    bond_code = str(data.get("bond_code") or data.get("code") or "").strip()
    name = str(data.get("bond_name") or data.get("name") or data.get("title") or "").strip()
    if not keyword or not event_date or not bond_code or not name:
        return None

    subscribe_code = str(data.get("subscribe_code") or "").strip()
    allotment_code = str(data.get("allotment_code") or data.get("placing_code") or "").strip()
    stock_code = str(data.get("stock_code") or "").strip()
    url = str(data.get("details_url") or data.get("url") or "").strip()
    all_codes = all_six_digit_codes(
        "\n".join(
            [
                bond_code,
                subscribe_code,
                allotment_code,
                stock_code,
                str(data.get("description") or ""),
            ]
        )
    )
    description_lines = [
        f"转债代码：{bond_code}",
    ]
    if subscribe_code:
        description_lines.append(f"申购代码：{subscribe_code}")
    if allotment_code:
        description_lines.append(f"配售代码：{allotment_code}")
    if stock_code:
        description_lines.append(f"正股代码：{stock_code}")
    if data.get("winning_date"):
        description_lines.append(f"中签号发布日:{data['winning_date']}")
    if data.get("listing_date"):
        description_lines.append(f"上市日期:{data['listing_date']}")
    if data.get("description"):
        description_lines.append(str(data["description"]).strip())

    event = dict(data)
    event.update(
        {
            "event_type": event_type,
            "keyword": keyword,
            "date": event_date,
            "bond_code": bond_code,
            "bond_name": name,
            "name": name,
            "title": f"【{keyword}】{name}",
            "subscribe_code": subscribe_code,
            "allotment_code": allotment_code,
            "stock_code": stock_code,
            "description": "\n".join(line for line in description_lines if line),
            "url": url,
            "details_url": url,
            "all_codes": all_codes,
            "source": str(data.get("source") or "custom"),
        }
    )
    return event

def normalize_eastmoney_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    bond_code = str(row.get("SECURITY_CODE") or "").strip()
    bond_name = str(row.get("SECURITY_NAME_ABBR") or row.get("SECURITY_NAME") or "").strip()
    if not bond_code or not bond_name:
        return []

    subscribe_code = str(row.get("CORRECODE") or "").strip()
    allotment_code = str(row.get("CORRECODEO") or "").strip()
    stock_code = str(row.get("CONVERT_STOCK_CODE") or "").strip()
    winning_date = date_text(row.get("BOND_START_DATE"))
    listing_date = date_text(row.get("LISTING_DATE"))
    common = {
        "bond_code": bond_code,
        "bond_name": bond_name,
        "subscribe_code": subscribe_code,
        "allotment_code": allotment_code,
        "stock_code": stock_code,
        "details_url": eastmoney_detail_url(bond_code),
        "source": "eastmoney",
        "winning_date": winning_date,
        "listing_date": listing_date,
        "raw": row,
    }
    event_specs = [
        ("subscribe", row.get("PUBLIC_START_DATE")),
        ("winning", row.get("BOND_START_DATE")),
        ("listing", row.get("LISTING_DATE")),
    ]
    events: list[dict[str, Any]] = []
    for event_type, raw_date in event_specs:
        event = normalize_bond_event({**common, "event_type": event_type, "date": date_text(raw_date)})
        if event:
            events.append(event)
    return events

def jisilu_detail_url_for(row: dict[str, Any], config: dict[str, Any]) -> str:
    code = str(row.get("bond_id") or row.get("bond_code") or row.get("code") or "").strip()
    raw_url = str(row.get("url") or row.get("href") or "").strip()
    if raw_url:
        return urljoin(str(config.get("base_url") or DEFAULT_JISILU_BASE_URL), raw_url)
    template = str(config.get("detail_url_template") or "")
    if template and code:
        return render_template(template, {"code": code, "bond_code": code})
    return ""

def normalize_jisilu_event(row: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    config = config or default_jisilu_calendar_config()
    title = clean_text(row.get("title") or row.get("name") or "")
    keyword = event_keyword(title)
    event_type = {"申购日": "subscribe", "上市日": "listing"}.get(keyword or "")
    event_date = date_text(row.get("start") or row.get("date") or row.get("start_date"))
    description = clean_text(row.get("description") or row.get("content") or "")
    text_blob = "\n".join([title, description])
    bond_code = (
        str(row.get("bond_id") or row.get("bond_code") or row.get("code") or "").strip()
        or (all_six_digit_codes(text_blob)[0] if all_six_digit_codes(text_blob) else "")
    )
    if not event_type:
        return None
    return normalize_bond_event(
        {
            "event_type": event_type,
            "date": event_date,
            "bond_code": bond_code,
            "bond_name": strip_event_prefix(title),
            "subscribe_code": extract_code("申购代码", text_blob),
            "allotment_code": extract_code("配售代码", text_blob),
            "description": description,
            "details_url": jisilu_detail_url_for(row, config),
            "source": "jisilu",
            "raw": row,
        }
    )

def merge_events(primary: list[dict[str, Any]], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(primary)
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for event in merged:
        code_or_name = str(event.get("bond_code") or event.get("name") or "")
        index[(str(event.get("keyword") or ""), code_or_name)] = event

    for event in fallback:
        code_or_name = str(event.get("bond_code") or event.get("name") or "")
        key = (str(event.get("keyword") or ""), code_or_name)
        existing = index.get(key)
        if existing:
            if existing.get("date") != event.get("date"):
                print(
                    f"Warning: {event.get('name') or code_or_name} {event.get('keyword')} 日期不一致，"
                    f"保留优先适配器日期 {existing.get('date')}，忽略后续适配器日期 {event.get('date')}",
                    file=sys.stderr,
                )
            for field in ("url", "details_url", "description", "subscribe_code", "allotment_code"):
                if not existing.get(field) and event.get(field):
                    existing[field] = event[field]
            continue
        merged.append(event)
        index[key] = event
    return merged

def load_python_adapter(path: str) -> Any:
    if not isinstance(path, str) or ":" not in path:
        raise AdapterLoadError("Python adapter must use 'module:attribute' format")
    module_name, attr_name = path.split(":", 1)
    module = importlib.import_module(module_name)
    target = getattr(module, attr_name)
    if inspect.isclass(target):
        return target()
    if callable(target):
        result = target()
        return result if result is not None else target
    return target

class EastmoneyCalendarAdapter:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or default_eastmoney_calendar_config()

    def load_events(self) -> list[dict[str, Any]] | None:
        rows = fetch_eastmoney_data(self.config)
        if rows is None:
            return None
        return [
            event
            for item in rows
            for event in normalize_eastmoney_row(item)
        ]

class JisiluCalendarAdapter:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or default_jisilu_calendar_config()

    def load_events(self) -> list[dict[str, Any]] | None:
        rows = fetch_jisilu_calendar_data(self.config)
        if rows is None:
            return None
        return [
            event
            for item in rows
            if (event := normalize_jisilu_event(item, self.config))
        ]

class CompositeCalendarAdapter:
    def __init__(self, adapters: list[Any]) -> None:
        self.adapters = adapters

    def load_events(self) -> list[dict[str, Any]] | None:
        event_groups: list[list[dict[str, Any]]] = []
        any_error = False
        for adapter in self.adapters:
            raw_events = adapter.load_events()
            if raw_events is None:
                any_error = True
                continue
            events = [event for raw in raw_events if (event := normalize_bond_event(raw))]
            if events:
                event_groups.append(events)
        if not event_groups and any_error:
            return None
        if not event_groups:
            return []
        merged = event_groups[0]
        for events in event_groups[1:]:
            merged = merge_events(merged, events)
        return sorted(merged, key=lambda e: (e["date"], e.get("bond_code") or "", e["title"]))

class EastmoneyPush2QuoteAdapter:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or default_eastmoney_quote_config()

    def get_quote(self, bond_code: str) -> dict[str, Any] | None:
        data = request_json(
            str(self.config["api_url"]),
            merge_headers(default_eastmoney_quote_config()["headers"], self.config.get("headers")),
            render_quote_params(self.config["params"], bond_code),
            retries=2,
            timeout=10,
        )
        if not isinstance(data, dict):
            return None
        payload = get_path(data, str(self.config.get("data_path") or "data"))
        if not isinstance(payload, dict):
            return None
        return normalize_eastmoney_quote(payload)

class ConfiguredQuoteAdapter:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get_quote(self, bond_code: str) -> dict[str, Any] | None:
        data = request_json(
            self.config["api_url"],
            self.config.get("headers", {}),
            render_quote_params(self.config.get("params", {}), bond_code),
            retries=2,
            timeout=10,
        )
        if not isinstance(data, dict):
            return None
        payload = get_path(data, self.config.get("data_path", ""))
        if not isinstance(payload, dict):
            return None
        return normalize_standard_quote(payload)

def configured_builtin_calendar_adapter(strategy: dict[str, Any]) -> Any:
    adapters: list[Any] = []
    for raw_adapter in strategy.get("adapters", []):
        if not isinstance(raw_adapter, dict):
            continue
        adapter_type = raw_adapter.get("type")
        if adapter_type == "eastmoney":
            adapters.append(EastmoneyCalendarAdapter(raw_adapter))
        elif adapter_type == "jisilu":
            adapters.append(JisiluCalendarAdapter(raw_adapter))
    return CompositeCalendarAdapter(adapters or [EastmoneyCalendarAdapter(), JisiluCalendarAdapter()])

def load_calendar_adapter() -> Any:
    config = load_config()
    strategy = config.get("calendar_strategy")
    if isinstance(strategy, dict) and strategy.get("type") == "python":
        return load_python_adapter(str(strategy.get("adapter") or ""))
    if isinstance(strategy, dict) and strategy.get("type") == "builtin":
        return configured_builtin_calendar_adapter(strategy)
    return CompositeCalendarAdapter([EastmoneyCalendarAdapter(), JisiluCalendarAdapter()])

def load_quote_adapter() -> Any:
    config = load_config()
    strategy = config.get("quote_strategy")
    if isinstance(strategy, dict) and strategy.get("type") == "python":
        return load_python_adapter(str(strategy.get("adapter") or ""))
    if isinstance(strategy, dict) and strategy.get("type") == "normalized_json":
        return ConfiguredQuoteAdapter(strategy)
    if isinstance(strategy, dict) and strategy.get("type") == "eastmoney_push2":
        return EastmoneyPush2QuoteAdapter(strategy)
    return EastmoneyPush2QuoteAdapter()

def fetch_eastmoney_bond_quote(code: str) -> dict[str, Any] | None:
    headers = dict(DEFAULT_HEADERS)
    headers.setdefault("Referer", DEFAULT_EASTMONEY_REFERER)
    data = request_json(
        DEFAULT_EASTMONEY_QUOTE_API_URL,
        headers,
        {"secid": eastmoney_quote_secid(code), "fields": DEFAULT_EASTMONEY_QUOTE_FIELDS},
        retries=2,
        timeout=10,
    )
    if not isinstance(data, dict):
        return None
    quote = data.get("data")
    if not isinstance(quote, dict):
        return None
    return normalize_eastmoney_quote(quote)

def fetch_bond_quote(code: str) -> dict[str, Any] | None:
    adapter = load_quote_adapter()
    if not hasattr(adapter, "get_quote"):
        print("Error: quote adapter must provide get_quote(bond_code)", file=sys.stderr)
        return None
    quote = adapter.get_quote(code)
    if not isinstance(quote, dict):
        return None
    if {"last_price", "change_percent"} <= set(quote):
        return normalize_standard_quote(quote)
    return quote

def load_events() -> list[dict[str, Any]] | None:
    adapter = load_calendar_adapter()
    if not hasattr(adapter, "load_events"):
        print("Error: calendar adapter must provide load_events()", file=sys.stderr)
        return None
    raw_events = adapter.load_events()
    if raw_events is None:
        return None
    events = [event for raw in raw_events if isinstance(raw, dict) and (event := normalize_bond_event(raw))]
    return sorted(events, key=lambda e: (e["date"], e.get("bond_code") or "", e["title"]))
