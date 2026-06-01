# 东方财富可转债接口字段说明

本文档记录东方财富可转债申购页面及其接口中常见字段的含义。它是内置 `EastmoneyCalendarAdapter` 示例适配器的字段参考，不是项目主协议。项目主协议见 `references/data-adapter-contract.md`；用户可以使用任何数据来源，只要适配器返回标准 `BondEvent`。

> 风险说明：本文档仅供学习、研究和技术交流使用。学习完成后请自行删除本项目、本文档及其生成文件。第三方接口字段、含义和可用性可能随时变化，实际投资操作请以交易所公告、发行人公告、券商系统和官方披露信息为准。因使用、传播、修改、部署或依赖本项目及其生成内容产生的任何直接或间接损失、争议或法律责任，均与项目开发者无关，项目开发者不承担任何责任。

## 数据来源

页面来源：

```text
https://data.eastmoney.com/xg/xg/?mkt=kzz
```

接口地址：

```text
https://datacenter-web.eastmoney.com/api/data/v1/get
```

常用查询参数：

| 参数 | 示例值 | 说明 |
|---|---|---|
| `reportName` | `RPT_BOND_CB_LIST` | 可转债列表报表 |
| `columns` | `ALL` | 返回全部字段 |
| `source` | `WEB` | 东方财富页面使用的来源标识 |
| `client` | `WEB` | 东方财富页面使用的客户端标识 |
| `pageNumber` | `1` | 页码 |
| `pageSize` | `20` | 每页数量 |
| `sortColumns` | `PUBLIC_START_DATE,SECURITY_CODE` | 排序字段 |
| `sortTypes` | `-1,1` | 排序方向 |

示例请求：

```text
https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_BOND_CB_LIST&columns=ALL&source=WEB&client=WEB&pageNumber=1&pageSize=20&sortColumns=PUBLIC_START_DATE,SECURITY_CODE&sortTypes=-1,1
```

## 项目重点字段

这些字段最适合进入本项目的日历生成逻辑：

| 字段 | 含义 | 项目用途 |
|---|---|---|
| `SECURITY_CODE` | 转债代码 | 生成稳定 UID，避免重复事件 |
| `SECURITY_NAME_ABBR` | 转债简称 | 生成事件标题 |
| `CORRECODE` | 申购代码 | 放入申购日事件描述 |
| `PUBLIC_START_DATE` | 申购日 | 生成“申购日”提醒 |
| `BOND_START_DATE` | 中签号发布日 | 生成“中签结果公布”提醒 |
| `LISTING_DATE` | 上市日 | 生成“上市日”提醒 |
| `ONLINE_GENERAL_LWR` | 网上发行中签率 | 数据公布后放入事件描述 |
| `RATING` | 信用评级 | 放入事件描述，辅助识别风险等级 |

当前事件类型：

| 事件 | 日期字段 | 建议标题 |
|---|---|---|
| 申购日 | `PUBLIC_START_DATE` | `【申购日】通合转债` |
| 中签结果公布 | `BOND_START_DATE` | `【中签结果公布】通合转债` |
| 上市日 | `LISTING_DATE` | `【上市日】通合转债` |

## 字段说明

### 身份与交易市场

| 字段 | 含义 | 使用建议 |
|---|---|---|
| `SECURITY_CODE` | 转债代码 | 核心字段，用于 UID、标题和详情链接 |
| `SECUCODE` | 带市场后缀的证券代码，如 `123271.SZ` | 可用于识别市场 |
| `SECURITY_NAME_ABBR` | 转债简称 | 核心字段，用于日历标题 |
| `TRADE_MARKET` | 交易市场，如 `CNSESZ` | 可用于判断深市或沪市 |
| `MARKET` | 市场字段，部分记录为空 | 暂不使用 |
| `BOND_COMBINE_CODE` | 东方财富内部组合编码 | 暂不使用 |
| `CONVERT_STOCK_CODE` | 正股代码 | 可放入描述 |
| `SECURITY_SHORT_NAME` | 正股简称 | 可放入描述 |

### 申购与发行

| 字段 | 含义 | 使用建议 |
|---|---|---|
| `PUBLIC_START_DATE` | 网上申购日 | 核心字段，生成申购日提醒 |
| `PUBLIC_START_DATE_HOURS` | 带具体时间的申购日期字段 | 暂不作为事件时间来源 |
| `CORRECODE` | 申购代码 | 放入申购日描述 |
| `CORRECODE_NAME_ABBR` | 申购简称 | 可放入描述 |
| `CORRECODEO` | 配售代码 | 可放入描述 |
| `CORRECODE_NAME_ABBRO` | 配售简称 | 可放入描述 |
| `SECURITY_START_DATE` | 股权登记日 | 原股东配售相关，可选 |
| `FIRST_PER_PREPLACING` | 每股配售额 | 原股东配售相关，可选 |
| `ONLINE_GENERAL_AAU` | 申购上限，单位通常为万元 | 可放入申购日描述 |
| `ACTUAL_ISSUE_SCALE` | 实际发行规模，单位通常为亿元 | 可放入描述 |
| `ISSUE_PRICE` | 发行价格 | 可放入描述 |
| `ISSUE_TYPE` | 发行类型编码 | 暂不直接展示 |
| `ISSUE_YEAR` | 发行年份 | 暂不使用 |
| `ISSUE_OBJECT` | 发行对象说明 | 文本较长，谨慎截短展示 |
| `PARAM_NAME` | 发行方式说明 | 文本字段，可选展示 |
| `REMARK` | 发行备注 | 文本较长，适合截短放入描述 |

### 中签与上市

| 字段 | 含义 | 使用建议 |
|---|---|---|
| `BOND_START_DATE` | 中签号发布日 | 核心字段，生成中签结果公布提醒 |
| `ONLINE_GENERAL_LWR` | 网上发行中签率 | 数据公布后可放入描述 |
| `FIRST_PROFIT` | 每中一签获利估算 | 仅供展示参考，不建议作为提醒依据 |
| `LISTING_DATE` | 上市日 | 核心字段，生成上市日提醒 |
| `DELIST_DATE` | 退市日 | 暂不用于打新提醒 |

### 转股与债券生命周期

| 字段 | 含义 | 使用建议 |
|---|---|---|
| `INITIAL_TRANSFER_PRICE` | 初始转股价 | 可选展示 |
| `TRANSFER_PRICE` | 当前转股价 | 可选展示 |
| `TRANSFER_VALUE` | 转股价值 | 可选展示 |
| `TRANSFER_PREMIUM_RATIO` | 转股溢价率 | 可选展示 |
| `TRANSFER_START_DATE` | 转股开始日 | 不建议进入打新日历 |
| `TRANSFER_END_DATE` | 转股结束日 | 不建议进入打新日历 |
| `IS_CONVERT_STOCK` | 是否已转股相关状态 | 暂不使用 |
| `VALUE_DATE` | 起息日 | 不建议作为打新提醒 |
| `CEASE_DATE` | 止息日 | 暂不使用 |
| `EXPIRE_DATE` | 到期日 | 暂不使用 |
| `BOND_EXPIRE` | 债券期限，通常为年数 | 可选展示 |

### 赎回、回售与下修

| 字段 | 含义 | 使用建议 |
|---|---|---|
| `IS_REDEEM` | 是否设置赎回条款 | 暂不用于打新提醒 |
| `REDEEM_TYPE` | 赎回类型 | 暂不使用 |
| `REDEEM_TRIG_PRICE` | 强赎触发价 | 可选展示 |
| `REDEEM_CLAUSE` | 赎回条款说明 | 文本较长，暂不放入日历 |
| `IS_SELLBACK` | 是否设置回售条款 | 暂不用于打新提醒 |
| `RESALE_TRIG_PRICE` | 回售触发价 | 可选展示 |
| `RESALE_CLAUSE` | 回售条款说明 | 文本较长，暂不放入日历 |
| `EXECUTE_REASON_HS` | 沪市执行原因编码 | 暂不使用 |
| `EXECUTE_REASON_SH` | 深市执行原因编码 | 暂不使用 |
| `EXECUTE_PRICE_HS` | 沪市执行价格 | 暂不使用 |
| `EXECUTE_PRICE_SH` | 深市执行价格 | 暂不使用 |
| `EXECUTE_START_DATEHS` | 沪市执行开始日 | 暂不使用 |
| `EXECUTE_START_DATESH` | 深市执行开始日 | 暂不使用 |
| `EXECUTE_END_DATE` | 执行结束日 | 暂不使用 |
| `NOTICE_DATE_HS` | 沪市公告日期 | 暂不使用 |
| `NOTICE_DATE_SH` | 深市公告日期 | 暂不使用 |
| `RECORD_DATE_SH` | 登记日期相关字段 | 暂不使用 |

### 利息与付息

| 字段 | 含义 | 使用建议 |
|---|---|---|
| `INTEREST_RATE_EXPLAIN` | 票面利率说明 | 可选展示，不建议放入日历 |
| `COUPON_IR` | 票面利率字段 | 暂不使用 |
| `PAY_INTEREST_DAY` | 每年付息日，如 `06-02` | 不是中签结果公布日期，不建议用于打新提醒 |
| `PAYDAYNEW` | 付息日辅助字段 | 暂不使用 |
| `CASHFLOW_DATE` | 现金流日期 | 暂不使用 |
| `IB_START_DATE` | 计息区间开始日 | 暂不使用 |
| `IB_END_DATE` | 计息区间结束日 | 暂不使用 |
| `PAR_VALUE` | 债券面值 | 可选展示 |

### 行情、估值与评级

| 字段 | 含义 | 使用建议 |
|---|---|---|
| `CURRENT_BOND_PRICE` | 当前债券价格 | 可选展示 |
| `CURRENT_BOND_PRICENEW` | 当前债券价格辅助字段 | 可选展示 |
| `CONVERT_STOCK_PRICE` | 正股价格 | 可选展示 |
| `CONVERT_STOCK_PRICEHQ` | 正股行情价格辅助字段 | 可选展示 |
| `PBV_RATIO` | 市净率 | 暂不用于日历 |
| `RATING` | 信用评级 | 可放入描述 |
| `PARTY_NAME` | 评级机构 | 可选展示 |

## 使用建议

内置东方财富日历示例适配器主要使用下面 3 个日期字段：

```text
PUBLIC_START_DATE -> 申购日
BOND_START_DATE   -> 中签结果公布
LISTING_DATE      -> 上市日
```

不要把 `PAY_INTEREST_DAY`、`VALUE_DATE`、`TRANSFER_START_DATE` 等字段误认为中签结果公布日期；这些字段属于付息、起息或转股生命周期，不是打新流程中的结果查询提醒。
