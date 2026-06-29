"""
考勤数据服务
============
负责从钉钉 API 获取考勤打卡记录，或使用 Mock 数据用于测试。

对外暴露的入口: get_attendance_summary()
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from app import config
from app.dingtalk import ding_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class AttendanceRecord:
    """单条考勤汇总"""
    user_id: str
    name: str
    department: str = ""           # 最低一级组织单元名称
    absence_count: int = 0         # 缺勤次数（全天未到）
    late_count: int = 0            # 实际迟到次数
    early_leave_count: int = 0     # 实际早退次数
    on_duty_lack: int = 0          # 上班缺卡
    off_duty_lack: int = 0         # 下班缺卡

    @property
    def late_display(self) -> int:
        """显示用迟到次数（含缺卡）"""
        return self.late_count + self.on_duty_lack

    @property
    def early_leave_display(self) -> int:
        """显示用早退次数（含缺卡）"""
        return self.early_leave_count + self.off_duty_lack


@dataclass
class AttendanceSummary:
    """考勤汇总结果"""
    period: str                # "today" / "week" / "month"
    period_label: str          # 中文标签，如"6月24日" / "第26周" / "6月"
    date_range: str            # 日期范围，如"6月24日" 或 "6月18日 - 6月24日"
    records: list[AttendanceRecord] = field(default_factory=list)
    total_people: int = 0
    problem_people: int = 0

    @property
    def has_problems(self) -> bool:
        return len(self.records) > 0


# ---------------------------------------------------------------------------
# Mock 数据（用于开发和测试）
# 使用真实企业中的用户，让模拟数据更贴近实际
# ---------------------------------------------------------------------------
_MOCK_USERS = [
    {"user_id": "103408242523124456", "name": "孙仁杰"},
    {"user_id": "230636040221996464", "name": "管理员A"},
    {"user_id": "3606420551847104", "name": "管理员B"},
    {"user_id": "174209460620840492", "name": "负责人"},
]

_MOCK_ABSENT_USERS = {"103408242523124456", "174209460620840492"}  # 经常缺勤的人
_MOCK_LATE_USERS = {"230636040221996464", "3606420551847104"}      # 经常迟到的人
_MOCK_EARLY_LEAVE_USERS = {"3606420551847104", "174209460620840492"}  # 经常早退的人


def _generate_mock_records(period: str) -> list[AttendanceRecord]:
    """生成模拟考勤数据"""
    records = []
    now = date.today()

    if period == "today":
        days = [now]
    elif period == "week":
        monday = now - timedelta(days=now.weekday())
        days = [monday + timedelta(days=i) for i in range(7)]
    else:  # month
        month_start = now.replace(day=1)
        if now.month == 12:
            month_end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
        days = [month_start + timedelta(days=i) for i in range((month_end - month_start).days + 1)]

    # 只考虑工作日
    workdays = [d for d in days if d.weekday() < 5]
    total_workdays = len(workdays)

    for user in _MOCK_USERS:
        uid = user["user_id"]
        absence = 0
        late = 0
        early_leave = 0

        if period == "today":
            import random
            r = random.Random(f"{uid}_{now}")
            if uid in _MOCK_ABSENT_USERS:
                absence = 1 if r.random() < 0.4 else 0
            if uid in _MOCK_LATE_USERS:
                late = 1 if r.random() < 0.5 else 0
            if uid in _MOCK_EARLY_LEAVE_USERS:
                early_leave = 1 if r.random() < 0.3 else 0
        else:
            if uid in _MOCK_ABSENT_USERS:
                absence = max(1, total_workdays // 4)
            if uid in _MOCK_LATE_USERS:
                late = max(1, total_workdays // 6)
            if uid in _MOCK_EARLY_LEAVE_USERS:
                early_leave = max(1, total_workdays // 8)

        if absence > 0 or late > 0 or early_leave > 0:
            records.append(AttendanceRecord(
                user_id=uid,
                name=user["name"],
                absence_count=absence,
                late_count=late,
                early_leave_count=early_leave,
            ))

    # 按问题严重程度排序
    records.sort(key=lambda r: (r.absence_count + r.late_count), reverse=True)
    return records


# ---------------------------------------------------------------------------
# 真实数据（钉钉 API — 逐用户逐天查询，带重试）
# ---------------------------------------------------------------------------
async def _fetch_real_records(period: str) -> tuple[list[AttendanceRecord], int]:
    """
    从钉钉 API 获取真实的考勤数据并汇总。

    流程:
    1. get_attendance_group_members → 获取考勤组所有成员
    2. schedule/listbyday → 获取排班（每人每天一次调用，带自动重试）
    3. schedule/result/listbyids → 获取打卡结果
    """
    date_from, date_to = _get_date_range(period)

    # 1. 从考勤组获取成员
    try:
        member_ids = await ding_client.get_attendance_group_members(
            config.ATTENDANCE_GROUP_ID
        )
    except Exception as e:
        logger.error("获取考勤组成员失败: %s", e)
        member_ids = await ding_client.get_all_user_ids(dept_id=config.SUB_DEPT_ID)
        if not member_ids:
            member_ids = await ding_client.get_all_user_ids(dept_id=config.ROOT_DEPT_ID)

    total_people = len(member_ids)
    if not member_ids:
        logger.warning("未获取到任何用户")
        return [], 0

    logger.info("考勤组成员数: %d", total_people)

    # 2. 生成日期范围内每天的时间戳
    tz = ZoneInfo("Asia/Shanghai")
    current = date_from
    timestamps: list[int] = []
    while current <= date_to:
        ts = int(datetime(current.year, current.month, current.day, tzinfo=tz).timestamp() * 1000)
        timestamps.append(ts)
        current += timedelta(days=1)

    logger.info("查询日期范围: %s ~ %s (%d天, %d人)",
                date_from, date_to, len(timestamps), len(member_ids))
    # 估算 API 调用量
    est_schedule = len(timestamps) * len(member_ids)  # listbyday
    cached = bool(ding_client._user_cache)
    logger.info("预估API调用: 排班%d + 打卡结果 + 用户信息(%s) ≈ %d",
                est_schedule,
                "已缓存" if cached else "首次需查",
                est_schedule + (0 if cached else len(member_ids)) + 1)

    # 3. 按天批量查询排班（listbyusers，每天一次调用查所有人）
    all_schedules: list[dict] = []
    for ts in timestamps:
        schedules = await ding_client.get_schedules_by_day(member_ids, ts)
        all_schedules.extend(schedules)

    if not all_schedules:
        logger.info("排班数据为空")
        return [], total_people

    logger.info("获取到 %d 条排班记录", len(all_schedules))

    # 4. 获取打卡结果详情
    all_schedule_ids = [s["id"] for s in all_schedules]
    results_map: dict[int, dict] = {}
    if all_schedule_ids:
        results = await ding_client.get_attendance_results(all_schedule_ids)
        for r in results:
            results_map[r.get("schedule_id")] = r
        logger.info("获取到 %d 条打卡结果", len(results))

    # 5. 按用户汇总
    user_stats: dict[str, dict] = {}
    for s in all_schedules:
        uid = s["user_id"]
        check_type = s.get("check_type", "")
        check_status = s.get("check_status", "")
        is_rest = s.get("is_rest", "N")
        if is_rest == "Y":
            continue
        if uid not in user_stats:
            user_stats[uid] = {"name": "", "absence": 0, "late": 0, "early_leave": 0,
                               "on_duty_lack": 0, "off_duty_lack": 0}
        schedule_id = s.get("id")
        time_result = None
        if schedule_id and schedule_id in results_map:
            time_result = results_map[schedule_id].get("time_result", "")
        if check_type == "OnDuty":
            if time_result == "Absenteeism":
                user_stats[uid]["absence"] += 1
            elif time_result == "NotSigned":
                user_stats[uid]["on_duty_lack"] += 1
            elif time_result == "Late":
                user_stats[uid]["late"] += 1
            elif time_result is None and check_status in ("Timeout", "NotChecked", "Absent"):
                user_stats[uid]["absence"] += 1
        elif check_type == "OffDuty":
            if time_result == "EarlyLeave":
                user_stats[uid]["early_leave"] += 1
            elif time_result == "NotSigned":
                user_stats[uid]["off_duty_lack"] += 1

    # 6. 并发获取用户姓名和部门信息（分批，避免限流）
    uid_list = list(user_stats.keys())
    user_dept_map: dict[str, list[int]] = {}
    all_dept_ids: set[int] = set()

    for i in range(0, len(uid_list), 10):
        batch = uid_list[i:i + 10]
        info_tasks = [ding_client.get_user_info(uid) for uid in batch]
        info_results = await asyncio.gather(*info_tasks, return_exceptions=True)
        for uid, result in zip(batch, info_results):
            if isinstance(result, tuple):
                name, dept_ids = result
                user_stats[uid]["name"] = name if name else uid[:8]
                user_dept_map[uid] = dept_ids
                all_dept_ids.update(dept_ids)
            else:
                user_stats[uid]["name"] = uid[:8]
                user_dept_map[uid] = []

    # 批量获取部门 parent_id（填充缓存）
    dept_parent_tasks = [ding_client.get_dept_name(did) for did in all_dept_ids]
    await asyncio.gather(*dept_parent_tasks, return_exceptions=True)

    # 解析最低一级部门
    def _get_lowest_dept(dept_ids: list[int]) -> str:
        """从用户所属部门列表中找出最低一级组织单元名称"""
        if not dept_ids:
            return ""
        # 用缓存中的 parent_id 找最深层部门
        best = dept_ids[0]
        best_depth = 0
        for did in dept_ids:
            depth = 0
            cur = did
            seen = set()
            while cur != 1 and cur not in seen:
                seen.add(cur)
                info = ding_client._dept_cache.get(cur)
                if info is None:
                    break
                cur = info[1]  # parent_id
                depth += 1
            if depth > best_depth:
                best_depth = depth
                best = did
        # 从缓存拿名称
        cached = ding_client._dept_cache.get(best)
        return cached[0] if cached else str(best)

    # 7. 转换为记录列表
    records = [
        AttendanceRecord(user_id=uid, name=info["name"],
                         department=_get_lowest_dept(user_dept_map.get(uid, [])),
                         absence_count=info["absence"], late_count=info["late"],
                         early_leave_count=info["early_leave"],
                         on_duty_lack=info["on_duty_lack"],
                         off_duty_lack=info["off_duty_lack"])
        for uid, info in user_stats.items()
        if info["absence"] > 0 or info["late"] > 0 or info["early_leave"] > 0
        or info["on_duty_lack"] > 0 or info["off_duty_lack"] > 0
    ]
    records.sort(key=lambda r: (r.absence_count + r.late_display + r.early_leave_display), reverse=True)
    logger.info("总人数: %d, 有排班: %d, 异常: %d", total_people, len(user_stats), len(records))
    return records, total_people


# ---------------------------------------------------------------------------
# 日期工具
# ---------------------------------------------------------------------------
def _get_date_range(period: str) -> tuple[date, date]:
    """获取统计日期范围"""
    now = date.today()

    if period == "today":
        return now, now
    elif period == "week":
        monday = now - timedelta(days=now.weekday())  # Mon=0
        sunday = monday + timedelta(days=6)
        return monday, sunday
    else:  # month
        month_start = now.replace(day=1)
        if now.month == 12:
            month_end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
        return month_start, month_end


def _format_period_label(period: str) -> tuple[str, str]:
    """返回 (period_label, date_range)"""
    now = date.today()
    date_from, date_to = _get_date_range(period)

    fmt_from = f"{date_from.month}月{date_from.day}日"
    fmt_to = f"{date_to.month}月{date_to.day}日"

    if period == "today":
        label = fmt_from
        date_range = fmt_from
    elif period == "week":
        import datetime as dt
        iso_week = now.isocalendar()[1]
        label = f"第{iso_week}周"
        date_range = f"{fmt_from} - {fmt_to}"
    else:
        label = f"{now.month}月"
        date_range = f"{fmt_from} - {fmt_to}"

    return label, date_range


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------
async def get_attendance_summary(period: str) -> AttendanceSummary:
    """
    获取考勤汇总。
    period: "today" / "week" / "month"
    如果开启了 MOCK_MODE，则返回模拟数据；否则从钉钉 API 获取。
    """
    period_label, date_range = _format_period_label(period)

    if config.MOCK_MODE:
        logger.info("使用 Mock 模式获取考勤数据")
        records = _generate_mock_records(period)
        total_people = len(_MOCK_USERS)
    else:
        logger.info("从钉钉 API 获取考勤数据")
        try:
            records, total_people = await _fetch_real_records(period)
        except Exception as e:
            logger.error("获取考勤数据失败: %s", e)
            records, total_people = [], 0

    return AttendanceSummary(
        period=period,
        period_label=period_label,
        date_range=date_range,
        records=records,
        total_people=total_people,
        problem_people=len(records),
    )
