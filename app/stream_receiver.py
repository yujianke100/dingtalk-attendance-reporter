"""
钉钉 Stream 模式消息接收器
============================
通过 WebSocket 长连接接收钉钉机器人消息，无需开放任何端口。

相比 HTTP 回调的优势：
- 不需要公网 IP 或端口映射
- 不需要 ngrok 内网穿透
- 连接由本机主动发起，防火墙友好
- 钉钉官方推荐方式
"""
import logging
from typing import Optional

import dingtalk_stream
from dingtalk_stream import AckMessage

from app import config
from app.handlers import parse_command, build_reply

logger = logging.getLogger(__name__)

_client: Optional[dingtalk_stream.DingTalkStreamClient] = None


class AttendanceBotHandler(dingtalk_stream.ChatbotHandler):
    """考勤机器人消息处理器"""

    def __init__(self, logger: logging.Logger = None):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        msg_type = incoming.message_type or ""

        # 只处理文本消息
        if msg_type != "text" or not incoming.text:
            return AckMessage.STATUS_OK, "OK"

        text = incoming.text.content.strip()
        self.logger.info(
            "收到消息: %s (来自: %s, 会话: %s)",
            text, incoming.sender_nick, incoming.conversation_type,
        )

        # 解析命令
        period = parse_command(text)
        if period is None:
            return AckMessage.STATUS_OK, "OK"

        # 构建回复
        reply_text = await build_reply(period)
        if reply_text:
            # 通过 Stream 连接直接回复 Markdown
            self.reply_markdown("考勤统计", reply_text, incoming)
            self.logger.info("已通过 Stream 回复 %s", incoming.sender_nick)

        return AckMessage.STATUS_OK, "OK"


def start_stream_client():
    """启动 Stream 客户端（非阻塞，后台运行）"""
    global _client

    if _client is not None:
        logger.warning("Stream 客户端已运行")
        return

    credential = dingtalk_stream.Credential(
        config.DINGTALK_APP_KEY,
        config.DINGTALK_APP_SECRET,
    )
    _client = dingtalk_stream.DingTalkStreamClient(credential)
    _client.register_callback_handler(
        dingtalk_stream.ChatbotMessage.TOPIC,
        AttendanceBotHandler(logger),
    )

    # 注册连接断开自动重连
    def on_error(e):
        logger.warning("Stream 连接异常，将自动重连: %s", e)

    _client.background_task.add_done_callback(on_error)

    # 在后台启动（不阻塞主线程）
    import asyncio
    asyncio.ensure_future(_client.start())
    logger.info("🤝 Stream 客户端已启动（WebSocket 长连接，无需开放端口）")


def stop_stream_client():
    """停止 Stream 客户端"""
    global _client
    if _client:
        try:
            # SDK 无 stop 方法，取消后台任务即可
            for task in _client.background_task:
                task.cancel()
        except Exception:
            pass
        _client = None
        logger.info("Stream 客户端已停止")
