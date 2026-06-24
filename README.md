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
# 1. 配置
cp .env.example .env
# 编辑 .env，填入钉钉应用凭证

# 2. 启动（默认 Stream 模式，不占端口，支持群命令）
docker compose up -d
```

### 方式二：直接运行

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env

# 默认 Stream 模式（推荐，不占端口）
python -m app.main

# 仅定时推送（不接收群消息）
python -m app.main --scheduler-only
```

---

## ⚙️ 配置说明

所有配置均通过 `.env` 文件管理，迁移只需复制一份 `.env` 即可。

```ini
# --- 钉钉应用凭证 ---
DINGTALK_APP_KEY=your_app_key
DINGTALK_APP_SECRET=your_app_secret
DINGTALK_AGENT_ID=your_agent_id

# --- 群机器人 Webhook ---
ROBOT_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx
ROBOT_SECRET=                          # 创建时选了"加签"才需填写

# ==================== 定时任务 ====================
SCHEDULE_DAY_OF_WEEK=6                 # 0=周一 .. 6=周日
SCHEDULE_HOUR=12                       # 时（24小时制）
SCHEDULE_MINUTE=0                      # 分
DEFAULT_PERIOD=week                    # today / week / month
DEFAULT_SEND_TYPE=group                # group（群发）/ private（私发）

# ==================== 考勤组 & 组织架构 ====================
ATTENDANCE_GROUP_ID=1373082784         # 钉钉考勤组ID
OP_USER_ID=xxx                         # 有考勤权限的员工 userId
SUB_DEPT_ID=xxx                        # 部门ID（降级获取用户用）

# ==================== HTTP回调服务 ====================
ENABLE_CALLBACK_SERVER=stream         # stream/http/false
# HOST=0.0.0.0
# PORT=8000

# ==================== Mock 模式 ====================
MOCK_MODE=false                        # 开发测试用，生产环境关闭
```

---

## 🐳 Docker 部署详解

### Stream 模式（默认，推荐）

默认使用 **Stream 模式**——通过 WebSocket 长连接接收钉钉消息，**完全不需要开放端口**。

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

每次推送 `main` 或打 `v*` 标签时自动构建，产物存储在两个地方：

| 产物 | 位置 | 拉取方式 |
|------|------|----------|
| 🐳 Docker 镜像 | **GitHub Container Registry** | `docker pull ghcr.io/zjgsu-scie-302/sign-in-notification-bot:main` |
| 📦 压缩包 | **Actions Artifact** | Actions 页面直接下载 `.tar.gz` |

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
├── .env                  # 本地配置（不提交）
├── .env.example          # 配置模板
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