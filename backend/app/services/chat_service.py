import asyncio
import logging
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

from fastapi import HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.config import get_settings
from app.schemas import IndustryReportRequest
from app.utils.http_client import HTTPClient
from app.utils.safety_guard import SafetyGuard, SafetyGuardError
from app.services.user import get_principal, update_principal_id
from app.models.models import ChatSession, ChatMessage
from app.services.report_usage import track_report

logger = logging.getLogger(__name__)

# Do not let a single completed report occupy an unbounded amount of Redis.
# The database remains the source of truth for chat history.
MAX_REPORT_CACHE_BYTES = 10 * 1024 * 1024
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}
MAX_POLLS = 100         # 最大轮询次数，防止上游卡死时无限等待
POLL_INTERVAL = 5.0     # 轮询间隔（秒）；可改为指数退避，见下方说明

def _event_text(event_data: str) -> str:
    """Return only user-visible text from one upstream AgentEvent."""
    try:
        payload = json.loads(event_data)
    except (TypeError, json.JSONDecodeError):
        return ""

    if not isinstance(payload, dict):
        return ""
    event_data_payload = payload.get("data")
    if not isinstance(event_data_payload, dict):
        return ""
    if event_data_payload.get("type") != "text":
        return ""
    text = event_data_payload.get("text")
    return text if isinstance(text, str) else ""


def _is_message_completed(event_name: str | None, event_data: str) -> tuple[bool, dict[str, Any] | None]:
    """
    Only MESSAGE_COMPLETED + terminal=true + finishReason=STOP is treated
    as a normal upstream business completion.

    SSE EOF by itself is NOT a successful completion.
    """
    if event_name != "MESSAGE_COMPLETED":
        return False, None

    try:
        payload = json.loads(event_data)
    except (TypeError, json.JSONDecodeError):
        return False, None

    if not isinstance(payload, dict):
        return False, None

    if payload.get("terminal") is not True:
        return False, payload

    data = payload.get("data")
    if not isinstance(data, dict):
        return False, payload

    if data.get("finishReason") != "STOP":
        return False, payload

    return True, payload


def _cache_size_bytes(events: list[dict[str, Any]]) -> int:
    return len(json.dumps(events, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _response_text(payload: Any) -> str:
    """Extract visible text from a non-stream response for chat history."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "result", "output"):
                value = payload.get(key)
                text = _response_text(value)
                if text:
                    return text
        for key in ("text", "content", "answer", "assistantReply"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
     
    return ""


async def _collect_upstream_sse(
    client: HTTPClient,
    target: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any],
    request_id: str,
) -> str:
    """Consume an upstream SSE stream and return its visible text."""
    output_text: list[str] = []
    event_name: str | None = None
    data_lines: list[str] = []
    completed = False

    async def flush_event() -> None:
        nonlocal event_name, data_lines, completed
        if not data_lines:
            event_name = None
            return
        event_data = "\n".join(data_lines)
        is_completed, _ = _is_message_completed(event_name, event_data)
        completed = completed or is_completed
        output_text.append(_event_text(event_data))
        event_name = None
        data_lines = []

    try:
        async with client.stream(
            "GET", target, headers=headers, params=params,
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "上游流式接口请求失败: "
                        f"{body.decode('utf-8', errors='ignore')[:500]}"
                    ),
                )
            async for line in response.aiter_lines():
                logger.info(f"NO SSE upstream line - request_id={request_id} - line={line[:200]}",)
                if line == "":
                    await flush_event()
                elif line.startswith("event:"):
                    event_name = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:"):].lstrip())
                elif line.startswith((":", "id:", "retry:")):
                    continue

            if data_lines:
                await flush_event()
    except HTTPException:
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Non-stream upstream SSE failed",
            extra={"request_id": str(request_id)},
        )
        raise HTTPException(status_code=502, detail="获取行业分析结果失败") from exc

    if not completed:
        logger.warning(f"Upstream SSE stream ended without MESSAGE_COMPLETED - request_id={request_id}")
        raise HTTPException(
            status_code=502,
            detail="上游流式接口未正常完成",
        )
    return "".join(output_text)


# ============================================================
# 工具函数
# ============================================================

async def get_or_create_principal(user,
  db: AsyncSession,
  client: HTTPClient):
    """
    根据当前登录用户获取 principal_id。

    流程：

        1. 查询本地数据库
        2. 如果存在 principal_id，直接返回
        3. 如果不存在，调用上游 /principal/create
        4. 获取 principal_id
        5. 保存到本地数据库
        6. 返回 principal_id

    注意：
    下面的数据库查询/保存部分需要替换成你项目实际的 ORM / Service。
    """
    settings = get_settings()
    username = user.get("userNo") if isinstance(user, dict) else getattr(user, "name", None)
    user_id = user.get("userNo") or user.get("userNo") if isinstance(user, dict) else getattr(user, "id", None)
    if not username:
        username = str(user_id or "anonymous")
    #获取用户主体信息
    principal = await get_principal(db, username)
           
    if principal is not None and  principal.principal_id is not None:
        principal_id = principal.principal_id
        return principal_id
    else:
        target = (
            f"{settings.external_api_url.rstrip('/')}"
            "/principal/create"
        )
        payload = {
            "principalName": str(username) or str(user_id),
        }
        try:
            resp = await client.post(
                target,
                json=payload,
            )

            if resp.status_code >= 400:
                logger.error(
                    "principal create failed status=%s body=%s",
                    resp.status_code,
                    resp.text,
                )
                raise HTTPException(
                    status_code=502,
                    detail="创建 principal 失败",
                )
            result = resp.json()

        except HTTPException:
            raise

        except Exception as exc:
            logger.exception(
                "principal create request failed"
            )

            raise HTTPException(
                status_code=502,
                detail="创建 principal 请求失败",
            )

        logger.info(f"创建主体成功，{result}")
        data = result.get("data") or {}
        principal_id = data.get("principalId") or data.get("principal_id")
   
        if principal_id is None:
            raise HTTPException(
                status_code=502,
                detail="创建 principal 成功，但未获取到 principalId",
            )

        updated = await update_principal_id(
            db=db,
            username=username,
            principal_id=principal_id,
        )
        logger.info(f"user 更新识别{updated}")
        if updated is None:
            raise HTTPException(status_code=404, detail="当前用户不存在")

        return principal_id



# ============================================================
# POST /api/industry/report
# ============================================================

@track_report
async def industry_report(
    data: IndustryReportRequest,
    request: Request,
    user: dict,
    db: AsyncSession,
    client: HTTPClient

):
    """
    企业行业分析统一接口。

    前端只需要调用这一个接口。

    内部流程：

        1. 根据用户获取 principal_id
        2. 不存在则创建 principal
        3. 调用 /agent/run/async
        4. 获取 requestId
        5. 调用 /agent/run/stream
        6. 将 SSE 原样转发给前端
    """
    
    settings = get_settings()
    usage = request.state.report_usage
    claims = user or {}
    userNo = str(claims.get("userNo") or claims.get("userNo") or "anonymous")
    user_department = claims.get("org")
    request_time = datetime.now(timezone.utc).isoformat()

    # Create/reuse a local conversation before any upstream work.  Every API
    # invocation gets one user message; the assistant message is appended
    # after the stream has completed.

    session = None
    if data.sessionId:
        session = (await db.execute(select(ChatSession).where(
            ChatSession.id == data.sessionId, ChatSession.user_id == userNo,
        ))).scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    if session is None:
        session = ChatSession(
            user_id=userNo,
            local_user_id=claims.get("local_user_id"),
            user_department=user_department,
            biz_key=data.bizKey,
            title=data.userInput[:255],
            status="active",
            session_type="ai_agent",
            metadata_json={
                "created_by": userNo,
                "created_at": request_time,
                "source": "industry_report",
            },
        )
        db.add(session)
        await db.flush()
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=data.userInput,
        message_type="text",
        user_id=userNo,
        user_department=user_department,
        local_user_id=claims.get("local_user_id"),
        business_type="industry_report",
        is_stream=data.stream,
        execution_status="processing",
        category="question",
        status="completed",
        metadata_json={
            "source": "industry_report",
            "user_name": userNo,
            "biz_key": data.bizKey,
            "agent_id": data.agentId or settings.agent_id,
            "request_time": request_time,
        },
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    local_session_id, user_message_id = session.id, user_message.id
    usage.message_id = user_message_id

    async def persist_assistant_message(
        content: str,
        request_id: str,
        role: str = "assistant",
        *,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not content:
            return
        try:

            db.add(ChatMessage(
                session_id=local_session_id,
                role=role,
                content=content,
                message_type="text",
                user_id=userNo,
                local_user_id=claims.get("local_user_id"),
                user_department=user_department,
                category="answer",
                parent_id=user_message_id,
                request_id=str(request_id),
                status=status,
                metadata_json=metadata or {},
            ))
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Failed to persist assistant message", extra={
                "request_id": request_id,
                "user_id": userNo,
            })

    question_hash = hashlib.sha256(
        data.userInput.encode("utf-8")
    ).hexdigest()
    protocol = "stream" if data.stream else "nonstream"
    cache_key = f"industry_report:{question_hash}:{protocol}"
    cache = getattr(request.app.state, "redis", None)
    cache_ttl = max(1, int(getattr(settings, "redis_cache_ttl", 86400) or 86400))

    async def store_cache(value: Any) -> None:
        if not cache:
            return
        try:
            await cache.set_json(cache_key, value, ttl=cache_ttl)
        except Exception:
            logger.exception(
                "Redis cache write failed",
                extra={"user_id": userNo, "cache_key": cache_key},
            )

    usage.cache_status = "miss" if cache else "unavailable"
    try:
        cached_result = await cache.get_json(cache_key) if cache else None
    except Exception:
        usage.cache_status = "error"
        cached_result = None
        logger.warning("redis cache read failed", extra={"user_id": userNo, "cache_key": cache_key}, exc_info=True)
    valid_cache = (data.stream and isinstance(cached_result, list)) or (not data.stream and isinstance(cached_result, dict))
    if cached_result is not None and valid_cache:
        usage.cache_status = "hit"
        usage.request_id = f"cache:{question_hash}"
    await usage.write()
    if cached_result is not None and data.stream and isinstance(cached_result, list):
        async def cached_stream():
            cached_text: list[str] = []
            for event in cached_result:
                if isinstance(event, dict):
                    cached_text.append(_event_text(str(event.get("data", ""))))
                yield event
            if any(_is_message_completed(e.get("event"), str(e.get("data", "")))[0] for e in cached_result if isinstance(e, dict)):
                usage.result("success")
            await persist_assistant_message(
                "".join(cached_text),
                f"cache:{question_hash}",
                role="redis_cache",
                metadata={
                    "source": "redis_cache",
                    "cache_hit": True,
                    "cache_key": cache_key,
                },
            )
        logger.info(f"Cache hit for stream request: {cache_key}")
        return EventSourceResponse(cached_stream(), ping=360, headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no", "X-Session-Id": str(local_session_id), "X-User-Message-Id": str(user_message_id)})

    if cached_result is not None and not data.stream and isinstance(cached_result, dict):
        logger.info(f"Cache hit for non-stream request: {cache_key}")
        await persist_assistant_message(
            _response_text(cached_result),
            f"cache:{question_hash}",
            role="redis_cache",
            metadata={
                "source": "redis_cache",
                "cache_hit": True,
                "cache_key": cache_key,
            },
        )
        usage.result("success")
        return cached_result
    
    usage.stage = "safety"
    guard = SafetyGuard(settings)

    if settings.safety_filter_enabled:
        try:
            result = await guard.analyze_input(data.userInput)
        except SafetyGuardError as exc:
            logger.exception("SafetyGuard input analysis failed")
            raise HTTPException(
                status_code=502,
                detail=f"安全审核服务调用失败: {exc}",
            ) from exc

        # 解析审核结果
        action = int(result.get("action") or 0)
        is_safe = int(result.get("isSafe") if result.get("isSafe") is not None else 1)

        # action != 0 或 isSafe == 0，均视为未通过审核
        if action != 0 or is_safe == 0:
            message = (
                result.get("defaultAnswer")
                or result.get("safeChat")
                or "输入内容未通过安全审核"
            )

            # 兼容 message 为 dict 的情况
            if isinstance(message, dict):
                message = (
                    message.get("data")
                    or message.get("message")
                    or "输入内容未通过安全审核"
                )

            raise HTTPException(
                status_code=400,
                detail=str(message),
            )


    # ========================================================
    # 第一阶段：获取 principal_id
    # ========================================================

       

    # 假设 cache 和 cache_ttl 已经在前面获取到了
    # cache = getattr(request.app.state, "redis", None)
    # cache_ttl = max(1, int(getattr(settings, "redis_cache_ttl", 86400) or 86400))

    # 1. 定义缓存 Key（使用冒号分隔的命名空间规范，便于后续管理和排查）
    usage.stage = "upstream"
    cache_userno = f"principal:{userNo}"

    # 2. 优先尝试从 Redis 缓存中获取 principal_id
    if cache:
        try:
            cached_principal_id = await cache.get_json(cache_userno)
        except Exception:
            cached_principal_id = None
        if cached_principal_id:
            # 缓存命中，直接反序列化并返回，跳过数据库查询
            principal_id =cached_principal_id
            logger.info(f"Redis 缓存命中 principal_id: {principal_id} for userNo: {userNo}")
        else:
            # 3. 缓存未命中，执行原有的数据库查询逻辑
            try:
                principal_id = await get_or_create_principal(user, db, client)
            except Exception as exc:    
                raise HTTPException(
                    status_code=500,
                    detail=f"获取 principal 失败: {exc}",
                )
            
            # 4. 将查询结果写入 Redis 缓存，并设置过期时间（防缓存雪崩）
            try:
                logger.info(f"写入 Redis 缓存 principal_id: {principal_id} for userNo: {userNo}")
                await cache.set_json(cache_userno, principal_id, ttl=cache_ttl)
            except Exception:
                # 缓存写入失败不应影响主业务流程，静默忽略或记录日志即可
                pass
    else:
        # 5. 兜底逻辑：如果 Redis 连接未初始化，直接走数据库查询
        try:
            principal_id = await get_or_create_principal(user, db, client)
        except Exception as exc:    
            raise HTTPException(
                status_code=500,
                detail=f"获取 principal 失败: {exc}",
            )


    # ========================================================
    # 第二阶段：调用 agent/run/async
    # ========================================================
   
    async_target = (
        f"{settings.external_api_url.rstrip('/')}"
        "/agent/run/async"
    )

    headers = {
        "X-Principal-Id": str(principal_id),
    
    }

    agent_payload = data.model_dump()

    # 自动设置 agentId
    if not agent_payload.get("agentId"):
        agent_payload["agentId"] = settings.agent_id

    # ========================================================
    # 将企业名称 + 行业分析报告传给 Agent
    # ========================================================

    agent_payload["userInput"] = data.userInput
    try:

        async_response = await client.post(
            async_target,
            json=agent_payload,
            headers=headers,
        )

        if async_response.status_code >= 400:
            logger.error(
                "agent/run/async failed status=%s body=%s",
                async_response.status_code,
                async_response.text,
            )
            raise HTTPException(
                status_code=502,
                detail="提交行业分析任务失败",
            )
        async_result = async_response.json()

    except HTTPException:
        raise

    except Exception as exc:

        logger.exception(
            "agent/run/async request failed"
        )
        raise HTTPException(
            status_code=502,
            detail=f"提交分析任务失败: {exc}",
        ) from exc

    # ========================================================
    # 第三阶段：获取 requestId
    # ========================================================


      # ✅ 正确：用 [] 访问字典
    request_id = None
    if async_result.get("success"):
        result_data = async_result.get("data") or {}
        request_id = result_data.get("requestId") or result_data.get("request_id")
        session_id =result_data.get("sessionId") 

    else:
        # 处理业务失败的情况
        logger.error(
            "Agent run failed: message=%s, status=%s",
            async_result.get("message"),
            async_result.get("httpStatusCode")
        )
  

    logger.info(f"agent/run/async result: {request_id}, {userNo}, {principal_id}")
    if request_id is None:
        raise HTTPException(
            status_code=502,
            detail="上游未返回 requestId",
        )
    
    usage.request_id = str(request_id)
    await usage.write()
    if not data.stream and not settings.nonstream_use:
        messages_target = (
            f"{settings.external_api_url.rstrip('/')}"
            "/agent/run/messages?requestId=" + str(request_id)
        )
        messages_headers = {
            "X-Principal-Id": str(principal_id),
      
        }

        async def _fetch_once():
            """发起一次 run/messages 查询，返回解析后的 messages_result(dict)。"""
            messages_response = await client.get(
                messages_target,
                headers=messages_headers,
            )
            logger.info(
                f"run/messages response: {messages_response.status_code},{messages_target}"
            )
            if messages_response.status_code >= 400:
                logger.error(
                    "run/messages failed status=%s body=%s",
                    messages_response.status_code,
                    messages_response.text,
                )
                raise HTTPException(status_code=502, detail="获取行业分析结果失败")
            messages_result = messages_response.json()
            logger.info(f"run/messages result: {messages_result}")
            return messages_result

        try:
            # 1) 首次查询
            messages_result = await _fetch_once()

            # 2) 取出运行状态，判断是否已终结
            result_data = (
                messages_result.get("data")
                if isinstance(messages_result, dict) else None
            )
            run_status = (
                result_data.get("status")
                if isinstance(result_data, dict) else None
            )

            # 3) 非终态则轮询，直到 COMPLETED / FAILED / CANCELLED 或达到上限
            poll_count = 0
            while run_status not in TERMINAL_STATUSES and poll_count < settings.max_polls:
                poll_count += 1
                await asyncio.sleep(settings.poll_interval)

                messages_result = await _fetch_once()
                result_data = (
                    messages_result.get("data")
                    if isinstance(messages_result, dict) else None
                )
                run_status = (
                    result_data.get("status")
                    if isinstance(result_data, dict) else None
                )
                logger.info(
                    f"run/messages poll #{poll_count}: requestId={request_id}, "
                    f"status={run_status}"
                )

            # 4) 轮询到上限仍未终态：明确告警，避免把"未结束"误当成"无结果"
            if run_status not in TERMINAL_STATUSES:
                logger.warning(
                    "run/messages 轮询 %s 次仍未终态, requestId=%s, last_status=%s",
                    settings.max_polls, request_id, run_status,
                )
                # 按业务需要二选一：
                # A. 视为超时失败：
                # raise HTTPException(status_code=504, detail="获取分析结果超时，请稍后重试")
                # B. 容忍返回当前进度：继续往下走（此时 assistantReply 可能为空）

            # 5) 终态但异常终止：单独记录，避免和"正常空回复"混淆
            if run_status in ("FAILED", "CANCELLED"):
                logger.error(
                    "run/messages 运行异常终止, requestId=%s, status=%s, errCode=%s",
                    request_id, run_status,
                    (result_data or {}).get("errCode"),
                )

            # 6) COMPLETED 但 assistantReply 仍为空时给出提示（便于排查非 TEXT 结尾的运行）
            if run_status == "COMPLETED":
                reply = (result_data or {}).get("assistantReply")
                if not reply:
                    logger.warning(
                        "run/messages COMPLETED 但 assistantReply 为空, requestId=%s",
                        request_id,
                    )

        except HTTPException as exc:
            logger.error("run/messages request failed: %s", exc.detail)
            raise
        except Exception as exc:
            logger.error("run/messages request failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"获取分析结果失败: {exc}") from exc

        # 7) 以下落库与返回逻辑保持原样，复用最后一次轮询到的 messages_result
        request_id_value = "nonstream"
        if isinstance(messages_result, dict):
            result_data = messages_result.get("data")
            if isinstance(result_data, dict):
                request_id_value = str(
                    result_data.get("requestId")
                    or result_data.get("request_id")
                    or request_id_value
                )
        await persist_assistant_message(
            _response_text(messages_result),
            request_id_value,
            metadata={"source": "upstream_nonstream", "cache_hit": False},
        )
        if run_status == "COMPLETED":
            usage.result("success")
            await store_cache(messages_result)
        elif run_status == "CANCELLED":
            usage.result("interrupted", "UPSTREAM_CANCELLED", "上游取消任务")
        elif run_status == "FAILED":
            usage.result("failed", "UPSTREAM_FAILED", "上游任务失败")
        else:
            usage.result("failed", "POLL_TIMEOUT", "查询结果超时，未确认任务完成")
        logger.info("run/messages final result: %s", messages_result)
        return messages_result

    if not data.stream and settings.nonstream_use:
        stream_target = (
            f"{settings.external_api_url.rstrip('/')}"
            "/agent/run/stream"
        )
        stream_headers = {
            "X-Principal-Id": str(principal_id),
            "Accept": "text/event-stream",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
        }
        text = await _collect_upstream_sse(
            client,
            stream_target,
            headers=stream_headers,
            params={"requestId": request_id},
            request_id=str(request_id),
        )
        messages_result = {
            "success": True,
            "data": {
                "requestId": str(request_id),
                "assistantReply": text,
            },
        }

        await persist_assistant_message(
            text,
            str(request_id),
            metadata={
                "source": "upstream_sse_nonstream",
                "cache_hit": False,
            },
        )
        usage.result("success")
        await store_cache(messages_result)
        logger.info("non-stream upstream SSE final result: %s", messages_result)
        return messages_result

    # =============== =========================================
    # 第四阶段：通过 requestId 建立 SSE
    # ========================================================

    stream_target = (
        f"{settings.external_api_url.rstrip('/')}"
        "/agent/run/stream"
    )

    stream_params = {
        "requestId": request_id,
    }

    stream_headers = {
        "X-Principal-Id": str(principal_id),
        "Accept": "text/event-stream",
        "Accept-Encoding": "identity",  
        "Cache-Control": "no-cache",
    }

    # ========================================================
    # SSE Generator
    # ========================================================

    async def events():
        cached_output: list[dict[str, Any]] = []
        output_text: list[str] = []

        started_at = time.monotonic()
        first_token_at: float | None = None

        # IMPORTANT:
        # EOF is not completion. Only MESSAGE_COMPLETED + terminal=true
        # + finishReason=STOP is considered a normal business completion.
        completed = False
        message_completed = False
        cancelled = False
        error_message: str | None = None

        event_name: str | None = None
        event_id: str | None = None
        data_lines: list[str] = []

        event_count = 0
        duplicate_message_completed = 0

        async def flush_event():
            """
            Flush one complete SSE event to the downstream client.

            The completion state is decided BEFORE yielding the event so that
            the finally block can reliably distinguish normal completion from
            a transport-level EOF/disconnect.
            """
            nonlocal event_name
            nonlocal event_id
            nonlocal data_lines
            nonlocal first_token_at
            nonlocal message_completed
            nonlocal completed
            nonlocal event_count
            nonlocal duplicate_message_completed

            if not data_lines:
                event_name = None
                event_id = None
                return

            event_data = "\n".join(data_lines)
            current_event_name = event_name
            current_event_id = event_id

            event_count += 1

            # Parse the actual business completion event.
            is_completed, payload = _is_message_completed(
                current_event_name,
                event_data,
            )

            if is_completed:
                if message_completed:
                    duplicate_message_completed += 1
                    logger.warning(
                        "Duplicate MESSAGE_COMPLETED received",
                        extra={
                            "request_id": str(request_id),
                            "event_id": current_event_id,
                            "duplicate_count": duplicate_message_completed,
                        },
                    )
                else:
                    message_completed = True
                    completed = True

                    payload_data = (
                        payload.get("data")
                        if isinstance(payload, dict)
                        else {}
                    )
                    if not isinstance(payload_data, dict):
                        payload_data = {}

                    logger.info(
                        "SSE MESSAGE_COMPLETED received",
                        extra={
                            "request_id": str(request_id),
                            "event_id": current_event_id,
                            "message_id": payload_data.get("messageId"),
                            "finish_reason": payload_data.get("finishReason"),
                            "terminal": payload.get("terminal"),
                            "step": payload.get("step"),
                            "total_tokens": payload.get("totalTokens"),
                        },
                    )

            # First upstream data, not necessarily the first visible text token.
            if first_token_at is None:
                first_token_at = time.monotonic()

                logger.info(
                    "SSE first upstream data received",
                    extra={
                        "request_id": str(request_id),
                        "user_id": userNo,
                        "ttft_ms": round(
                            (first_token_at - started_at) * 1000,
                            2,
                        ),
                    },
                )

            output: dict[str, Any] = {
                "data": event_data,
            }

            if current_event_name:
                output["event"] = current_event_name

            if current_event_id:
                output["id"] = current_event_id

            # Do not let HEARTBEAT events grow Redis cache forever.
            # We still forward them to the browser.
            if current_event_name != "HEARTBEAT":
                cached_output.append(output)

            visible_text = _event_text(event_data)
            if visible_text:
                output_text.append(visible_text)

            # Reset parser state before yielding. This prevents stale fields
            # from leaking into the next event if the downstream disconnects.
            event_name = None
            event_id = None
            data_lines = []

            yield output

        try:
            logger.info(
                "SSE_UPSTREAM_CONNECT",
                extra={
                    "request_id": str(request_id),
                    "user_id": userNo,
                    "session_id": str(local_session_id),
                },
            )

            async with client.stream(
                "GET",
                stream_target,
                headers=stream_headers,
                params=stream_params,
            ) as response:

                logger.info(
                    "SSE response headers",
                    extra={
                        "request_id": str(request_id),
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                    },
                )

                if response.status_code >= 400:
                    body = await response.aread()

                    error_message = body.decode(
                        "utf-8",
                        errors="ignore",
                    )[:2000]

                    logger.error(
                        "SSE upstream HTTP error",
                        extra={
                            "request_id": str(request_id),
                            "status_code": response.status_code,
                            "error": error_message,
                        },
                    )

                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {
                                "code": "UPSTREAM_HTTP_ERROR",
                                "message": "上游流式接口请求失败",
                                "status_code": response.status_code,
                            },
                            ensure_ascii=False,
                        ),
                    }

                    return

                async for line in response.aiter_lines():
                    logger.info(
                        f"SSE upstream line - request_id={request_id} - line={line[:200]}",
                    )
                    # Empty line terminates one SSE event.
                    if line == "":
                        async for event in flush_event():
                            yield event
                        continue

                    # SSE comment / heartbeat:
                    # ": ping ..."
                    if line.startswith(":"):
                        continue

                    if line.startswith("event:"):
                        event_name = line[len("event:"):].strip()
                        continue

                    if line.startswith("id:"):
                        event_id = line[len("id:"):].strip()
                        continue

                    if line.startswith("data:"):
                        data_value = line[len("data:"):].lstrip()
                        data_lines.append(data_value)
                        continue

                    if line.startswith("retry:"):
                        continue

                    logger.debug(
                        "Unknown SSE line",
                        extra={
                            "request_id": str(request_id),
                            "line": line[:500],
                        },
                    )

                # Process a final event if the upstream closed without the
                # usual blank line terminator.
                if data_lines:
                    async for event in flush_event():
                        yield event

                # CRITICAL:
                # Do NOT set completed=True here.
                # The upstream can close because of F5/nginx/TCP timeout,
                # proxy reset, application cancellation, etc.
                logger.info(
                    "SSE upstream EOF",
                    extra={
                        "request_id": str(request_id),
                        "message_completed": message_completed,
                        "completed": completed,
                        "event_count": event_count,
                        "cached_event_count": len(cached_output),
                    },
                )

                if not message_completed:
                    error_message = (
                        "upstream SSE closed before MESSAGE_COMPLETED"
                    )

                    logger.warning(
                        "SSE upstream closed before MESSAGE_COMPLETED",
                        extra={
                            "request_id": str(request_id),
                            "user_id": userNo,
                            "session_id": str(local_session_id),
                            "event_count": event_count,
                        },
                    )

        except asyncio.CancelledError:
            cancelled = True

            logger.info(
                "SSE client disconnected",
                extra={
                    "request_id": str(request_id),
                    "user_id": userNo,
                    "session_id": str(local_session_id),
                },
            )

            raise

        except Exception as exc:
            error_message = str(exc)

            logger.exception(
                "SSE stream failed",
                extra={
                    "request_id": str(request_id),
                    "user_id": userNo,
                    "session_id": str(local_session_id),
                    "error": error_message,
                },
            )

            try:
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {
                            "success": False,
                            "code": "SSE_STREAM_ERROR",
                            "message": "流式处理失败",
                        },
                        ensure_ascii=False,
                    ),
                }
            except Exception:
                logger.debug(
                    "Unable to send SSE error to client",
                    exc_info=True,
                )

        finally:
            duration_ms = (
                time.monotonic() - started_at
            ) * 1000

            ttft_ms = None
            if first_token_at is not None:
                ttft_ms = (
                    first_token_at - started_at
                ) * 1000

            logger.info(
                "SSE stream finished",
                extra={
                    "request_id": str(request_id),
                    "user_id": userNo,
                    "session_id": str(local_session_id),
                    "completed": completed,
                    "message_completed": message_completed,
                    "cancelled": cancelled,
                    "duration_ms": round(duration_ms, 2),
                    "ttft_ms": (
                        round(ttft_ms, 2)
                        if ttft_ms is not None
                        else None
                    ),
                    "event_count": event_count,
                    "cached_event_count": len(cached_output),
                    "duplicate_message_completed": duplicate_message_completed,
                    "error": error_message,
                },
            )

            if cancelled:
                usage.result("interrupted", "CLIENT_DISCONNECTED", "客户端中断请求")
            elif completed and message_completed:
                usage.result("success")
            else:
                usage.result("failed", "INCOMPLETE_STREAM", "上游未返回有效完成事件")

            # Persist only after a real upstream business completion.
            if completed and message_completed and not cancelled:
                await persist_assistant_message(
                    "".join(output_text),
                    str(request_id),
                    role="assistant",
                    status="completed",
                    metadata={
                        "source": "upstream_sse",
                        "cache_hit": False,
                        "event_count": event_count,
                        "cached_event_count": len(cached_output),
                        "duplicate_message_completed": duplicate_message_completed,
                        "text_length": sum(len(item) for item in output_text),
                        "duration_ms": round(duration_ms, 2),
                        "ttft_ms": (
                            round(ttft_ms, 2)
                            if ttft_ms is not None
                            else None
                        ),
                        "completion_event": "MESSAGE_COMPLETED",
                        "finish_reason": "STOP",
                    },
                )

            # Cache only a successfully completed report.
            if (
                cache
                and completed
                and message_completed
                and not cancelled
                and cached_output
            ):
                cache_size = _cache_size_bytes(cached_output)

                if cache_size > MAX_REPORT_CACHE_BYTES:
                    logger.warning(
                        "Report SSE cache skipped because it is too large",
                        extra={
                            "request_id": str(request_id),
                            "cache_key": cache_key,
                            "size_bytes": cache_size,
                        },
                    )
                else:
                    try:
                        await cache.set_json(
                            cache_key,
                            cached_output,
                            ttl=max(
                                1,
                                int(
                                    getattr(
                                        settings,
                                        "redis_cache_ttl",
                                        86400,
                                    )
                                    or 86400
                                ),
                            ),
                        )
                    except Exception:
                        logger.exception(
                            "Redis cache write failed",
                            extra={
                                "request_id": str(request_id),
                                "user_id": userNo,
                                "cache_key": cache_key,
                            },
                        )


    return EventSourceResponse(
        events(),
        # 下游 SSE 心跳
        ping=15,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",

            "X-Session-Id": str(
                local_session_id
            ),

            "X-User-Message-Id": str(
                user_message_id
            ),

            "X-Request-Id": str(
                request_id
            ),
        },
    )
