# =============================================================================
# Dockerfile — 钉钉考勤通知机器人
# =============================================================================
# 构建:
#   docker build -t dingtalk-attendance-reporter .
#
# 运行（Stream 模式，默认，不占端口）:
#   docker run -d --name attendance-bot --env-file .env \
#     ghcr.io/yujianke100/dingtalk-attendance-reporter:main
#
# 运行（仅定时推送）:
#   docker run -d --name attendance-bot --env-file .env \
#     ghcr.io/yujianke100/dingtalk-attendance-reporter:main --scheduler-only
# =============================================================================

FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
FROM python:3.11-slim

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .

# 非 root 用户
RUN groupadd -r bot && useradd -r -g bot bot
USER bot

ENTRYPOINT ["python", "-m", "app.main"]
CMD []  # 默认回调服务模式，可通过 --scheduler-only 切换
