"""
定时任务调度器
==============
使用 APScheduler 实现定时推送考勤统计。支持多目标分别配置不同周期。
"""
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler = AsyncIOScheduler()


def _parse_schedule(spec: str) -> dict:
    """解析 "6 12:00" → {day_of_week:6, hour:12, minute:0}，缺省周日12点"""
    parts = spec.strip().split()
    day = int(parts[0]) if parts else 6
    time_part = parts[1] if len(parts) > 1 else "12:00"
    hour, minute = (int(x) for x in time_part.split(":"))
    return {"day_of_week": day, "hour": hour, "minute": minute}


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
        sched = _parse_schedule(t.get("schedule", "6 12:00"))
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
                    i, sched["day_of_week"], sched["hour"], sched["minute"],
                    t.get("period","?"), t.get("type","?"))

    scheduler.start()
    """停止定时任务"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时任务已停止")
