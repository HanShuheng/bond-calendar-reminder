# bond-calendar-reminder

CowAgent 专属可转债申购与上市提醒 Skill。

本项目面向 [CowAgent](https://cowagent.ai/) 的 Skill 运行方式设计。CowAgent 读取 `SKILL.md` 识别用户意图后，调用 `scripts/bond_calendar.py` 查询可转债申购、上市日期和中签追踪状态，并通过 CowAgent scheduler 创建一次性提醒任务。

> 本项目仅用于学习、研究和个人自动化实践，不构成投资建议、数据服务承诺或任何形式的金融服务。

## 功能特性

- 查询指定日期或日期范围内的可转债申购。
- 支持按债券名、转债代码、申购代码、配售代码过滤申购事项。
- 查询可转债上市日期。
- 记录中签转债；暂未查到上市日时自动追踪，查到后创建上市提醒。
- 创建 CowAgent scheduler 一次性提醒任务。
- 查看、取消当前债券相关提醒和追踪事项。
- 支持自定义申购提醒时间和上市提醒时间。
- 数据源地址、详情页模板和请求头由用户配置，不在代码中写死。
- 运行数据保存在 CowAgent workspace，便于备份和排障。

## 适用场景

适合：

- 在微信里问 CowAgent：“今天有哪些可转债申购？”
- 在微信里问 CowAgent：“123270 什么时候上市？”
- 中签后告诉 CowAgent：“我中了 123270，上市提醒我。”
- 用 crontab 每天自动检查当天申购和待追踪上市事项。

不适合：

- 作为独立金融数据服务对外提供接口。
- 接入券商账户、自动交易或判断用户是否真实中签。
- 绕过第三方数据源的访问规则、授权或风控限制。

## 项目状态

当前版本为 `0.1.0`，属于早期可用版本。接口、配置字段和 CowAgent Skill 约定仍可能调整。建议个人使用前先在测试环境验证配置和提醒链路。

## 工作原理

```text
用户微信消息
    ↓
CowAgent 读取 SKILL.md 并匹配意图
    ↓
CowAgent 调用 scripts/bond_calendar.py
    ↓
脚本读取可转债日历 JSON 数据源
    ↓
脚本查询结果、写入追踪状态或创建 scheduler 任务
    ↓
CowAgent 整理脚本输出并回复用户 / 执行后续提醒
```

仓库结构：

```text
bond-calendar-reminder/
├── SKILL.md                  # CowAgent Skill 元数据、意图映射和回复模板
├── README.md                 # 项目说明
├── LICENSE                   # MIT License
├── requirements.txt          # Python 依赖
├── examples/
│   ├── config.example.json
│   └── config.jisilu.example.json
├── scripts/
│   └── bond_calendar.py      # 命令行入口
└── tests/
    └── test_bond_calendar.py
```

运行时默认写入：

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

可通过环境变量修改 CowAgent workspace：

```bash
export COW_WORKSPACE=/path/to/cow
```

## 环境要求

- CowAgent 技能系统。
- Python 3.10 或更新版本。
- 可访问用户自行配置的可转债日历 JSON 数据源。
- 自动提醒依赖 CowAgent scheduler。
- 每日自动检查建议使用 crontab 或其他定时任务系统触发。

Python 依赖见 `requirements.txt`。

## 安装

### 方式一：通过 CowAgent CLI 安装

在 CowAgent 服务器上执行：

```bash
cow skill install HanShuheng/bond-calendar-reminder
```

如果 CLI 不支持 GitHub shorthand，可以使用仓库地址：

```bash
cow skill install https://github.com/HanShuheng/bond-calendar-reminder
```

### 方式二：手动安装

```bash
mkdir -p ~/cow/skills
git clone https://github.com/HanShuheng/bond-calendar-reminder.git ~/cow/skills/bond-calendar-reminder
```

安装依赖：

```bash
cd ~/cow/skills/bond-calendar-reminder
python3 -m pip install -r requirements.txt
```

如果 CowAgent 使用自己的虚拟环境，建议使用 CowAgent 的 Python：

```bash
~/CowAgent/.venv/bin/python -m pip install -r ~/cow/skills/bond-calendar-reminder/requirements.txt
```

## 配置

配置文件默认路径：

```text
~/cow/bond_reminders/config.json
```

创建配置目录：

```bash
mkdir -p ~/cow/bond_reminders
```

使用通用模板：

```bash
cp ~/cow/skills/bond-calendar-reminder/examples/config.example.json ~/cow/bond_reminders/config.json
```

如果你确认自己可以合规访问集思录可转债日历接口，也可以使用内置模板：

```bash
cp ~/cow/skills/bond-calendar-reminder/examples/config.jisilu.example.json ~/cow/bond_reminders/config.json
```

编辑配置：

```bash
nano ~/cow/bond_reminders/config.json
```

最小配置示例：

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

配置字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `data_source.calendar_url` | 是 | 可转债日历 JSON 接口地址 |
| `data_source.base_url` | 否 | 用于把相对详情页地址拼成完整 URL |
| `data_source.detail_url_template` | 否 | 详情页模板，支持 `{code}` |
| `data_source.headers` | 否 | 请求数据源时附加的 HTTP headers |
| `subscribe_reminder_schedule` | 否 | 当天申购提醒计划，每项包含 `time` 和 `label` |
| `listing_reminder_schedule` | 否 | 上市提醒计划，每项包含 `days_offset`、`time` 和 `label` |
| `listing_tracking_max_days` | 否 | 暂未公布上市日时的最长追踪天数，默认 `180` |

也可以用环境变量临时覆盖日历接口：

```bash
export BOND_CALENDAR_URL="https://example.com/path/to/convert-bond-calendar.json"
```

## 数据源格式

脚本期望 `calendar_url` 返回 JSON 数组。每个事件建议包含：

| 字段 | 说明 |
| --- | --- |
| `title` | 事件标题，应能区分 `申购日` 或 `上市日` |
| `start` | 事件日期，建议格式为 `YYYY-MM-DD` 或以该格式开头 |
| `code` | 可选。转债代码 |
| `description` | 可选。用于提取转债代码、申购代码、配售代码 |
| `url` | 可选。详情页 URL，可以是绝对地址或相对地址 |

不同数据源字段可能有差异。若数据源返回格式变化，脚本可能需要适配。

## 快速验证

```bash
cd ~/cow/skills/bond-calendar-reminder
python3 scripts/bond_calendar.py --help
python3 scripts/bond_calendar.py info
python3 scripts/bond_calendar.py find-subscribe --date 今天
```

如果 `info` 显示提醒目标未识别，先在微信里和 CowAgent 机器人产生一次对话，再重新执行：

```bash
python3 scripts/bond_calendar.py info
```

## 常用命令

查询申购：

```bash
python3 scripts/bond_calendar.py find-subscribe --date 今天
python3 scripts/bond_calendar.py find-subscribe --date "3月5号-3月10号"
python3 scripts/bond_calendar.py find-subscribe --start 今天 --days 5
python3 scripts/bond_calendar.py find-subscribe --query 123270
python3 scripts/bond_calendar.py find-subscribe --date 今天 --query 阳谷转债
```

准备当天申购提醒：

```bash
python3 scripts/bond_calendar.py prepare-subscribe-today
```

只刷新缓存，不创建提醒：

```bash
python3 scripts/bond_calendar.py prepare-subscribe-today --no-create-tasks
```

输出已缓存的申购提醒：

```bash
python3 scripts/bond_calendar.py send-prepared-subscribe --slot 10:00
python3 scripts/bond_calendar.py send-prepared-subscribe --slot 13:00
python3 scripts/bond_calendar.py send-prepared-subscribe --slot query
```

查询上市日期：

```bash
python3 scripts/bond_calendar.py find-listing --query 123270
python3 scripts/bond_calendar.py find-listing --query 阳谷转债
```

记录中签并追踪上市日：

```bash
python3 scripts/bond_calendar.py track-listing --query 123270
```

取消上市提醒或追踪：

```bash
python3 scripts/bond_calendar.py cancel-listing --query 123270
```

查看当前债券提醒：

```bash
python3 scripts/bond_calendar.py list-reminders
```

查看 Skill 状态看板：

```bash
python3 scripts/bond_calendar.py info
```

检查追踪列表：

```bash
python3 scripts/bond_calendar.py check-tracked-listings
```

## 自动化

推荐用 crontab 定时触发每日检查：

```bash
crontab -e
```

示例：

```cron
0 7 * * * /usr/bin/python3 ~/cow/skills/bond-calendar-reminder/scripts/bond_calendar.py prepare-subscribe-today >> ~/cow/bond_reminders/bond_calendar.log 2>&1
5 7 * * * /usr/bin/python3 ~/cow/skills/bond-calendar-reminder/scripts/bond_calendar.py check-tracked-listings >> ~/cow/bond_reminders/bond_calendar.log 2>&1
```

如果 CowAgent 使用虚拟环境，请把 `/usr/bin/python3` 替换为 CowAgent 的 Python 路径。

| 时间 | 命令 | 说明 |
| --- | --- | --- |
| 每天 `07:00` | `prepare-subscribe-today` | 查询当天申购事项，有申购时创建提醒 |
| 每天 `07:05` | `check-tracked-listings` | 检查已记录的中签转债，查到上市日后创建提醒 |

自动任务无事项时应保持静默：每日申购检查无结果、每日上市追踪无新日期时，不主动发送微信消息。只有用户主动查询时才回复“暂无事项”。

## CowAgent 回复约定

脚本输出使用固定前缀，CowAgent 可按前缀决定回复策略：

| 输出前缀 | 含义 |
| --- | --- |
| `ALERT` | 有查询结果或提醒内容 |
| `SCHEDULED` | 已创建提醒任务 |
| `TRACKING` | 已加入追踪列表 |
| `NO_ALERT` | 当前无匹配事项 |
| `NOT_FOUND` | 未查到对应上市日期 |
| `MULTIPLE_MATCHES` | 匹配到多个候选 |
| `CANCELED` | 已取消上市提醒或追踪 |
| `EXPIRED` | 已查到上市日但提醒点均已过期 |
| `ERROR` | 数据源或运行异常 |
| `INFO` | 当前 Skill 状态看板 |

完整用户意图、命令映射和微信回复模板见 `SKILL.md`。

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

## 安全与隐私

- 不要提交个人 `config.json`、`watchlist.json`、`daily_subscribe.json`、日志、token、cookie、Authorization header 或其他敏感信息。
- 不要把个人服务器路径、账号信息或私有数据源地址写死进代码。
- `data_source.headers` 可能包含敏感 header。公开 issue 或 PR 时请先脱敏。
- 本项目不会主动上传用户本地配置、提醒数据或 CowAgent 凭证。
- 如果你发现安全问题，请不要在公开 issue 中披露敏感细节，可以先通过仓库维护者提供的私有渠道联系。

## 贡献

欢迎提交 issue 和 pull request。为了便于维护，请尽量遵循：

1. 先描述问题、复现步骤和期望行为。
2. 修改范围保持聚焦，不提交无关格式化。
3. 涉及行为变更时同步更新 `README.md` 或 `SKILL.md`。
4. 提交前运行：

```bash
python3 -m unittest discover -s tests
python3 -m py_compile scripts/bond_calendar.py
```

## 开源注意事项

- 本项目使用 MIT License，详见 `LICENSE`。
- 本项目不附带、代理或保证任何第三方金融数据源。
- 示例配置仅用于说明字段结构，不代表对第三方数据源可用性、授权状态或合规性的承诺。
- 使用者应自行确认第三方数据源的服务条款、访问频率限制、授权要求和当地法律法规。

## 免责声明

本项目仅用于学习、研究和个人自动化实践，不构成投资建议、数据服务承诺或任何形式的金融服务。项目不保证第三方数据源的可用性、准确性、及时性或合规性。

用户接入、访问、抓取、调用或使用第三方数据源，以及基于查询结果或提醒做出的任何操作，均由用户自行判断并承担全部责任；由此产生的法律、合规、交易、资金、账号或其他风险，均与本项目及作者无关。
