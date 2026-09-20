"""Baidu LLM safety guard client (multi-tenant BCE authentication)."""

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.bce_auth import get_tokens
from app.core.config import Settings

logger = logging.getLogger(__name__)

class SafetyGuardError(RuntimeError):
    """安全护栏请求或业务异常。"""


class SafetyGuard:
    """百度 LLM 内容安全护栏客户端，支持多租户 BCE 鉴权。"""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        # 允许外部注入 httpx 客户端，便于测试复用连接池；
        # 未注入时自动创建，超时时间从配置读取
        self.client = client or httpx.AsyncClient(
            timeout=settings.safety_timeout,
        )

    # ------------------------------------------------------------------
    # BCE v1 签名（简化版，仅适配 POST + host 头）
    # ------------------------------------------------------------------
    def _headers(self, timestamp: int) -> dict[str, str]:
        """生成 BCE auth-v1 鉴权请求头。

        签名流程：
        1. signing_key = HMAC-SHA256(secret, "bce-auth-v1/{appkey}/{ts}/1800")
        2. signature   = HMAC-SHA256(signing_key, "POST\\n\\nhost:")
        3. Authorization = "{prefix}/host/{signature}"
        """
        prefix = (
            f"bce-auth-v1/"
            f"{self.settings.safety_appkey}/"
            f"{timestamp}/1800"  # 签名有效期 1800s
        )

        # 第一步：派生签名密钥
        signing_key = hmac.new(
            self.settings.safety_secret_key.encode(),
            prefix.encode(),
            hashlib.sha256,
        ).hexdigest()

        # 第二步：对 HTTP 方法 + 空 body + host 头签名
        # ⚠️ 此处为简化实现，仅适用于固定 POST 且无额外 signed headers 的场景
        canonical_request = b"POST\n\nhost:"
        signature = hmac.new(
            signing_key.encode(),
            canonical_request,
            hashlib.sha256,
        ).hexdigest()

        return {
            "Authorization": f"{prefix}/host/{signature}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    async def analyze_input(self, query: str) -> dict[str, Any]:
        """检测用户输入内容是否合规。"""
        return await self._analyze(
            "input_content_analyze",
            {"query": query, "stream": False},
        )

    async def analyze_output(
        self,
        content: str,
        request_id: str,
        is_first: bool = True,
    ) -> dict[str, Any]:
        """检测模型输出内容是否合规。

        Args:
            content: 待检测的模型输出文本。
            request_id: 关联的请求 ID，用于流式场景上下文关联。
            is_first: 是否为流式输出的首包（1=首包, 2=后续包）。
        """
        return await self._analyze(
            "output_content_analyze",
            {
                "content": content,
                "reqId": request_id,
                "isFirst": 1 if is_first else 2,
            },
        )

    # ------------------------------------------------------------------
    # 内部统一请求方法
    # ------------------------------------------------------------------
    async def _analyze(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """发送安全检测请求并解析响应。配置缺失时安全失败。"""
        if not all([
            self.settings.safety_base_url,
            self.settings.safety_appkey,
            self.settings.safety_secret_key,
            self.settings.safety_template_id,
        ]):
            raise SafetyGuardError("安全护栏配置不完整")

        # ---- 生成签名请求头 ----  
        ts = int(datetime.now(timezone.utc).timestamp())
        tz = str(ts)  # 转为字符串用于拼接和签名
        auth_header = get_tokens(self.settings.safety_appkey, self.settings.safety_secret_key, 1800, tz)
        if isinstance(auth_header, str):
            headers = {
                "Content-Type": "application/json",
                "Authorization": auth_header,
            }
        elif isinstance(auth_header, dict):
            headers = auth_header
            headers.setdefault("Content-Type", "application/json")
        else:
            raise SafetyGuardError(f"get_tokens 返回了无效的 headers 格式: {type(auth_header)}")

        # appkey + timestamp 作为 query string 传递（BCE 规范要求）
        query = urlencode({
            "appkey": self.settings.safety_appkey,
            "timestamp": tz,
        })
        url = (
            f"{self.settings.safety_base_url.rstrip('/')}"
            f"/llm/{endpoint}?{query}"
        )
        logger.info("安全护栏请求 endpoint=%s", endpoint)
        try:
            response = await self.client.post(
                url,
                json={
                    **payload,
                },
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "安全护栏请求失败 endpoint=%s error=%s",
                endpoint,
                type(exc).__name__,
            )
            raise SafetyGuardError("安全护栏请求失败") from exc

        # ---- 业务状态码校验（兼容 ret_code/code 两种字段命名）----
        ret_code = str(result.get("ret_code", result.get("code", 0)))
        if ret_code != "0":
            logger.warning("安全护栏返回失败 endpoint=%s code=%s", endpoint, ret_code)
            raise SafetyGuardError("安全护栏返回失败")

        # 兼容 ret_data/data 两种响应体结构
        return result.get("ret_data") or result.get("data") or {}
