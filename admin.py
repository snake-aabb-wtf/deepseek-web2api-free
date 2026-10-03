"""
Admin API — authentication, statistics tracking, account pool management.
"""
import os
import secrets
import threading
import time
from collections import deque

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from account_pool import AccountPool
from crypto import is_enabled as crypto_is_enabled, _resolve_key
from ip_utils import get_real_client_ip, is_trusted_proxy
from logger import get_logger
from stats_history import get_history, start_sampler
from api_key_store import get_api_key_store

log = get_logger("admin")

# ── Admin password (set DEEPSEEK_ADMIN_PASSWORD in .env) ──────
_ADMIN_PASSWORD = os.environ.get("DEEPSEEK_ADMIN_PASSWORD", "admin")
# Insecure defaults that we explicitly forbid on a public bind unless
# the operator sets ALLOW_INSECURE_PUBLIC_DEFAULTS=true.
_INSECURE_PASSWORDS = {"", "admin", "password", "123456", "changeme"}

# ── Token management ──────────────────────────────────────────
_tokens: set[str] = set()


def _generate_token() -> str:
    return secrets.token_hex(32)


def is_admin_password_weak() -> bool:
    """True if the configured admin password is the default or otherwise weak.

    The caller decides what to do with this signal (warn loudly, refuse to
    start on a public bind, etc.). We never refuse on a loopback bind.
    """
    return (_ADMIN_PASSWORD or "") in _INSECURE_PASSWORDS


def _verify_token(token: str) -> bool:
    if not token:
        return False
    # Constant-time membership: compare against every stored token. The set is
    # small (one entry per active admin session) so the cost is negligible.
    snapshot = tuple(_tokens)
    matched = False
    for stored in snapshot:
        if secrets.compare_digest(token, stored):
            matched = True
    return matched


def verify_admin_token(token: str | None) -> bool:
    """Public check: is this a valid admin-session token?

    Used by server.py so authenticated webui sessions can also call the
    /v1/* endpoints (model list, chat) with the same bearer token.
    """
    return _verify_token(token or "")


# ── Login throttling ──────────────────────────────────────────
# Per-IP sliding window: at most _LOGIN_MAX failures per _LOGIN_WINDOW seconds.
_LOGIN_MAX = 5
_LOGIN_WINDOW = 300
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    """Resolve the *real* client IP. Trusts X-Forwarded-For only when the
    immediate connection peer is in the TRUSTED_PROXIES allowlist.
    """
    peer = request.client.host if request.client else None
    return get_real_client_ip(request.headers, peer)


def _login_record_failure(ip: str) -> None:
    now = time.time()
    with _login_lock:
        attempts = _login_attempts.setdefault(ip, [])
        cutoff = now - _LOGIN_WINDOW
        attempts[:] = [t for t in attempts if t > cutoff]
        attempts.append(now)


def _login_check_over_limit(ip: str) -> None:
    """Raise 429 if this IP has too many recent failures.
    Call AFTER recording the failure so the current attempt is counted."""
    now = time.time()
    with _login_lock:
        attempts = _login_attempts.get(ip, [])
        cutoff = now - _LOGIN_WINDOW
        recent = [t for t in attempts if t > cutoff]
        if len(recent) >= _LOGIN_MAX:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts; try again later",
            )


def _login_clear(ip: str) -> None:
    with _login_lock:
        _login_attempts.pop(ip, None)


# ── Stats ─────────────────────────────────────────────────────
_LATENCY_WINDOW_SIZE = 1024


def _percentile(values: list[float], pct: float) -> int:
    """Return the pct-th percentile of a sorted list of numbers (0..100)."""
    if not values:
        return 0
    sorted_v = sorted(values)
    k = max(0, min(len(sorted_v) - 1, int(round((pct / 100.0) * (len(sorted_v) - 1)))))
    return int(sorted_v[k])


class StatsSnapshot:
    def __init__(self):
        self.reset()

    def reset(self):
        self.total_requests = 0
        self.success_requests = 0
        self.failed_requests = 0
        self.total_latency_ms = 0.0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.start_time = time.time()
        self.models: dict[str, dict] = {}
        # Bounded ring buffer of recent latencies (ms) for percentile
        # computation. ``deque(maxlen=N)`` is O(1) on push and silently
        # drops the oldest entry when full.
        self._recent_latencies: deque[float] = deque(maxlen=_LATENCY_WINDOW_SIZE)

    def record(self, model: str, latency_ms: float,
               prompt_tokens: int = 0, completion_tokens: int = 0,
               success: bool = True):
        self.total_requests += 1
        if success:
            self.success_requests += 1
            if latency_ms > 0:
                self._recent_latencies.append(float(latency_ms))
        else:
            self.failed_requests += 1
        self.total_latency_ms += latency_ms
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        if model not in self.models:
            self.models[model] = {"requests": 0, "prompt_tokens": 0,
                                  "completion_tokens": 0, "errors": 0}
        self.models[model]["requests"] += 1
        self.models[model]["prompt_tokens"] += prompt_tokens
        self.models[model]["completion_tokens"] += completion_tokens
        if not success:
            self.models[model]["errors"] += 1

    def percentile(self, pct: float) -> int:
        return _percentile(list(self._recent_latencies), pct)

    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.success_requests / self.total_requests


_stats = StatsSnapshot()
_pool = AccountPool()


def get_pool() -> AccountPool:
    return _pool


def get_stats() -> StatsSnapshot:
    return _stats


# ── Pydantic models ───────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


class AccountAddRequest(BaseModel):
    token: str
    cookies: str
    email: str | None = ""


class AccountUpdateRequest(BaseModel):
    token: str | None = None
    cookies: str | None = None
    email: str | None = None


class AccountReloginResponse(BaseModel):
    ok: bool
    message: str


class ApiKeyCreateRequest(BaseModel):
    name: str


# ── Router ────────────────────────────────────────────────────

router = APIRouter(prefix="/admin/api")


def _check_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not _verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _pool_error(e: Exception):
    if isinstance(e, KeyError):
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    if isinstance(e, PermissionError):
        raise HTTPException(status_code=400, detail=str(e))
    if isinstance(e, RuntimeError):
        raise HTTPException(status_code=409, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=400, detail=str(e))
    raise e


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    ip = _client_ip(request)
    # Constant-time compare so a wrong password and a right one take the
    # same time. Throttle is checked AFTER the compare so a legitimate
    # password resets the counter even if the IP was previously cooling
    # down — typical SSH/GitHub semantics, prevents lockout-of-self.
    correct = secrets.compare_digest(req.password or "", _ADMIN_PASSWORD or "")
    if correct:
        _login_clear(ip)
        token = _generate_token()
        _tokens.add(token)
        log.info("admin_login_success", extra={"ip": ip})
        return {"token": token}
    _login_record_failure(ip)
    log.warning("admin_login_failed", extra={"ip": ip})
    _login_check_over_limit(ip)
    raise HTTPException(status_code=403, detail="Invalid password")


@router.post("/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if token:
        _tokens.discard(token)
    return {"ok": True}


@router.get("/api-keys")
async def list_api_keys(request: Request):
    _check_auth(request)
    return {"keys": get_api_key_store().list_keys()}


@router.post("/api-keys")
async def create_api_key(req: ApiKeyCreateRequest, request: Request, response: Response):
    _check_auth(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        return get_api_key_store().create_key(req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, request: Request):
    _check_auth(request)
    if not get_api_key_store().revoke_key(key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return {"ok": True}


@router.get("/stats")
async def stats(request: Request):
    _check_auth(request)
    s = _stats
    uptime = int(time.time() - s.start_time)
    avg_latency = int(s.total_latency_ms / s.total_requests) if s.total_requests > 0 else 0
    return {
        "total_requests": s.total_requests,
        "success_requests": s.success_requests,
        "failed_requests": s.failed_requests,
        "success_rate": round(s.success_rate(), 4),
        "avg_latency_ms": avg_latency,
        "p50_latency_ms": s.percentile(50),
        "p95_latency_ms": s.percentile(95),
        "p99_latency_ms": s.percentile(99),
        "latency_window_size": len(s._recent_latencies),
        "total_prompt_tokens": s.total_prompt_tokens,
        "total_completion_tokens": s.total_completion_tokens,
        "uptime_secs": uptime,
        "models": s.models,
    }


@router.get("/history")
async def history(request: Request):
    """Return the rolling time-series of StatsSnapshot, for the dashboard charts."""
    _check_auth(request)
    h = get_history()
    return {
        "interval_secs": h.interval(),
        "points": h.points(),
    }


@router.get("/env")
async def env_info(request: Request):
    """Return a read-only view of the effective runtime configuration.

    Powers the React "Settings" page. Intentionally hides secret values
    (only "set / default" indicators for credentials) so a logged-in
    admin cannot exfiltrate the DeepSeek token via this endpoint.
    """
    _check_auth(request)
    pool = _pool

    # Enumerate the env vars we know about. ``is_default`` is True when
    # the value matches the module-level default; "set" otherwise.
    def _env(name: str) -> str:
        return os.environ.get(name, "")

    def _flag(name: str) -> str:
        return "set" if os.environ.get(name) else "default"

    admin_pwd = os.environ.get("DEEPSEEK_ADMIN_PASSWORD", "admin")
    crypto_on = crypto_is_enabled()
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    trusted = [p.strip() for p in os.environ.get("TRUSTED_PROXIES", "").split(",") if p.strip()]

    return {
        "host": os.environ.get("HOST", "127.0.0.1"),
        "port": int(os.environ.get("PORT", "8080")),
        "insecure_public_defaults": os.environ.get("ALLOW_INSECURE_PUBLIC_DEFAULTS", "false").lower() in {"1", "true", "yes", "on"},
        "admin_password_set": bool(admin_pwd),
        "admin_password_weak": admin_pwd in {"", "admin", "password", "123456", "changeme"},
        "accounts_total": pool.count(),
        "accounts_source_env": sum(1 for a in pool.get_all() if a.get("source") == "env"),
        "accounts_source_file": sum(1 for a in pool.get_all() if a.get("source") == "file"),
        "crypto": {
            "enabled": crypto_on,
            "fernet_configured": bool(_resolve_key()),
        },
        "cors": {
            "origins": origins,
            "allow_credentials": os.environ.get("ALLOW_CORS_CREDENTIALS", "false").lower() in {"1", "true", "yes", "on"},
        },
        "trusted_proxies": trusted,
        "model_routes_configured": bool(os.environ.get("MODEL_ROUTES", "").strip()),
        "rate_limit": {
            "enabled": os.environ.get("ENABLE_RATE_LIMIT", "true").lower() in {"1", "true", "yes", "on"},
            "per_key": int(os.environ.get("CLIENT_RPM_PER_KEY", "60") or 60),
            "per_ip": int(os.environ.get("CLIENT_RPM_PER_IP", "120") or 120),
        },
        "session_cache_ttl": int(os.environ.get("SESSION_CACHE_TTL", "600") or 600),
        "log_level": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "log_format": os.environ.get("LOG_FORMAT", "json").lower(),
        "dsml_max_buffer_bytes": int(os.environ.get("DSML_MAX_BUFFER_BYTES", "1048576") or 1048576),
        "uptime_secs": int(time.time() - _stats.start_time),
        "server_version": "3.3.6-rc.3",
        "env_overrides": [
            {"name": "HOST", "value": _env("HOST") or "127.0.0.1", "is_default": _flag("HOST") == "default"},
            {"name": "PORT", "value": _env("PORT") or "8080", "is_default": _flag("PORT") == "default"},
            {"name": "ALLOW_UNAUTHENTICATED_API", "value": _env("ALLOW_UNAUTHENTICATED_API") or "false", "is_default": _flag("ALLOW_UNAUTHENTICATED_API") == "default"},
            {"name": "ALLOW_INSECURE_PUBLIC_DEFAULTS", "value": _env("ALLOW_INSECURE_PUBLIC_DEFAULTS") or "false", "is_default": _flag("ALLOW_INSECURE_PUBLIC_DEFAULTS") == "default"},
            {"name": "MODE", "value": _env("MODE") or "auto", "is_default": _flag("MODE") == "default"},
            {"name": "THINKING", "value": _env("THINKING") or "auto", "is_default": _flag("THINKING") == "default"},
            {"name": "SEARCH", "value": _env("SEARCH") or "auto", "is_default": _flag("SEARCH") == "default"},
            {"name": "MODEL_NAME", "value": _env("MODEL_NAME") or "deepseek-chat", "is_default": _flag("MODEL_NAME") == "default"},
            {"name": "MODEL_ROUTES", "value": _env("MODEL_ROUTES") or "", "is_default": _flag("MODEL_ROUTES") == "default"},
            {"name": "DEEPSEEK_ADMIN_PASSWORD", "value": "***" if admin_pwd else "", "is_default": _flag("DEEPSEEK_ADMIN_PASSWORD") == "default"},
            {"name": "DEEPSEEK_ENCRYPTION_KEY", "value": "***" if crypto_on else "", "is_default": _flag("DEEPSEEK_ENCRYPTION_KEY") == "default"},
            {"name": "ALLOWED_ORIGINS", "value": _env("ALLOWED_ORIGINS") or "", "is_default": _flag("ALLOWED_ORIGINS") == "default"},
            {"name": "TRUSTED_PROXIES", "value": _env("TRUSTED_PROXIES") or "", "is_default": _flag("TRUSTED_PROXIES") == "default"},
            {"name": "ENABLE_RATE_LIMIT", "value": _env("ENABLE_RATE_LIMIT") or "true", "is_default": _flag("ENABLE_RATE_LIMIT") == "default"},
            {"name": "CLIENT_RPM_PER_KEY", "value": _env("CLIENT_RPM_PER_KEY") or "60", "is_default": _flag("CLIENT_RPM_PER_KEY") == "default"},
            {"name": "CLIENT_RPM_PER_IP", "value": _env("CLIENT_RPM_PER_IP") or "120", "is_default": _flag("CLIENT_RPM_PER_IP") == "default"},
            {"name": "SESSION_CACHE_TTL", "value": _env("SESSION_CACHE_TTL") or "600", "is_default": _flag("SESSION_CACHE_TTL") == "default"},
            {"name": "LOG_LEVEL", "value": _env("LOG_LEVEL") or "INFO", "is_default": _flag("LOG_LEVEL") == "default"},
            {"name": "LOG_FORMAT", "value": _env("LOG_FORMAT") or "json", "is_default": _flag("LOG_FORMAT") == "default"},
            {"name": "DSML_MAX_BUFFER_BYTES", "value": _env("DSML_MAX_BUFFER_BYTES") or "1048576", "is_default": _flag("DSML_MAX_BUFFER_BYTES") == "default"},
            {"name": "STATS_HISTORY_INTERVAL_SECS", "value": _env("STATS_HISTORY_INTERVAL_SECS") or "30", "is_default": _flag("STATS_HISTORY_INTERVAL_SECS") == "default"},
            {"name": "DEEPSEEK_IMPERSONATE", "value": _env("DEEPSEEK_IMPERSONATE") or "chrome131", "is_default": _flag("DEEPSEEK_IMPERSONATE") == "default"},
            {"name": "DEEPSEEK_JITTER_SECS", "value": _env("DEEPSEEK_JITTER_SECS") or "0.0", "is_default": _flag("DEEPSEEK_JITTER_SECS") == "default"},
        ],
    }


@router.get("/accounts")
async def list_accounts(request: Request):
    _check_auth(request)
    pool = get_pool()
    return {
        "accounts": pool.get_all(),
        **pool.stats(),
    }


@router.post("/accounts")
async def add_account(req: AccountAddRequest, request: Request):
    _check_auth(request)
    pool = get_pool()
    try:
        acct = pool.add(token=req.token, cookies=req.cookies, email=req.email or "")
    except Exception as e:
        _pool_error(e)
    return {"ok": True, "account": acct.to_dict()}


@router.put("/accounts/{account_id}")
async def update_account(account_id: str, req: AccountUpdateRequest, request: Request):
    _check_auth(request)
    pool = get_pool()
    try:
        acct = pool.update(account_id, token=req.token, cookies=req.cookies, email=req.email)
    except Exception as e:
        _pool_error(e)
    return {"ok": True, "account": acct.to_dict()}


@router.delete("/accounts/{account_id}")
async def remove_account(account_id: str, request: Request):
    _check_auth(request)
    pool = get_pool()
    try:
        ok = pool.remove_by_id(account_id)
    except Exception as e:
        _pool_error(e)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"ok": True}


@router.post("/accounts/{account_id}/relogin")
async def relogin_account(account_id: str, request: Request) -> AccountReloginResponse:
    _check_auth(request)
    pool = get_pool()
    ok, msg = pool.relogin_by_id(account_id)
    return AccountReloginResponse(ok=ok, message=msg)
