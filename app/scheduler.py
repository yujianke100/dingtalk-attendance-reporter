"""
定时任务调度器
==============
使用 APScheduler 实现每周定时推送考勤统计。
"""
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import config

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler = AsyncIOScheduler()


def start_scheduler():
    """配置并启动定时任务"""
    if scheduler.running:
        logger.warning("调度器已在运行")
        return

    # 动态导入避免循环依赖
    from app.handlers import send_scheduled_attendance

    # 每周日指定时间执行
    scheduler.add_job(
        send_scheduled_attendance,
        trigger="cron",
        day_of_week=config.SCHEDULE_DAY_OF_WEEK,
        hour=config.SCHEDULE_HOUR,
        minute=config.SCHEDULE_MINUTE,
        id="weekly_attendance",
        name="每周考勤推送",
        replace_existing=True,
        misfire_grace_time=300,  # 允许延迟 5 分钟
    )

    scheduler.start()
    logger.info(
        "定时任务已启动: 每周%d %02d:%02d 推送考勤",
        config.SCHEDULE_DAY_OF_WEEK,
        config.SCHEDULE_HOUR,
        config.SCHEDULE_MINUTE,
    )


def stop_scheduler():
    """停止定时任务"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时任务已停止")
