# -*- coding: utf-8 -*-
"""
大模型安全护栏接口调用封装（输入安全 / 输出安全）
依赖: pip install requests
"""
import json
import httpx
from .bce_auth import get_tokens, current_timestamp


class GuardrailError(RuntimeError):
    pass


class GuardrailClient:
    INPUT_PATH = "/llm/input_content_analyze"
    OUTPUT_PATH = "/llm/output_content_analyze"

    def __init__(self, host: str, ak: str, sk: str,
                 template_id: str, timeout: float = 15.0,
                 client: httpx.AsyncClient = None):
        """
        :param host: 服务地址，如 http://10.60.38.12:8080
        :param ak:   appkey / Access Key
        :param sk:   Secret Key
        :param template_id: 管理控制台配置的策略模板编码
        """
        self.host = host.rstrip("/")
        self.ak = ak
        self.sk = sk
        self.template_id = template_id
        self.timeout = timeout
        self.client = client

    # ---------- 内部：构建请求 ----------
    def _build(self, path: str, body: dict):
        if not self.host or not self.ak or not self.sk or not self.template_id:
            raise GuardrailError("安全护栏配置不完整")
        # ⚠️ URL 上的 timestamp 必须与签名里的 timeZone 完全一致
        ts = current_timestamp()
        url = f"{self.host}{path}"
        params = {"appkey": self.ak, "timestamp": ts}
        headers = {
            "Content-Type": "application/json",
            "Authorization": get_tokens(self.ak, self.sk, 1800, ts),
        }
        return url, params, headers

    # ---------- 4.4 输入内容分析（非流式） ----------
    def input_content_analyze(self, query: str,
                              history_qa: list = None,
                              appid: str = None,
                              user_id: str = None,
                              extra_info: dict = None,
                              stream: bool = False):
        """
        :param query:      检测内容，最大 8k
        :param history_qa: [{"Q": "...", "A": "..."}, ...]，QA 对总长 < 2048
        :param stream:     True 则命中安全大模型代答时流式返回
        :return: dict 响应 JSON
        """
        body = {"query": query, "templateId": self.template_id}
        if history_qa is not None:
            body["historyQA"] = history_qa
        if appid:
            body["appid"] = appid
        if user_id:
            body["userId"] = user_id
        if extra_info:
            body["extraInfo"] = extra_info
        body["stream"] = bool(stream)

        url, params, headers = self._build(self.INPUT_PATH, body)

        if stream:
            return self._sse_post(url, params, headers, body)

        return self._post_sync(url, params, headers, body)

    def _post_sync(self, url, params, headers, body):
        # Retained for legacy synchronous callers.
        import requests
        try:
            resp = requests.post(url, params=params, headers=headers,
                                 json=body, timeout=self.timeout)
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:
            raise GuardrailError(f"安全护栏请求失败: {exc}") from exc
        if str(result.get("ret_code", result.get("code", 0))) != "0":
            raise GuardrailError(result.get("ret_msg", result.get("msg", "安全护栏返回失败")))
        return result.get("ret_data") or result.get("data") or result

    async def input_content_analyze_async(self, query: str, **kwargs):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        body = {"query": query, "templateId": self.template_id, "stream": bool(kwargs.pop("stream", False))}
        body.update({"historyQA": kwargs["history_qa"]} if kwargs.get("history_qa") is not None else {})
        body.update({"appid": kwargs["appid"]} if kwargs.get("appid") else {})
        body.update({"userId": kwargs["user_id"]} if kwargs.get("user_id") else {})
        body.update({"extraInfo": kwargs["extra_info"]} if kwargs.get("extra_info") else {})
        return await self._post_async(self.INPUT_PATH, body)

    async def output_content_analyze_async(self, content: str, req_id: str, is_first: int = 1, **kwargs):
        if not content or not req_id or is_first not in (1, 2):
            raise ValueError("content, req_id and is_first (1 or 2) are required")
        body = {"content": content, "reqId": req_id, "isFirst": is_first, "templateId": self.template_id}
        return await self._post_async(self.OUTPUT_PATH, body)

    async def _post_async(self, path, body):
        url, params, headers = self._build(path, body)
        own = self.client is None
        http = self.client or httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await http.post(url, params=params, headers=headers, json=body)
            resp.raise_for_status(); result = resp.json()
        except Exception as exc:
            raise GuardrailError(f"安全护栏请求失败: {exc}") from exc
        finally:
            if own: await http.aclose()
        if str(result.get("ret_code", result.get("code", 0))) != "0":
            raise GuardrailError(result.get("ret_msg", result.get("msg", "安全护栏返回失败")))
        return result.get("ret_data") or result.get("data") or result

    analyze_input = input_content_analyze_async
    analyze_output = output_content_analyze_async

    # ---------- 4.5 输出内容分析 ----------
    def output_content_analyze(self, content: str, req_id: str,
                               is_first: int = 1,
                               appid: str = None,
                               user_id: str = None,
                               extra_info: dict = None):
        """
        :param content:  输出内容切片（建议 100-500 token 送审一次，最大 8K）
        :param req_id:   输入接口返回的 request_id，用于关联两次请求
        :param is_first: 1=大模型输出首段，2=非首段
        """
        body = {
            "content": content,
            "isFirst": is_first,
            "reqId": req_id,
            "templateId": self.template_id,
        }
        if appid:
            body["appid"] = appid
        if user_id:
            body["userId"] = user_id
        if extra_info:
            body["extraInfo"] = extra_info

        url, params, headers = self._build(self.OUTPUT_PATH, body)
        return self._post_sync(url, params, headers, body)

    # ---------- SSE 流式解析 ----------
    def _sse_post(self, url, params, headers, body):
        """解析 data:{...} 形式的 SSE 流，返回拼接后的完整代答内容"""
        import requests
        full_answer = []
        last = None
        with requests.post(url, params=params, headers=headers,
                           data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                           stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                payload = json.loads(line[len("data:"):])
                last = payload
                data = payload.get("ret_data", {})
                safe_chat = data.get("safeChat")
                if isinstance(safe_chat, dict):
                    full_answer.append(safe_chat.get("data", ""))
                    if safe_chat.get("end"):
                        break
        return {"raw": last, "answer": "".join(full_answer)}

