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


async def send_attendance_report(period: str, target_type: str = None, webhook_url: str = None, user_ids: list[str] = None):
    """发送考勤报告"""
    summary = await get_attendance_summary(period)
    message = build_attendance_message(summary)

    if target_type == "private" and user_ids:
        if summary.has_problems:
            await ding_client.send_work_notification(
                user_ids=user_ids, title="考勤异常通知", text=message,
            )
            logger.info("已向 %d 人发送私聊通知", len(user_ids))
    else:
        url = webhook_url or config.ROBOT_WEBHOOK_URL
        if not url:
            logger.warning("Webhook URL 未配置，无法发送")
            return
        await ding_client.send_group_message_by_webhook(
            webhook_url=url, title="考勤统计", text=message, secret=config.ROBOT_SECRET,
        )
        logger.info("已发送群消息")

    # ── 阈值通知：按周期检查阈值，给当事人发通知 ──
    import json as _json
    thresholds = {}
    try:
        thresholds = _json.loads(config.NOTIFY_THRESHOLDS) if config.NOTIFY_THRESHOLDS.strip() else {}
    except Exception:
        pass

    threshold = thresholds.get(summary.period, 0)
    if threshold > 0 and summary.has_problems:
        for rec in summary.records:
            total = rec.absence_count + rec.late_display + rec.early_leave_display
            if total >= threshold:
                period_map = {"today": "今日", "week": "本周", "month": "本月"}
                try:
                    notify_msg = (
                        f"### ⚠️ 考勤异常提醒\n\n"
                        f"**统计周期**: {summary.date_range}\n\n"
                        f"您在{period_map.get(summary.period, summary.period)}累计 **{total}** 次考勤异常"
                        f"（缺勤{rec.absence_count}次，迟到{rec.late_display}次，早退{rec.early_leave_display}次），"
                        f"已超过阈值（{threshold}次），请留意。"
                    )
                    await ding_client.send_work_notification(
                        user_ids=[rec.user_id], title="考勤异常提醒", text=notify_msg,
                    )
                    logger.info("已向 %s(%s) 发送阈值通知", rec.name, rec.user_id[:8])
                except Exception as e:
                    logger.warning("发送阈值通知失败 %s: %s", rec.name, e)


async def send_scheduled_attendance(_target_index: int = -1):
    """
    定时任务入口。
    优先读取多目标配置 NOTIFICATION_TARGETS，其次使用默认单目标配置。
    """
    import json
    targets = json.loads(config.NOTIFICATION_TARGETS) if config.NOTIFICATION_TARGETS.strip() else []

    if targets and _target_index >= 0:
        # 多目标模式：只推送指定的目标
        t = targets[_target_index]
        logger.info("多目标 #%d: period=%s, type=%s", _target_index, t.get("period"), t.get("type"))
        await send_attendance_report(
            period=t.get("period", config.DEFAULT_PERIOD),
            target_type=t.get("type", config.DEFAULT_SEND_TYPE),
            webhook_url=t.get("webhook"),
            user_ids=t.get("user_ids"),
        )
    elif targets and _target_index < 0:
        # 兼容旧调用（无 _target_index）
        logger.info("多目标模式: %d 个目标", len(targets))
        for i, t in enumerate(targets):
            try:
                await send_attendance_report(
                    period=t.get("period", config.DEFAULT_PERIOD),
                    target_type=t.get("type", config.DEFAULT_SEND_TYPE),
                    webhook_url=t.get("webhook"),
                    user_ids=t.get("user_ids"),
                )
            except Exception as e:
                logger.error("目标推送失败: %s", e)
    else:
        # 单目标模式（默认）
        logger.info("单目标模式: period=%s, type=%s", config.DEFAULT_PERIOD, config.DEFAULT_SEND_TYPE)
        if config.DEFAULT_SEND_TYPE == "private":
            summary = await get_attendance_summary(config.DEFAULT_PERIOD)
            if summary.has_problems:
                user_ids = [r.user_id for r in summary.records]
                await send_attendance_report(config.DEFAULT_PERIOD, "private", user_ids=user_ids)
        else:
            await send_attendance_report(config.DEFAULT_PERIOD)
