"""
命令处理器
==========
解析钉钉机器人收到的消息并分派到对应的处理逻辑。
"""
import logging
from typing import Optional

from app import config
from app.attendance import get_attendance_summary
from app.dingtalk import ding_client
from app.messages import build_attendance_message, build_help_message

logger = logging.getLogger(__name__)

# 命令前缀
# 支持的命令映射（支持 /前缀 或无前缀）
COMMANDS = {
    "本日考勤": "today",
    "今日考勤": "today",
    "本周考勤": "week",
    "本月考勤": "month",
    "帮助": "help",
    "help": "help",
}


def parse_command(text: str) -> Optional[str]:
    """
    解析消息文本，返回对应的 period 值。
    兼容 @机器人 + 命令、/前缀、无前缀三种格式。
    返回 None 表示不是有效命令。
    """
    text = text.strip()
    # 去掉开头的 @提及（钉钉群中 @机器人 会自动带 @xxx 前缀）
    if text.startswith("@"):
        # 去掉 @提及部分（@xxx 后面可能跟着空格）
        import re
        text = re.sub(r"^@\S+\s*", "", text).strip()
    # 去掉可选的 / 前缀
    if text.startswith("/"):
        text = text[1:].strip()
    return COMMANDS.get(text)


async def build_reply(period: str) -> Optional[str]:
    """构建考勤回复内容"""
    if period == "help":
        return build_help_message()
    summary = await get_attendance_summary(period)
    return build_attendance_message(summary)


async def handle_message(
    conversation_type: str,      # "GROUP" 或 "PRIVATE"
    sender_id: str,              # 发送者 userId
    sender_nick: str,            # 发送者昵称
    text: str,                   # 消息文本
    session_webhook: str,        # 用于回复的 Webhook
    conversation_id: str,        # 会话 ID
) -> Optional[str]:
    """
    处理收到的消息（HTTP 回调模式）。
    如果是有效命令，构造回复内容并通过 sessionWebhook 回复。
    """
    period = parse_command(text)
    if period is None:
        return None

    logger.info("收到命令: %s (来自: %s, 会话类型: %s)", text, sender_nick, conversation_type)
    reply = await build_reply(period)

    if reply:
        try:
            await ding_client.reply_via_session_webhook(session_webhook, reply)
            logger.info("已回复消息到会话 %s", conversation_id)
        except Exception as e:
            logger.error("回复消息失败: %s", e)

    return reply


async def send_scheduled_attendance():
    """
    定时任务入口：发送默认周期的考勤统计。
    按配置发送到群聊或私聊。
    """
    logger.info("触发定时考勤推送 (period=%s, type=%s)", config.DEFAULT_PERIOD, config.DEFAULT_SEND_TYPE)

    summary = await get_attendance_summary(config.DEFAULT_PERIOD)
    message = build_attendance_message(summary)

    if config.DEFAULT_SEND_TYPE == "private":
        # 私发：通过工作通知发送给所有有异常的人
        if summary.has_problems:
            user_ids = [r.user_id for r in summary.records]
            # 同时通知管理员（如果有的话）
            try:
                await ding_client.send_work_notification(
                    user_ids=user_ids,
                    title="考勤异常通知",
                    text=message,
                )
                logger.info("已向 %d 人发送工作通知", len(user_ids))
            except Exception as e:
                logger.error("发送工作通知失败: %s", e)
        else:
            logger.info("无考勤异常，跳过私发通知")
    else:
        # 群发：通过机器人 Webhook 发送到群
        if not config.ROBOT_WEBHOOK_URL:
            logger.warning("ROBOT_WEBHOOK_URL 未配置，无法发送群消息")
            return
        try:
            await ding_client.send_group_message_by_webhook(
                webhook_url=config.ROBOT_WEBHOOK_URL,
                title="本周考勤统计",
                text=message,
                secret=config.ROBOT_SECRET,
            )
            logger.info("已发送群消息")
        except Exception as e:
            logger.error("发送群消息失败: %s", e)
