# bond-calendar-reminder-skill

CowAgent 专属可转债申购与上市提醒 Skill。

本项目面向 [CowAgent](https://cowagent.ai/) 的 Skill 运行方式设计。CowAgent 读取 `SKILL.md` 识别用户意图后，调用 `scripts/bond_calendar.py` 查询可转债申购、上市日期和中签追踪状态，并通过 CowAgent scheduler 创建一次性提醒任务。

> 本项目仅用于学习、研究和个人自动化实践，不构成投资建议、数据服务承诺或任何形式的金融服务。

安装后可以直接使用：未创建 `config.json` 时，脚本会启用内置示例数据源，即东方财富日历为主、集思录日历兜底、东方财富 push2 行情用于上市日涨幅检查。配置文件只用于修改时间、关闭自动任务或接入用户自己的数据源。

## 功能特性

- 查询指定日期或日期范围内的可转债申购。
- 支持按债券名、转债代码、申购代码、配售代码过滤申购事项。
- 自动检查当天中签结果公布日，并创建 `10:30`、`13:00` 中签结果公布提醒。
- 查询可转债上市日期。
- 记录中签转债；暂未查到上市日时自动追踪，查到后创建上市提醒。
- 创建 CowAgent scheduler 一次性提醒任务。
- 查看、取消当前债券相关提醒和追踪事项。
- 支持自定义申购提醒、中签结果公布提醒和上市提醒时间。
- 核心业务只依赖标准 `BondEvent` / `BondQuote` 数据协议。
- 支持策略模式和适配器模式，用户可通过 Python 模块路径接入自己的日历和行情数据源。
- 内置东方财富、集思录和东方财富 push2 适配器作为可运行示例。
- 运行数据保存在 CowAgent workspace，便于备份和排障。

## 适用场景

适合：

- 在微信里问 CowAgent：“今天有哪些可转债申购？”
- 在微信里问 CowAgent：“123270 什么时候上市？”
- 中签后告诉 CowAgent：“我中了 123270，上市提醒我。”
- 用 crontab 每天自动检查当天申购、中签结果公布和待追踪上市事项。

不适合：

- 作为独立金融数据服务对外提供接口。
- 接入券商账户、自动交易或判断用户是否真实中签。
- 绕过第三方数据源的访问规则、授权或风控限制。

## 项目状态

当前版本为 `0.2.1`，属于早期可用版本。接口、配置字段和 CowAgent Skill 约定仍可能调整。建议个人使用前先在测试环境验证配置和提醒链路。

## 工作原理

```text
用户微信消息
    ↓
CowAgent 读取 SKILL.md 并匹配意图
    ↓
CowAgent 调用 scripts/bond_calendar.py
    ↓
脚本通过 calendar_strategy 读取标准 BondEvent
    ↓
脚本查询结果、写入追踪状态或创建 scheduler 任务
    ↓
CowAgent 整理脚本输出并回复用户 / 执行后续提醒
```

仓库结构：

```text
bond-calendar-reminder-skill/
├── SKILL.md                  # CowAgent Skill 元数据、意图映射和回复模板
├── README.md                 # 项目说明
├── CHANGELOG.md              # 版本变化记录
├── LICENSE                   # MIT License
├── requirements.txt          # Python 依赖
├── examples/
│   ├── config.example.json
│   ├── config.builtin-eastmoney-jisilu.example.json
│   ├── config.python-adapter.example.json
│   └── config.jisilu.example.json
├── references/
│   ├── data-adapter-contract.md
│   ├── cowagent-multi-instance-workspace.md
│   ├── eastmoney-bond-fields.md
│   ├── quote-data-source.md
│   └── uninstall.md
├── scripts/
│   ├── bond_calendar.py      # 命令行入口
│   └── bond_calendar_lib/    # 配置、数据源、查询、scheduler 和业务命令模块
└── tests/
    └── test_bond_calendar.py
```

运行时默认写入：

```text
~/cow/bond_reminders/
├── config.json
├── daily_subscribe.json
├── daily_winning.json
├── update_check.json
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
- 可访问用户配置的数据源；默认内置示例适配器会访问东方财富和集思录。
- 自动提醒依赖 CowAgent scheduler。
- 每日自动检查会通过 `post_install_command` 或首次运行 skill 命令时自动写入 crontab；已有同名任务会跳过，不重复添加。

Python 依赖见 `requirements.txt`。

## 安装

### 方式一：通过 CowAgent CLI 安装

在 CowAgent 服务器上执行：

```bash
cow skill install HanShuheng/bond-calendar-reminder-skill
```

如果 CLI 不支持 GitHub shorthand，可以使用仓库地址：

```bash
cow skill install https://github.com/HanShuheng/bond-calendar-reminder-skill
```

### 方式二：手动安装

```bash
mkdir -p ~/cow/skills
git clone https://github.com/HanShuheng/bond-calendar-reminder-skill.git ~/cow/skills/bond-calendar-reminder-skill
```

安装依赖：

```bash
cd ~/cow/skills/bond-calendar-reminder-skill
python3 -m pip install -r requirements.txt
```

如果 CowAgent 使用自己的虚拟环境，建议使用 CowAgent 的 Python：

```bash
~/CowAgent/.venv/bin/python -m pip install -r ~/cow/skills/bond-calendar-reminder-skill/requirements.txt
```

## 配置

默认情况下不需要配置文件也能使用。只有在下面场景才需要创建 `~/cow/bond_reminders/config.json`：

- 修改自动检查时间或提醒发送时间。
- 关闭自动设置 crontab。
- 显式选择内置示例适配器。
- 接入自己的 Python 日历或行情适配器。

如果一台服务器运行多个 CowAgent 实例，每个实例必须使用独立的 `COW_WORKSPACE`。所有会写配置、缓存、scheduler、crontab 或用户上下文的 skill 都需要按 workspace 隔离；详细说明见 `references/cowagent-multi-instance-workspace.md`。

配置文件默认路径：

```text
~/cow/bond_reminders/config.json
```

创建配置目录：

```bash
mkdir -p ~/cow/bond_reminders
```

使用空白通用模板：

```bash
cp ~/cow/skills/bond-calendar-reminder-skill/examples/config.example.json ~/cow/bond_reminders/config.json
```

`config.example.json` 是通用模板，只保留项目标准策略入口和提醒时间，不绑定任何厂商。即使没有复制这个文件，项目也会启用内置默认示例：东方财富日历为主、集思录日历兜底、东方财富 push2 行情。

如果要直接使用内置示例适配器，推荐复制：

```bash
cp ~/cow/skills/bond-calendar-reminder-skill/examples/config.builtin-eastmoney-jisilu.example.json ~/cow/bond_reminders/config.json
```

如果要接入自己的数据源，参考：

```bash
cp ~/cow/skills/bond-calendar-reminder-skill/examples/config.python-adapter.example.json ~/cow/bond_reminders/config.json
```

如果只想验证集思录单一日历适配器，可以参考 `examples/config.jisilu.example.json`。它是特殊示例，不是默认推荐配置；该文件不配置行情适配器，因此默认关闭上市日涨幅二次提醒。

编辑配置：

```bash
nano ~/cow/bond_reminders/config.json
```

配置入口速查：

| 目标 | 看哪里 |
| --- | --- |
| 只改提醒时间或自动检查时间 | `examples/config.example.json` |
| 显式使用内置示例数据源 | `examples/config.builtin-eastmoney-jisilu.example.json` |
| 接入自己的 Python 数据源 | `examples/config.python-adapter.example.json` 和 `references/data-adapter-contract.md` |
| 查看内置东方财富字段映射 | `references/eastmoney-bond-fields.md` |
| 查看内置行情示例 | `references/quote-data-source.md` |

核心业务只认项目标准数据协议，不要求使用某个固定厂商接口。日历数据统一转成 `BondEvent`，行情数据统一转成 `BondQuote`；完整字段、适配器方法和示例代码见 `references/data-adapter-contract.md`。

## 快速验证

```bash
cd ~/cow/skills/bond-calendar-reminder-skill
python3 scripts/bond_calendar.py --help
python3 scripts/bond_calendar.py info
python3 scripts/bond_calendar.py find-subscribe --date 今天
```

第一次执行业务命令时，脚本会自动检查定时任务是否存在；如果缺少默认任务，会补齐 `prepare-daily-reminders`、`check-tracked-listings`、`check-listing-limit-up`。如果 CowAgent 安装阶段已执行 `post_install_command`，这些任务会在安装时提前写入。

如果 `info` 显示提醒目标未识别，先在微信里和 CowAgent 机器人产生一次对话，再重新执行：

```bash
python3 scripts/bond_calendar.py info
```

## 常用命令

| 目标 | 命令 |
| --- | --- |
| 查询今日申购 | `python3 scripts/bond_calendar.py find-subscribe --date 今天` |
| 按日期范围查申购 | `python3 scripts/bond_calendar.py find-subscribe --date "3月5号-3月10号"` |
| 按名称或代码查申购 | `python3 scripts/bond_calendar.py find-subscribe --query 123270` |
| 准备当天申购和中签结果公布提醒 | `python3 scripts/bond_calendar.py prepare-daily-reminders` |
| 只刷新当天缓存，不创建提醒 | `python3 scripts/bond_calendar.py prepare-daily-reminders --no-create-tasks` |
| 查询上市日期 | `python3 scripts/bond_calendar.py find-listing --query 123270` |
| 记录中签并追踪上市日 | `python3 scripts/bond_calendar.py track-listing --query 123270` |
| 检查上市日涨幅二次提醒 | `python3 scripts/bond_calendar.py check-listing-limit-up` |
| 取消上市提醒或追踪 | `python3 scripts/bond_calendar.py cancel-listing --query 123270` |
| 查看当前提醒和追踪 | `python3 scripts/bond_calendar.py list-reminders` |
| 查看 Skill 状态看板 | `python3 scripts/bond_calendar.py info` |
| 查看版本 | `python3 scripts/bond_calendar.py version` |
| 检查更新 | `python3 scripts/bond_calendar.py check-update` |
| 跳过某个版本 | `python3 scripts/bond_calendar.py skip-update --version 0.2.1` |

更完整的用户话术、命令映射和微信回复模板见 `SKILL.md`。

## 升级与版本管理

本项目用 `SKILL.md` 中的 `metadata.version` 作为 Skill 版本号，并在 `CHANGELOG.md` 记录每次发布的变化。

用户可以主动检查更新：

```bash
cd ~/cow/skills/bond-calendar-reminder-skill
python3 scripts/bond_calendar.py check-update
```

用户主动使用查询、追踪、取消、列表或状态看板等交互命令时，脚本会每天最多自动检查一次 GitHub main 分支版本。如果发现新版本，会先输出更新提示并询问是否更新；当天已经检查过后，不会重复检查。

如果用户暂不更新，可以跳过这一个版本：

```bash
python3 scripts/bond_calendar.py skip-update --version <最新版本号>
```

跳过后不会再为同一个版本提示；如果以后发布了更高版本，下一次每日检查仍会提示。

如果输出提示有新版本，按下面步骤升级：

```bash
cd ~/cow/skills/bond-calendar-reminder-skill
git pull
python3 -m pip install -r requirements.txt
python3 scripts/bond_calendar.py info
```

如果 CowAgent 使用自己的虚拟环境，请把 `python3` 替换为 CowAgent 的 Python 路径。

维护者发布新版本时建议遵循：

1. 更新 `SKILL.md` 的 `metadata.version`。
2. 更新 `CHANGELOG.md`。
3. 提交代码并打 tag，例如 `v0.1.1`。
4. 在 GitHub Release 中复制对应版本的 changelog。

## 卸载与清理

如果不再使用本 skill，需要同时清理 4 类内容：

- crontab 中的每日自动检查任务。
- CowAgent scheduler 中已经创建的一次性提醒任务。
- `~/cow/bond_reminders/` 下的配置、缓存、追踪和日志。
- skill 代码目录。

完整步骤见 `references/uninstall.md`。建议先按文档备份，再删除运行数据；其中 `config.json`、`watchlist.json`、`daily_subscribe.json`、`daily_winning.json` 和 `bond_calendar.log` 都属于个人运行数据。

## 自动化

首次运行任意业务命令时，脚本会自动检查并补齐 3 个 crontab 定时任务。它按命令去重：如果已有同名 `bond_calendar.py` 任务，就不会重复添加。

| 时间 | 命令 | 说明 |
| --- | --- | --- |
| 每天 `07:00` | `prepare-daily-reminders` | 一次查询当天申购和中签结果公布事项，并分别创建提醒 |
| 每天 `07:05` | `check-tracked-listings` | 检查已记录的中签转债，查到上市日后创建提醒 |
| 每天 `14:50` | `check-listing-limit-up` | 检查今日上市转债涨幅，达到阈值时创建 14:55 二次提醒 |

可预览将写入的任务：

```bash
python3 scripts/bond_calendar.py setup-schedule
```

确认写入：

```bash
python3 scripts/bond_calendar.py setup-schedule --yes
```

修改每日检查时间：

```bash
python3 scripts/bond_calendar.py setup-schedule --replace --yes \
  --daily-time 08:00 \
  --tracking-time 08:05 \
  --limit-up-time 14:45
```

也可以在 `config.json` 中配置：

```json
{
  "auto_setup_schedule": {
    "enabled": true,
    "daily_time": "07:00",
    "tracking_time": "07:05",
    "limit_up_time": "14:50"
  }
}
```

如需关闭自动设置 crontab，把 `auto_setup_schedule.enabled` 设为 `false`。

自动任务无事项时应保持静默：每日申购检查无结果、每日中签结果公布检查无结果、每日上市追踪无新日期、上市日涨停检查未达到阈值时，不主动发送微信消息。只有用户主动查询时才回复“暂无事项”。

## CowAgent 回复约定

脚本输出使用纯文本协议，第一行固定为 `STATUS: 简短摘要`，后续使用稳定分节，便于 CowAgent 生成微信回复。完整状态前缀、分节规则、用户意图映射和回复模板都维护在 `SKILL.md`，README 不再重复展开。

## 测试

运行单元测试：

```bash
python3 -m unittest discover -s tests
```

检查脚本语法：

```bash
python3 -m py_compile scripts/bond_calendar.py scripts/bond_calendar_lib/*.py
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
| 数据源配置错误 | `calendar_strategy` 或 `quote_strategy` 配置不完整，或自定义适配器未返回标准字段 | 先删除自定义配置验证默认内置示例，或改用 `examples/config.builtin-eastmoney-jisilu.example.json` |

## 安全与免责声明

- 本项目使用 MIT License，详见 `LICENSE`。
- 本项目仅用于学习、研究和个人自动化实践，不构成投资建议、数据服务承诺或任何形式的金融服务。
- 本项目不附带、代理或保证任何第三方金融数据源；使用者应自行确认数据源服务条款、访问频率限制、授权要求和当地法律法规。
- 不要提交个人 `config.json`、`watchlist.json`、`daily_subscribe.json`、`daily_winning.json`、`update_check.json`、日志、token、cookie、Authorization header 或其他敏感信息。
- 不要把个人服务器路径、账号信息或私有数据源地址写死进代码。
- `calendar_strategy` / `quote_strategy` 中的 headers 可能包含敏感信息。公开 issue 或 PR 时请先脱敏。
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
python3 -m py_compile scripts/bond_calendar.py scripts/bond_calendar_lib/*.py
```
