# bond-calendar-reminder

CowAgent 可转债申购与上市提醒技能。

本技能从用户配置的可转债日历数据源读取数据，支持查询申购日、查询上市日、记录中签转债，并通过 CowAgent scheduler 创建一次性提醒任务。

## 免责声明

本项目仅用于学习、研究和个人自动化实践，不构成投资建议、数据服务承诺或任何形式的金融服务。项目不保证第三方数据源的可用性、准确性、及时性或合规性。

用户接入、访问、抓取、调用或使用第三方数据源，以及基于查询结果或提醒做出的任何操作，均由用户自行判断并承担全部责任；由此产生的法律、合规、交易、资金、账号或其他风险，均与本项目及作者无关。

## 快速开始

### 1. 安装技能

在 CowAgent 服务器上执行：

```bash
cow skill install HanShuheng/bond-calendar-reminder
```

如果 CLI 无法识别 GitHub shorthand，也可以使用仓库地址：

```bash
cow skill install https://github.com/HanShuheng/bond-calendar-reminder
```

手动安装方式：

```bash
mkdir -p ~/cow/skills
git clone https://github.com/HanShuheng/bond-calendar-reminder.git ~/cow/skills/bond-calendar-reminder
```

### 2. 安装依赖

```bash
cd ~/cow/skills/bond-calendar-reminder
python3 -m pip install -r requirements.txt
```

如果 CowAgent 使用虚拟环境，建议改用 CowAgent 的 Python：

```bash
~/CowAgent/.venv/bin/python -m pip install -r ~/cow/skills/bond-calendar-reminder/requirements.txt
```

### 3. 创建配置

```bash
mkdir -p ~/cow/bond_reminders
cp ~/cow/skills/bond-calendar-reminder/examples/config.example.json ~/cow/bond_reminders/config.json
```

如果你直接使用集思录可转债日历接口，可以复制内置的集思录模板：

```bash
mkdir -p ~/cow/bond_reminders
cp ~/cow/skills/bond-calendar-reminder/examples/config.jisilu.example.json ~/cow/bond_reminders/config.json
```

然后编辑：

```bash
nano ~/cow/bond_reminders/config.json
```

如果使用通用模板，至少需要把 `data_source.calendar_url` 改成你自己的可转债日历 JSON 接口。`base_url`、`detail_url_template`、`headers` 按你的数据源需要填写。使用集思录模板时，默认字段已经填好，可以先直接验证。

### 4. 验证命令

```bash
cd ~/cow/skills/bond-calendar-reminder
python3 scripts/bond_calendar.py --help
python3 scripts/bond_calendar.py info
python3 scripts/bond_calendar.py find-subscribe --date 今天
```

如果 `info` 显示“提醒目标：未识别”，先在微信里和 CowAgent 机器人发一条消息，再重新执行：

```bash
python3 scripts/bond_calendar.py info
```

### 5. 配置自动化

用 crontab 每天自动检查申购和中签上市日期：

```bash
crontab -e
```

示例：

```cron
0 7 * * * /usr/bin/python3 ~/cow/skills/bond-calendar-reminder/scripts/bond_calendar.py prepare-subscribe-today >> ~/cow/bond_reminders/bond_calendar.log 2>&1
5 7 * * * /usr/bin/python3 ~/cow/skills/bond-calendar-reminder/scripts/bond_calendar.py check-tracked-listings >> ~/cow/bond_reminders/bond_calendar.log 2>&1
```

如果 CowAgent 使用虚拟环境，请把 `/usr/bin/python3` 替换为 CowAgent 的 Python 路径。

## 元数据

| 字段 | 值 |
| --- | --- |
| 名称 | `bond-calendar-reminder` |
| 作者 | `xixilili` |
| 版本 | `0.1.0` |
| 许可证 | `MIT` |
| 语言 | `zh-CN` |
| 分类 | `finance` |
| 入口脚本 | `scripts/bond_calendar.py` |
| 配置文件 | `~/cow/bond_reminders/config.json` |
| 运行数据目录 | `~/cow/bond_reminders` |
| 默认申购提醒计划 | `10:00 申购提醒`、`13:00 申购提醒` |
| 默认上市提醒计划 | 上市前一天 `12:00`、上市当天 `08:30`、上市当天 `13:00` |

## 功能

- 按指定日期查询可转债申购。
- 按日期范围查询可转债申购，范围为左右闭区间。
- 查询申购时可按债券名、转债代码、申购代码或配售代码过滤。
- 按债券名、转债代码、申购代码或配售代码查询上市日期。
- 记录中签转债；暂未查到上市日期时自动追踪，查到后创建提醒并停止追踪。
- 可取消中签上市追踪或已创建的上市提醒。
- 可查看当前有效的申购提醒、上市提醒和待追踪上市事项。
- 可查看插件配置、crontab、scheduler、缓存和追踪状态。
- 自动创建申购提醒和上市提醒。
- 申购提醒计划可在配置文件中自定义，默认 `10:00` 和 `13:00`。
- 上市提醒计划可在配置文件中自定义，支持任意条数。
- 数据源地址、详情页模板和请求头由用户配置，不写死在脚本中。

## 非目标

- 不接入券商账户。
- 不判断用户是否真实中签。
- 不提供投资建议。
- 不保证第三方日历数据实时、完整或准确。
- 不承担用户接入数据源、使用提醒或进行交易操作产生的任何法律、合规、资金或账号风险。

## 目录结构

```text
bond-calendar-reminder/
├── SKILL.md
├── README.md
├── requirements.txt
├── examples/
│   ├── config.example.json
│   └── config.jisilu.example.json
├── scripts/
│   └── bond_calendar.py
└── tests/
    └── test_bond_calendar.py
```

运行时数据默认写入 CowAgent workspace：

```text
~/cow/bond_reminders/
├── config.json
├── daily_subscribe.json
├── watchlist.json
└── bond_calendar.log
```

CowAgent scheduler 任务默认写入：

```text
~/cow/scheduler/tasks.json
```

可以通过 `COW_WORKSPACE` 修改 workspace：

```bash
export COW_WORKSPACE=/path/to/cow
```

## 安装

复制技能到 CowAgent workspace：

```bash
mkdir -p ~/cow/skills
cp -R bond-calendar-reminder ~/cow/skills/
```

安装依赖：

```bash
cd ~/cow/skills/bond-calendar-reminder
python3 -m pip install -r requirements.txt
```

如果 CowAgent 使用虚拟环境，建议使用 CowAgent 的 Python：

```bash
~/CowAgent/.venv/bin/python -m pip install -r ~/cow/skills/bond-calendar-reminder/requirements.txt
```

确认脚本可运行：

```bash
python3 scripts/bond_calendar.py --help
```

## 配置

使用前需要配置数据源。创建提醒任务前，脚本会尽量从 CowAgent 微信凭证中自动识别提醒目标。配置文件路径：

```text
~/cow/bond_reminders/config.json
```

可以从示例复制：

```bash
mkdir -p ~/cow/bond_reminders
cp examples/config.example.json ~/cow/bond_reminders/config.json
```

示例文件：

- `examples/config.example.json`：通用模板，适合接入任意可转债日历 JSON 数据源。
- `examples/config.jisilu.example.json`：集思录模板，已填好集思录可转债日历接口和 Referer。

示例：

```json
{
  "data_source": {
    "calendar_url": "https://example.com/path/to/convert-bond-calendar.json",
    "base_url": "https://example.com",
    "detail_url_template": "https://example.com/convert-bond/{code}",
    "headers": {
      "Referer": "https://example.com/calendar"
    }
  },
  "subscribe_reminder_schedule": [
    {"time": "10:00", "label": "10:00 申购提醒"},
    {"time": "13:00", "label": "13:00 申购提醒"}
  ],
  "listing_reminder_schedule": [
    {"days_offset": -1, "time": "12:00", "label": "上市前一天 12:00"},
    {"days_offset": 0, "time": "08:30", "label": "上市当天 08:30，开盘前 1 小时"},
    {"days_offset": 0, "time": "13:00", "label": "上市当天 13:00"}
  ],
  "listing_tracking_max_days": 180
}
```

字段说明：

### data_source

| 字段 | 说明 |
| --- | --- |
| `calendar_url` | 必填。可转债日历 JSON 接口地址 |
| `base_url` | 可选。用于把数据源返回的相对详情页地址拼成完整地址 |
| `detail_url_template` | 可选。当事件没有详情页地址时，用该模板生成详情页地址，支持 `{code}` |
| `headers` | 可选。请求数据源时附加的 HTTP headers，例如 `Referer`、`Authorization` |

脚本期望 `calendar_url` 返回 JSON 数组。每个事件建议包含以下字段：

| 字段 | 说明 |
| --- | --- |
| `title` | 事件标题，应能区分 `申购日` 或 `上市日` |
| `start` | 事件日期，建议格式为 `YYYY-MM-DD` 或以该格式开头 |
| `code` | 可选。转债代码 |
| `description` | 可选。用于提取转债代码、申购代码、配售代码 |
| `url` | 可选。详情页 URL，可以是绝对地址或相对地址 |

### 提醒配置

| 字段 | 说明 |
| --- | --- |
| `subscribe_reminder_schedule` | 可选。当天申购提醒计划，每项包含 `time`、`label`，默认 `10:00` 和 `13:00` |
| `listing_reminder_schedule` | 可选。上市提醒计划，每项包含 `days_offset`、`time`、`label` |
| `listing_tracking_max_days` | 可选。暂未公布上市日时的最长追踪天数，默认 `180` |

`subscribe_reminder_schedule` 示例：

```json
[
  {"time": "10:00", "label": "10:00 申购提醒"},
  {"time": "13:00", "label": "13:00 申购提醒"}
]
```

`time` 使用 `HH:MM` 格式，`label` 会显示在 scheduler 任务名和提醒内容中。旧版 `subscribe_reminder_times` 仍兼容，但新配置建议统一使用 `subscribe_reminder_schedule`。

`listing_reminder_schedule` 示例：

```json
[
  {"days_offset": -1, "time": "12:00", "label": "上市前一天 12:00"},
  {"days_offset": 0, "time": "08:30", "label": "上市当天 08:30，开盘前 1 小时"},
  {"days_offset": 0, "time": "13:00", "label": "上市当天 13:00"}
]
```

`days_offset` 以上市日为基准，`-1` 表示上市前一天，`0` 表示上市当天，`1` 表示上市后一天。脚本不会创建已经过去的提醒；如果所有提醒点都已过期，该追踪记录会标记为 `expired`。

定时提醒的发送目标默认由脚本从 CowAgent 微信凭证 `~/.weixin_cow_credentials.json` 中自动识别。`receiver`、`receiver_name`、`is_group`、`channel_type`、`notify_session_id` 不是债券业务配置，普通用户不需要手动填写；旧配置中如果已经存在这些字段，脚本仍会兼容使用。

也可以用环境变量临时覆盖日历接口地址：

```bash
export BOND_CALENDAR_URL="https://example.com/path/to/convert-bond-calendar.json"
```

## 命令

### 查询申购

```bash
python3 scripts/bond_calendar.py find-subscribe --date 今天
python3 scripts/bond_calendar.py find-subscribe --date 昨天
python3 scripts/bond_calendar.py find-subscribe --date 3月4号
python3 scripts/bond_calendar.py find-subscribe --date "3月5号-3月10号"
python3 scripts/bond_calendar.py find-subscribe --date 今天后一个星期内
python3 scripts/bond_calendar.py find-subscribe --date 今天开始5天内
python3 scripts/bond_calendar.py find-subscribe --date "12月30号-1月3号"
python3 scripts/bond_calendar.py find-subscribe --start 今天 --days 5
python3 scripts/bond_calendar.py find-subscribe --start 3月5号 --end 3月10号
```

日期范围为左右闭区间。例如 `3月5号-3月10号` 会包含 `3月5号` 和 `3月10号`。
如果结束日期早于开始日期，例如 `12月30号-1月3号`，会自动解释为跨到下一年。

叠加债券过滤：

```bash
python3 scripts/bond_calendar.py find-subscribe --date 今天 --query 阳谷转债
python3 scripts/bond_calendar.py find-subscribe --date 今天 --query 123270
python3 scripts/bond_calendar.py find-subscribe --date 今天 --query 370881
python3 scripts/bond_calendar.py find-subscribe --date 今天 --query 380881
```

只按债券名或代码查询申购日期时，可以省略日期参数，脚本会查询数据源可见范围内的匹配申购事件：

```bash
python3 scripts/bond_calendar.py find-subscribe --query 123270
python3 scripts/bond_calendar.py find-subscribe --query 阳谷转债
```

### 准备当天申购提醒

```bash
python3 scripts/bond_calendar.py prepare-subscribe-today
```

这个命令会查询当天申购事项并写入 `daily_subscribe.json`。如果当天有申购事项，会按 `subscribe_reminder_schedule` 创建一次性提醒任务；未配置时使用默认 `10:00` 和 `13:00`。
如果运行时某个提醒时间已经过去，脚本不会再创建该过去时间的提醒。

只刷新缓存、不创建提醒：

```bash
python3 scripts/bond_calendar.py prepare-subscribe-today --no-create-tasks
```

### 输出已缓存的申购提醒

```bash
python3 scripts/bond_calendar.py send-prepared-subscribe --slot 10:00
python3 scripts/bond_calendar.py send-prepared-subscribe --slot 13:00
python3 scripts/bond_calendar.py send-prepared-subscribe --slot query
```

### 查询上市日期

```bash
python3 scripts/bond_calendar.py find-listing --query 123270
python3 scripts/bond_calendar.py find-listing --query 370881
python3 scripts/bond_calendar.py find-listing --query 380881
python3 scripts/bond_calendar.py find-listing --query 阳谷转债
```

### 记录中签并追踪上市日

```bash
python3 scripts/bond_calendar.py track-listing --query 123270
```

如果已查到上市日期，脚本会创建三次提醒：

- 上市前一天 `12:00`
- 上市当天 `08:30`
- 上市当天 `13:00`

这三次是默认计划；实际以 `config.json` 中的 `listing_reminder_schedule` 为准，可以增删任意提醒点。

如果暂未查到上市日期，脚本会写入 `watchlist.json`，等待后续检查。
如果已经查到上市日期但提醒目标暂未识别，脚本会保留追踪，后续检查时继续重试，不会把记录标记为 `expired`。

### 取消上市提醒或追踪

```bash
python3 scripts/bond_calendar.py cancel-listing --query 123270
python3 scripts/bond_calendar.py cancel-listing --query 阳谷转债
```

该命令可以取消 `pending`、`needs_confirmation`、`scheduled` 状态的记录。取消 `scheduled` 记录时，会同时把对应 scheduler 任务设为 disabled。

### 查询当前债券相关提醒事项

```bash
python3 scripts/bond_calendar.py list-reminders
```

默认只展示当前有效事项：

- 未来 enabled 的 `bond-subscribe-*` 申购提醒。
- 未来 enabled 的 `bond-listing-*` 上市提醒。
- `watchlist.json` 中 `pending` / `needs_confirmation` 的中签追踪需求。

不会展示 disabled、expired、canceled 或已经过去的任务。

### 查询待执行任务看板

```bash
python3 scripts/bond_calendar.py info
```

`info` 默认展示这个 skill 接下来会自动做什么，包括：

- 未来 enabled 的 `bond-subscribe-*` 申购提醒任务。
- 未来 enabled 的 `bond-listing-*` 上市提醒任务。
- 当前 crontab 中未注释且包含 `bond_calendar.py` 的自动触发任务。
- `watchlist.json` 中 `pending` / `needs_confirmation` 的中签上市追踪。
- `daily_subscribe.json` 的日期、状态、生成时间、事项数。
- 简短配置摘要：数据源、提醒目标识别状态、申购提醒计划、上市提醒计划数量、最长追踪天数和关键文件路径。

`info` 不展示真实 `receiver`、session id、token 或 context token。如果提醒目标无法自动识别，会提示“自动提醒任务无法创建”。

## 微信回复模板参考

CowAgent 调用本技能后，应把脚本输出整理成简洁实用的微信回复：直接告诉用户结果、提醒状态和下一步。字段缺失时直接省略对应行，不输出空值或“未知”。

常用模板：

| 场景 | 回复口径 |
| --- | --- |
| 申购查询有结果 | `查到了，{date_or_range} 有以下可转债申购：`，随后列出债券名、转债代码、申购代码、配售代码和详情链接 |
| 申购查询无结果 | `{date_or_range} 暂无匹配的可转债申购事项。` |
| 上市日期有结果 | `查到了，{bond_name} 的上市日期是 {listing_date}。`，随后列出可用代码和详情链接 |
| 上市日期无结果 | `暂未查到 {query} 的上市日期。`，提示用户可说“我中了 {query}，上市提醒我” |
| 中签追踪已创建 | `已记录 {query}。现在还没查到上市日期，我会继续追踪。` |
| 提醒创建暂时失败 | 已查到上市日期但提醒任务没创建成功时，告知用户会保留追踪并后续重试 |
| 上市提醒已创建 | `已为 {bond_name} 创建上市提醒。`，随后列出上市日期和提醒计划 |
| 匹配到多个候选 | 提示用户改用更准确的转债代码，并列出候选 |
| 取消成功 | `已取消 {query} 的上市提醒/追踪。` |
| 当前提醒列表 | 分组展示申购提醒、上市提醒、待追踪上市 |
| `info` 看板 | 保留脚本看板结构，前置一句 `这是当前可转债 Skill 的待执行任务看板：` |
| 错误 | `这次没有处理成功：{reason}`，并说明没有创建新的提醒任务 |

自动任务无事项时保持静默：每日申购检查无结果、每日上市追踪无新日期、crontab 正常执行但没有新事项时，不主动发送微信消息。只有用户主动查询时才回复“暂无事项”。

完整模板见 `SKILL.md` 的“微信回复模板”章节。

### 检查追踪列表

```bash
python3 scripts/bond_calendar.py check-tracked-listings
```

该命令只检查 `pending` 和 `needs_confirmation` 状态的记录。记录变成 `scheduled` 后，不会继续每日追踪。

## 自动化

推荐用 `crontab` 定时触发：

```bash
crontab -e
```

示例：

```cron
0 7 * * * /path/to/CowAgent/.venv/bin/python /path/to/cow/skills/bond-calendar-reminder/scripts/bond_calendar.py prepare-subscribe-today >> /path/to/cow/bond_reminders/bond_calendar.log 2>&1
5 7 * * * /path/to/CowAgent/.venv/bin/python /path/to/cow/skills/bond-calendar-reminder/scripts/bond_calendar.py check-tracked-listings >> /path/to/cow/bond_reminders/bond_calendar.log 2>&1
```

| 时间 | 命令 | 说明 |
| --- | --- | --- |
| 每天 `07:00` | `prepare-subscribe-today` | 查询当天申购事项，有申购时按 `subscribe_reminder_schedule` 创建提醒 |
| 每天 `07:05` | `check-tracked-listings` | 检查已记录的中签转债，查到上市日期后创建上市提醒 |

## 数据文件

### daily_subscribe.json

```json
{
  "date": "2026-06-03",
  "generated_at": "2026-06-03T07:00:00+08:00",
  "status": "ok",
  "events": []
}
```

### watchlist.json

```json
{
  "version": 1,
  "updated_at": "2026-06-03T07:05:00+08:00",
  "items": {
    "123270": {
      "query": "123270",
      "status": "pending",
      "created_at": "2026-06-01T12:00:00+08:00",
      "updated_at": "2026-06-03T07:05:00+08:00"
    }
  }
}
```

状态说明：

| 状态 | 说明 |
| --- | --- |
| `pending` | 已记录，等待上市日期公布 |
| `needs_confirmation` | 匹配到多个候选，需要用户提供更准确代码 |
| `scheduled` | 已查到上市日期，并创建 scheduler 提醒任务 |
| `expired` | 已过最长追踪期，或查到上市日时所有提醒点都已过期 |
| `canceled` | 用户主动取消追踪或提醒 |

## 测试

运行单元测试：

```bash
python3 -m unittest discover -s tests
```

检查脚本语法：

```bash
python3 -m py_compile scripts/bond_calendar.py
```

## 排障

查看 crontab：

```bash
crontab -l | grep bond_calendar.py
```

查看日志：

```bash
tail -n 100 ~/cow/bond_reminders/bond_calendar.log
```

查看 scheduler 任务：

```bash
python3 -m json.tool ~/cow/scheduler/tasks.json
```

常见问题：

| 问题 | 可能原因 | 处理方式 |
| --- | --- | --- |
| 提醒没有发送 | 提醒目标无法自动识别，或 CowAgent 微信凭证中没有可用 context token | 先和机器人产生一次对话，再运行 `python3 scripts/bond_calendar.py info` 查看提醒目标状态 |
| crontab 没执行 | Python 路径或脚本路径不正确 | 使用绝对路径，并查看 `bond_calendar.log` |
| 查询不到上市日期 | 数据源尚未公布上市日，或查询词不够准确 | 使用转债代码重新查询，或先加入追踪 |
| 数据源报错 | 网络异常、接口临时不可用或返回格式变化 | 稍后重试，并保留日志用于排查 |
| 提示缺少数据源配置 | `config.json` 未设置 `data_source.calendar_url` | 复制 `examples/config.example.json` 并填写自己的数据源地址 |

## 开源注意事项

- 不要提交个人的 `config.json`、`watchlist.json`、`daily_subscribe.json`、日志、密钥或 token。
- 不要把个人服务器路径或特定商业站点地址写死进 Python 代码。
- 如果扩展多用户或多账号，建议把接收者配置抽象为独立 profile，而不是覆盖单一 `config.json`。
