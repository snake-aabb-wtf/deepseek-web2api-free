"""
OpenAI-compatible API proxy for DeepSeek Chat
Supports streaming, tool calling (via DSML prompt injection), content parts, expert mode.
"""
import json
import os
import secrets
import sys
import threading
import time
import uuid
from typing import Optional, Union, Any

import uvicorn
from dotenv import load_dotenv
import os as _os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from adapter import (
    DeepSeekAdapter,
    UpstreamEmptyError,
    UpstreamHintError,
    RateLimitError,
    UserMutedError,
)
from admin import (
    router as admin_router,
    get_pool,
    get_stats,
    is_admin_password_weak,
    verify_admin_token,
)
from stats_history import start_sampler
from tool_dsml import (
    parse_dsml_tool_calls,
    format_tool_calls_for_prompt,
    build_dsml_tool_prompt,
)
from tool_sieve import StreamSieve, SieveEvent
from anthropic_format import (
    AnthropicRequest,
    build_anthropic_prompt,
    build_nonstream_response,
    stream_response,
    _msg_id,
)
from logger import get_logger, configure_from_env
from crypto import is_enabled as crypto_is_enabled
from token_counter import count_text
from rate_limiter import RateLimiter
from ip_utils import get_real_client_ip, is_trusted_proxy
from model_router import ModelRouter
from session_cache import SessionCache, ChatSession

load_dotenv()
configure_from_env()
log = get_logger("server")

MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-chat")
MODE = os.environ.get("MODE", "auto").strip().lower()
THINKING = os.environ.get("THINKING", "auto").strip().lower()
SEARCH = os.environ.get("SEARCH", "auto").strip().lower()
HOST = os.environ.get("HOST", "127.0.0.1").strip()
PORT = int(os.environ.get("PORT", "8080"))
ALLOW_UNAUTHENTICATED_API = os.environ.get("ALLOW_UNAUTHENTICATED_API", "false").strip().lower() in {"1", "true", "yes", "on"}
ALLOW_INSECURE_PUBLIC_DEFAULTS = os.environ.get("ALLOW_INSECURE_PUBLIC_DEFAULTS", "false").strip().lower() in {"1", "true", "yes", "on"}

# CORS allow-list. Empty = same-origin only.
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOW_CREDENTIALS = bool(ALLOWED_ORIGINS) and os.environ.get("ALLOW_CORS_CREDENTIALS", "false").strip().lower() in {"1", "true", "yes", "on"}


def _load_api_keys() -> list[str]:
    keys = []
    raw_keys = os.environ.get("API_KEYS", "")
    for item in raw_keys.split(","):
        item = item.strip()
        if item:
            keys.append(item)
    single_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if single_key:
        keys.append(single_key)

    deduped = []
    seen = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


API_KEYS = _load_api_keys()
RATE_LIMITER = RateLimiter()
MODEL_ROUTER = ModelRouter()
SESSION_CACHE = SessionCache()


def _extract_api_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key", "").strip()


def _client_ip(request: Request) -> str:
    """Resolve the real client IP, honouring XFF only when the peer is trusted."""
    peer = request.client.host if request.client else None
    return get_real_client_ip(request.headers, peer)


def _check_api_auth(request: Request):
    if ALLOW_UNAUTHENTICATED_API:
        return
    # A valid admin-session token is accepted too: the webui signs its
    # /v1 calls (model list, Playground) with the same bearer token that
    # authenticated the admin session, and anyone holding it already has
    # full control of the account pool.
    supplied = _extract_api_key(request)
    if supplied and verify_admin_token(supplied):
        return
    if not API_KEYS:
        raise HTTPException(status_code=503, detail="API key authentication is not configured")
    if not supplied:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not any(secrets.compare_digest(supplied, key) for key in API_KEYS):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _check_rate_limit(request: Request) -> dict:
    """Return a dict of rate-limit headers to merge into the response.

    Raises HTTPException(429) when the limit is exceeded.
    """
    api_key = _extract_api_key(request) or None
    ip = _client_ip(request)
    allowed, headers = RATE_LIMITER.check(api_key, ip)
    if not allowed:
        # Don't leak whether the key or the IP was the limit, to limit
        # username-enumeration. Same response regardless of dimension.
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Slow down and retry after the indicated time.",
            headers=headers,
        )
    return headers


app = FastAPI(title="DeepSeek Chat API (Expert Preview)", version="2.2.0")

# ── CORS ─────────────────────────────────────────────────────────────
# Empty ALLOWED_ORIGINS ⇒ same-origin only. We deliberately do NOT set
# `allow_origins=["*"]` with `allow_credentials=True` (spec violation; most
# browsers silently strip credentials).
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Default: strict same-origin. The middleware only does anything when
    # `allow_origins` is non-empty, so omitting it is safe.
    pass


# ── Security response headers ────────────────────────────────────────
@app.middleware("http")
async def _add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # WebUI gets an extra CSP; JSON APIs do not (SSE is not worth breaking).
    path = request.url.path
    if path.startswith("/webui") or path == "/webui":
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'",
        )
    return response


pool = get_pool()

# Start the rolling history sampler (v3 webui dashboard charts).
start_sampler(get_stats())

if pool.count() == 0:
    log.warning(
        "no_accounts_in_pool",
        extra={"hint": "Set DEEPSEEK_TOKEN and DEEPSEEK_COOKIES in .env"},
    )


# ── Startup safety checks ────────────────────────────────────────────
def _validate_startup() -> None:
    """Run fatal pre-flight checks; raise SystemExit on hard failures."""
    binding_public = HOST in {"0.0.0.0", "::"}  # noqa: S104 — by design
    weak_password = is_admin_password_weak()

    if binding_public and weak_password and not ALLOW_INSECURE_PUBLIC_DEFAULTS:
        msg = (
            "\n"
            "=" * 72 + "\n"
            "FATAL: Refusing to start with default admin password on a public bind.\n"
            f"  HOST={HOST} (public), DEEPSEEK_ADMIN_PASSWORD is unset or weak.\n"
            "  Fix one of:\n"
            "    1. Bind to loopback:  HOST=127.0.0.1 (recommended for dev).\n"
            "    2. Set a strong password:  DEEPSEEK_ADMIN_PASSWORD=<random>.\n"
            "    3. Acknowledge risk explicitly:\n"
            "         ALLOW_INSECURE_PUBLIC_DEFAULTS=true\n"
            "       (only do this behind a reverse proxy that already enforces auth.)\n"
            "=" * 72 + "\n"
        )
        sys.stderr.write(msg)
        sys.stderr.flush()
        raise SystemExit(2)

    if binding_public and not ALLOWED_ORIGINS:
        log.warning(
            "cors_strict_default_in_effect",
            extra={
                "host": HOST,
                "hint": "Set ALLOWED_ORIGINS=https://app.example.com for browser access.",
            },
        )

    if not crypto_is_enabled() and pool.count() > 0:
        log.warning(
            "credentials_stored_in_plaintext",
            extra={
                "hint": (
                    "Set DEEPSEEK_ENCRYPTION_KEY to encrypt data/accounts.json. "
                    "Generate one with: python -c \"from cryptography.fernet "
                    "import Fernet; print(Fernet.generate_key().decode())\""
                ),
            },
        )

    if weak_password:
        log.warning("admin_password_is_weak", extra={"host": HOST})

    log.info(
        "startup_ok",
        extra={
            "host": HOST,
            "port": PORT,
            "accounts": pool.count(),
            "crypto_enabled": crypto_is_enabled(),
            "cors_origins": len(ALLOWED_ORIGINS),
            "allow_unauthenticated_api": ALLOW_UNAUTHENTICATED_API,
        },
    )


# ---- Pydantic models ----

class ContentPart(BaseModel):
    type: str
    text: Optional[str] = None


class FunctionCall(BaseModel):
    name: str
    arguments: str  # JSON string


class ToolCall(BaseModel):
    id: str
    type: str = "function"
    function: FunctionCall


class ChatMessage(BaseModel):
    role: str
    content: Optional[Union[str, list[ContentPart]]] = None
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None


class FunctionDef(BaseModel):
    name: str
    description: Optional[str] = ""
    parameters: Optional[dict] = None


class ToolDef(BaseModel):
    type: str = "function"
    function: FunctionDef


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = MODEL_NAME
    messages: list[ChatMessage]
    stream: Optional[bool] = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    tools: Optional[list[ToolDef]] = None
    tool_choice: Optional[Union[str, dict]] = None
    # Expert mode
    thinking_mode: Optional[bool] = False
    search_enabled: Optional[bool] = False


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "deepseek"


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


# ---- Account pool helpers ----

class AcquiredAccount:
    """Context manager wrapping an acquired pool account."""
    def __init__(self, acct, cache_key: str | None = None):
        self.acct = acct
        self.adapter = acct.adapter
        self._session_id: str | None = None
        self._parent_message_id: int | None = None
        self._cache_key = cache_key
        self._cached_session: ChatSession | None = None
        self._released = False
        # If we have a cache key, try to reuse the existing session first.
        if cache_key:
            self._cached_session = SESSION_CACHE.get(cache_key)

    def create_session(self) -> str:
        # Reuse the cached session if we have one — multi-turn support.
        if self._cached_session is not None:
            self._session_id = self._cached_session.chat_session_id
            self._parent_message_id = self._cached_session.parent_message_id
            return self._session_id
        ds_id = self.adapter.create_session()
        self._session_id = ds_id
        if self._cache_key:
            sess = ChatSession(chat_session_id=ds_id)
            SESSION_CACHE.put(self._cache_key, sess)
            # Keep the live reference so record_message_id() can update the
            # parent id in place (the cache stores the same object).
            self._cached_session = sess
        return ds_id

    def prepare_prompt(self, full_prompt: str) -> str:
        """Return the prompt to send upstream.

        On a reused cached session this may be an incremental *tail* (only
        the new user turn) via ``delta_prompt`` — the parent chain keeps the
        context server-side. Resending the full history on every turn would
        make the DeepSeek conversation embed previous turns repeatedly
        (quadratic growth, bot-spam signature).

        Call *before* ``create_session()``: when the history diverges from
        what was previously sent, the cached session is invalidated so the
        next ``create_session()`` starts a fresh chain.
        """
        cached = self._cached_session
        if self._cache_key and cached is not None and cached.sent_prompt:
            prev = cached.sent_prompt
            if full_prompt.startswith(prev) and full_prompt != prev:
                tail = full_prompt[len(prev):].lstrip("\n ")
                if tail:
                    return tail
            if not full_prompt.startswith(prev):
                # Divergent history — abandon the cached chain entirely
                # instead of duplicating it under a mismatched parent.
                SESSION_CACHE.invalidate(self._cache_key)
                self._cached_session = None
                self._parent_message_id = None
        return full_prompt

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            raise RuntimeError("No session created")
        return self._session_id

    @property
    def parent_message_id(self) -> int | None:
        """Return the current parent_message_id for the cached session, or None
        for a fresh session (caller should treat as a new conversation).
        """
        return self._parent_message_id

    def record_message_id(self, mid: int, session_id: str | None = None,
                          full_prompt: str = "") -> None:
        """After a successful turn, record the upstream response message id
        (and the session that actually answered) into the cache so the next
        turn sends the correct ``parent_message_id``.

        Fixes the v3.2.2 leftover: previously never called, so a reused
        cached session sent ``parent_message_id=0`` on the second turn and
        the upstream replied with an empty body.
        """
        if not self._cache_key:
            return
        sess = self._cached_session
        if sess is None:
            sess = SESSION_CACHE.get(self._cache_key)
        if sess is None:
            sess = ChatSession(chat_session_id=session_id or "")
            SESSION_CACHE.put(self._cache_key, sess)
        if session_id:
            sess.chat_session_id = session_id
        sess.parent_message_id = mid
        if full_prompt:
            sess.sent_prompt = full_prompt
        self._cached_session = sess

    def release(self):
        if self._released:
            return
        self._released = True
        pool.release(self.acct)
        _UPSTREAM_LIMITER.release()


def _acquire(cache_key: str | None = None) -> AcquiredAccount:
    # Global upstream concurrency cap (e.g. coding agents spawning parallel
    # sub-agents). Wait for a slot before grabbing a pool account so queued
    # requests don't hold accounts busy.
    _UPSTREAM_LIMITER.acquire()
    try:
        acct = pool.acquire()
    except Exception:
        _UPSTREAM_LIMITER.release()
        raise
    if acct is None:
        _UPSTREAM_LIMITER.release()
        raise HTTPException(status_code=503, detail="All accounts busy, try again later")
    return AcquiredAccount(acct, cache_key=cache_key)


def _upstream_limit_from_env() -> int:
    try:
        return max(1, int(os.environ.get("DEEPSEEK_MAX_CONCURRENCY", "2")))
    except ValueError:
        return 2


_UPSTREAM_LIMITER = threading.BoundedSemaphore(_upstream_limit_from_env())


def _extract_openai_user(messages: list[ChatMessage], request: Request) -> str:
    """Derive a per-conversation cache key for the OpenAI endpoint.

    Strategy: combine the client IP (when trusted) with the SHA-256 of
    the first user-role message. The first-message hash is good enough
    stickiness for short conversations; clients that want a stronger
    identity should set the OpenAI ``user`` field (we don't model it
    directly in the request schema yet, so it lives in headers as
    ``X-Conversation-Id``).
    """
    cid = request.headers.get("X-Conversation-Id", "").strip()
    if cid:
        return f"hdr:{cid}"
    return SessionCache.derive_conversation_id(None, [m.model_dump() for m in messages], None)


def _extract_anthropic_user(req: AnthropicRequest, request: Request) -> str:
    cid = request.headers.get("X-Conversation-Id", "").strip()
    if cid:
        return f"hdr:{cid}"
    metadata = req.metadata or {}
    return SessionCache.derive_conversation_id(
        None, [m.model_dump() for m in req.messages], metadata
    )


# ---- Message / prompt building ----

def _extract_text(content: Union[str, list[ContentPart], None]) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return " ".join(
        p.text for p in content if p.type == "text" and p.text
    )


def _build_prompt(messages: list[ChatMessage], tools: list[ToolDef] | None = None,
                  tool_choice: str | dict | None = None) -> str:
    """Build a prompt string from messages, injecting tool definitions if present."""
    parts = []

    tool_prompt_text = None
    if tools:
        tool_prompt_text = build_dsml_tool_prompt([t.model_dump() for t in tools], tool_choice)

    has_system_message = any(m.role == "system" for m in messages)
    tool_injected = False

    for m in messages:
        if m.role == "system":
            text = _extract_text(m.content)
            if tool_prompt_text and not tool_injected:
                text = text + "\n\n" + tool_prompt_text if text else tool_prompt_text
                tool_injected = True
            if text:
                parts.append(f"System: {text}")
        elif m.role == "user":
            parts.append(f"User: {_extract_text(m.content)}")
        elif m.role == "assistant":
            segs = []
            text = _extract_text(m.content)
            if text:
                segs.append(text)
            if m.tool_calls:
                dsml = format_tool_calls_for_prompt([tc.model_dump() for tc in m.tool_calls])
                if dsml:
                    segs.append(dsml)
            if segs:
                parts.append(f"Assistant: {' '.join(segs)}")
        elif m.role == "tool":
            result = _extract_text(m.content)
            prefix = f"Tool result (call_id={m.tool_call_id}):" if m.tool_call_id else "Tool result:"
            parts.append(f"{prefix} {result[:1000]}")

    if tool_prompt_text and not has_system_message:
        parts.insert(0, f"System: {tool_prompt_text}")

    return "\n".join(parts)


# ---- OpenAI SSE helpers ----

def _openai_chunk(proxy_id: str, content: str = "", finish: bool = False,
                  reasoning_content: str = None, role: str = None) -> str:
    delta = {}
    if not finish:
        if role:
            delta["role"] = role
        if reasoning_content is not None:
            delta["reasoning_content"] = reasoning_content
        elif content:
            delta["content"] = content
    choice = {
        "index": 0,
        "delta": delta,
        "finish_reason": "stop" if finish else None,
    }
    chunk = {
        "id": proxy_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": MODEL_NAME,
        "choices": [choice],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _emit_tool_calls_chunks(tool_calls: list[dict], chat_id: str) -> list[str]:
    """生成 OpenAI 流式 tool_calls SSE 事件。"""
    chunks = []
    created = int(time.time())
    for i, tc in enumerate(tool_calls):
        # 首帧：id + name
        delta = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "index": i,
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["function"]["name"], "arguments": ""},
            }],
        }
        chunks.append(f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created, 'model': MODEL_NAME, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]}, ensure_ascii=False)}\n\n")
        # 次帧：arguments
        delta2 = {
            "tool_calls": [{
                "index": i,
                "function": {"arguments": tc["function"]["arguments"]},
            }],
        }
        chunks.append(f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created, 'model': MODEL_NAME, 'choices': [{'index': 0, 'delta': delta2, 'finish_reason': None}]}, ensure_ascii=False)}\n\n")
    # finish
    chunks.append(f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created, 'model': MODEL_NAME, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]}, ensure_ascii=False)}\n\n")
    return chunks


# ---- Extract tool names ----

def _get_tool_names(tools: list[ToolDef] | None) -> list[str]:
    names = []
    for t in tools or []:
        if t.function and t.function.name:
            names.append(t.function.name)
    return names


# ---- Response parsing for non-streaming ----

def _parse_response_for_tools(text: str, tool_names: list[str]) -> tuple[list[dict] | None, str]:
    """Parse response text for DSML tool calls. Returns (tool_calls, cleaned_text)."""
    return parse_dsml_tool_calls(text, tool_names)


# ---- Endpoints ----

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models(request: Request):
    _check_api_auth(request)
    rate_headers = _check_rate_limit(request)
    # Surface every model declared in MODEL_ROUTES; fall back to MODEL_NAME.
    names = MODEL_ROUTER.models or [MODEL_NAME]
    return JSONResponse(
        ModelList(data=[
            ModelInfo(id=name, created=int(time.time())) for name in names
        ]).model_dump(),
        headers=rate_headers,
    )


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    _check_api_auth(request)
    rate_headers = _check_rate_limit(request)
    proxy_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    prompt = _build_prompt(req.messages, req.tools, req.tool_choice)

    # Resolve model_type / thinking / search from MODEL_ROUTES first, then
    # MODE/THINKING/SEARCH env vars, then the per-request fields.
    decision = MODEL_ROUTER.route_for(req.model)

    # MODE controls model_type (quick → "default", expert → "expert")
    if decision.matched_model:
        model_type = decision.model_type
    elif MODE == "expert":
        model_type = "expert"
    else:
        model_type = "default"  # quick mode or auto, matches native request format

    # THINKING controls thinking_enabled independent of mode
    if decision.thinking is not None:
        thinking = decision.thinking
    elif THINKING == "enabled":
        thinking = True
    elif THINKING == "disabled":
        thinking = False
    else:
        thinking = req.thinking_mode or False

    # SEARCH controls search_enabled independently
    if decision.search is not None:
        search = decision.search
    elif SEARCH == "enabled":
        search = True
    elif SEARCH == "disabled":
        search = False
    else:
        search = req.search_enabled or False

    # Session cache keys are mode-scoped: reusing a session created by a
    # streamed call from a non-streaming call (or vice versa) makes the
    # upstream return an empty response. Same-mode multi-turn still works.
    openai_user = _extract_openai_user(req.messages, request)
    if req.stream:
        return await _handle_stream(proxy_id, prompt, req.tools, model_type=model_type, thinking_mode=thinking, search_enabled=search, rate_headers=rate_headers,
                                    cache_key=f"stream:{openai_user}")

    return _handle_nonstream(proxy_id, prompt, req.tools, model_type=model_type, thinking_mode=thinking, search_enabled=search,
                             cache_key=f"nonstream:{openai_user}")


# ---- Anthropic /v1/messages endpoint ----


@app.post("/v1/messages")
async def messages(req: AnthropicRequest, request: Request):
    _check_api_auth(request)
    rate_headers = _check_rate_limit(request)
    proxy_id = _msg_id()
    system_str = req.system
    if isinstance(system_str, list):
        system_str = " ".join(
            b.text for b in system_str if b.type == "text" and b.text
        )

    tools_dict = [t.model_dump() for t in req.tools] if req.tools else None
    prompt = build_anthropic_prompt(
        [m.model_dump() for m in req.messages],
        tools=tools_dict,
        system_str=system_str,
    )

    # Resolve model_type / thinking / search from MODEL_ROUTES first, then
    # MODE/THINKING/SEARCH env vars, then the per-request fields.
    decision = MODEL_ROUTER.route_for(req.model)

    # MODE controls model_type
    if decision.matched_model:
        model_type = decision.model_type
    elif MODE == "expert":
        model_type = "expert"
    else:
        model_type = "default"

    # THINKING — Anthropic thinking param maps to thinking_mode
    if decision.thinking is not None:
        thinking = decision.thinking
    elif THINKING == "enabled":
        thinking = True
    elif THINKING == "disabled":
        thinking = False
    else:
        thinking = (req.thinking is not None and req.thinking.type == "enabled") or False

    # SEARCH
    if decision.search is not None:
        search = decision.search
    elif SEARCH == "enabled":
        search = True
    elif SEARCH == "disabled":
        search = False
    else:
        search = False

    tool_names = []
    if req.tools:
        for t in req.tools:
            if t.name:
                tool_names.append(t.name)

    anth_user = _extract_anthropic_user(req, request)
    if req.stream:
        return await _anthropic_stream(proxy_id, prompt, tool_names,
                                       model_type=model_type, thinking_mode=thinking,
                                       search_enabled=search,
                                       rate_headers=rate_headers,
                                       cache_key=f"stream:{anth_user}")

    return _anthropic_nonstream(proxy_id, prompt, tool_names,
                                model_type=model_type, thinking_mode=thinking,
                                search_enabled=search,
                                cache_key=f"nonstream:{anth_user}")


def _anthropic_nonstream(msg_id: str, prompt: str, tool_names: list[str],
                         model_type: str | None = None,
                         thinking_mode: bool = False, search_enabled: bool = False,
                         cache_key: str | None = None):
    acq = _acquire(cache_key=cache_key)
    try:
        eff = acq.prepare_prompt(prompt)
        ds_id = acq.create_session()
        t0 = time.time()
        ready_out: dict = {}
        content, thinking = acq.adapter.chat(ds_id, eff, model_type=model_type,
                                              thinking_enabled=thinking_mode, search_enabled=search_enabled,
                                              parent_message_id=acq.parent_message_id,
                                              ready_out=ready_out)
        if ready_out.get("response_message_id") is not None:
            acq.record_message_id(ready_out["response_message_id"],
                                  ready_out.get("session_id"),
                                  full_prompt=prompt)
        get_stats().record(MODEL_NAME, (time.time() - t0) * 1000)
    except Exception as e:
        get_stats().record(MODEL_NAME, 0, success=False)
        if isinstance(e, (RateLimitError, UpstreamEmptyError)):
            if cache_key:
                SESSION_CACHE.invalidate(cache_key)
        else:
            pool.mark_error(acq.acct, str(e))
        raise
    finally:
        acq.release()

    tool_calls, cleaned = parse_dsml_tool_calls(content, tool_names)
    return build_nonstream_response(
        msg_id, MODEL_NAME,
        content_text=cleaned or content,
        tool_calls=tool_calls,
        thinking_text=thinking,
    )


async def _anthropic_stream(msg_id: str, prompt: str, tool_names: list[str],
                            model_type: str | None = None,
                            thinking_mode: bool = False, search_enabled: bool = False,
                            rate_headers: dict | None = None,
                            cache_key: str | None = None):
    acq = _acquire(cache_key=cache_key)
    try:
        eff = acq.prepare_prompt(prompt)
        ds_id = acq.create_session()
    except Exception as e:
        get_stats().record(MODEL_NAME, 0, success=False)
        pool.mark_error(acq.acct, str(e))
        acq.release()
        raise
    t0 = time.time()

    async def event_stream():
        nonlocal t0
        ready_out: dict = {}
        try:
            for event in stream_response(
                msg_id, MODEL_NAME,
                acq.adapter.chat_stream(ds_id, eff,
                                       model_type=model_type,
                                       thinking_enabled=thinking_mode,
                                       search_enabled=search_enabled,
                                       parent_message_id=acq.parent_message_id,
                                       ready_out=ready_out),
                tool_names,
                thinking_mode=thinking_mode,
            ):
                yield event
            if ready_out.get("response_message_id") is not None:
                acq.record_message_id(ready_out["response_message_id"],
                                      ready_out.get("session_id"),
                                      full_prompt=prompt)
            get_stats().record(MODEL_NAME, (time.time() - t0) * 1000)
        except Exception as e:
            get_stats().record(MODEL_NAME, (time.time() - t0) * 1000, success=False)
            if isinstance(e, (RateLimitError, UpstreamEmptyError)):
                if cache_key:
                    SESSION_CACHE.invalidate(cache_key)
            else:
                pool.mark_error(acq.acct, str(e))
            raise
        finally:
            acq.release()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            **(rate_headers or {}),
        },
    )


# ---- OpenAI handlers ----


def _handle_nonstream(proxy_id: str, prompt: str, tools: list[ToolDef] | None = None,
                      model_type: str | None = None,
                      thinking_mode: bool = False, search_enabled: bool = False,
                      cache_key: str | None = None):
    """Non-streaming completion with tool call detection."""
    prompt_tokens = count_text(prompt)
    acq = _acquire(cache_key=cache_key)
    try:
        eff = acq.prepare_prompt(prompt)
        ds_id = acq.create_session()
        t0 = time.time()
        ready_out: dict = {}
        content, thinking = acq.adapter.chat(ds_id, eff, model_type=model_type,
                                              thinking_enabled=thinking_mode, search_enabled=search_enabled,
                                              parent_message_id=acq.parent_message_id,
                                              ready_out=ready_out)
        if ready_out.get("response_message_id") is not None:
            acq.record_message_id(ready_out["response_message_id"],
                                  ready_out.get("session_id"),
                                  full_prompt=prompt)
        completion_tokens = count_text(content) + count_text(thinking)
        get_stats().record(MODEL_NAME, (time.time() - t0) * 1000,
                           prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    except RateLimitError as e:
        # Rate limiting is a transient upstream state, not a credential
        # problem — do NOT mark the account as errored, or the pool would
        # drain to 503 once the limiter cools down. Invalidate the cached
        # session so the next call starts fresh.
        get_stats().record(MODEL_NAME, 0, success=False)
        if cache_key:
            SESSION_CACHE.invalidate(cache_key)
        raise HTTPException(status_code=429, detail=f"上游限流：{e.args[0] if e.args else '请求过于频繁'}，请稍后重试")
    except UpstreamHintError as e:
        get_stats().record(MODEL_NAME, 0, success=False)
        pool.mark_error(acq.acct, str(e))
        raise HTTPException(status_code=502, detail=str(e))
    except UpstreamEmptyError as e:
        # Transient empty responses (stale pooled connection / upstream
        # hiccup) — retried in the adapter already; do not poison the pool.
        get_stats().record(MODEL_NAME, 0, success=False)
        if cache_key:
            SESSION_CACHE.invalidate(cache_key)
        raise HTTPException(status_code=502, detail="上游返回空响应（可能触发限流），请稍后重试")
    except Exception as e:
        get_stats().record(MODEL_NAME, 0, success=False)
        pool.mark_error(acq.acct, str(e))
        raise
    finally:
        acq.release()

    tool_names = _get_tool_names(tools)
    tool_calls, cleaned = _parse_response_for_tools(content, tool_names)
    total = prompt_tokens + count_text(cleaned or content)

    if tool_calls:
        return {
            "id": proxy_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": MODEL_NAME,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls,
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": count_text(cleaned),
                "total_tokens": total,
            },
        }

    return {
        "id": proxy_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_NAME,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": cleaned or content,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": count_text(cleaned or content),
            "total_tokens": total,
        },
    }


async def _handle_stream(proxy_id: str, prompt: str, tools: list[ToolDef] | None = None,
                         model_type: str | None = None,
                         thinking_mode: bool = False, search_enabled: bool = False,
                         rate_headers: dict | None = None,
                         cache_key: str | None = None):
    """Streaming completion with StreamSieve tool call detection and expert mode support."""
    prompt_tokens = count_text(prompt)
    acq = _acquire(cache_key=cache_key)
    try:
        eff = acq.prepare_prompt(prompt)
        ds_id = acq.create_session()
    except Exception as e:
        get_stats().record(MODEL_NAME, 0, success=False, prompt_tokens=prompt_tokens)
        pool.mark_error(acq.acct, str(e))
        acq.release()
        raise
    tool_names = _get_tool_names(tools)
    t0 = time.time()

    async def event_stream():
        nonlocal t0
        completion_parts: list[str] = []
        # Multi-turn: filled by adapter with the upstream response message id
        # (and the actual session id after a retry-swap). Recorded into the
        # session cache on success so the next turn has a valid parent.
        ready_out: dict = {}
        try:
            yield _openai_chunk(proxy_id, finish=False)
            role_sent = False

            def _parse_fn(text):
                return parse_dsml_tool_calls(text, tool_names)

            sieve = StreamSieve(parse_fn=_parse_fn)
            full_buf = ""

            def _record_turn():
                # Persist the upstream response message id (and the session
                # actually used, e.g. after an internal retry swap) so the
                # next turn's parent_message_id is valid.
                if ready_out.get("response_message_id") is not None:
                    acq.record_message_id(ready_out["response_message_id"],
                                          ready_out.get("session_id"),
                                          full_prompt=prompt)

            for token in acq.adapter.chat_stream(ds_id, eff,
                                                  model_type=model_type,
                                                  thinking_enabled=thinking_mode,
                                                  search_enabled=search_enabled,
                                                  parent_message_id=acq.parent_message_id,
                                                  ready_out=ready_out):
                if isinstance(token, dict):
                    tt = token.get("__type")
                    if tt == "status":
                        if token["status"] == "FINISHED":
                            break
                        continue
                    elif tt == "thinking":
                        content = token.get("content", "")
                        if content:
                            completion_parts.append(content)
                            if not role_sent:
                                yield _openai_chunk(proxy_id, reasoning_content="", role="assistant")
                                role_sent = True
                            yield _openai_chunk(proxy_id, reasoning_content=content)
                        continue

                # Normal text token (str) — feed to sieve
                full_buf += token
                for evt in sieve.feed(token):
                    if evt.type == "text":
                        if evt.data:
                            completion_parts.append(evt.data)
                            if not role_sent:
                                if thinking_mode:
                                    yield _openai_chunk(proxy_id, reasoning_content="")
                                yield _openai_chunk(proxy_id, content=evt.data, role="assistant")
                                role_sent = True
                            else:
                                yield _openai_chunk(proxy_id, content=evt.data)
                    elif evt.type == "tool_calls":
                        for chunk in _emit_tool_calls_chunks(evt.data, proxy_id):
                            yield chunk
                        _record_turn()
                        yield "data: [DONE]\n\n"
                        return

            # Flush sieve
            had_tool = False
            for evt in sieve.flush():
                if evt.type == "text" and evt.data:
                    completion_parts.append(evt.data)
                    if not role_sent:
                        if thinking_mode:
                            yield _openai_chunk(proxy_id, reasoning_content="")
                        yield _openai_chunk(proxy_id, content=evt.data, role="assistant")
                        role_sent = True
                    else:
                        yield _openai_chunk(proxy_id, content=evt.data)
                elif evt.type == "tool_calls":
                    had_tool = True
                    for chunk in _emit_tool_calls_chunks(evt.data, proxy_id):
                        yield chunk

            if had_tool:
                _record_turn()
                yield "data: [DONE]\n\n"
                return

            # Fallback: parse full buffer
            if not had_tool and full_buf:
                tc_result, _ = parse_dsml_tool_calls(full_buf, tool_names)
                if tc_result:
                    if not role_sent:
                        if thinking_mode:
                            yield _openai_chunk(proxy_id, reasoning_content="")
                        role_sent = True
                    for chunk in _emit_tool_calls_chunks(tc_result, proxy_id):
                        yield chunk
                    _record_turn()
                    yield "data: [DONE]\n\n"
                    return

            _record_turn()
            yield _openai_chunk(proxy_id, finish=True)
            yield "data: [DONE]\n\n"
            completion_tokens = count_text("".join(completion_parts))
            get_stats().record(MODEL_NAME, (time.time() - t0) * 1000,
                               prompt_tokens=prompt_tokens,
                               completion_tokens=completion_tokens)
        except Exception as e:
            get_stats().record(MODEL_NAME, (time.time() - t0) * 1000, success=False,
                               prompt_tokens=prompt_tokens)
            # Rate limit / transient empty responses are not credential
            # failures — keep the account usable instead of draining the pool.
            if isinstance(e, (RateLimitError, UpstreamEmptyError)):
                if cache_key:
                    SESSION_CACHE.invalidate(cache_key)
            else:
                pool.mark_error(acq.acct, str(e))
            log.exception("openai_stream_failed")
            # Emit a uniform error frame to the client, then [DONE] so the
            # client SDK doesn't see a truncated stream.
            err = {
                "id": proxy_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": MODEL_NAME,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "error",
                }],
                "error": {
                    "type": "upstream_error",
                    "message": str(e)[:500],
                },
            }
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            acq.release()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            **(rate_headers or {}),
        },
    )


# ── Admin & static file serving ──────────────────────────────

# v3 webui lives under webui-new/dist/ (built by `npm run build` /
# `scripts/build_webui.sh`). The old v2.2.0 webui/ directory is removed
# in v3.0.0; for development convenience we still fall back to it if
# the new dist/ hasn't been built yet.
_WEBUI_DIST = _os.path.realpath(
    _os.path.join(_os.path.dirname(__file__), "webui-new", "dist")
)
_WEBUI_LEGACY = _os.path.realpath(
    _os.path.join(_os.path.dirname(__file__), "webui")
)
# Always register the /webui routes even if the build hasn't run yet —
# the handlers will return a friendly JSON error pointing the operator
# at `npm run build`. This keeps the routes in the OpenAPI schema so
# the smoke test (and downstream tooling) can find them.
_WEBUI_DIR = (
    _WEBUI_DIST if _os.path.isdir(_WEBUI_DIST)
    else _WEBUI_LEGACY if _os.path.isdir(_WEBUI_LEGACY)
    else _WEBUI_DIST  # fall through to the canonical v3 path
)

app.include_router(admin_router)


def _safe_webui_path(rest_of_path: str) -> str | None:
    """Resolve a path inside the webui dir, refusing traversal.

    Returns the absolute file path if it points to a file under _WEBUI_DIR,
    otherwise None. Defends against `..\\..\\.env` style requests that would
    otherwise let unauthenticated callers read project secrets.
    """
    if not rest_of_path:
        return None
    # Reject obviously hostile inputs early.
    if "\x00" in rest_of_path:
        return None
    candidate = _os.path.realpath(_os.path.join(_WEBUI_DIR, rest_of_path))
    try:
        common = _os.path.commonpath([candidate, _WEBUI_DIR])
    except ValueError:
        # Different drives on Windows raise ValueError.
        return None
    if common != _WEBUI_DIR:
        return None
    if not _os.path.isfile(candidate):
        return None
    return candidate


def _webui_index_path() -> str | None:
    index = _os.path.join(_WEBUI_DIR, "index.html")
    return index if _os.path.isfile(index) else None


if _os.path.isdir(_WEBUI_DIR) or True:  # always register so /webui is in the OpenAPI schema
    @app.get("/webui/{rest_of_path:path}")
    async def webui_spa(rest_of_path: str):
        safe = _safe_webui_path(rest_of_path)
        if safe is not None:
            return FileResponse(safe)
        # SPA fallback: serve index.html so react-router-dom can take over.
        index = _webui_index_path()
        if index is not None:
            return FileResponse(index)
        return {"error": "webui not built — run `npm run build` in webui-new/"}

    @app.get("/webui")
    async def webui_root():
        index = _webui_index_path()
        if index is not None:
            return FileResponse(index)
        return {"error": "webui not built — run `npm run build` in webui-new/"}

if __name__ == "__main__":
    _validate_startup()
    uvicorn.run("server:app", host=HOST, port=PORT, reload=False)
