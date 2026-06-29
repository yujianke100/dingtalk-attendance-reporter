"""
消息格式化
==========
将考勤汇总数据格式化为钉钉 Markdown 消息。
"""
from collections import OrderedDict
from app.attendance import AttendanceSummary


def build_attendance_message(summary: AttendanceSummary) -> str:
    """
    构建考勤统计 Markdown 消息，按最低一级组织单元分组显示。
    """
    lines: list[str] = []

    # ---- 标题 ----
    period_map = {
        "today": "本日考勤统计",
        "week": "本周考勤统计",
        "month": "本月考勤统计",
    }
    title = period_map.get(summary.period, "考勤统计")
    lines.append(f"# 📊 {title}")
    lines.append("")
    lines.append(f"**统计周期**: {summary.date_range}")
    lines.append("")

    if not summary.has_problems:
        lines.append("✅ **全员出勤正常，无缺勤/迟到/早退情况。**")
        lines.append("")
        return "\n".join(lines)

    # ---- 概览 ----
    lines.append(f"👥 总人数: **{summary.total_people}** 人  |  ⚠️ 有异常: **{summary.problem_people}** 人")
    lines.append("")

    # ---- 按部门分组 ----
    dept_groups: dict[str, list] = OrderedDict()
    for rec in summary.records:
        dept = rec.department or "未分组"
        dept_groups.setdefault(dept, []).append(rec)

    for dept_name, group in dept_groups.items():
        lines.append(f"### 📁 {dept_name}")
        lines.append("")
        lines.append("| 姓名 | 缺勤次数 | 迟到次数(含缺卡) | 早退次数(含缺卡) |")
        lines.append("| :--- | :------: | :--------------: | :--------------: |")

        for rec in group:
            total_issues = rec.absence_count + rec.late_display + rec.early_leave_display
            flag = " 🔴" if total_issues >= 5 else " 🟡" if total_issues >= 2 else ""
            late_str = str(rec.late_display)
            early_str = str(rec.early_leave_display)
            if rec.on_duty_lack:
                late_str += f"(缺卡{rec.on_duty_lack})"
            if rec.off_duty_lack:
                early_str += f"(缺卡{rec.off_duty_lack})"
            lines.append(f"| {rec.name}{flag} | {rec.absence_count} | {late_str} | {early_str} |")

        lines.append("")

    lines.append("---")
    lines.append(f"🕐 生成时间: {_now_string()}")

    return "\n".join(lines)


def build_help_message() -> str:
    """帮助信息"""
    return """# 🤖 考勤机器人使用说明

## 命令列表

| 命令 | 说明 |
| :--- | :--- |
| `/本日考勤` | 查看今日考勤异常情况 |
| `/本周考勤` | 查看本周考勤异常情况 |
| `/本月考勤` | 查看本月考勤异常情况 |
| `/帮助` | 显示此帮助信息 |

## 自动推送
- ⏰ 每周日 **中午 12:00** 自动推送本周考勤汇总到群
- 可在 `app/config.py` 中修改推送时间和周期
"""


def _now_string() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M")
