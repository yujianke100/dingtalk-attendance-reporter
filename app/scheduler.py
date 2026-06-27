"""
定时任务调度器
==============
使用 APScheduler 实现定时推送考勤统计。支持多目标分别配置不同周期。
"""
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import config

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler = AsyncIOScheduler()


def _parse_schedule(spec: str) -> dict:
    """
    解析 "5 22:00" → {day_of_week:4, hour:22, minute:0}。

    用户配置中星期用 1~7 表示 周一~周日，
    但 APScheduler 的 cron day_of_week 使用 0~6，
    因此需要减 1 转换。缺省周日 12:00。
    """
    parts = spec.strip().split()
    day = int(parts[0]) if parts else 7
    time_part = parts[1] if len(parts) > 1 else "12:00"
    hour, minute = (int(x) for x in time_part.split(":"))
    return {"day_of_week": day - 1, "hour": hour, "minute": minute}


def start_scheduler():
    """配置并启动定时任务"""
    if scheduler.running:
        logger.warning("调度器已在运行")
        return

    from app.handlers import send_scheduled_attendance

    # ── 检查多目标配置 ──
    targets = []
    try:
        raw = config.NOTIFICATION_TARGETS.strip()
        if raw:
            targets = json.loads(raw)
    except Exception:
        pass

    if not targets:
        logger.info("NOTIFICATION_TARGETS 为空，不启动定时推送")
        scheduler.start()
        return

    for i, t in enumerate(targets):
        raw_spec = t.get("schedule", "7 12:00")
        parts = raw_spec.strip().split()
        raw_day = int(parts[0])  # 用户配置的原始星期（1=周一, 7=周日）
        sched = _parse_schedule(raw_spec)
        scheduler.add_job(
            send_scheduled_attendance,
            trigger="cron",
            day_of_week=sched["day_of_week"],
            hour=sched["hour"],
            minute=sched["minute"],
            id=f"target_{i}",
            name=f"目标{i}: {t.get('period','?')} {t.get('type','?')}",
            replace_existing=True,
            misfire_grace_time=300,
            kwargs={"_target_index": i},
        )
        logger.info("定时目标 %d: 每周%d %02d:%02d %s→%s",
                    i, raw_day, sched["hour"], sched["minute"],
                    t.get("period","?"), t.get("type","?"))

    # ── 每日阈值检查（如有周期配了阈值）──
    if any(config.NOTIFY_THRESHOLDS.get(p, 0) > 0 for p in ("week", "month")):
        from app.handlers import check_thresholds_daily
        scheduler.add_job(
            check_thresholds_daily,
            trigger="cron",
            hour=config.CHECK_HOUR,
            minute=config.CHECK_MINUTE,
            id="daily_threshold_check",
            name="每日阈值检查",
            replace_existing=True,
            misfire_grace_time=600,
        )
        logger.info("每日阈值检查: %02d:%02d", config.CHECK_HOUR, config.CHECK_MINUTE)

    scheduler.start()


def stop_scheduler():
    """停止定时任务"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时任务已停止")
