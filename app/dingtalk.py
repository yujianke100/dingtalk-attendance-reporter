"""
钉钉 API 客户端
==============
封装钉钉开放平台常用接口：认证、考勤查询、用户信息、消息发送等。
"""
import asyncio
import hashlib
import base64
import hmac
import json
import time
import logging
from typing import Optional

import httpx

from app import config

logger = logging.getLogger(__name__)


class DingTalkClient:
    """钉钉 API 客户端（单例）"""

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires_at: float = 0
        self._dept_cache: dict[int, tuple[str, int]] = {}  # dept_id → (name, parent_id)

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------
    async def get_access_token(self) -> str:
        """获取 access_token（自动缓存刷新）"""
        if self._token and time.time() < self._token_expires_at:
            return self._token

        if not config.DINGTALK_APP_KEY or not config.DINGTALK_APP_SECRET:
            raise RuntimeError("请在 config.py 中配置 DINGTALK_APP_KEY 和 DINGTALK_APP_SECRET")

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://oapi.dingtalk.com/gettoken",
                params={
                    "appkey": config.DINGTALK_APP_KEY,
                    "appsecret": config.DINGTALK_APP_SECRET,
                },
            )
            data = resp.json()
            if data.get("errcode") != 0:
                raise RuntimeError(f"获取 access_token 失败: {data}")
            self._token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 7200) - 120
            logger.info("access_token 已刷新")
            return self._token

    # ------------------------------------------------------------------
    # 考勤数据（新版API）
    # ------------------------------------------------------------------
    async def get_attendance_group_members(self, group_id: int) -> list[str]:
        """获取考勤组所有成员 userId 列表"""
        token = await self.get_access_token()
        members: list[str] = []
        cursor = 0
        has_more = True

        async with httpx.AsyncClient(timeout=15) as client:
            while has_more:
                resp = await client.post(
                    "https://oapi.dingtalk.com/topapi/attendance/group/memberusers/list",
                    params={"access_token": token},
                    json={
                        "op_user_id": config.OP_USER_ID,
                        "group_id": group_id,
                        "cursor": cursor,
                        "size": 100,
                    },
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    logger.warning("获取考勤组成员失败: %s", data)
                    break
                result_list = data.get("result", {}).get("result", [])
                members.extend(result_list)
                has_more = data.get("result", {}).get("has_more", False)

        return members

    async def get_schedules_by_day(
        self, user_ids: list[str], timestamp: int
    ) -> list[dict]:
        """
        查询所有用户在指定日期的排班数据。

        使用 listbyday 逐个用户查询（带重试），但按天分批调用。
        """
        token = await self.get_access_token()
        all_results: list[dict] = []

        for uid in user_ids:
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.post(
                            "https://oapi.dingtalk.com/topapi/attendance/schedule/listbyday",
                            params={"access_token": token},
                            json={
                                "op_user_id": config.OP_USER_ID,
                                "user_id": uid,
                                "date_time": timestamp,
                            },
                        )
                        data = resp.json()
                    if data.get("errcode") == 0:
                        all_results.extend(data.get("result", []))
                        break
                    elif data.get("errcode") == 41041:
                        break
                    elif data.get("errcode") in (90002, 90006) and attempt < 2:
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                    else:
                        logger.warning("查询排班失败 uid=%s ts=%s: %s", uid, timestamp, data)
                        break
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                    logger.warning("查询排班异常 uid=%s ts=%s: %s", uid, timestamp, e)
                    break

        return all_results

    async def get_attendance_results(
        self, schedule_ids: list[int]
    ) -> list[dict]:
        """
        根据排班ID列表获取打卡结果详情。
        返回包含 user_check_time、time_result 等字段。
        """
        if not schedule_ids:
            return []

        token = await self.get_access_token()
        all_results: list[dict] = []
        # API 单次最多查 50 个 ID，分批查询
        batch_size = 50

        async with httpx.AsyncClient(timeout=15) as client:
            for i in range(0, len(schedule_ids), batch_size):
                batch = schedule_ids[i : i + batch_size]
                ids_str = ",".join(str(sid) for sid in batch)
                resp = await client.post(
                    "https://oapi.dingtalk.com/topapi/attendance/schedule/result/listbyids",
                    params={"access_token": token},
                    json={
                        "op_user_id": config.OP_USER_ID,
                        "schedule_ids": ids_str,
                    },
                )
                data = resp.json()
                if data.get("errcode") == 0:
                    all_results.extend(data.get("result", []))
                else:
                    logger.warning("获取打卡结果失败(批次%d): %s", i // batch_size, data)

        logger.info("获取到 %d 条打卡结果", len(all_results))
        return all_results

    async def get_attendance_groups(self) -> list[dict]:
        """获取考勤组列表（含排班信息）"""
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://oapi.dingtalk.com/topapi/attendance/getsimplegroups",
                params={"access_token": token},
                json={"offset": 0, "size": 20},
            )
            data = resp.json()
            if data.get("errcode") != 0:
                logger.warning("获取考勤组失败: %s", data)
                return []
            groups = data.get("result", {}).get("groups", [])
            return groups

    async def get_all_user_ids(self, dept_id: str = "1") -> list[str]:
        """获取部门下所有用户的 userId"""
        token = await self.get_access_token()
        user_ids: list[str] = []
        cursor = 0
        has_more = True

        async with httpx.AsyncClient(timeout=15) as client:
            while has_more:
                resp = await client.post(
                    "https://oapi.dingtalk.com/topapi/user/listsimple",
                    params={"access_token": token},
                    json={"dept_id": dept_id, "cursor": cursor, "size": 100},
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    logger.warning("获取用户列表失败: %s", data)
                    break
                result = data.get("result", {})
                user_ids.extend(u.get("userid") for u in result.get("list", []))
                has_more = result.get("has_more", False)
                cursor = result.get("next_cursor", 0)

        return user_ids

    async def get_user_name(self, user_id: str) -> str:
        """根据 userId 获取用户姓名"""
        name, _ = await self.get_user_info(user_id)
        return name

    async def get_user_info(self, user_id: str) -> tuple[str, list[int]]:
        """返回 (name, dept_ids)"""
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://oapi.dingtalk.com/topapi/v2/user/get",
                params={"access_token": token},
                json={"userid": user_id},
            )
            data = resp.json()
            if data.get("errcode") != 0:
                return user_id, []
            result = data.get("result", {})
            return result.get("name", user_id), result.get("dept_id_list", [])

    async def get_dept_name(self, dept_id: int) -> str:
        """获取部门名称（带缓存）"""
        # 先查缓存
        if dept_id in self._dept_cache:
            return self._dept_cache[dept_id][0]
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://oapi.dingtalk.com/topapi/v2/department/get",
                params={"access_token": token},
                json={"dept_id": dept_id, "language": "zh_CN"},
            )
            data = resp.json()
            if data.get("errcode") != 0:
                return str(dept_id)
            result = data.get("result", {})
            name = result.get("name", str(dept_id))
            parent_id = result.get("parent_id", 1)
            self._dept_cache[dept_id] = (name, parent_id)
            return name

    # ------------------------------------------------------------------
    # 消息发送
    # ------------------------------------------------------------------
    async def send_group_message_by_webhook(
        self,
        webhook_url: str,
        title: str,
        text: str,
        secret: str = "",
    ) -> dict:
        """通过机器人 Webhook 发送 Markdown 群消息"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text,
            },
        }
        url = webhook_url
        if secret:
            timestamp = str(round(time.time() * 1000))
            sign = self._generate_webhook_sign(timestamp, secret)
            url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
            if result.get("errcode") != 0:
                logger.warning("发送群消息失败: %s", result)
            return result

    async def send_work_notification(
        self,
        user_ids: list[str],
        title: str,
        text: str,
    ) -> dict:
        """通过工作通知 API 发送消息（支持私聊，需要用户装有该应用）"""
        token = await self.get_access_token()
        payload = {
            "agent_id": config.DINGTALK_AGENT_ID,
            "userid_list": ",".join(user_ids),
            "msg": {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": text,
                },
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2",
                params={"access_token": token},
                json=payload,
            )
            result = resp.json()
            if result.get("errcode") != 0:
                logger.warning("发送工作通知失败: %s", result)
            return result

    async def reply_via_session_webhook(self, webhook_url: str, content: str) -> dict:
        """通过 sessionWebhook 回复消息（用于即时响应机器人消息）"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "考勤结果",
                "text": content,
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            return resp.json()

    # ------------------------------------------------------------------
    # AgentId 自动发现
    # ------------------------------------------------------------------
    async def discover_agent_id(self) -> Optional[str]:
        """
        尝试从钉钉 API 自动发现应用的 AgentId。
        某些版本的应用可以通过 corp_token 查询。
        """
        if config.DINGTALK_AGENT_ID:
            return config.DINGTALK_AGENT_ID

        try:
            token = await self.get_access_token()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://oapi.dingtalk.com/topapi/microapp/listbypage?access_token="
                    + token,
                    json={"offset": 0, "size": 10},
                )
                data = resp.json()
                if data.get("errcode") == 0:
                    app_list = data.get("appList", [])
                    if app_list:
                        agent_id = str(app_list[0].get("agentId", ""))
                        logger.info("自动发现 AgentId: %s", agent_id)
                        return agent_id
        except Exception as e:
            logger.debug("自动发现 AgentId 失败（可忽略）: %s", e)
        return None

    # ------------------------------------------------------------------
    # 连通性检查
    # ------------------------------------------------------------------
    async def check_connectivity(self) -> dict:
        """
        检查钉钉 API 连通性，返回各接口状态。
        用于启动时诊断和用户排查问题。
        """
        status = {
            "token": False,
            "user_list": False,
            "attendance": False,
            "agent_id": None,
            "errors": [],
        }

        # 1. token
        try:
            token = await self.get_access_token()
            status["token"] = True
        except Exception as e:
            status["errors"].append(f"获取token失败: {e}")
            return status

        # 2. user list
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://oapi.dingtalk.com/topapi/user/listsimple?access_token="
                    + token,
                    json={"dept_id": "1", "cursor": 0, "size": 1},
                )
                data = resp.json()
                if data.get("errcode") == 0:
                    status["user_list"] = True
                else:
                    status["errors"].append(
                        f"通讯录权限不足: {data.get('sub_msg', data.get('errmsg', ''))}"
                    )
        except Exception as e:
            status["errors"].append(f"查询用户列表异常: {e}")

        # 3. agent_id
        status["agent_id"] = config.DINGTALK_AGENT_ID or await self.discover_agent_id()

        return status

    # ------------------------------------------------------------------
    # 签名
    # ------------------------------------------------------------------
    @staticmethod
    def verify_callback_signature(timestamp: str, sign: str, secret: str) -> bool:
        """验证钉钉回调请求签名"""
        string_to_sign = f"{timestamp}\n{secret}"
        expected = base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return expected == sign

    @staticmethod
    def _generate_webhook_sign(timestamp: str, secret: str) -> str:
        """生成 Webhook 签名（用于发送消息时加签）"""
        string_to_sign = f"{timestamp}\n{secret}"
        return base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")


# 全局单例
ding_client = DingTalkClient()
