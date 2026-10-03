"""
Account pool — multi-account management for DeepSeek Chat proxy.

Manages multiple DeepSeek accounts, tracks their states (idle/busy/error),
provides credential health checking, session lifecycle, and persistent
panel-managed accounts.
"""
import hashlib
import json
import os
import secrets
import tempfile
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from adapter import DeepSeekAdapter
from crypto import (
    is_enabled as crypto_is_enabled,
    encrypt_account_dict,
    decrypt_account_dict,
    detect_store_version,
    STORE_VERSION_ENCRYPTED,
    STORE_VERSION_PLAIN,
    maybe_upgrade_store_file,
)
from logger import get_logger

load_dotenv()

log = get_logger("account_pool")

STORE_VERSION = 1
DEFAULT_STORE_PATH = Path(__file__).resolve().parent / "data" / "accounts.json"

# Auto-recovery: when an account has accumulated this many errors,
# schedule a background health check to clear the error state if the
# upstream is reachable again. Set to 0 to disable (every error is
# permanent until manual relogin).
_RECOVER_ERROR_THRESHOLD = 3
_RECOVER_FLAG_DISABLED = os.environ.get("DISABLE_AUTO_RECOVER", "").lower() in {
    "1", "true", "yes", "on",
}


def _now() -> int:
    return int(time.time())


def _account_id(prefix: str = "acc") -> str:
    return f"{prefix}_{secrets.token_urlsafe(9)}"


def _credential_fingerprint(token: str, cookies: str) -> str:
    return hashlib.sha256(f"{token}\0{cookies}".encode()).hexdigest()


def _mask_secret(value: str, start: int = 6, end: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= start + end:
        return "*" * len(value)
    return f"{value[:start]}...{value[-end:]}"


def _cookie_names(cookies: str, limit: int = 6) -> str:
    names = []
    for part in cookies.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        names.append(part.split("=", 1)[0].strip())
    if not names:
        return _mask_secret(cookies, 12, 4)
    suffix = "" if len(names) <= limit else f", +{len(names) - limit} more"
    return ", ".join(names[:limit]) + suffix


@dataclass
class Account:
    """A single DeepSeek account with credentials and runtime state."""
    token: str
    cookies: str
    email: str = ""
    id: str = field(default_factory=_account_id)
    source: str = "file"       # persisted account
    proxy: str = ""             # per-account upstream proxy (optional)
    created_at: int = field(default_factory=_now)
    updated_at: int = field(default_factory=_now)
    state: str = "idle"        # idle | busy | error
    error_count: int = 0
    last_error: str = ""
    last_used: float = 0.0
    _adapter: Optional[DeepSeekAdapter] = field(default=None, repr=False)

    @property
    def adapter(self) -> DeepSeekAdapter:
        if self._adapter is None:
            self._adapter = DeepSeekAdapter(
                token=self.token,
                cookies=self.cookies,
                proxy=self.proxy or None,
            )
        return self._adapter

    @property
    def fingerprint(self) -> str:
        return _credential_fingerprint(self.token, self.cookies)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "source": self.source,
            "state": self.state,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_used": int(self.last_used),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "token_preview": _mask_secret(self.token),
            "cookies_preview": _cookie_names(self.cookies),
            "credential_fingerprint": self.fingerprint[:12],
        }

    def to_store_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "token": self.token,
            "cookies": self.cookies,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AccountPool:
    """Thread-safe pool of DeepSeek accounts with round-robin selection."""

    def __init__(self):
        self._lock = threading.Lock()
        self._accounts: list[Account] = []
        self._next_idx = 0
        configured_store = Path(os.environ.get("ACCOUNT_STORE_PATH", str(DEFAULT_STORE_PATH)))
        if not configured_store.is_absolute():
            configured_store = Path(__file__).resolve().parent / configured_store
        self._store_path = configured_store
        self._load_persisted_accounts()

    # ── Loading / persistence ────────────────────────────────────

    def _append_loaded(self, acct: Account):
        if any(a.fingerprint == acct.fingerprint for a in self._accounts):
            log.warning("skipping_duplicate_account", extra={"email": acct.email, "id": acct.id})
            return
        self._accounts.append(acct)

    def _load_persisted_accounts(self):
        path = self._store_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("failed_to_load_account_store", extra={"path": str(path), "error": str(e)})
            return

        version = detect_store_version(data)
        if version == STORE_VERSION_ENCRYPTED and not crypto_is_enabled():
            log.error("encrypted_store_without_key", extra={"path": str(path)})
            return

        # If we're encrypted, rewrite the file as v2 in place (one-shot migration).
        if version == STORE_VERSION_PLAIN and crypto_is_enabled():
            try:
                maybe_upgrade_store_file(path)
                log.info("upgraded_account_store_to_encrypted", extra={"path": str(path)})
            except Exception as e:
                log.warning("account_store_upgrade_failed", extra={"path": str(path), "error": str(e)})

        for item in data.get("accounts", []):
            # Decrypt in-memory copy if v2.
            item = decrypt_account_dict(item) if version == STORE_VERSION_ENCRYPTED else item
            token = str(item.get("token") or "").strip()
            cookies = str(item.get("cookies") or "").strip()
            if not token or not cookies:
                log.warning("skipping_account_missing_credentials", extra={"id": item.get("id")})
                continue
            created_at = int(item.get("created_at") or _now())
            updated_at = int(item.get("updated_at") or created_at)
            self._append_loaded(Account(
                id=str(item.get("id") or _account_id()),
                email=str(item.get("email") or ""),
                token=token,
                cookies=cookies,
                source="file",
                created_at=created_at,
                updated_at=updated_at,
            ))

    def _ensure_store_dir(self):
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self._store_path.parent, 0o700)

    def _save_persisted_accounts_locked(self):
        self._ensure_store_dir()
        if crypto_is_enabled():
            accounts = [encrypt_account_dict(a.to_store_dict()) for a in self._accounts]
            data = {
                "version": STORE_VERSION_ENCRYPTED,
                "encryption": "fernet",
                "accounts": accounts,
            }
        else:
            data = {
                "version": STORE_VERSION_PLAIN,
                "accounts": [a.to_store_dict() for a in self._accounts],
            }
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self._store_path.name}.",
            suffix=".tmp",
            dir=str(self._store_path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self._store_path)
            os.chmod(self._store_path, 0o600)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    # ── CRUD ───────────────────────────────────────────────────

    def add(self, token: str, cookies: str, email: str = "") -> Account:
        token = (token or "").strip()
        cookies = (cookies or "").strip()
        email = (email or "").strip()
        if not token or not cookies:
            raise ValueError("Token and cookies are required")

        with self._lock:
            fp = _credential_fingerprint(token, cookies)
            if any(a.fingerprint == fp for a in self._accounts):
                raise ValueError("Account already exists")
            if not email:
                email = f"acc-{len(self._accounts) + 1}"
            now = _now()
            acct = Account(
                id=_account_id(),
                token=token,
                cookies=cookies,
                email=email,
                source="file",
                created_at=now,
                updated_at=now,
            )
            self._accounts.append(acct)
            self._save_persisted_accounts_locked()
            return acct

    def get_by_id(self, account_id: str) -> Optional[Account]:
        with self._lock:
            return next((a for a in self._accounts if a.id == account_id), None)

    def update(self, account_id: str, token: str | None = None,
               cookies: str | None = None, email: str | None = None) -> Account:
        with self._lock:
            acct = next((a for a in self._accounts if a.id == account_id), None)
            if acct is None:
                raise KeyError("Account not found")
            new_token = acct.token if token is None or token == "" else token.strip()
            new_cookies = acct.cookies if cookies is None or cookies == "" else cookies.strip()
            new_email = acct.email if email is None else email.strip()
            if not new_token or not new_cookies:
                raise ValueError("Token and cookies cannot be empty")

            new_fp = _credential_fingerprint(new_token, new_cookies)
            if any(a.id != account_id and a.fingerprint == new_fp for a in self._accounts):
                raise ValueError("Account already exists")

            credentials_changed = new_token != acct.token or new_cookies != acct.cookies
            acct.token = new_token
            acct.cookies = new_cookies
            acct.email = new_email or acct.email
            acct.updated_at = _now()
            if credentials_changed:
                acct._adapter = None
                acct.state = "idle"
                acct.error_count = 0
                acct.last_error = ""
            self._save_persisted_accounts_locked()
            return acct

    def remove_by_id(self, account_id: str) -> bool:
        with self._lock:
            for idx, acct in enumerate(self._accounts):
                if acct.id != account_id:
                    continue
                self._accounts.pop(idx)
                if self._next_idx >= len(self._accounts):
                    self._next_idx = 0
                self._save_persisted_accounts_locked()
                return True
            return False

    # Backward-compatible index removal for callers that have not migrated.
    def remove(self, index: int) -> bool:
        with self._lock:
            if not (0 <= index < len(self._accounts)):
                return False
            account_id = self._accounts[index].id
        return self.remove_by_id(account_id)

    def get_all(self) -> list[dict]:
        with self._lock:
            return [a.to_dict() for a in self._accounts]

    def count(self) -> int:
        with self._lock:
            return len(self._accounts)

    # ── Selection ──────────────────────────────────────────────

    def acquire(self) -> Optional[Account]:
        """Get the next idle account (round-robin), or None if all busy.

        Returns None when no configured account is idle.
        """
        with self._lock:
            if not self._accounts:
                return None
            n = len(self._accounts)
            for _ in range(n):
                idx = self._next_idx % n
                self._next_idx += 1
                acct = self._accounts[idx]
                if acct.state == "idle":
                    acct.state = "busy"
                    acct.last_used = time.time()
                    return acct
            return None

    def acquire_by_id(self, account_id: str) -> Optional[Account]:
        """Acquire one specific idle account.

        Used for cached upstream conversations: a DeepSeek chat session is
        owned by the credentials that created it, so round-robin selection is
        unsafe when continuing that session.
        """
        if not account_id:
            return None
        with self._lock:
            candidates = self._accounts
            for acct in candidates:
                if acct.id == account_id and acct.state == "idle":
                    acct.state = "busy"
                    acct.last_used = time.time()
                    return acct
            return None

    def release(self, acct: Account):
        """Mark account back to idle unless it was already marked as error."""
        with self._lock:
            if acct.state == "busy":
                acct.state = "idle"

    def mark_error(self, acct: Account, error_msg: str = ""):
        """Mark an account as `error`. If it has failed too many times, schedule
        a background health check to see if the credentials have come back
        (e.g. WAF challenge window expired, IP block lifted). The threshold
        is intentionally low so that transient blips heal automatically.
        """
        with self._lock:
            acct.state = "error"
            acct.error_count += 1
            acct.last_error = error_msg
            should_recover = acct.error_count >= _RECOVER_ERROR_THRESHOLD

        if should_recover and not _RECOVER_FLAG_DISABLED:
            # Run the health check on a background thread so the request
            # thread isn't blocked. We don't wait for the result; acquire()
            # will see the new state next time.
            t = threading.Thread(
                target=self._background_recover,
                args=(acct,),
                daemon=True,
            )
            t.start()

    def _background_recover(self, acct: Account) -> None:
        try:
            ok = self.check_health(acct)
            log.info(
                "background_recover_finished",
                extra={"id": acct.id, "ok": ok, "error": acct.last_error},
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "background_recover_crashed",
                extra={"id": acct.id, "error": str(e)},
            )

    def mark_recovered(self, acct: Account) -> None:
        """Public hook: reset error counters and return to idle."""
        with self._lock:
            acct.state = "idle"
            acct.error_count = 0
            acct.last_error = ""
            acct._adapter = None

    # ── Health check / relogin ─────────────────────────────────

    def check_health(self, acct: Account) -> bool:
        """Test if account credentials are valid by creating a session."""
        try:
            adapter = DeepSeekAdapter(token=acct.token, cookies=acct.cookies)
            adapter.create_session()
            return True
        except Exception as e:
            with self._lock:
                acct.state = "error"
                acct.error_count += 1
                acct.last_error = str(e)
            return False

    def relogin_by_id(self, account_id: str) -> tuple[bool, str]:
        """Attempt to heal an error account by testing credentials."""
        with self._lock:
            acct = next((a for a in self._accounts if a.id == account_id), None)
            if acct is None:
                return False, "Account not found"
            if acct.state != "error":
                return False, f"Account is {acct.state}, not error"

        ok = self.check_health(acct)
        if ok:
            self.mark_recovered(acct)
            return True, "ok"
        return False, acct.last_error or "unknown error"

    def relogin(self, index: int) -> tuple[bool, str]:
        with self._lock:
            if not (0 <= index < len(self._accounts)):
                return False, "Account not found"
            account_id = self._accounts[index].id
        return self.relogin_by_id(account_id)

    # ── Stats ──────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            accounts = self._accounts
            total = len(accounts)
            idle = sum(1 for a in accounts if a.state == "idle")
            busy = sum(1 for a in accounts if a.state == "busy")
            error = sum(1 for a in accounts if a.state == "error")
            return {
                "total": total,
                "idle": idle,
                "busy": busy,
                "error": error,
            }
