"""Unit tests for AccountPool configuration, selection, and persistence."""
import pytest

from account_pool import AccountPool


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Use an isolated store and clear account-related environment values."""
    monkeypatch.setenv("ACCOUNT_STORE_PATH", str(tmp_path / "accounts.json"))
    for name in [
        "DEEPSEEK_TOKEN", "DEEPSEEK_COOKIES", "DEEPSEEK_EMAIL", "DEEPSEEK_PROXY",
        "DEEPSEEK_JITTER_SECS", "DEEPSEEK_RATE_LIMIT_RETRY_DELAYS",
    ]:
        monkeypatch.delenv(name, raising=False)
    for i in range(1, 6):
        for suffix in ["TOKEN", "COOKIES", "EMAIL", "PROXY"]:
            monkeypatch.delenv(f"DEEPSEEK_{suffix}_{i}", raising=False)
    return monkeypatch


def _pool():
    return AccountPool()


def test_env_credentials_are_ignored(clean_env):
    """Only the account store and account management API configure accounts."""
    clean_env.setenv("DEEPSEEK_TOKEN", "legacy-token")
    clean_env.setenv("DEEPSEEK_COOKIES", "legacy-cookie")
    clean_env.setenv("DEEPSEEK_EMAIL", "legacy-account")
    clean_env.setenv("DEEPSEEK_TOKEN_1", "numbered-token")
    clean_env.setenv("DEEPSEEK_COOKIES_1", "numbered-cookie")
    clean_env.setenv("DEEPSEEK_EMAIL_1", "numbered-account")

    pool = _pool()

    assert pool.get_all() == []
    assert pool.stats() == {"total": 0, "idle": 0, "busy": 0, "error": 0}
    assert pool.acquire() is None


def test_acquire_uses_configured_accounts_in_round_robin_order(clean_env):
    pool = _pool()
    first = pool.add(token="first-token", cookies="first-cookie", email="first")
    second = pool.add(token="second-token", cookies="second-cookie", email="second")

    acquired_first = pool.acquire()
    acquired_second = pool.acquire()

    assert acquired_first.id == first.id
    assert acquired_second.id == second.id
    assert pool.acquire() is None
    pool.release(acquired_first)
    pool.release(acquired_second)


def test_acquire_by_id_only_returns_configured_account(clean_env):
    pool = _pool()
    account = pool.add(token="pool-token", cookies="pool-cookie", email="pool")

    acquired = pool.acquire_by_id(account.id)

    assert acquired is account
    assert pool.acquire_by_id("missing-account") is None
    pool.release(acquired)


def test_accounts_are_editable_and_removable(clean_env):
    pool = _pool()
    account = pool.add(token="old-token", cookies="old-cookie", email="before")

    updated = pool.update(account.id, token="new-token", cookies="new-cookie", email="after")
    assert updated.token == "new-token"
    assert updated.cookies == "new-cookie"
    assert updated.email == "after"
    assert "read_only" not in updated.to_dict()

    assert pool.remove_by_id(account.id) is True
    assert pool.get_all() == []


def test_account_persists_across_pool_reload(clean_env):
    pool = _pool()
    account = pool.add(token="persist-token", cookies="persist-cookie", email="persisted")

    pool2 = _pool()
    assert [item["id"] for item in pool2.get_all()] == [account.id]
    assert pool2.remove_by_id(account.id) is True

    pool3 = _pool()
    assert pool3.get_all() == []
