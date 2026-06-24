"""
Smoke test — verifies the FastAPI app boots, routes are registered, and the
high-risk paths (admin auth, webui path traversal) behave correctly.

Designed to run WITHOUT any real DeepSeek credentials and WITHOUT network
access. Touches no upstream service; all HTTP calls go through FastAPI's
in-process TestClient.

Run:
    python -m tests.smoke
or
    python tests/smoke.py

Exits 0 on success, non-zero with a diagnostic on the first failure.
"""
from __future__ import annotations

import importlib
import os
import sys
import traceback
from pathlib import Path


# ── environment hardening for CI ─────────────────────────────
# 1. Pin a known admin password so the login positive-path is deterministic.
# 2. Force a throwaway account-store path so the test never reads or writes
#    a real user accounts.json.
# 3. Use a non-zero PORT so the test never accidentally binds.
# 4. Make sure adapters/POW paths are inert: no upstream calls are made in
#    this test, but we still want a stable, isolated env.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DEEPSEEK_ADMIN_PASSWORD", "ci-smoke-test-pw")
os.environ.setdefault("ACCOUNT_STORE_PATH", str(PROJECT_ROOT / "data" / "accounts.ci.json"))
os.environ.setdefault("ALLOW_UNAUTHENTICATED_API", "false")
os.environ.setdefault("PORT", "18080")

# Run from the project root so adapter.py's `open("sha3_wasm_bg.wasm")`
# resolves. The FastAPI app itself only does that at import time.
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))


# ── minimal test runner ──────────────────────────────────────
class SmokeFailure(AssertionError):
    pass


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise SmokeFailure(msg)
    print(f"  ✓ {msg}")


def section(title: str) -> None:
    print(f"\n── {title} ──")


# ── tests ────────────────────────────────────────────────────
def _all_route_paths(app) -> set[str]:
    """Return every registered HTTP path, including those in mounted sub-apps.

    Uses `app.openapi()` as the primary source because it already includes
    routes from included sub-routers (e.g. the admin router mounted at
    /admin/api). Falls back to recursive walking of `app.routes` if openapi
    is unavailable for any reason. The recursive path is not used on
    current FastAPI/Starlette versions because `_IncludedRouter` does not
    expose its inner `routes` directly — the openapi approach is simpler
    and version-agnostic.
    """
    try:
        spec = app.openapi()
        return {p for p in spec.get("paths", {}).keys() if isinstance(p, str)}
    except Exception:
        # Best-effort fallback: walk the route tree, descending into
        # whatever does expose a `.routes` attribute.
        out: set[str] = set()

        def walk(routes) -> None:
            for r in routes:
                p = getattr(r, "path", None)
                if isinstance(p, str) and p:
                    out.add(p)
                # `APIRouter` exposes `.routes` directly.
                if hasattr(r, "routes") and r is not routes:
                    try:
                        walk(r.routes)
                    except Exception:
                        pass

        walk(app.routes)
        return out


def test_import() -> None:
    section("import server (boots the whole app graph)")
    # Importing `server` transitively imports adapter, account_pool, admin,
    # tool_dsml, tool_sieve, anthropic_format. If any of them have a
    # top-level SyntaxError / ImportError / wasm-load failure, we catch
    # it here as a smoke failure rather than as a cryptic 500 in the
    # TestClient tests below.
    server = importlib.import_module("server")
    _check(server.app is not None, "server.app exists")
    paths = _all_route_paths(server.app)
    _check("/health" in paths, "/health route registered")
    _check("/v1/models" in paths, "/v1/models route registered")
    _check("/v1/chat/completions" in paths, "/v1/chat/completions route registered")
    _check("/v1/messages" in paths, "/v1/messages route registered")
    _check("/admin/api/login" in paths, "/admin/api/login route registered")
    _check("/admin/api/stats" in paths, "/admin/api/stats route registered")
    _check(any(p == "/webui" or p.startswith("/webui/") for p in paths),
           "/webui (and /webui/{path}) routes registered")


def test_health_and_static() -> None:
    section("/health and /webui static file serving")
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as client:
        r = client.get("/health")
        _check(r.status_code == 200, f"GET /health → 200 (got {r.status_code})")
        _check(r.json() == {"status": "ok"}, "/health body == {status: ok}")

        r = client.get("/webui")
        _check(r.status_code == 200, f"GET /webui → 200 (got {r.status_code})")
        _check("text/html" in r.headers.get("content-type", ""),
               "/webui returns text/html")

        r = client.get("/webui/index.html")
        _check(r.status_code == 200, f"GET /webui/index.html → 200 (got {r.status_code})")
        _check("<html" in r.text.lower() or "<!doctype" in r.text.lower(),
               "/webui/index.html looks like an HTML document")


def test_webui_path_traversal_blocked() -> None:
    """
    Regression test for the path-traversal vulnerability in /webui/{rest_of_path}.

    A request like /webui/..%2F.env should NOT return the .env file. It must
    fall back to serving index.html (the SPA's catch-all behavior) so that
    unauthenticated callers cannot read project secrets.
    """
    section("webui path-traversal defense")
    from fastapi.testclient import TestClient
    from server import app

    payloads = [
        "/webui/..%2F.env",          # url-encoded ../
        "/webui/..%2F..%2F.env",     # deeper traversal
        "/webui/..%5C.env",          # backslash variant
        "/webui/..%2Fdata%2Faccounts.json",  # try to read accounts store
        "/webui/%2E%2E%2F.env",      # fully encoded ..
        "/webui/....%2F%2F.env",     # double-dot bypass attempt
    ]

    with TestClient(app) as client:
        for payload in payloads:
            r = client.get(payload)
            # The handler should fall back to index.html on a traversal
            # attempt. That means 200 with the SPA shell, not the leaked
            # file contents.
            body = r.text
            leaked = (
                "DEEPSEEK_TOKEN" in body
                or "DEEPSEEK_COOKIES" in body
                or "DEEPSEEK_ADMIN_PASSWORD" in body
            )
            _check(not leaked, f"{payload} does not leak secrets "
                               f"(status={r.status_code}, len={len(body)})")
            # The status should be 200 (SPA fallback) or 404 (FastAPI rejected
            # the path). Anything else (e.g. 500) is a regression.
            _check(r.status_code in (200, 404),
                   f"{payload} returns 200 (SPA fallback) or 404 (rejected), "
                   f"got {r.status_code}")


def test_admin_auth_required() -> None:
    section("admin endpoints require auth")
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as client:
        r = client.get("/admin/api/stats")
        _check(r.status_code == 401, f"GET /admin/api/stats without auth → 401 "
                                     f"(got {r.status_code})")

        r = client.get("/admin/api/accounts")
        _check(r.status_code == 401, f"GET /admin/api/accounts without auth → 401 "
                                     f"(got {r.status_code})")

        r = client.post("/admin/api/accounts",
                        json={"token": "x", "cookies": "y"})
        _check(r.status_code == 401, f"POST /admin/api/accounts without auth → 401 "
                                     f"(got {r.status_code})")


def test_admin_login_flow() -> None:
    section("admin login: wrong → 403, right → 200 + token, stats with token → 200")
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as client:
        # Wrong password.
        r = client.post("/admin/api/login",
                        json={"password": "definitely-wrong"})
        _check(r.status_code == 403, f"login with wrong password → 403 "
                                     f"(got {r.status_code})")

        # Right password (set in os.environ at the top of this file).
        r = client.post("/admin/api/login",
                        json={"password": "ci-smoke-test-pw"})
        _check(r.status_code == 200, f"login with right password → 200 "
                                     f"(got {r.status_code})")
        token = r.json().get("token", "")
        _check(isinstance(token, str) and len(token) >= 16,
               "login response contains a non-trivial token")

        # Authenticated stats call.
        r = client.get("/admin/api/stats",
                       headers={"Authorization": f"Bearer {token}"})
        _check(r.status_code == 200, f"stats with valid token → 200 "
                                     f"(got {r.status_code})")
        body = r.json()
        for key in ("total_requests", "success_requests", "failed_requests",
                    "uptime_secs", "models"):
            _check(key in body, f"stats body has '{key}' field")


def test_models_requires_api_key() -> None:
    section("/v1/models requires an API key when unauthenticated access is off")
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as client:
        r = client.get("/v1/models")
        # We deliberately do NOT set API_KEYS in the smoke test environment.
        # The server is therefore expected to refuse the request. It does so
        # with one of:
        #   401 — keys are configured but the request didn't supply one
        #   503 — keys are not configured at all (operator hasn't set them yet)
        # Either is the correct "unauth = refused" response. Anything else
        # (200, 500) would mean the auth check is broken.
        _check(r.status_code in (401, 503),
               f"GET /v1/models without api key → 401 or 503 "
               f"(got {r.status_code})")

        # When we DO present a key (any non-empty value), the response must
        # not be 200 unless that key matches a configured one — and we
        # haven't configured one, so the configured-keys path returns 503.
        # This confirms the unauthenticated-bypass path is not reachable
        # by simply sending a header.
        r = client.get("/v1/models",
                       headers={"Authorization": "Bearer not-a-real-key"})
        _check(r.status_code in (401, 503),
               f"GET /v1/models with unknown key → 401 or 503 "
               f"(got {r.status_code})")


def test_adapter_token_normalization() -> None:
    """
    Sanity check on the DeepSeekAdapter._normalize_token helper if it exists
    (added by the anti-detection PR). If the helper is not present on this
    branch, the check is a no-op — we don't want CI to depend on unmerged
    feature branches.
    """
    section("adapter: token normalization helper (if present)")
    from adapter import DeepSeekAdapter

    if not hasattr(DeepSeekAdapter, "_normalize_token"):
        print("  · skipped: _normalize_token not on this branch")
        return

    n = DeepSeekAdapter._normalize_token
    _check(n('{"value":"abc","__version":"0"}') == "abc",
           "JSON wrapper {value,__version} is unwrapped to bare token")
    _check(n("Bearer xyz") == "xyz",
           "Bearer prefix is stripped")
    _check(n("plain-token") == "plain-token",
           "bare token is unchanged")
    _check(n("") == "",
           "empty input is empty output")
    _check(n("not-json-{") == "not-json-{",
           "malformed JSON is passed through unchanged")


# ── runner ───────────────────────────────────────────────────
def main() -> int:
    tests = [
        test_import,
        test_health_and_static,
        test_webui_path_traversal_blocked,
        test_admin_auth_required,
        test_admin_login_flow,
        test_models_requires_api_key,
        test_adapter_token_normalization,
    ]
    failed: list[tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except SmokeFailure as e:
            failed.append((t.__name__, str(e)))
            print(f"  ✗ FAIL: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

    print()
    if failed:
        print(f"SMOKE TEST FAILED — {len(failed)} of {len(tests)} check(s) broke:")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        return 1
    print(f"SMOKE TEST PASSED — {len(tests)} check group(s) green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
