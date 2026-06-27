"""
钉钉考勤机器人配置
==================
所有配置均从环境变量读取（.env 文件），方便迁移和部署。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# 钉钉应用凭证
# =============================================================================
DINGTALK_APP_KEY = os.getenv("DINGTALK_APP_KEY", "")
DINGTALK_APP_SECRET = os.getenv("DINGTALK_APP_SECRET", "")
DINGTALK_AGENT_ID = os.getenv("DINGTALK_AGENT_ID", "")

# =============================================================================
# 机器人 Webhook
# =============================================================================
ROBOT_WEBHOOK_URL = os.getenv("ROBOT_WEBHOOK_URL", "")
ROBOT_SECRET = os.getenv("ROBOT_SECRET", "")

# =============================================================================
# 定时任务（默认周日12:00推送本周考勤到群）
# =============================================================================
SCHEDULE_DAY_OF_WEEK = int(os.getenv("SCHEDULE_DAY_OF_WEEK", "6"))   # 6=周日
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "12"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))
DEFAULT_PERIOD = os.getenv("DEFAULT_PERIOD", "week")        # today/week/month
DEFAULT_SEND_TYPE = os.getenv("DEFAULT_SEND_TYPE", "group") # group/private

# =============================================================================
# 考勤组 & 组织架构
# =============================================================================
ATTENDANCE_GROUP_ID = int(os.getenv("ATTENDANCE_GROUP_ID", "1373082784"))
OP_USER_ID = os.getenv("OP_USER_ID", "103408242523124456")
SUB_DEPT_ID = os.getenv("SUB_DEPT_ID", "1071654357")

# =============================================================================
# 运行模式
# =============================================================================
# 默认 Stream 模式（WebSocket 长连接，不占端口）
# 设为 "http" 则使用传统 HTTP 回调（需开放端口）
# 设为其他值则仅定时推送
ENABLE_CALLBACK_SERVER = os.getenv("ENABLE_CALLBACK_SERVER", "stream").lower()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# =============================================================================
# 阈值通知配置（从 thresholds.json 读取）
# =============================================================================
import json as _json

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_config_file(name: str) -> str | None:
    """优先从 config/ 子目录读取，其次从项目根目录读取"""
    for base in (_PROJECT_ROOT / "config", _PROJECT_ROOT):
        path = base / name
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


_THR_RAW = _read_config_file("thresholds.json")
_NOTIFY_RAW = _json.loads(_THR_RAW) if _THR_RAW else {}

# 各维度的权重分（加权用）
WEIGHT_ABSENCE = _NOTIFY_RAW.get("weights", {}).get("absence", 3)
WEIGHT_LATE = _NOTIFY_RAW.get("weights", {}).get("late", 1)
WEIGHT_EARLY_LEAVE = _NOTIFY_RAW.get("weights", {}).get("early_leave", 1)

# 各周期的加权阈值（0=关闭）
NOTIFY_THRESHOLDS = _NOTIFY_RAW.get("thresholds", {})

# 每日检查时间（默认 22:00）
CHECK_HOUR, CHECK_MINUTE = (int(x) for x in _NOTIFY_RAW.get("check_time", "22:00").split(":"))
# 周检查仅在周一到周五运行
WEEKDAYS_ONLY = _NOTIFY_RAW.get("weekdays_only", True)
# 月检查仅在每月最后一天运行
MONTH_END_ONLY = _NOTIFY_RAW.get("month_end_only", True)

# =============================================================================
# 多目标配置（JSON 数组，覆盖默认的群发/私发）
# 格式:
# [
#   {"type":"group", "webhook":"...", "period":"week", "schedule":"6 12:00"},
#   {"type":"private", "user_ids":["..."], "period":"month", "schedule":"1 09:00"}
# ]
# 优先读环境变量，为空时尝试读取 config/targets.json 或 targets.json
_NOTIFICATION_TARGETS_ENV = os.getenv("NOTIFICATION_TARGETS", "")
if not _NOTIFICATION_TARGETS_ENV:
    _raw = _read_config_file("targets.json")
    if _raw:
        _NOTIFICATION_TARGETS_ENV = _raw
NOTIFICATION_TARGETS = _NOTIFICATION_TARGETS_ENV

# =============================================================================
# Mock 模式
# =============================================================================
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"
