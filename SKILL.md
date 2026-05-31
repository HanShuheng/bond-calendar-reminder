---
name: bond-calendar-reminder
description: 可转债申购与上市提醒。支持按日期或日期范围查询申购、按债券名/转债代码/申购代码/配售代码查询上市日期，并为中签转债创建上市提醒。
license: MIT
compatibility: CowAgent 技能系统；Python 3.10+；需要可访问用户配置的可转债日历 JSON 数据源；自动提醒依赖 CowAgent scheduler，crontab 仅用于可选的每日自动触发。
metadata:
  author: xixilili
  version: 0.1.0
  language: zh-CN
  category: finance
  tags:
    - convertible-bond
    - reminder
    - scheduler
    - wechat
    - cowagent
  entrypoint: scripts/bond_calendar.py
  config_file: ~/cow/bond_reminders/config.json
  optional_config:
    - subscribe_reminder_schedule
    - listing_reminder_schedule
    - listing_tracking_max_days
  legacy_optional_config:
    - subscribe_reminder_times
  runtime_data_dir: ~/cow/bond_reminders
  scheduler_file: ~/cow/scheduler/tasks.json
  timezone: Asia/Shanghai
  data_source:
    type: user-configured-json-calendar
    required_config:
      - data_source.calendar_url
    optional_config:
      - data_source.base_url
      - data_source.detail_url_template
      - data_source.headers
  reminders:
    subscribe_schedule:
      - time: "10:00"
        label: "10:00 申购提醒"
      - time: "13:00"
        label: "13:00 申购提醒"
    subscribe_schedule_config: subscribe_reminder_schedule
    listing_times:
      - 上市前一天 12:00
      - 上市当天 08:30
      - 上市当天 13:00
    listing_times_config: listing_reminder_schedule
  requires:
    bins: ["python3"]
    env: []
    python_packages: ["requests"]
allowed-tools: terminal scheduler file
---

# bond-calendar-reminder

这是 CowAgent 的可转债日历技能。完整安装、数据源配置和维护说明见 `README.md`。

## 免责声明

本技能仅用于学习、研究和个人自动化实践，不构成投资建议、数据服务承诺或任何形式的金融服务。第三方数据源的可用性、准确性、及时性、授权和合规性由用户自行确认。

用户接入、访问、抓取、调用或使用第三方数据源，以及基于查询结果或提醒做出的任何操作，均由用户自行判断并承担全部责任；由此产生的法律、合规、交易、资金、账号或其他风险，均与本项目及作者无关。

## 能力边界

- 查询指定日期或日期范围内的可转债申购事项。
- 查询申购时支持按债券名、转债代码、申购代码、配售代码过滤。
- 用户只提供债券名或代码查询申购时，查询数据源可见范围内的匹配申购日。
- 查询可转债上市日期。
- 用户中签后，记录转债并追踪上市日期；查到上市日期并创建提醒后停止追踪。
- 创建 CowAgent scheduler 一次性提醒任务。
- 取消中签上市追踪或已创建的上市提醒。
- 查询当前有效的债券相关申购提醒、上市提醒和待追踪事项。
- 查询可转债 skill 的待执行任务看板，包括 scheduler、crontab、缓存和追踪状态。
- 已经过点的申购提醒不会补建，避免产生过去时间任务。
- 已经过点的上市提醒不会补建；所有上市提醒点都过期时记录为 `expired`。
- 数据源地址、详情页模板、请求头均由用户在配置文件中提供。
- 不接入券商账户，不判断用户是否真实中签，不提供投资建议。
- 不承担用户接入数据源、使用提醒或进行交易操作产生的任何法律、合规、资金或账号风险。

## 用户意图

### 查询申购

用户可能会说：

```text
今天有哪些可转债申购？
昨天有哪些可转债申购？
3月4号有哪些可转债申购？
今天后一个星期内有哪些可转债申购？
今天开始5天内有哪些可转债申购？
3月5号到3月10号有哪些可转债申购？
查一下 123270 的申购日期
查一下申购代码 370881 的申购日期
```

执行：

```bash
python {baseDir}/scripts/bond_calendar.py find-subscribe --date "<日期或日期范围>" --query "<债券名或代码>"
```

如果用户没有提供债券名或代码，省略 `--query`。
如果用户只提供债券名或代码，省略 `--date`，只传 `--query`。

如果用户表达为“从今天开始 N 天内”，优先使用：

```bash
python {baseDir}/scripts/bond_calendar.py find-subscribe --start 今天 --days N
```

日期范围按左右闭区间处理，包含开始日期和结束日期。
跨年范围自动顺延，例如 `12月30号-1月3号` 解释为下一年 `1月3号`。

### 今日申购提醒查询

用户只问“今天有没有可转债申购”且不要求创建提醒时，执行：

```bash
python {baseDir}/scripts/bond_calendar.py prepare-subscribe-today --no-create-tasks
python {baseDir}/scripts/bond_calendar.py send-prepared-subscribe --slot query
```

### 查询上市日期

用户可能会说：

```text
帮我查 123270 什么时候上市
阳谷转债什么时候上市？
申购代码 370881 什么时候上市？
配售代码 380881 什么时候上市？
```

执行：

```bash
python {baseDir}/scripts/bond_calendar.py find-listing --query "<债券名或代码>"
```

### 中签后创建上市提醒

用户可能会说：

```text
我中了 123270，上市提醒我
我中了申购代码 370881，上市提醒我
我中了配售代码 380881，上市提醒我
我中了阳谷转债，上市提醒我
```

执行：

```bash
python {baseDir}/scripts/bond_calendar.py track-listing --query "<债券名或代码>"
```

如果已经查到上市日期，脚本会创建：

- 上市前一天 `12:00`
- 上市当天 `08:30`
- 上市当天 `13:00`

以上是默认计划；实际提醒点以 `config.json` 的 `listing_reminder_schedule` 为准。

如果暂未查到上市日期，脚本会写入追踪列表，等待后续 `check-tracked-listings` 自动检查。
如果已经查到上市日期但提醒目标暂未识别，脚本会保留 `pending` 追踪并在后续检查时重试，不要回复用户“追踪已结束”。

### 取消上市提醒或追踪

用户可能会说：

```text
取消 123270 的上市提醒
取消阳谷转债的上市追踪
这个中签提醒不用了
```

执行：

```bash
python {baseDir}/scripts/bond_calendar.py cancel-listing --query "<债券名或代码>"
```

### 查询当前债券提醒事项

用户可能会说：

```text
当前债券相关有哪些提醒事项？
我现在有哪些可转债提醒？
债券相关的提醒列表给我看一下
```

执行：

```bash
python {baseDir}/scripts/bond_calendar.py list-reminders
```

默认只展示当前有效事项：未来 enabled 的申购提醒、未来 enabled 的上市提醒、以及 `pending` / `needs_confirmation` 的中签追踪需求。

### 查询待执行任务看板

用户可能会说：

```text
当前这个可转债插件接下来会做什么？
债券相关的定时任务有哪些？
crontab 和提醒配置是什么？
这个插件现在有哪些信息？
```

执行：

```bash
python {baseDir}/scripts/bond_calendar.py info
```

输出重点展示待执行事项：未来 enabled 的申购/上市 scheduler 任务、crontab 自动触发行、`pending` / `needs_confirmation` 上市追踪、当天申购缓存和简短配置摘要。不要要求用户理解或手动配置 `receiver`、`receiver_name`、`is_group`；它们只是 scheduler 兼容字段。

## 输出处理

| 输出前缀 | 含义 | 回复策略 |
| --- | --- | --- |
| `ALERT` | 有查询结果或提醒内容 | 整理脚本输出并回复用户 |
| `SCHEDULED` | 已创建提醒任务 | 告知用户提醒已安排 |
| `TRACKING` | 已加入追踪列表 | 告知用户暂未查到上市日，会继续追踪 |
| `NO_ALERT` | 当前无匹配事项 | 简短告知暂无事项 |
| `NOT_FOUND` | 未查到对应上市日期 | 建议用户改用更准确代码，或加入追踪 |
| `MULTIPLE_MATCHES` | 匹配到多个候选 | 请用户提供转债代码后再查 |
| `CANCELED` | 已取消上市提醒或追踪 | 告知用户已取消 |
| `EXPIRED` | 已查到上市日但提醒点均已过期 | 告知用户不会继续追踪 |
| `ERROR` | 数据源或运行异常 | 告知用户稍后再试，不要声称已创建提醒 |
| `INFO` | 待执行任务看板 | 保留看板结构，简短说明这是当前可转债 Skill 的待执行任务 |

## 微信回复模板

回复风格应简洁实用：直接告诉用户结果、提醒状态和下一步，不做长篇解释。脚本输出中的空字段不要硬填“未知”，字段缺失时直接省略对应行。

模板变量：

- `{date}`：日期
- `{start_date}` / `{end_date}`：日期范围
- `{date_or_range}`：单日或日期范围展示文本
- `{query}`：用户输入的债券名、转债代码、申购代码或配售代码
- `{bond_name}`：债券名
- `{bond_code}`：转债代码
- `{subscribe_code}`：申购代码
- `{allotment_code}`：配售代码
- `{listing_date}`：上市日期
- `{task_count}`：任务数量
- `{reason}`：失败或无结果原因

### 申购查询有结果

适用命令：`find-subscribe`、`prepare-subscribe-today --no-create-tasks`、`send-prepared-subscribe --slot query`。

```text
查到了，{date_or_range} 有以下可转债申购：

{subscribe_items}

数据来自当前配置的数据源，请以交易软件最终展示为准。
```

单条事项格式：

```text
- {bond_name}
  转债代码：{bond_code}
  申购代码：{subscribe_code}
  配售代码：{allotment_code}
  详情：{url}
```

### 申购查询无结果

适用输出：`NO_ALERT`。

```text
{date_or_range} 暂无匹配的可转债申购事项。
```

如果用户带了债券名或代码：

```text
暂未查到 {query} 在 {date_or_range} 的申购事项。
可以换用转债代码、申购代码或配售代码再查一次。
```

### 申购提醒已创建

适用命令：`prepare-subscribe-today`。

```text
今日有可转债申购，已为你安排提醒。

提醒计划：
{subscribe_reminder_items}

{subscribe_items}
```

如果部分提醒时间已经过期：

```text
今日有可转债申购，已安排后续未过期的提醒。

已跳过已经过去的提醒时间。
```

### 查询上市日期有结果

适用命令：`find-listing --query <query>`。

```text
查到了，{bond_name} 的上市日期是 {listing_date}。

转债代码：{bond_code}
申购代码：{subscribe_code}
配售代码：{allotment_code}
详情：{url}
```

### 查询上市日期无结果

适用输出：`NOT_FOUND`。

```text
暂未查到 {query} 的上市日期。

如果你已经中签，可以让我先记录下来：
“我中了 {query}，上市提醒我”
```

### 中签追踪已创建

适用输出：`TRACKING`。也适用于已经查到上市日期但提醒任务暂时创建失败、脚本保留追踪等待重试的情况。

```text
已记录 {query}。

现在还没查到上市日期，我会在每日检查时继续追踪；查到后会自动创建上市提醒。
```

如果脚本已查到上市日期但提醒任务创建失败：

```text
已查到 {bond_name} 的上市日期是 {listing_date}，但这次提醒任务还没创建成功。

我会保留追踪，后续检查时继续重试。你可以先和机器人发一条消息，再重新查看提醒目标状态。
```

### 上市提醒已创建

适用输出：`SCHEDULED`。

```text
已为 {bond_name} 创建上市提醒。

上市日期：{listing_date}
提醒计划：
{listing_reminder_items}
```

提醒项格式：

```text
- {run_at}：{label}
```

如果有跳过的过期提醒：

```text
其中 {skipped_count} 个提醒时间已经过去，已自动跳过。
```

### 上市日期已过期

适用输出：`EXPIRED`。

```text
查到了 {bond_name} 的上市日期是 {listing_date}，但配置的提醒时间都已经过去。

这条追踪已结束，不会继续每日检查。
```

### 匹配到多个候选

适用输出：`MULTIPLE_MATCHES`。

```text
找到了多个候选，暂时不能确定是哪一只。

请用更准确的转债代码再试，例如：
“查询 123270 上市日期”
或
“我中了 123270，上市提醒我”

候选：
{candidate_items}
```

候选项格式：

```text
- {date} {bond_name} {bond_code}
```

### 取消成功

适用输出：`CANCELED`。

```text
已取消 {query} 的上市提醒/追踪。
```

如果禁用了 scheduler 任务：

```text
同时已禁用 {task_count} 个待执行提醒任务。
```

### 当前提醒列表

适用命令：`list-reminders`。

有结果模板：

```text
当前债券相关提醒如下：

申购提醒：
{subscribe_task_items}

上市提醒：
{listing_task_items}

待追踪上市：
{tracking_items}
```

无结果模板：

```text
当前暂无债券相关提醒事项。
```

### 待执行任务看板

适用命令：`info`。

```text
这是当前可转债 Skill 的待执行任务看板：

{info_output}
```

如果提醒目标未识别，追加：

```text
提醒目标还没有识别到，自动提醒任务暂时无法创建。你可以先和机器人发一条消息，再重新查看。
```

### 数据源或运行错误

适用输出：`ERROR`。

```text
这次没有处理成功：{reason}

我没有创建新的提醒任务。可以稍后再试，或检查数据源配置和日志。
```

### 命令静默或无须打扰

适用场景：

- 每日 `07:00` 自动查申购，今日无申购。
- 每日追踪上市，没有查到新上市日期。
- crontab 正常执行但没有新事项。

模板策略：

```text
不主动发送微信消息。
```

只在用户主动查询时回复 `NO_ALERT` 模板。

## 常用命令

```bash
python scripts/bond_calendar.py find-subscribe --date 今天
python scripts/bond_calendar.py find-subscribe --date "3月5号-3月10号"
python scripts/bond_calendar.py find-subscribe --start 今天 --days 5
python scripts/bond_calendar.py find-subscribe --date 今天 --query 123270
python scripts/bond_calendar.py find-subscribe --query 123270
python scripts/bond_calendar.py find-listing --query 123270
python scripts/bond_calendar.py track-listing --query 123270
python scripts/bond_calendar.py cancel-listing --query 123270
python scripts/bond_calendar.py list-reminders
python scripts/bond_calendar.py info
python scripts/bond_calendar.py prepare-subscribe-today
python scripts/bond_calendar.py check-tracked-listings
```
