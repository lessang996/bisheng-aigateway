import asyncio
import logging
import hashlib
import json
from datetime import datetime, timezone
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



logger = logging.getLogger(__name__)

client = HTTPClient()

# Do not let a single completed report occupy an unbounded amount of Redis.
# The database remains the source of truth for chat history.
MAX_REPORT_CACHE_BYTES = 10 * 1024 * 1024


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


def _cache_size_bytes(events: list[dict[str, Any]]) -> int:
    return len(json.dumps(events, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


# ============================================================
# 工具函数
# ============================================================

async def get_or_create_principal(user,
  db: AsyncSession):
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
    username = user.get("name") if isinstance(user, dict) else getattr(user, "name", None)
    user_id = user.get("id") or user.get("sub") if isinstance(user, dict) else getattr(user, "id", None)
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
            "principalName": username or str(user_id),
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
      
        data = result.get("data") or {}
        principal_id = data.get("principalId") or data.get("principal_id")
   
        if principal_id is None:

            logger.error(
                "获取用户主体失败: %s",
                result,
            )
            raise HTTPException(
                status_code=502,
                detail="创建 principal 成功，但未获取到 principalId",
            )

        updated = await update_principal_id(
            db=db,
            username=username,
            principal_id=principal_id,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="当前用户不存在")

        return principal_id




# ============================================================
# POST /api/industry/report
# ============================================================

async def industry_report(
    data: IndustryReportRequest,
    request: Request,
    user: dict,
    db: AsyncSession,
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
    claims = user or {}
    user_id = str(claims.get("sub") or claims.get("id") or "anonymous")
    user_name = str(claims.get("name") or claims.get("username") or "anonymous")
    user_department = claims.get("department")
    request_time = datetime.now(timezone.utc).isoformat()

    # Create/reuse a local conversation before any upstream work.  Every API
    # invocation gets one user message; the assistant message is appended
    # after the stream has completed.

    session = None
    if data.sessionId:
        session = (await db.execute(select(ChatSession).where(
            ChatSession.id == data.sessionId, ChatSession.user_id == user_id,
        ))).scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    if session is None:
        session = ChatSession(
            user_id=user_id,
            user_department=user_department,
            biz_key=data.bizKey,
            title=data.userInput[:255],
            status="active",
            session_type="ai_agent",
            metadata_json={
                "created_by": user_name,
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
        user_id=user_id,
        user_department=user_department,
        category="question",
        status="completed",
        metadata_json={
            "source": "industry_report",
            "user_name": user_name,
            "biz_key": data.bizKey,
            "agent_id": data.agentId or settings.agent_id,
            "request_time": request_time,
        },
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    local_session_id, user_message_id = session.id, user_message.id

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
                user_id=user_id,
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
                "user_id": user_id,
            })

    
    params_hash = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cache_key = f"report:{user_id}:{params_hash}"
    cache = getattr(request.app.state, "redis", None)
    try:
        cached_events = await cache.get_json(cache_key) if cache else None
    except Exception:
        cached_events = None
        logger.warning("redis cache read failed", extra={"user_id": user_id, "cache_key": cache_key}, exc_info=True)
    if cached_events:     
        async def cached_stream():
            cached_text: list[str] = []
            for event in cached_events:
                if isinstance(event, dict):
                    cached_text.append(_event_text(str(event.get("data", ""))))
                yield event
            await persist_assistant_message(
                "".join(cached_text),
                f"cache:{params_hash}",
                role="redis_cache",
                metadata={
                    "source": "redis_cache",
                    "cache_hit": True,
                    "cache_key": cache_key,
                },
            )
        return EventSourceResponse(cached_stream(), ping=360, headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no", "X-Session-Id": str(local_session_id), "X-User-Message-Id": str(user_message_id)})
    
    guard = SafetyGuard(settings)

    if settings.safety_filter_enabled:
        try:
            logger.info("SafetyGuard input analysis for user_id=%s", user_id)
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

    try:
        principal_id = await get_or_create_principal(user, db)
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

    except Exception as exc:

        logger.exception(
            "agent/run/async request failed"
        )
        raise HTTPException(
            status_code=502,
            detail=f"提交分析任务失败: {exc}",
        )

    # ========================================================
    # 第三阶段：获取 requestId
    # ========================================================


      # ✅ 正确：用 [] 访问字典
    if async_result.get("success"):
        result_data = async_result.get("data") or {}
        request_id = result_data.get("requestId") or result_data.get("request_id")
    else:
        # 处理业务失败的情况
        logger.error(
            "Agent run failed: message=%s, status=%s",
            async_result.get("message"),
            async_result.get("httpStatusCode")
        )
  
    if request_id is None:
        raise HTTPException(
            status_code=502,
            detail="上游未返回 requestId",
        )

    # ========================================================
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
    }

    # ========================================================
    # SSE Generator
    # ========================================================

    async def events():
        cached_output: list[dict[str, Any]] = []
        output_text: list[str] = []

        started_at = time.monotonic()
        first_token_at: float | None = None

        completed = False
        cancelled = False
        error_message: str | None = None

        event_name: str | None = None
        event_id: str | None = None
        data_lines: list[str] = []

        async def flush_event():
            """
            将一个完整 SSE event 输出给客户端。
            """

            nonlocal event_name
            nonlocal event_id
            nonlocal data_lines
            nonlocal first_token_at

            if not data_lines:
                event_name = None
                event_id = None
                return

            event_data = "\n".join(data_lines)

            # 第一个有效数据到达时间
            if first_token_at is None:
                first_token_at = time.monotonic()

                logger.info(
                    "SSE first upstream data received",
                    extra={
                        "request_id": str(request_id),
                        "user_id": user_id,
                        "ttft_ms": round(
                            (first_token_at - started_at) * 1000,
                            2,
                        ),
                    },
                )

            output: dict[str, Any] = {
                "data": event_data,
            }

            if event_name:
                output["event"] = event_name

            if event_id:
                output["id"] = event_id

            cached_output.append(output)
            output_text.append(_event_text(event_data))

            yield output

            event_name = None
            event_id = None
            data_lines = []

        try:

            logger.info(
                "SSE upstream request started",
                extra={
                    "request_id": str(request_id),
                    "user_id": user_id,
                    "session_id": str(local_session_id),
                },
            )

            # ==========================================================
            # 上游 SSE
            # ==========================================================

            async with client.stream(
                "GET",
                stream_target,
                headers=stream_headers,
                params=stream_params,
            ) as response:

                if response.status_code >= 400:

                    body = await response.aread()

                    error_message = (
                        body.decode(
                            "utf-8",
                            errors="ignore",
                        )[:2000]
                    )

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

                # ======================================================
                # SSE parser
                # ======================================================
              
                async for line in response.aiter_lines():

                    # --------------------------------------------------
                    # 空行 = 一个 SSE Event 完成
                    # --------------------------------------------------
                    logger.debug(
                        "SSE upstream line",
                        extra={
                            "request_id": str(request_id),  
                            "line": line[:500], })
                    if line == "":
                        async for event in flush_event():
                            yield event

                        continue

                    # --------------------------------------------------
                    # SSE comment
                    # --------------------------------------------------

                    if line.startswith(":"):
                        continue

                    # --------------------------------------------------
                    # event:
                    # --------------------------------------------------

                    if line.startswith("event:"):

                        event_name = line[
                            len("event:"):
                        ].strip()

                        continue

                    # --------------------------------------------------
                    # id:
                    # --------------------------------------------------

                    if line.startswith("id:"):

                        event_id = line[
                            len("id:"):
                        ].strip()

                        continue

                    # --------------------------------------------------
                    # data:
                    # --------------------------------------------------

                    if line.startswith("data:"):

                        data_value = line[
                            len("data:"):
                        :].lstrip()

                        data_lines.append(data_value)

                        continue

                    # --------------------------------------------------
                    # retry:
                    # --------------------------------------------------

                    if line.startswith("retry:"):
                        continue

                    # --------------------------------------------------
                    # 未知 SSE 字段
                    # --------------------------------------------------

                    logger.debug(
                        "Unknown SSE line",
                        extra={
                            "request_id": str(request_id),
                            "line": line[:500],
                        },
                    )

                # ======================================================
                # 上游正常关闭前，处理最后一个 event
                # ======================================================

                if data_lines:

                    async for event in flush_event():
                        yield event

                completed = True

        except asyncio.CancelledError:

            cancelled = True

            logger.info(
                "SSE client disconnected",
                extra={
                    "request_id": str(request_id),
                    "user_id": user_id,
                    "session_id": str(local_session_id),
                },
            )

            # 必须继续抛出
            # 让 FastAPI / Starlette 正确结束请求
            raise

        except Exception as exc:

            error_message = str(exc)

            logger.exception(
                "SSE stream failed",
                extra={
                    "request_id": str(request_id),
                    "user_id": user_id,
                    "session_id": str(local_session_id),
                    "error": error_message,
                },
            )

            # 如果连接还没有被客户端取消，
            # 尝试通知客户端
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
                    "user_id": user_id,
                    "session_id": str(local_session_id),
                    "completed": completed,
                    "cancelled": cancelled,
                    "duration_ms": round(duration_ms, 2),
                    "ttft_ms": (
                        round(ttft_ms, 2)
                        if ttft_ms is not None
                        else None
                    ),
                    "event_count": len(cached_output),
                    "error": error_message,
                },
            )

            if completed and not cancelled:
                await persist_assistant_message(
                    "".join(output_text),
                    str(request_id),
                    role="assistant",
                    status="completed",
                    metadata={
                        "source": "upstream_sse",
                        "cache_hit": False,
                        "event_count": len(cached_output),
                        "text_length": sum(len(item) for item in output_text),
                        "duration_ms": round(duration_ms, 2),
                        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
                    },
                )

            # ==========================================================
            # Redis cache
            # ==========================================================

            if cache and completed and not cancelled and cached_output:
                cache_size = _cache_size_bytes(cached_output)
                if cache_size > MAX_REPORT_CACHE_BYTES:
                    logger.warning("Report SSE cache skipped because it is too large", extra={
                        "request_id": str(request_id),
                        "cache_key": cache_key,
                        "size_bytes": cache_size,
                    })
                else:
                    try:
                        await cache.set_json(
                            cache_key,
                            cached_output,
                            ttl=max(1, int(getattr(settings, "redis_cache_ttl", 86400) or 86400)),
                        )
                    except Exception:
                        logger.exception(
                            "Redis cache write failed",
                            extra={
                                "request_id": str(request_id),
                                "user_id": user_id,
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
