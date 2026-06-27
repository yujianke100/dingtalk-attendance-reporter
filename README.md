# 📢 钉钉考勤通知机器人

> **About**: 自动推送钉钉考勤异常通知的机器人。定时或按需查询考勤缺勤/迟到/早退情况，群发或私发Markdown表格报告。
> 基于钉钉 Stream 模式 WebSocket 长连接，无需开放任何端口。

群内 @机器人 或私聊发送 `本日考勤` `本周考勤` `本月考勤`，即可收到考勤异常统计表（仅显示有异常的人员）。也支持每周日中午12:00自动推送。

---

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 📊 考勤统计 | 缺勤、迟到、早退三项指标，仅显示异常人员 |
| ⏰ 定时推送 | 默认每周日 **12:00** 自动推送（时间/周期/方式全可配） |
| 🗣️ 命令触发 | 群内 @机器人 或私聊发送 `本日考勤` `本周考勤` `本月考勤` |
| 🐳 Docker 部署 | 支持纯调度模式（不占端口）和回调服务模式 |
| 🔌 所有配置在 `.env` | 迁移只需复制 `.env`，不改代码 |

---

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆
git clone git@github.com:yujianke100/dingtalk-attendance-reporter.git
cd dingtalk-attendance-reporter

# 2. 配置
cp .env.example .env                    # 钉钉凭证等常规配置
cp targets.example.json targets.json    # 推送目标（哪些群/人）
cp thresholds.example.json thresholds.json  # 阈值通知（可选）
# 编辑以上文件填入真实值

# 3. 启动
docker compose up -d
```

### 方式二：直接运行

```bash
pip install -r requirements.txt
cp .env.example .env
cp targets.example.json targets.json
cp thresholds.example.json thresholds.json

# Stream 模式（推荐，不占端口）
python -m app.main

# 仅定时推送（不接收群消息）
python -m app.main --scheduler-only
```

---

## ⚙️ 配置说明

配置分布在三个文件中，各司其职：

### `.env` — 应用凭证 & 基础设置

```ini
DINGTALK_APP_KEY=xxx          # 钉钉 AppKey
DINGTALK_APP_SECRET=xxx       # 钉钉 AppSecret
DINGTALK_AGENT_ID=xxx         # 应用 AgentId
ATTENDANCE_GROUP_ID=1373082784
OP_USER_ID=xxx                # 有考勤权限的员工 userId
SUB_DEPT_ID=xxx               # 部门ID
ENABLE_CALLBACK_SERVER=stream # 运行模式
MOCK_MODE=false
```

### `targets.json` — 定时推送目标

```json
[
  {
    "type": "group",
    "webhook": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
    "period": "week",
    "schedule": "4 12:00",
    "secret": ""
  },
  {
    "type": "private",
    "user_ids": ["userid1"],
    "period": "month",
    "schedule": "0 09:00"
  }
]
```

| 字段 | 说明 |
|------|------|
| `type` | `group`（群发）或 `private`（私发） |
| `webhook` | 群机器人 Webhook URL（群发时必填） |
| `secret` | 加签密钥（没选加签则省略） |
| `period` | `week` / `month` / `today` |
| `schedule` | 定时规则 `"星期 时:分"`，星期值 **0=周一 ~ 6=周日**（APScheduler 标准），如 `"4 12:00"` = 周五12点 |
| `user_ids` | 私发的 userId 列表（私发时必填） |

> 数组为空或不存在的文件 = 不定时推送。群内 @机器人 发 `本日考勤` 仍会回复。

### `thresholds.json` — 阈值通知（可选）

```json
{ "week": 2, "month": 8 }
```

周期内异常次数达到阈值时，自动给当事人发钉钉通知。不设则关闭。

---

## 🐳 Docker 部署详解

```yaml
# docker-compose.yml 默认配置
services:
  attendance-bot:
    build: .
    env_file: .env
    restart: unless-stopped
```

```bash
docker compose up -d
```

在钉钉群中 @机器人 发送 `本日考勤` 即可实时回复，无需任何网络映射。

> **原理**: 机器人主动连接钉钉服务器的 WebSocket 端点，像微信一样长连收消息，不占宿主机端口。

### HTTP 回调模式（传统方式）

如需传统 HTTP 回调，修改 `.env` 并开放端口：

```ini
ENABLE_CALLBACK_SERVER=http
```

```yaml
services:
  attendance-bot:
    build: .
    env_file: .env
    ports:
      - "8000:8000"
```

然后去 [钉钉开放平台](https://open.dingtalk.com) → 事件订阅 → 改为 **HTTP 推送**。

> 本地开发可用 [ngrok](https://ngrok.com) 暴露端口。

### GitHub Actions 自动构建

打 `v*` 标签时自动构建 Docker 镜像并推送到 GHCR：

```bash
git tag v1.0.0
git push origin v1.0.0
```

| 标签 | 拉取命令 |
|------|----------|
| `v1.0.0` | `docker pull ghcr.io/yujianke100/dingtalk-attendance-reporter:v1.0.0` |
| `latest` | `docker pull ghcr.io/yujianke100/dingtalk-attendance-reporter:latest` |

自动使用 GitHub 内置 `GITHUB_TOKEN` 鉴权，**无需配置任何 Secrets**。

---

## 🎮 群内命令

在群聊中 **@机器人** 或私聊发送以下命令（`/` 前缀可选）：

| 命令 | 说明 |
|:---|:---|
| `本日考勤` 或 `今日考勤` | 查看今日考勤异常 |
| `本周考勤` | 查看本周考勤异常 |
| `本月考勤` | 查看本月考勤异常 |
| `帮助` | 显示帮助信息 |

命令格式灵活，以下均有效：`/本日考勤`、`@机器人 本日考勤`、`本日考勤`

---

## 🔧 手动触发（运维调试，仅 HTTP 模式）

```bash
curl -X POST http://localhost:8000/trigger \
  -H "Content-Type: application/json" \
  -d '{"period":"week"}'
```

> Stream 模式下无需 HTTP 端口，定时推送会自动触发。如需手动测试，临时切到 HTTP 模式或直接在代码中调用 `send_scheduled_attendance()`。

---

## 📋 消息示例

```
📊 本周考勤统计

**统计周期**: 6月22日 - 6月28日

👥 总人数: 18 人  |  ⚠️ 有异常: 3 人

| 姓名 | 缺勤次数 | 迟到次数 | 早退次数 |
| :--- | :------: | :------: | :------: |
| 张三 🔴 | 3 | 1 | 0 |
| 李四 🟡 | 0 | 2 | 1 |
| 王五 🟡 | 0 | 0 | 2 |

---
🕐 生成时间: 2026-06-24 12:00
```

---

## 📁 项目结构

```
├── app/
│   ├── config.py         # 配置读取（所有值来自 .env）
│   ├── dingtalk.py       # 钉钉 API 客户端
│   ├── attendance.py     # 考勤数据获取与汇总
│   ├── messages.py       # 消息格式化（Markdown 表格）
│   ├── handlers.py       # 命令解析与分发
│   ├── scheduler.py      # APScheduler 定时任务
│   ├── stream_receiver.py# Stream WebSocket 消息接收
│   └── main.py           # 入口（Stream/调度器/HTTP 三种模式）
├── .env                  # 凭证等常规配置（不提交）
├── .env.example          # 模板
├── targets.json          # 定时推送目标（不提交）
├── targets.example.json  # 模板
├── thresholds.json       # 阈值通知（不提交）
├── thresholds.example.json
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/    # CI 自动构建
└── README.md
```

---

## 💡 常见问题

**Q: 需要开放端口吗？**
A: 不需要。默认 Stream 模式通过 WebSocket 长连接接收消息，不占任何端口。HTTP 模式才需开放。

**Q: 钉钉里必须 @机器人 吗？**
A: 群聊中需要 @机器人 才能触发。私聊直接发命令即可。`/` 前缀可选。

**Q: 考勤判定参数呢？**
A: 考勤结果（缺勤/迟到/早退）由钉钉考勤应用直接判定，本机器人只读取 `time_result` 字段，无需额外配置。

**Q: 如何迁移到新服务器？**
A: 复制 `.env` 到新服务器，然后：
```bash
docker pull ghcr.io/zjgsu-scie-302/sign-in-notification-bot:main
docker compose up -d
```

**Q: Docker 镜像存在哪？**
A: GitHub Container Registry。无需 Docker Hub 账号，仓库的 Actions 自动构建：`ghcr.io/zjgsu-scie-302/sign-in-notification-bot:main`

**Q: 三种运行模式怎么选？**
A: | 场景 | 命令 | 端口 |
|------|------|------|
| 默认（推荐） | `python -m app.main` | ❌ |
| 只定时推送 | `python -m app.main --scheduler-only` | ❌ |
| HTTP 回调 | `python -m app.main --http` | ✅ 8000 |