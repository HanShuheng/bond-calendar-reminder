# 更新日志

本文件记录项目的重要变更。

项目早期采用轻量级语义化版本约定。Skill 版本号存放在 `SKILL.md` 的 `metadata.version` 中。

## 0.2.0 - 2026-06-01

### 变更

- 重构为数据源策略和适配器模式，核心业务只依赖标准 `BondEvent` / `BondQuote`。
- 新增 `calendar_strategy` 和 `quote_strategy` 配置，移除旧厂商配置作为核心接口。
- 保留东方财富、集思录和东方财富 push2 作为内置示例适配器。
- 将东方财富 `PUBLIC_START_DATE`、`BOND_START_DATE`、`LISTING_DATE` 映射为标准债券事件。
- 将原来的单文件 CLI 实现拆分为 `scripts/bond_calendar_lib/` 下的多个职责明确的模块。
- 规范脚本输出格式，统一使用 `STATUS: 摘要` 首行和稳定的 CowAgent 回复分节。
- 将东方财富可转债字段说明移动到 `references/`，并在 `SKILL.md` 中暴露引用入口。
- 调整默认提醒时间：申购日为 `10:00`、`12:30`，中签结果公布日为 `10:30`、`13:00`，上市日为前一天提醒、当天 `09:25`、当天 `13:30`。
- 新增 `prepare-winning-today` 和 `send-prepared-winning`，支持中签结果公布日自动查询、缓存和提醒任务创建。
- 新增 `prepare-daily-reminders`，一次读取日历数据并同时准备申购和中签结果公布提醒。
- 新增上市日 `30%` 涨停后 `14:55` 二次提醒检查命令。
- 新增安装后/首次运行自动补齐 crontab 任务，并按命令去重避免重复设置。
- 规范示例配置：`config.example.json` 作为通用模板，新增东方财富主 + 集思录兜底示例和自定义 Python 适配器示例。
- 新增 `references/data-adapter-contract.md`，说明用户自定义 Python 适配器协议。

## 0.1.1 - 2026-05-31

### 新增

- 新增 `version` 命令，用于查看本地 Skill 版本。
- 新增 `check-update` 命令，用于对比本地版本和 GitHub main 分支版本。
- 补充 Skill 用户升级流程和维护者发布流程文档。

### 变更

- 更新 README，补充开源使用和版本管理说明。

## 0.1.0 - 2026-05-31

### 新增

- 初始化 CowAgent 可转债申购与上市提醒 Skill。
- 支持可配置的日历 JSON 数据源。
- 支持申购查询、上市日期查询、上市追踪、scheduler 任务创建、提醒列表查看和状态检查。
