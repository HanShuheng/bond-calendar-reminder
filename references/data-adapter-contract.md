# 数据适配器协议

本项目核心业务只依赖这里定义的标准数据协议，不要求用户使用东方财富、集思录或任何特定厂商接口。内置适配器只是可直接运行的示例；开源使用时，用户可以按自己的数据来源实现 Python 适配器。

## 配置入口

日历数据使用 `calendar_strategy`：

```json
{
  "calendar_strategy": {
    "type": "python",
    "adapter": "my_bond_data.adapters:MyCalendarAdapter"
  }
}
```

行情数据使用 `quote_strategy`：

```json
{
  "quote_strategy": {
    "type": "python",
    "adapter": "my_bond_data.adapters:MyQuoteAdapter"
  }
}
```

`adapter` 必须使用 `module:attribute` 格式。`attribute` 可以是类、工厂函数或已创建的对象；最终对象需要提供下文约定的方法。

## CalendarAdapter

日历适配器必须提供：

```python
class CalendarAdapter:
    def load_events(self) -> list[dict]:
        ...
```

每个事件返回一个标准 `BondEvent` 字典：

```python
{
    "event_type": "subscribe",
    "date": "2026-06-01",
    "bond_code": "123267",
    "bond_name": "珂玛转债",
    "subscribe_code": "371611",
    "allotment_code": "381611",
    "stock_code": "301611",
    "details_url": "https://example.com/bonds/123267",
    "source": "user-custom"
}
```

必填字段：

| 字段 | 说明 |
|---|---|
| `event_type` | 事件类型：`subscribe`、`winning`、`listing` |
| `date` | 事件日期，格式为 `YYYY-MM-DD` |
| `bond_code` | 转债代码 |
| `bond_name` | 转债简称 |

可选字段：

| 字段 | 说明 |
|---|---|
| `subscribe_code` | 申购代码 |
| `allotment_code` | 配售代码 |
| `stock_code` | 正股代码 |
| `details_url` | 详情页链接 |
| `source` | 数据来源标识，便于排障 |
| `description` | 补充说明，会进入事项描述 |

事件名固定映射：

| `event_type` | 中文事件名 |
|---|---|
| `subscribe` | 申购日 |
| `winning` | 中签结果公布日 |
| `listing` | 上市日 |

## QuoteAdapter

行情适配器必须提供：

```python
class QuoteAdapter:
    def get_quote(self, bond_code: str) -> dict | None:
        ...
```

返回一个标准 `BondQuote` 字典：

```python
{
    "bond_code": "123267",
    "bond_name": "珂玛转债",
    "last_price": 229.117,
    "prev_close": 242.0,
    "change": -12.883,
    "change_percent": -5.32,
    "quote_time": "2026-06-01T14:06:00",
    "source": "user-custom"
}
```

必填字段：

| 字段 | 说明 |
|---|---|
| `bond_code` | 转债代码 |
| `last_price` | 最新价 |
| `change_percent` | 涨跌幅百分比，直接使用百分数，例如 `30.0` 表示 `30%` |

可选字段：

| 字段 | 说明 |
|---|---|
| `bond_name` | 转债简称 |
| `prev_close` | 昨收 |
| `change` | 涨跌额 |
| `quote_time` | 行情时间，推荐本地无时区 ISO 文本 |
| `source` | 数据来源标识，便于排障 |

如果无法获取行情，返回 `None`。缺少 `change_percent` 时，项目不会创建上市日 `14:55` 涨停二次提醒。

## 自定义适配器示例

```python
class MyCalendarAdapter:
    def load_events(self) -> list[dict]:
        return [
            {
                "event_type": "subscribe",
                "date": "2026-06-01",
                "bond_code": "123267",
                "bond_name": "珂玛转债",
                "subscribe_code": "371611",
                "allotment_code": "381611",
                "details_url": "https://example.com/bonds/123267",
                "source": "my-calendar",
            },
            {
                "event_type": "winning",
                "date": "2026-06-03",
                "bond_code": "123267",
                "bond_name": "珂玛转债",
                "source": "my-calendar",
            },
            {
                "event_type": "listing",
                "date": "2026-06-20",
                "bond_code": "123267",
                "bond_name": "珂玛转债",
                "source": "my-calendar",
            },
        ]


class MyQuoteAdapter:
    def get_quote(self, bond_code: str) -> dict | None:
        return {
            "bond_code": bond_code,
            "bond_name": "珂玛转债",
            "last_price": 130.0,
            "prev_close": 100.0,
            "change": 30.0,
            "change_percent": 30.0,
            "quote_time": "2026-06-01T14:50:00",
            "source": "my-quote",
        }
```

## 内置示例适配器

项目内置以下示例适配器，方便新用户直接验证链路：

| 适配器 | 配置类型 | 说明 |
|---|---|---|
| `EastmoneyCalendarAdapter` | `calendar_strategy.type=builtin`，adapter `type=eastmoney` | 将东方财富可转债列表字段转换为标准 `BondEvent` |
| `JisiluCalendarAdapter` | `calendar_strategy.type=builtin`，adapter `type=jisilu` | 将集思录日历字段转换为标准 `BondEvent` |
| `EastmoneyPush2QuoteAdapter` | `quote_strategy.type=eastmoney_push2` | 将东方财富 push2 行情字段转换为标准 `BondQuote` |

内置示例适配器的字段资料见：

- `references/eastmoney-bond-fields.md`
- `references/quote-data-source.md`
