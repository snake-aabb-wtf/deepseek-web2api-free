"""
End-to-end CI validation script.

Runs three independent sub-process scenarios:

  1. Functional surface: security headers, rate-limit headers,
     MODEL_ROUTES, /admin/api/stats new fields, CORS not enabled.
  2. Startup refusal: HOST=0.0.0.0 + default admin password → SystemExit(2).
  3. Startup bypass: same as #2 with ALLOW_INSECURE_PUBLIC_DEFAULTS=true.

Each scenario runs in its own Python interpreter so that env-var changes
take effect (the server module caches HOST/admin-password at import time
and importlib.reload does NOT refresh `from admin import …` bindings).

Run from project root:  python scripts/run_e2e.py
Exit code 0 on success, non-zero on the first failure.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Strong password used by scenarios 1 (and intentionally the default
# password used by scenarios 2/3).
ADMIN_PW_STRONG = "ci-e2e-strong-pw-9X7K2mQ4vR8w"
API_KEY = "ci-e2e-key"
MODEL_ROUTES_JSON = '{"deepseek-chat":"default","deepseek-reasoner":"expert"}'


SCENARIO_1_PY = """
import os
from cryptography.fernet import Fernet
os.environ["DEEPSEEK_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
import server
from fastapi.testclient import TestClient

with TestClient(server.app) as client:
    # 1) Security headers on a public endpoint
    r = client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff", dict(r.headers)
    assert r.headers.get("x-frame-options") == "DENY", dict(r.headers)
    assert r.headers.get("referrer-policy") == "no-referrer", dict(r.headers)
    print("PASS: security headers present on /health")

    # 2) Rate-limit headers on /v1/models
    r = client.get("/v1/models", headers={"Authorization": "Bearer ci-e2e-key"})
    assert r.status_code == 200, r.text
    assert any(h.lower().startswith("x-ratelimit-") for h in r.headers), dict(r.headers)
    print("PASS: X-RateLimit-* headers present on /v1/models")

    # 3) MODEL_ROUTES populates /v1/models
    ids = sorted(m["id"] for m in r.json()["data"])
    assert "deepseek-chat" in ids, ids
    assert "deepseek-reasoner" in ids, ids
    print(f"PASS: /v1/models lists MODEL_ROUTES entries: {ids}")

    # 4) /admin/api/stats exposes p50/p95/p99 + success_rate
    r = client.post(
        "/admin/api/login",
        json={"password": "ci-e2e-strong-pw-9X7K2mQ4vR8w"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    r = client.get(
        "/admin/api/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("p50_latency_ms", "p95_latency_ms", "p99_latency_ms",
              "success_rate", "latency_window_size"):
        assert k in body, k
    print("PASS: /admin/api/stats exposes percentile + success_rate")

    # 5) CORS not enabled by default
    r = client.get("/v1/models", headers={"Authorization": "Bearer ci-e2e-key"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
    print("PASS: CORS not enabled by default (same-origin only)")

print("All e2e checks PASSED")
"""


SCENARIO_2_PY = """
import server
try:
    server._validate_startup()
    raise SystemExit("FAIL: expected refusal")
except SystemExit as e:
    assert e.code == 2, f"unexpected code {e.code!r}"
    print("PASS: refuses to start with default password on public bind (exit 2)")
"""


SCENARIO_3_PY = """
import server
server._validate_startup()
print("PASS: ALLOW_INSECURE_PUBLIC_DEFAULTS=true bypasses check")
"""


def _run(scenario: str, py: str, env_overrides: dict) -> None:
    env = os.environ.copy()
    env.update(env_overrides)
    print(f"── scenario {scenario}: {env_overrides} ──")
    result = subprocess.run(
        [sys.executable, "-c", py],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # Print stdout, but suppress noise (e.g. library deprecation warnings on stderr).
    if result.stdout:
        sys.stdout.write(result.stdout)
        if not result.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if result.returncode != 0:
        sys.stderr.write(f"FAIL: scenario {scenario} exited {result.returncode}\n")
        if result.stderr:
            sys.stderr.write(result.stderr)
        sys.exit(result.returncode)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ds2api-e2e-") as key_store_root:
        _run("1 (functional surface)", SCENARIO_1_PY, {
            "HOST": "127.0.0.1",
            "DEEPSEEK_ADMIN_PASSWORD": ADMIN_PW_STRONG,
            "API_KEYS": API_KEY,
            "API_KEY_STORE_PATH": str(Path(key_store_root) / "scenario-1" / "api_keys.sqlite3"),
            "MODEL_ROUTES": MODEL_ROUTES_JSON,
            "LOG_LEVEL": "WARNING",
        })
        _run("2 (startup refusal)", SCENARIO_2_PY, {
            "HOST": "0.0.0.0",
            "DEEPSEEK_ADMIN_PASSWORD": "admin",
            "API_KEY_STORE_PATH": str(Path(key_store_root) / "scenario-2" / "api_keys.sqlite3"),
            "ALLOW_INSECURE_PUBLIC_DEFAULTS": "false",
            "LOG_LEVEL": "WARNING",
        })
        _run("3 (startup bypass)", SCENARIO_3_PY, {
            "HOST": "0.0.0.0",
            "DEEPSEEK_ADMIN_PASSWORD": "admin",
            "API_KEY_STORE_PATH": str(Path(key_store_root) / "scenario-3" / "api_keys.sqlite3"),
            "ALLOW_INSECURE_PUBLIC_DEFAULTS": "true",
            "LOG_LEVEL": "WARNING",
        })
    print()
    print("All e2e scenarios PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
