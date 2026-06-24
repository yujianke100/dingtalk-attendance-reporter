# =============================================================================
# Dockerfile — 钉钉考勤机器人
# =============================================================================
# 构建:
#   docker build -t dingtalk-attendance-bot .
#
# 运行（回调服务模式，需开放端口）:
#   docker run -d --name attendance-bot --env-file .env -p 8000:8000 \
#     dingtalk-attendance-bot
#
# 运行（纯调度模式，不占端口）:
#   docker run -d --name attendance-bot --env-file .env \
#     dingtalk-attendance-bot --scheduler-only
# =============================================================================

FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .

# 非 root 用户
RUN groupadd -r bot && useradd -r -g bot bot
USER bot

ENTRYPOINT ["python", "-m", "app.main"]
CMD []  # 默认回调服务模式，可通过 --scheduler-only 切换
