"""
钉钉考勤机器人配置
==================
所有配置均从环境变量读取（.env 文件），方便迁移和部署。
"""
import os
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
# 阈值通知（周期内异常次数 ≥ 阈值时，给当事人发钉钉通知）
# JSON 格式，各周期独立配置：{"week":3, "month":9}
# 未配置的周期或不满足阈值则不通知；设为 {} 全局关闭
NOTIFY_THRESHOLDS = os.getenv("NOTIFY_THRESHOLDS", "{}")

# =============================================================================
# 多目标配置（JSON 数组，覆盖默认的群发/私发）
# 格式:
# [
#   {"type":"group", "webhook":"...", "period":"week", "schedule":"6 12:00"},
#   {"type":"private", "user_ids":["..."], "period":"month", "schedule":"1 09:00"}
# ]
# 优先读环境变量，为空时尝试读取 targets.json 文件
_NOTIFICATION_TARGETS_ENV = os.getenv("NOTIFICATION_TARGETS", "")
if not _NOTIFICATION_TARGETS_ENV:
    _targets_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "targets.json")
    if os.path.exists(_targets_file):
        with open(_targets_file, "r", encoding="utf-8") as f:
            _NOTIFICATION_TARGETS_ENV = f.read()
NOTIFICATION_TARGETS = _NOTIFICATION_TARGETS_ENV

# =============================================================================
# Mock 模式
# =============================================================================
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"
