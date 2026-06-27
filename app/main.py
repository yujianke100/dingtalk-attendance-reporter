"""
钉钉考勤机器人 — 入口
=====================
三种运行模式:
  1. 默认模式 — Stream + 定时任务（推荐，无需开放端口）
  2. 纯调度模式 — 仅定时推送，不接收群消息
  3. HTTP 回调模式 — 传统回调方式（需开放端口）

启动方式:
  # 默认（Stream 模式，不占端口）
  python -m app.main

  # 纯调度模式（仅定时推送，不接收群消息）
  python -m app.main --scheduler-only

  # HTTP 回调模式（传统方式，需公网端口）
  python -m app.main --http
"""
import asyncio
import logging
import sys

from app import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 诊断
# ---------------------------------------------------------------------------
async def run_diagnostics():
    """启动时输出连接诊断"""
    from app.dingtalk import ding_client

    logger.info("=" * 50)
    logger.info("  钉钉考勤机器人启动中...")
    logger.info("=" * 50)

    if not config.MOCK_MODE:
        logger.info("🔍 MOCK_MODE=false，检查钉钉 API 连通性...")
        try:
            status = await ding_client.check_connectivity()
            logger.info("  ✅ Token 获取: %s", "正常" if status["token"] else "失败")
            logger.info("  ✅ 通讯录权限: %s", "正常" if status["user_list"] else "未授权")
            logger.info("  ✅ AgentId: %s", status["agent_id"] or "未配置")
            if status["errors"]:
                for err in status["errors"]:
                    logger.warning("  ⚠️  %s", err)
        except Exception as e:
            logger.warning("  ⚠️  连通性检查异常: %s", e)
    else:
        logger.info("🔍 MOCK_MODE=true，使用模拟数据运行")
        logger.info("  💡 生产环境: 设置 MOCK_MODE=false 并配置 .env 钉钉凭证")


# ---------------------------------------------------------------------------
# 启动器（通用）
# ---------------------------------------------------------------------------
async def run_with_services(extra_name: str = ""):
    """启动诊断 + 定时任务 + 可选额外服务"""
    await run_diagnostics()
    from app.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    name = f"Stream+调度" if not extra_name else extra_name
    logger.info("🚀 %s 模式运行中，按 Ctrl+C 停止", name)

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        stop_scheduler()
        logger.info("钉钉考勤机器人已关闭")


# ---------------------------------------------------------------------------
# 默认模式：Stream + 定时任务（推荐，不占端口）
# ---------------------------------------------------------------------------
async def run_stream_mode():
    """Stream WebSocket 连接 + 定时任务"""
    from app.stream_receiver import start_stream_client, stop_stream_client
    from app.scheduler import start_scheduler, stop_scheduler

    await run_diagnostics()
    start_scheduler()
    start_stream_client()
    logger.info("🚀 Stream 模式运行中（WebSocket 长连接，无需开放端口）")
    logger.info("   群内 @机器人 发送「本日考勤」即可查询")
    logger.info("   按 Ctrl+C 停止")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        stop_stream_client()
        stop_scheduler()
        logger.info("钉钉考勤机器人已关闭")


# ---------------------------------------------------------------------------
# 纯调度模式 — 仅定时任务
# ---------------------------------------------------------------------------
async def run_scheduler_only():
    """仅定时推送，不接收群消息"""
    from app.scheduler import start_scheduler, stop_scheduler

    await run_diagnostics()
    start_scheduler()
    logger.info("⏰ 纯调度模式运行中（不接收群消息）")
    logger.info("   按 Ctrl+C 停止")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        stop_scheduler()
        logger.info("钉钉考勤机器人已关闭")


# ---------------------------------------------------------------------------
# HTTP 回调模式（传统方式，需开放端口）
# ---------------------------------------------------------------------------
def create_http_app():
    """创建 FastAPI 应用（HTTP 回调模式）"""
    from contextlib import asynccontextmanager
    from fastapi import FastAPI, Request
    from pydantic import BaseModel

    from app.dingtalk import ding_client
    from app.handlers import handle_message
    from app.scheduler import start_scheduler, stop_scheduler

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_diagnostics()
        start_scheduler()
        yield
        stop_scheduler()
        logger.info("钉钉考勤机器人已关闭")

    app = FastAPI(
        title="钉钉考勤机器人",
        description="群发/私发本日/本周/本月考勤缺勤迟到情况",
        version="1.1.0",
        lifespan=lifespan,
    )

    class DingTalkCallback(BaseModel):
        conversationId: str = ""
        conversationType: str = ""
        chatbotUserId: str = ""
        msgtype: str = ""
        text: dict = {"content": ""}
        senderId: str = ""
        senderNick: str = ""
        isInAtList: bool = False
        sessionWebhook: str = ""
        createAt: int = 0

    @app.get("/")
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "dingtalk-attendance-bot"}

    @app.post("/dingtalk/callback")
    async def dingtalk_callback(request: Request, body: DingTalkCallback):
        timestamp = request.headers.get("timestamp", "")
        sign = request.headers.get("sign", "")
        if timestamp and sign:
            valid = ding_client.verify_callback_signature(
                timestamp, sign, config.ROBOT_SECRET
            )
            if not valid:
                logger.warning("签名验证失败，拒绝请求")
                return {"errcode": 400, "errmsg": "sign check fail"}
        else:
            logger.warning("请求缺少签名头（开发环境可忽略）")
        if body.msgtype != "text":
            return {"errcode": 0, "errmsg": "ok"}
        text_content = body.text.get("content", "").strip()
        try:
            await handle_message(
                conversation_type=body.conversationType,
                sender_id=body.senderId,
                sender_nick=body.senderNick,
                text=text_content,
                session_webhook=body.sessionWebhook,
                conversation_id=body.conversationId,
            )
        except Exception as e:
            logger.exception("处理消息时出错: %s", e)
        return {"errcode": 0, "errmsg": "ok"}

    class TriggerRequest(BaseModel):
        period: str = "week"

    @app.post("/trigger")
    async def trigger_attendance(req: TriggerRequest):
        if req.period not in ("today", "week", "month"):
            return {"errcode": 400, "errmsg": "period 必须是 today/week/month"}
        from app.handlers import send_scheduled_attendance
        old = config.DEFAULT_PERIOD
        config.DEFAULT_PERIOD = req.period
        try:
            await send_scheduled_attendance()
            return {"errcode": 0, "errmsg": f"已触发 {req.period} 考勤推送"}
        finally:
            config.DEFAULT_PERIOD = old

    return app


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
app = None

if __name__ == "__main__":
    if "--scheduler-only" in sys.argv:
        asyncio.run(run_scheduler_only())
    elif "--http" in sys.argv or config.ENABLE_CALLBACK_SERVER == "http":
        import uvicorn
        app = create_http_app()
        uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=True)
    else:
        # 默认：Stream 模式（推荐）
        asyncio.run(run_stream_mode())
else:
    # uvicorn 导入：仅 HTTP 模式需要 app 对象
    if config.ENABLE_CALLBACK_SERVER == "http":
        app = create_http_app()
    else:
        logger.warning("Stream 模式下不要用 uvicorn 启动，请执行: python -m app.main")
