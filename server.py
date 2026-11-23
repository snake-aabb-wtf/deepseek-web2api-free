"""
OpenAI-compatible API proxy for DeepSeek Chat
Supports streaming, tool calling (via DSML prompt injection), content parts, and
the thinking / search capabilities (DeepSeek merged its quick and expert modes,
so ``thinking_enabled`` is the only model-behaviour switch left).
"""
import json
import os
import sys
import threading
import time
import uuid
import hashlib
import asyncio
from contextlib import aclosing
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
from starlette.concurrency import run_in_threadpool

from image_inputs import ImageAttachment, ImageError, normalize_images
from image_http import ImageBodyLimit, image_error_response
from turn_preparation import prepare_turn
from chat_service import ChatService
from chat_runtime import (prepare_account, thread_step as _thread_step,
    iterate_upstream as _iterate_upstream, AccountStreamingResponse as _AccountStreamingResponse)

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
from model_router import DEFAULT_MODEL_TYPE
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
from session_cache import SessionCache, ChatSession, delta_prompt
from api_key_store import get_api_key_store

load_dotenv()
configure_from_env()
log = get_logger("server")
API_KEY_STORE = get_api_key_store()

MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-chat")
#: Legacy mode knob.  DeepSeek merged quick/expert into a single model (the only
#: remaining difference is ``thinking_enabled``), so ``MODE`` no longer selects a
#: model: ``MODE=expert`` is honoured as "default thinking ON" for backward
#: compatibility with existing .env files, and ``MODE=quick`` as "thinking OFF".
#: Prefer THINKING=enabled/disabled, which says what it does.
MODE = os.environ.get("MODE", "auto").strip().lower()
THINKING = os.environ.get("THINKING", "auto").strip().lower()
SEARCH = os.environ.get("SEARCH", "auto").strip().lower()
#: Model names advertised on /v1/models. This proxy serves a **single** model:
#: whether it thinks is configured server-side (``THINKING``), not selected by
#: picking a different model name. Legacy names such as ``deepseek-reasoner``
#: are still accepted as aliases (see ``model_router.LEGACY_MODEL_ALIASES``) but
#: are not advertised and no longer map to a different behaviour.
DEFAULT_MODEL_NAMES = [MODEL_NAME]
HOST = os.environ.get("HOST", "127.0.0.1").strip()
PORT = int(os.environ.get("PORT", "8080"))
ALLOW_UNAUTHENTICATED_API = os.environ.get("ALLOW_UNAUTHENTICATED_API", "false").strip().lower() in {"1", "true", "yes", "on"}
ALLOW_INSECURE_PUBLIC_DEFAULTS = os.environ.get("ALLOW_INSECURE_PUBLIC_DEFAULTS", "false").strip().lower() in {"1", "true", "yes", "on"}

# CORS allow-list. Empty = same-origin only.
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOW_CREDENTIALS = bool(ALLOWED_ORIGINS) and os.environ.get("ALLOW_CORS_CREDENTIALS", "false").strip().lower() in {"1", "true", "yes", "on"}


RATE_LIMITER = RateLimiter()
MODEL_ROUTER = ModelRouter(models=DEFAULT_MODEL_NAMES)
SESSION_CACHE = SessionCache()


def _legacy_mode_thinking() -> bool | None:
    """Map the deprecated ``MODE`` knob onto the thinking capability.

    Returns ``None`` when MODE carries no information (``auto`` or unset).
    """
    if MODE in {"expert", "thinking", "reasoner"}:
        return True
    if MODE in {"quick", "default"}:
        return False
    return None


def resolve_model_controls(decision, req_thinking: bool = False,
                           req_search: bool = False) -> tuple[str, bool, bool]:
    """Resolve ``(model_type, thinking_enabled, search_enabled)`` for a request.

    Precedence, highest first:

    1. ``MODEL_ROUTES`` entry matched by the client's ``model`` name
       (thinking / search presets).
    2. ``THINKING`` / ``SEARCH`` env vars when set to enabled/disabled.
    3. The client's own fields (``thinking_mode`` / ``search_enabled``,
       or Anthropic's ``thinking`` block mapped by the caller).
    4. Legacy ``MODE=expert`` / ``MODE=quick`` → thinking on/off.

    ``model_type`` is a protocol field now: the upstream normalises every value
    to ``"default"`` (verified 2026-10-18), so it is whatever the matching route
    declares and defaults to ``"default"``.
    """
    model_type = decision.model_type or DEFAULT_MODEL_TYPE

    if decision.thinking is not None:
        thinking = decision.thinking
    elif THINKING == "enabled":
        thinking = True
    elif THINKING == "disabled":
        thinking = False
    else:
        legacy = _legacy_mode_thinking()
        if legacy is not None:
            # Deprecated MODE= still wins over the client field so old .env files
            # keep behaving as they did, but THINKING= is the supported knob.
            thinking = legacy
        else:
            thinking = bool(req_thinking)

    if decision.search is not None:
        search = decision.search
    elif SEARCH == "enabled":
        search = True
    elif SEARCH == "disabled":
        search = False
    else:
        search = bool(req_search)

    return model_type, thinking, search


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
    if not API_KEY_STORE.has_keys():
        raise HTTPException(status_code=503, detail="API key authentication is not configured")
    if not supplied:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not API_KEY_STORE.verify(supplied):
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


app = FastAPI(title="DeepSeek Chat API", version="4.1.5")
app.add_middleware(ImageBodyLimit)


@app.exception_handler(ImageError)
async def handle_image_error(request: Request, error: ImageError):
    return image_error_response(request.url.path, error)

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
        extra={"hint": "Add an account in the WebUI or data/accounts.json"},
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
    image_url: Optional[dict] = None


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
    # OpenAI's top-level end-user identifier.  It is used only as one part of
    # an opaque, caller-scoped upstream-session cache key.
    user: Optional[str] = None
    # Capability switches (NOT a model selector): thinking_mode → upstream
    # thinking_enabled, search_enabled → upstream search_enabled.
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
        self._pending_image_files: dict[str, str] | None = None
        self._seed_image_files: dict[str, str] = {}
        credential_material = str(getattr(acct, 'token', '')) + '\0' + str(getattr(acct, 'cookies', ''))
        self._credential_fingerprint = hashlib.sha256(credential_material.encode()).hexdigest()
        # If we have a cache key, try to reuse the existing session first.
        if cache_key:
            cached = SESSION_CACHE.get(cache_key)
            # A DeepSeek session belongs to the credentials that created it.
            # Reject mismatches (including legacy entries without a binding)
            # instead of submitting account A's session with account B.
            if (cached is not None and cached.account_id == self.acct.id
                    and (cached.credential_fingerprint == self._credential_fingerprint
                         or (not cached.credential_fingerprint and not cached.image_files))):
                self._cached_session = cached

    def create_session(self) -> str:
        # Reuse the cached session if we have one — multi-turn support.
        if self._cached_session is not None:
            self._session_id = self._cached_session.chat_session_id
            self._parent_message_id = self._cached_session.parent_message_id
            return self._session_id
        ds_id = self.adapter.create_session()
        self._session_id = ds_id
        if self._cache_key:
            sess = ChatSession(chat_session_id=ds_id, account_id=self.acct.id,
                               credential_fingerprint=self._credential_fingerprint)
            SESSION_CACHE.put(self._cache_key, sess)
            # Keep the live reference so record_message_id() can update the
            # parent id in place (the cache stores the same object).
            self._cached_session = sess
        return ds_id

    def prepare_prompt(self, full_prompt: str) -> str:
        """Return the prompt to send upstream for this turn.

        Three cases, decided by ``session_cache.delta_prompt``:

        * **Exact replay** — the client retried the same turn: send it again.
        * **Continuation** — the client resends the whole history and it grew:
          send only the new tail. The parent chain carries the earlier context
          server-side, which keeps the DeepSeek conversation from embedding every
          previous turn again (quadratic growth / bot-spam signature).
        * **Divergent history** — the client only sent the newest message, or
          edited/truncated the history: send the *full* prompt **on the existing
          session and parent chain**.

        That last case used to invalidate the cached session, which silently threw
        away the upstream conversation: a client that sends only the new user
        message per turn ("我叫什么名字？") got a brand-new session with no
        context, so the model answered as if the conversation had never happened.
        Reusing the chain and resending the whole prompt costs a few extra tokens
        once but keeps the conversation intact — verified against the live
        upstream.

        Call *before* ``create_session()``.
        """
        cached = self._cached_session
        if cached is None or not (self._cache_key and cached.sent_prompt):
            return full_prompt

        delta = delta_prompt(cached.sent_prompt, full_prompt)
        if delta is None:
            # Divergent history: keep the session, resend everything. The reply
            # to *this* turn is still appended to the same upstream thread, so
            # the next turn gets its context back.
            cached.diverged_turns += 1
            log.info(
                "session_prompt_diverged",
                extra={
                    "session_id": cached.chat_session_id,
                    "account_id": self.acct.id,
                    "diverged_turns": cached.diverged_turns,
                    "prompt_chars": len(full_prompt),
                },
            )
            return full_prompt
        if delta != full_prompt:
            log.debug(
                "session_prompt_delta",
                extra={"session_id": cached.chat_session_id, "delta_chars": len(delta)},
            )
        return delta

    @property
    def previous_prompt(self) -> str:
        return self._cached_session.sent_prompt if self._cached_session else ''

    @property
    def image_files(self) -> dict[str, str]:
        return dict(self._cached_session.image_files) if self._cached_session else dict(self._seed_image_files)

    @property
    def credential_fingerprint(self) -> str:
        return self._credential_fingerprint

    @property
    def prepared_image_files(self) -> dict[str, str]:
        return dict(self._pending_image_files) if self._pending_image_files is not None else self.image_files

    def seed_image_files(self, files: dict[str, str]) -> None:
        self._seed_image_files = dict(files)

    def stage_image_files(self, files: dict[str, str]) -> None:
        self._pending_image_files = files

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
            candidate = SESSION_CACHE.get(self._cache_key)
            # Do not overwrite another account's live cache entry in a
            # concurrent fallback path; this turn must establish its own.
            sess = candidate if candidate and candidate.account_id == self.acct.id else None
        if sess is None:
            sess = ChatSession(chat_session_id=session_id or "", account_id=self.acct.id)
            SESSION_CACHE.put(self._cache_key, sess)
        # Defensive repair for entries constructed by older versions.
        sess.account_id = self.acct.id
        sess.credential_fingerprint = self._credential_fingerprint
        if session_id:
            sess.chat_session_id = session_id
        sess.parent_message_id = mid
        if full_prompt:
            sess.sent_prompt = full_prompt
        if self._pending_image_files is not None:
            sess.image_files = self._pending_image_files
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
        cached = SESSION_CACHE.get(cache_key) if cache_key else None
        # Keep a cached conversation on its creating account whenever it is
        # available.  If it is busy/error, safely start a fresh conversation
        # on the next idle account rather than crossing credentials.
        acct = pool.acquire_by_id(cached.account_id) if cached and cached.account_id else None
        if acct is None:
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


def _cache_scope(request: Request) -> str:
    """Return an opaque caller scope for session-cache isolation."""
    supplied = _extract_api_key(request)
    if supplied:
        digest = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
        return f"key:{digest}"
    return f"ip:{_client_ip(request)}"


def _cache_key(request: Request, conversation_id: str | None,
               mode_conversation_id: str | None = None) -> str | None:
    """Return the session-cache key for one conversation.

    One namespace per conversation: stream and non-stream turns of the same
    conversation share a cache entry, so flipping ``stream`` mid-thread no longer
    starts a fresh upstream session.  (The old ``stream:``/``nonstream:`` split
    existed to dodge an empty response when a streamed session was reused
    non-streamed; keeping the parent chain plus the existing empty-response retry
    covers that case without losing the conversation.)

    Legacy 3-argument calls ``_cache_key(request, mode, conversation_id)`` are
    still accepted — ``mode`` is then ignored — so out-of-tree callers and older
    tests keep working.
    """
    if mode_conversation_id is not None:
        conversation_id = mode_conversation_id
    derived = SessionCache.derive_cache_key(_cache_scope(request), conversation_id)
    return f"conv:{derived}" if derived else None


def _extract_openai_user(req: ChatCompletionRequest, request: Request) -> str | None:
    """Derive a per-conversation cache key for the OpenAI endpoint.

    Only explicit identifiers are accepted.  Message-content hashing was
    unsafe because unrelated callers commonly share the same opener.
    """
    cid = request.headers.get("X-Conversation-Id", "").strip()
    if cid:
        return f"header:{cid}"
    return SessionCache.derive_conversation_id(req.user, None)


def _extract_anthropic_user(req: AnthropicRequest, request: Request) -> str | None:
    cid = request.headers.get("X-Conversation-Id", "").strip()
    if cid:
        return f"header:{cid}"
    metadata = req.metadata or {}
    return SessionCache.derive_conversation_id(None, metadata)


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
    return ChatService.build_prompt([m.model_dump() for m in messages],
        [t.model_dump() for t in tools] if tools else None, tool_choice)


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
    # One model only. MODEL_ROUTES is an optional advanced override for per-name
    # capability presets; when it is set its names are what clients can ask for.
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
    normalized, attachments = await run_in_threadpool(
        normalize_images, [m.model_dump() for m in req.messages], 'openai')
    prompt = _build_prompt([ChatMessage.model_validate(m) for m in normalized], req.tools, req.tool_choice)

    # Resolve model_type / thinking / search.  There is no quick-vs-expert model
    # any more: the upstream serves one model and normalises model_type to
    # "default"; the capabilities live in thinking_enabled / search_enabled.
    decision = MODEL_ROUTER.route_for(req.model)
    model_type, thinking, search = resolve_model_controls(
        decision, req_thinking=bool(req.thinking_mode), req_search=bool(req.search_enabled)
    )

    # One cache namespace per conversation: switching stream mode mid-thread must
    # not silently start a brand-new upstream session (it used to, because the
    # key was prefixed with stream:/nonstream:).
    openai_user = _extract_openai_user(req, request)
    cache_key = _cache_key(request, openai_user)
    if req.stream:
        return await _handle_stream(proxy_id, prompt, req.tools, model_type=model_type, thinking_mode=thinking, search_enabled=search, rate_headers=rate_headers,
                                    cache_key=cache_key, attachments=attachments)

    return await run_in_threadpool(_handle_nonstream, proxy_id, prompt, req.tools,
        model_type=model_type, thinking_mode=thinking, search_enabled=search,
        cache_key=cache_key, attachments=attachments)


# ---- Anthropic /v1/messages endpoint ----


@app.post("/v1/messages")
async def messages(req: AnthropicRequest, request: Request):
    _check_api_auth(request)
    rate_headers = _check_rate_limit(request)
    proxy_id = _msg_id()
    system_str = req.system
    if isinstance(system_str, list):
        if any(b.type in ('image', 'image_url') for b in system_str):
            raise ImageError('Images are not supported in system content')
        system_str = " ".join(
            b.text for b in system_str if b.type == "text" and b.text
        )

    tools_dict = [t.model_dump() for t in req.tools] if req.tools else None
    normalized, attachments = await run_in_threadpool(
        normalize_images, [m.model_dump() for m in req.messages], 'anthropic')
    prompt = build_anthropic_prompt(
        normalized,
        tools=tools_dict,
        system_str=system_str,
    )

    # Resolve model_type / thinking / search — same rules as the OpenAI endpoint
    # (Anthropic's thinking block is the request-level thinking signal).
    decision = MODEL_ROUTER.route_for(req.model)
    req_thinking = bool(req.thinking is not None and req.thinking.type == "enabled")
    model_type, thinking, search = resolve_model_controls(
        decision, req_thinking=req_thinking, req_search=False
    )

    tool_names = []
    if req.tools:
        for t in req.tools:
            if t.name:
                tool_names.append(t.name)

    anth_user = _extract_anthropic_user(req, request)
    cache_key = _cache_key(request, anth_user)
    if req.stream:
        return await _anthropic_stream(proxy_id, prompt, tool_names,
                                       model_type=model_type, thinking_mode=thinking,
                                       search_enabled=search,
                                       rate_headers=rate_headers,
                                       cache_key=cache_key, attachments=attachments)

    return await run_in_threadpool(_anthropic_nonstream, proxy_id, prompt, tool_names,
                                model_type=model_type, thinking_mode=thinking,
                                search_enabled=search,
                                cache_key=cache_key, attachments=attachments)


async def _prepare_stream_account(prompt, attachments, cache_key, thinking, model_type):
    return await prepare_account(lambda: _acquire(cache_key=cache_key),
        lambda acquired: prepare_turn(acquired, prompt, attachments, thinking=thinking,
                                      model_type=model_type or DEFAULT_MODEL_TYPE),
        lambda acquired, error: pool.mark_error(acquired.acct, str(error)), runner=run_in_threadpool)


def _anthropic_nonstream(msg_id: str, prompt: str, tool_names: list[str],
                         model_type: str | None = None,
                         thinking_mode: bool = False, search_enabled: bool = False,
                         cache_key: str | None = None,
                         attachments: tuple[ImageAttachment, ...] = ()):
    acq = _acquire(cache_key=cache_key)
    try:
        turn = prepare_turn(acq, prompt, attachments, thinking=thinking_mode,
                            model_type=model_type or DEFAULT_MODEL_TYPE)
        eff, ds_id = turn.prompt, turn.session_id
        t0 = time.time()
        ready_out: dict = {}
        content, thinking = ChatService.invoke(acq, turn, dict(model_type=model_type,
            thinking_enabled=thinking_mode, search_enabled=search_enabled), ready_out)
        if ready_out.get("response_message_id") is not None:
            acq.record_message_id(ready_out["response_message_id"],
                                  ready_out.get("session_id"),
                                  full_prompt=prompt)
        get_stats().record(MODEL_NAME, (time.time() - t0) * 1000)
    except ImageError:
        get_stats().record(MODEL_NAME, 0, success=False)
        raise
    except RateLimitError as e:
        # Match the OpenAI endpoint: upstream throttling is a client-visible
        # 429, not an opaque Anthropic 500. This includes account mute errors
        # because UserMutedError derives from RateLimitError.
        get_stats().record(MODEL_NAME, 0, success=False)
        if cache_key:
            SESSION_CACHE.invalidate(cache_key)
        raise HTTPException(
            status_code=429,
            detail=f"Upstream rate limited: {e.args[0] if e.args else 'too many requests'}, please retry later (上游限流，请稍后重试)",
        )
    except UpstreamHintError as e:
        get_stats().record(MODEL_NAME, 0, success=False)
        pool.mark_error(acq.acct, str(e))
        raise HTTPException(status_code=502, detail=str(e))
    except UpstreamEmptyError:
        # Empty upstream bodies are transient and should not poison the
        # account pool, but the client still needs a meaningful 502.
        get_stats().record(MODEL_NAME, 0, success=False)
        if cache_key:
            SESSION_CACHE.invalidate(cache_key)
        raise HTTPException(status_code=502, detail="Upstream returned an empty response (possibly rate limited), please retry later (上游返回空响应（可能触发限流），请稍后重试)")
    except Exception as e:
        get_stats().record(MODEL_NAME, 0, success=False)
        pool.mark_error(acq.acct, str(e))
        raise
    finally:
        acq.release()

    tool_calls, cleaned = parse_dsml_tool_calls(content, tool_names)
    return build_nonstream_response(
        msg_id, MODEL_NAME,
        # Empty cleaned text is valid for a pure tool response. Falling back
        # on truthiness would expose the original DSML alongside tool_use.
        content_text=cleaned if tool_calls else content,
        tool_calls=tool_calls,
        thinking_text=thinking,
    )


async def _anthropic_stream(msg_id: str, prompt: str, tool_names: list[str],
                            model_type: str | None = None,
                            thinking_mode: bool = False, search_enabled: bool = False,
                            rate_headers: dict | None = None,
                            cache_key: str | None = None,
                            attachments: tuple[ImageAttachment, ...] = ()):
    acq, turn = await _prepare_stream_account(prompt, attachments, cache_key, thinking_mode, model_type)
    eff, ds_id = turn.prompt, turn.session_id
    t0 = time.time()

    async def event_stream():
        nonlocal t0
        ready_out: dict = {}
        try:
            async with aclosing(_iterate_upstream(stream_response(
                msg_id, MODEL_NAME,
                ChatService.tokens(acq, turn, dict(model_type=model_type, thinking_enabled=thinking_mode, search_enabled=search_enabled), ready_out),
                tool_names,
                thinking_mode=thinking_mode,
            ))) as upstream:
                async for event in upstream:
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

    return _AccountStreamingResponse(acq,
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
                      cache_key: str | None = None,
                      attachments: tuple[ImageAttachment, ...] = ()):
    """Non-streaming completion with tool call detection."""
    prompt_tokens = count_text(prompt)
    acq = _acquire(cache_key=cache_key)
    try:
        turn = prepare_turn(acq, prompt, attachments, thinking=thinking_mode,
                            model_type=model_type or DEFAULT_MODEL_TYPE)
        eff, ds_id = turn.prompt, turn.session_id
        t0 = time.time()
        ready_out: dict = {}
        content, thinking = ChatService.invoke(acq, turn, dict(model_type=model_type,
            thinking_enabled=thinking_mode, search_enabled=search_enabled), ready_out)
        if ready_out.get("response_message_id") is not None:
            acq.record_message_id(ready_out["response_message_id"],
                                  ready_out.get("session_id"),
                                  full_prompt=prompt)
        completion_tokens = count_text(content) + count_text(thinking)
        get_stats().record(MODEL_NAME, (time.time() - t0) * 1000,
                           prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    except ImageError:
        get_stats().record(MODEL_NAME, 0, success=False)
        raise
    except RateLimitError as e:
        # Rate limiting is a transient upstream state, not a credential
        # problem — do NOT mark the account as errored, or the pool would
        # drain to 503 once the limiter cools down. Invalidate the cached
        # session so the next call starts fresh.
        get_stats().record(MODEL_NAME, 0, success=False)
        if cache_key:
            SESSION_CACHE.invalidate(cache_key)
        raise HTTPException(status_code=429, detail=f"Upstream rate limited: {e.args[0] if e.args else 'too many requests'}, please retry later (上游限流，请稍后重试)")
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
        raise HTTPException(status_code=502, detail="Upstream returned an empty response (possibly rate limited), please retry later (上游返回空响应（可能触发限流），请稍后重试)")
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

    # Mirror the streaming path: when thinking was on and the model produced a
    # reasoning chain, expose it as `reasoning_content` (the same non-standard
    # field DeepSeek's own API and the streaming branch use). It used to be
    # collected and then dropped here, so `thinking_mode=true` + `stream=false`
    # silently lost the chain while `stream=true` emitted it.
    message: dict = {
        "role": "assistant",
        "content": cleaned or content,
    }
    if thinking:
        message["reasoning_content"] = thinking

    return {
        "id": proxy_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_NAME,
        "choices": [{
            "index": 0,
            "message": message,
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
                         cache_key: str | None = None,
                         attachments: tuple[ImageAttachment, ...] = ()):
    """Streaming completion with StreamSieve tool call detection and thinking support."""
    prompt_tokens = count_text(prompt)
    acq, turn = await _prepare_stream_account(prompt, attachments, cache_key, thinking_mode, model_type)
    eff, ds_id = turn.prompt, turn.session_id
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

            async with aclosing(_iterate_upstream(ChatService.tokens(acq, turn, dict(model_type=model_type, thinking_enabled=thinking_mode, search_enabled=search_enabled), ready_out))) as upstream:
                async for token in upstream:
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

    return _AccountStreamingResponse(acq,
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

# Responses owns immutable snapshots independently of the legacy session cache.
from response_store import ResponseStore
from responses_errors import ResponseError
from responses_routes import create_responses_router

RESPONSE_STORE = ResponseStore()


def _acquire_response(parent):
    if parent is None:
        return _acquire()
    _UPSTREAM_LIMITER.acquire()
    try:
        account = pool.acquire_by_id(parent['account_id'])
    except BaseException:
        _UPSTREAM_LIMITER.release()
        raise
    if account is None:
        _UPSTREAM_LIMITER.release()
        raise ResponseError('Response account is busy or unavailable; retry or resend complete input',
                            503, 'response_context_unavailable')
    return AcquiredAccount(account)


def _responses_auth(request):
    _check_api_auth(request)
    return _check_rate_limit(request)


def _responses_controls(model):
    model_type, thinking, search = resolve_model_controls(MODEL_ROUTER.route_for(model))
    return dict(model_type=model_type, thinking_enabled=thinking, search_enabled=search)


app.include_router(create_responses_router(
    store=lambda: RESPONSE_STORE, acquire=lambda parent: _acquire_response(parent),
    authenticate=_responses_auth, scope=_cache_scope, controls=_responses_controls, model=lambda: MODEL_NAME,
    mark_error=lambda acquired, error: pool.mark_error(acquired.acct, str(error)),
    record=lambda elapsed, success: get_stats().record(MODEL_NAME, elapsed, success=success)))


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
