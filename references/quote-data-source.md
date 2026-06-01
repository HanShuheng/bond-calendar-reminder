# 行情示例适配器参考

本文档记录内置东方财富 `push2` 行情示例适配器和 `normalized_json` HTTP 示例适配器的配置方式。它不是项目主协议；项目主协议见 `references/data-adapter-contract.md`。开源使用时，用户可以实现自己的 `QuoteAdapter`，只要返回标准 `BondQuote`。

## 使用场景

当前用于上市日涨停二次提醒：

1. 上市日 `14:50` 左右执行 `check-listing-limit-up`。
2. 脚本按转债代码调用 `quote_strategy`。
3. 如果 `change_percent >= listing_limit_up_reminder.threshold_percent`，创建当天 `14:55` 提醒。

## 内置东方财富 push2 示例

```json
{
  "quote_strategy": {
    "type": "eastmoney_push2",
    "api_url": "https://push2.eastmoney.com/api/qt/stock/get",
    "params": {
      "secid": "{eastmoney_secid}",
      "fields": "f57,f58,f43,f60,f169,f170,f86"
    },
    "headers": {
      "Referer": "https://data.eastmoney.com/kzz/"
    }
  }
}
```

`params` 的字符串值支持以下模板变量：

| 变量 | 说明 |
|---|---|
| `{bond_code}` | 转债代码，例如 `123267` |
| `{eastmoney_secid}` | 东方财富 secid，例如深市 `0.123267`、沪市 `1.113682` |

东方财富 `push2` 返回的常用字段：

| 字段 | 标准字段 | 处理 |
|---|---|---|
| `f57` | `bond_code` | 原样 |
| `f58` | `bond_name` | 原样 |
| `f43` | `last_price` | 除以 `1000` |
| `f60` | `prev_close` | 除以 `1000` |
| `f169` | `change` | 除以 `1000` |
| `f170` | `change_percent` | 除以 `100` |
| `f86` | `quote_time` | Unix 时间戳转本地无时区 ISO 文本 |

## normalized_json HTTP 示例

如果用户暂时不想写 Python 适配器，也可以使用 `normalized_json` 作为简单 HTTP 示例：

```json
{
  "quote_strategy": {
    "type": "normalized_json",
    "api_url": "https://example.com/quote",
    "params": {
      "code": "{bond_code}"
    },
    "headers": {},
    "data_path": "data"
  }
}
```

接口应返回标准行情字段：

```json
{
  "data": {
    "bond_code": "123267",
    "bond_name": "珂玛转债",
    "last_price": 229.117,
    "prev_close": 242.0,
    "change": -12.883,
    "change_percent": -5.32,
    "quote_time": "2026-06-01T14:06:00",
    "source": "custom-http"
  }
}
```

`data_path` 为空时，脚本会把整个响应 JSON 当作标准字段对象；`data_path` 为 `data` 时，脚本读取响应里的 `data` 对象。

第三方接口字段和可用性可能变化。实际提醒仅作辅助，请以交易软件、交易所公告和券商系统为准。
