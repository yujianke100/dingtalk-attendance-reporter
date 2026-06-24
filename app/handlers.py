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


async def send_attendance_report(period: str, target_type: str = None, webhook_url: str = None, webhook_secret: str = None, user_ids: list[str] = None):
    """发送考勤报告"""
    summary = await get_attendance_summary(period)
    message = build_attendance_message(summary)

    if target_type == "private" and user_ids:
        if summary.has_problems:
            await ding_client.send_work_notification(
                user_ids=user_ids, title="考勤异常通知", text=message,
            )
            logger.info("已向 %d 人发送私聊通知", len(user_ids))
        return

    if not webhook_url:
        logger.warning("Webhook URL 未配置，无法群发")
        return
    await ding_client.send_group_message_by_webhook(
        webhook_url=webhook_url, title="考勤统计", text=message, secret=webhook_secret or "",
    )
    logger.info("已发送群消息")


# ── 加权计算 ──
def calc_weighted_score(rec) -> int:
    """按权重计算综合异常分"""
    return (rec.absence_count * config.WEIGHT_ABSENCE
            + rec.late_display * config.WEIGHT_LATE
            + rec.early_leave_display * config.WEIGHT_EARLY_LEAVE)


# ── 周期内去重 ──
_notified: set[str] = set()

def _notify_key(period: str, user_id: str) -> str:
    """生成周期+用户的去重键，跨周期自动失效"""
    from datetime import date
    today = date.today()
    if period == "week":
        cycle = today.isocalendar()[1]  # ISO 周数，每周一重置
    else:  # month
        cycle = f"{today.year}_{today.month}"  # 每月重置
    return f"{period}_{cycle}_{user_id}"


async def check_thresholds_daily():
    """
    每日阈值检查。
    - 周检查：仅在周一到周五运行（weekdays_only=true 时）
    - 月检查：仅在每月最后一天运行（month_end_only=true 时）
    """
    from datetime import date, timedelta
    today = date.today()
    is_weekday = today.weekday() < 5
    is_month_end = (today + timedelta(days=1)).month != today.month

    periods_to_check = []
    if config.NOTIFY_THRESHOLDS.get("week", 0) > 0:
        if config.WEEKDAYS_ONLY and not is_weekday:
            logger.debug("周末跳过周检查")
        else:
            periods_to_check.append("week")
    if config.NOTIFY_THRESHOLDS.get("month", 0) > 0:
        if config.MONTH_END_ONLY and not is_month_end:
            logger.debug("非月末跳过月检查")
        else:
            periods_to_check.append("month")

    if not periods_to_check:
        return

    logger.info("📊 阈值检查(%s): periods=%s", today, periods_to_check)

    for period in periods_to_check:
        threshold = config.NOTIFY_THRESHOLDS[period]
        summary = await get_attendance_summary(period)
        if not summary.has_problems:
            continue

        period_label = {"week": "本周", "month": "本月"}.get(period, period)

        for rec in summary.records:
            score = calc_weighted_score(rec)
            if score < threshold:
                continue

            key = _notify_key(period, rec.user_id)
            if key in _notified:
                continue  # 同周期已通知过，跳过

            _notified.add(key)
            notify_msg = (
                f"### ⚠️ 考勤异常提醒\n\n"
                f"**统计周期**: {summary.date_range}\n\n"
                f"您在{period_label}累计异常加权分 **{score}** 分"
                f"（缺勤{rec.absence_count}×{config.WEIGHT_ABSENCE}"
                f" + 迟到{rec.late_display}×{config.WEIGHT_LATE}"
                f" + 早退{rec.early_leave_display}×{config.WEIGHT_EARLY_LEAVE}），"
                f"已超过阈值（{threshold}分），请留意。"
            )
            try:
                await ding_client.send_work_notification(
                    user_ids=[rec.user_id], title="考勤异常提醒", text=notify_msg,
                )
                logger.info("阈值通知 -> %s (%s分)", rec.name, score)
            except Exception as e:
                logger.warning("阈值通知失败 %s: %s", rec.name, e)


async def send_scheduled_attendance(_target_index: int = 0):
    """定时任务入口：读取 NOTIFICATION_TARGETS 推送指定目标"""
    import json
    raw = config.NOTIFICATION_TARGETS.strip()
    if not raw:
        logger.info("NOTIFICATION_TARGETS 为空，跳过定时推送")
        return
    try:
        targets = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("NOTIFICATION_TARGETS 格式错误: %s", e)
        return

    if _target_index < 0 or _target_index >= len(targets):
        logger.warning("目标索引 %d 超出范围", _target_index)
        return

    t = targets[_target_index]
    logger.info("推送目标 #%d: period=%s, type=%s", _target_index, t.get("period"), t.get("type"))
    await send_attendance_report(
        period=t.get("period", "week"),
        target_type=t.get("type", "group"),
        webhook_url=t.get("webhook"),
        webhook_secret=t.get("secret", ""),
        user_ids=t.get("user_ids"),
    )
