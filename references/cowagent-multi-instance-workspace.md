# CowAgent 多实例与 Skill 隔离说明

本文档记录一台服务器运行多个 CowAgent 实例时，所有 skill 都应该注意的 workspace 隔离原则。

它不是某个 skill 的专属说明。任何会读写配置、缓存、日志、scheduler 任务、用户上下文或外部账号状态的 skill，都应该按这里的原则隔离。

## 核心结论

每个 CowAgent 实例都应该有独立的 `COW_WORKSPACE`。

不要让多个 CowAgent 共用同一个：

```text
~/cow
```

否则多个实例会共用这些数据：

```text
<COW_WORKSPACE>/skills/
<COW_WORKSPACE>/scheduler/tasks.json
<COW_WORKSPACE>/<skill-runtime-data>/
```

如果两个 CowAgent 共用同一份 workspace，常见问题包括：

- 两个实例扫描到同一套 skills，导致启用状态互相影响。
- 两个实例共用同一份 `scheduler/tasks.json`，导致定时提醒重复发送或发错对象。
- 不同实例共用同一个 skill 的运行数据，导致配置、缓存、用户状态、任务状态互相污染。
- 微信、Telegram、Web 等通道上下文被多个实例复用，导致主动消息发到不符合预期的会话。
- 一个实例升级 skill 后，另一个实例被动使用了新代码或新数据格式。

所以原则是：**实例隔离 = 程序目录隔离 + workspace 隔离 + 端口/通道配置隔离 + 定时任务隔离。**

## CowAgent Workspace 中通常有什么

不同 CowAgent 版本和部署方式可能略有差异，但通常会包含：

```text
<COW_WORKSPACE>/
├── skills/                 # 已安装 skills
├── scheduler/tasks.json    # scheduler 任务
├── logs/                   # 日志或运行输出，视部署而定
├── uploads/                # 用户上传文件，视部署而定
└── <skill-specific-data>/  # 各 skill 自己创建的数据目录
```

每个 skill 可能还会创建自己的运行目录，例如：

```text
<COW_WORKSPACE>/bond_reminders/
<COW_WORKSPACE>/coupon_data/
<COW_WORKSPACE>/knowledge_wiki/
```

这些都不应该在多个 CowAgent 实例之间默认共享。

## 推荐目录结构

例如同一台服务器运行两个实例：

```text
/root/CowAgent-A
/root/CowAgent-B

/root/cow-a
/root/cow-b
```

对应关系：

| 实例 | CowAgent 程序目录 | COW_WORKSPACE |
|---|---|---|
| A | `/root/CowAgent-A` | `/root/cow-a` |
| B | `/root/CowAgent-B` | `/root/cow-b` |

## systemd 配置

实例 A：

```ini
[Unit]
Description=CowAgent A
After=network.target

[Service]
WorkingDirectory=/root/CowAgent-A
Environment=COW_WORKSPACE=/root/cow-a
ExecStart=/root/CowAgent-A/.venv/bin/python /root/CowAgent-A/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

实例 B：

```ini
[Unit]
Description=CowAgent B
After=network.target

[Service]
WorkingDirectory=/root/CowAgent-B
Environment=COW_WORKSPACE=/root/cow-b
ExecStart=/root/CowAgent-B/.venv/bin/python /root/CowAgent-B/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

应用配置：

```bash
systemctl daemon-reload
systemctl restart cowagent-a
systemctl restart cowagent-b
```

确认环境变量：

```bash
systemctl show cowagent-a -p Environment
systemctl show cowagent-b -p Environment
```

## 安装 skill

安装任意 skill 时，都应该明确使用目标实例的 workspace。

实例 A：

```bash
COW_WORKSPACE=/root/cow-a cow skill install <skill-source>
```

实例 B：

```bash
COW_WORKSPACE=/root/cow-b cow skill install <skill-source>
```

如果使用手动安装，也要安装到各自 workspace：

```bash
git clone <skill-repo-url> /root/cow-a/skills/<skill-name>

git clone <skill-repo-url> /root/cow-b/skills/<skill-name>
```

安装后分别检查：

```bash
COW_WORKSPACE=/root/cow-a cow skill list
COW_WORKSPACE=/root/cow-b cow skill list
```

确认 A/B 两个实例看到的是各自 workspace 下的 skill 列表。

## crontab 必须带 COW_WORKSPACE

如果某个 skill 需要系统 crontab 主动运行脚本，crontab 行必须显式带 `COW_WORKSPACE`。

如果 crontab 不写 `COW_WORKSPACE`，脚本通常会回退到默认 `~/cow`，导致多个实例混用同一套数据。

通用格式：

```cron
* * * * * COW_WORKSPACE=/root/cow-a /path/to/instance-a/.venv/bin/python /root/cow-a/skills/<skill-name>/<script> <command> >> /root/cow-a/<skill-log-dir>/<log-file> 2>&1
```

不要写成：

```cron
* * * * * /path/to/python /root/cow-a/skills/<skill-name>/<script> <command>
```

因为这样脚本进程里可能没有正确的 `COW_WORKSPACE`。

## 可转债提醒 skill 示例

下面用 `bond-calendar-reminder-skill` 举例。其他 skill 也应按相同原则处理。

实例 A：

```cron
00 07 * * * COW_WORKSPACE=/root/cow-a /root/CowAgent-A/.venv/bin/python /root/cow-a/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py prepare-daily-reminders >> /root/cow-a/bond_reminders/bond_calendar.log 2>&1
05 07 * * * COW_WORKSPACE=/root/cow-a /root/CowAgent-A/.venv/bin/python /root/cow-a/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py check-tracked-listings >> /root/cow-a/bond_reminders/bond_calendar.log 2>&1
50 14 * * * COW_WORKSPACE=/root/cow-a /root/CowAgent-A/.venv/bin/python /root/cow-a/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py check-listing-limit-up >> /root/cow-a/bond_reminders/bond_calendar.log 2>&1
```

实例 B：

```cron
00 07 * * * COW_WORKSPACE=/root/cow-b /root/CowAgent-B/.venv/bin/python /root/cow-b/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py prepare-daily-reminders >> /root/cow-b/bond_reminders/bond_calendar.log 2>&1
05 07 * * * COW_WORKSPACE=/root/cow-b /root/CowAgent-B/.venv/bin/python /root/cow-b/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py check-tracked-listings >> /root/cow-b/bond_reminders/bond_calendar.log 2>&1
50 14 * * * COW_WORKSPACE=/root/cow-b /root/CowAgent-B/.venv/bin/python /root/cow-b/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py check-listing-limit-up >> /root/cow-b/bond_reminders/bond_calendar.log 2>&1
```

也可以用脚本自动生成，但执行时必须带对应 workspace：

```bash
cd /root/cow-a/skills/bond-calendar-reminder-skill
COW_WORKSPACE=/root/cow-a /root/CowAgent-A/.venv/bin/python scripts/bond_calendar.py setup-schedule --replace --yes

cd /root/cow-b/skills/bond-calendar-reminder-skill
COW_WORKSPACE=/root/cow-b /root/CowAgent-B/.venv/bin/python scripts/bond_calendar.py setup-schedule --replace --yes
```

## 检查是否隔离成功

分别查看两个实例：

```bash
COW_WORKSPACE=/root/cow-a cow skill list
COW_WORKSPACE=/root/cow-b cow skill list
```

如果 skill 有自己的状态命令，也应该分别检查。例如可转债提醒 skill：

```bash
COW_WORKSPACE=/root/cow-a /root/CowAgent-A/.venv/bin/python /root/cow-a/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py info

COW_WORKSPACE=/root/cow-b /root/CowAgent-B/.venv/bin/python /root/cow-b/skills/bond-calendar-reminder-skill/scripts/bond_calendar.py info
```

重点检查输出里的路径：

```text
配置文件
运行数据目录
scheduler 文件
今日申购缓存
今日中签结果公布缓存
上市追踪列表
```

它们应该分别指向 `/root/cow-a/...` 和 `/root/cow-b/...`。

检查 crontab：

```bash
crontab -l | grep bond_calendar.py
```

每一行都应该显式包含对应的：

```text
COW_WORKSPACE=/root/cow-a
COW_WORKSPACE=/root/cow-b
```

检查 systemd：

```bash
systemctl show cowagent-a -p Environment
systemctl show cowagent-b -p Environment
```

检查进程：

```bash
systemctl status cowagent-a
systemctl status cowagent-b
```

确认它们的 `WorkingDirectory`、`ExecStart`、监听端口和 workspace 都是各自独立的。

## 单实例情况

如果一台服务器只运行一个 CowAgent，使用默认 workspace 即可：

```text
/root/CowAgent
/root/cow
```

这时 skill 默认会使用：

```text
/root/cow/skills/
/root/cow/scheduler/tasks.json
/root/cow/<skill-runtime-data>/
```

## 迁移提醒

从单实例迁移到多实例时，不要直接复制整份 `/root/cow` 给多个实例后同时运行。

建议流程：

1. 停止旧 CowAgent。
2. 备份 `/root/cow`。
3. 为每个实例创建独立 workspace。
4. 分别复制或重新安装需要的 skills。
5. 分别配置微信上下文和 scheduler。
6. 分别执行各 skill 的状态命令检查路径；如果某个 skill 没有状态命令，就检查它的配置文件、日志和 scheduler 任务路径。
7. 最后再开启各自 crontab。

这样可以避免提醒任务、微信接收目标和可转债追踪状态混在一起。

## 适用于所有 skill 的检查清单

新增或安装任意 skill 前，先确认：

- 这个 skill 会不会写配置文件。
- 这个 skill 会不会写缓存、日志、数据库或状态文件。
- 这个 skill 会不会创建 scheduler 任务。
- 这个 skill 会不会写系统 crontab。
- 这个 skill 会不会保存用户上下文、接收目标、外部账号或 token。
- 这个 skill 是否需要联网检查更新或拉取远程数据。

如果任意一项答案是“会”，多实例部署时就必须确认它读写的是当前实例自己的 `COW_WORKSPACE`。
