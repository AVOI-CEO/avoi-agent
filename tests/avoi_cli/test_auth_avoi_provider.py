"""Regression tests for AVOI OAuth refresh + agent-key mint interactions."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from avoi_cli.auth import AuthError, get_provider_auth_state, resolve_avoi_runtime_credentials


# =============================================================================
# _resolve_verify: CA bundle path validation
# =============================================================================


class TestResolveVerifyFallback:
    """Verify _resolve_verify falls back to True when CA bundle path doesn't exist."""

    def test_missing_ca_bundle_in_auth_state_falls_back(self):
        from avoi_cli.auth import _resolve_verify

        result = _resolve_verify(auth_state={
            "tls": {"insecure": False, "ca_bundle": "/nonexistent/ca-bundle.pem"},
        })
        assert result is True

    def test_valid_ca_bundle_in_auth_state_is_returned(self, tmp_path):
        from avoi_cli.auth import _resolve_verify

        ca_file = tmp_path / "ca-bundle.pem"
        ca_file.write_text("fake cert")
        result = _resolve_verify(auth_state={
            "tls": {"insecure": False, "ca_bundle": str(ca_file)},
        })
        assert result == str(ca_file)

    def test_missing_ssl_cert_file_env_falls_back(self, monkeypatch):
        from avoi_cli.auth import _resolve_verify

        monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/ssl-cert.pem")
        monkeypatch.delenv("avoi_CA_BUNDLE", raising=False)
        result = _resolve_verify(auth_state={"tls": {}})
        assert result is True

    def test_missing_avoi_ca_bundle_env_falls_back(self, monkeypatch):
        from avoi_cli.auth import _resolve_verify

        monkeypatch.setenv("avoi_CA_BUNDLE", "/nonexistent/avoi-ca.pem")
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        result = _resolve_verify(auth_state={"tls": {}})
        assert result is True

    def test_insecure_takes_precedence_over_missing_ca(self):
        from avoi_cli.auth import _resolve_verify

        result = _resolve_verify(
            insecure=True,
            auth_state={"tls": {"ca_bundle": "/nonexistent/ca.pem"}},
        )
        assert result is False

    def test_no_ca_bundle_returns_true(self, monkeypatch):
        from avoi_cli.auth import _resolve_verify

        monkeypatch.delenv("avoi_CA_BUNDLE", raising=False)
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        result = _resolve_verify(auth_state={"tls": {}})
        assert result is True

    def test_explicit_ca_bundle_param_missing_falls_back(self):
        from avoi_cli.auth import _resolve_verify

        result = _resolve_verify(ca_bundle="/nonexistent/explicit-ca.pem")
        assert result is True

    def test_explicit_ca_bundle_param_valid_is_returned(self, tmp_path):
        from avoi_cli.auth import _resolve_verify

        ca_file = tmp_path / "explicit-ca.pem"
        ca_file.write_text("fake cert")
        result = _resolve_verify(ca_bundle=str(ca_file))
        assert result == str(ca_file)


def _setup_avoi_auth(
    avoi_home: Path,
    *,
    access_token: str = "access-old",
    refresh_token: str = "refresh-old",
) -> None:
    avoi_home.mkdir(parents=True, exist_ok=True)
    auth_store = {
        "version": 1,
        "active_provider": "avoi",
        "providers": {
            "avoi": {
                "portal_base_url": "https://portal.example.com",
                "inference_base_url": "https://inference.example.com/v1",
                "client_id": "avoi-cli",
                "token_type": "Bearer",
                "scope": "inference:mint_agent_key",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "obtained_at": "2026-02-01T00:00:00+00:00",
                "expires_in": 0,
                "expires_at": "2026-02-01T00:00:00+00:00",
                "agent_key": None,
                "agent_key_id": None,
                "agent_key_expires_at": None,
                "agent_key_expires_in": None,
                "agent_key_reused": None,
                "agent_key_obtained_at": None,
            }
        },
    }
    (avoi_home / "auth.json").write_text(json.dumps(auth_store, indent=2))


def _mint_payload(api_key: str = "agent-key") -> dict:
    return {
        "api_key": api_key,
        "key_id": "key-id-1",
        "expires_at": datetime.now(timezone.utc).isoformat(),
        "expires_in": 1800,
        "reused": False,
    }


def test_get_avoi_auth_status_checks_credential_pool(tmp_path, monkeypatch):
    """get_avoi_auth_status() should find AVOI credentials in the pool
    even when the auth store has no AVOI provider entry — this is the
    case when login happened via the dashboard device-code flow which
    saves to the pool only.
    """
    from avoi_cli.auth import get_avoi_auth_status

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    # Empty auth store — no AVOI provider entry
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    # Seed the credential pool with an AVOI entry
    from agent.credential_pool import PooledCredential, load_pool
    pool = load_pool("avoi")
    entry = PooledCredential.from_dict("avoi", {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "portal_base_url": "https://portal.example.com",
        "inference_base_url": "https://inference.example.com/v1",
        "agent_key": "test-agent-key",
        "agent_key_expires_at": "2099-01-01T00:00:00+00:00",
        "label": "dashboard device_code",
        "auth_type": "oauth",
        "source": "manual:dashboard_device_code",
        "base_url": "https://inference.example.com/v1",
    })
    pool.add_entry(entry)

    status = get_avoi_auth_status()
    assert status["logged_in"] is True
    assert "example.com" in str(status.get("portal_base_url", ""))


def test_get_avoi_auth_status_auth_store_fallback(tmp_path, monkeypatch):
    """get_avoi_auth_status() falls back to auth store when credential
    pool is empty.
    """
    from avoi_cli.auth import get_avoi_auth_status

    avoi_home = tmp_path / "avoi"
    _setup_avoi_auth(avoi_home, access_token="at-123")
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    status = get_avoi_auth_status()
    assert status["logged_in"] is True
    assert status["portal_base_url"] == "https://portal.example.com"


def test_get_avoi_auth_status_empty_returns_not_logged_in(tmp_path, monkeypatch):
    """get_avoi_auth_status() returns logged_in=False when both pool
    and auth store are empty.
    """
    from avoi_cli.auth import get_avoi_auth_status

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    status = get_avoi_auth_status()
    assert status["logged_in"] is False


def test_refresh_token_persisted_when_mint_returns_insufficient_credits(tmp_path, monkeypatch):
    avoi_home = tmp_path / "avoi"
    _setup_avoi_auth(avoi_home, refresh_token="refresh-old")
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    refresh_calls = []
    mint_calls = {"count": 0}

    def _fake_refresh_access_token(*, client, portal_base_url, client_id, refresh_token):
        refresh_calls.append(refresh_token)
        idx = len(refresh_calls)
        return {
            "access_token": f"access-{idx}",
            "refresh_token": f"refresh-{idx}",
            "expires_in": 0,
            "token_type": "Bearer",
        }

    def _fake_mint_agent_key(*, client, portal_base_url, access_token, min_ttl_seconds):
        mint_calls["count"] += 1
        if mint_calls["count"] == 1:
            raise AuthError("credits exhausted", provider="avoi", code="insufficient_credits")
        return _mint_payload(api_key="agent-key-2")

    monkeypatch.setattr("avoi_cli.auth._refresh_access_token", _fake_refresh_access_token)
    monkeypatch.setattr("avoi_cli.auth._mint_agent_key", _fake_mint_agent_key)

    with pytest.raises(AuthError) as exc:
        resolve_avoi_runtime_credentials(min_key_ttl_seconds=300)
    assert exc.value.code == "insufficient_credits"

    state_after_failure = get_provider_auth_state("avoi")
    assert state_after_failure is not None
    assert state_after_failure["refresh_token"] == "refresh-1"
    assert state_after_failure["access_token"] == "access-1"

    creds = resolve_avoi_runtime_credentials(min_key_ttl_seconds=300)
    assert creds["api_key"] == "agent-key-2"
    assert refresh_calls == ["refresh-old", "refresh-1"]


def test_refresh_token_persisted_when_mint_times_out(tmp_path, monkeypatch):
    avoi_home = tmp_path / "avoi"
    _setup_avoi_auth(avoi_home, refresh_token="refresh-old")
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    def _fake_refresh_access_token(*, client, portal_base_url, client_id, refresh_token):
        return {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 0,
            "token_type": "Bearer",
        }

    def _fake_mint_agent_key(*, client, portal_base_url, access_token, min_ttl_seconds):
        raise httpx.ReadTimeout("mint timeout")

    monkeypatch.setattr("avoi_cli.auth._refresh_access_token", _fake_refresh_access_token)
    monkeypatch.setattr("avoi_cli.auth._mint_agent_key", _fake_mint_agent_key)

    with pytest.raises(httpx.ReadTimeout):
        resolve_avoi_runtime_credentials(min_key_ttl_seconds=300)

    state_after_failure = get_provider_auth_state("avoi")
    assert state_after_failure is not None
    assert state_after_failure["refresh_token"] == "refresh-1"
    assert state_after_failure["access_token"] == "access-1"


def test_mint_retry_uses_latest_rotated_refresh_token(tmp_path, monkeypatch):
    avoi_home = tmp_path / "avoi"
    _setup_avoi_auth(avoi_home, refresh_token="refresh-old")
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    refresh_calls = []
    mint_calls = {"count": 0}

    def _fake_refresh_access_token(*, client, portal_base_url, client_id, refresh_token):
        refresh_calls.append(refresh_token)
        idx = len(refresh_calls)
        return {
            "access_token": f"access-{idx}",
            "refresh_token": f"refresh-{idx}",
            "expires_in": 0,
            "token_type": "Bearer",
        }

    def _fake_mint_agent_key(*, client, portal_base_url, access_token, min_ttl_seconds):
        mint_calls["count"] += 1
        if mint_calls["count"] == 1:
            raise AuthError("stale access token", provider="avoi", code="invalid_token")
        return _mint_payload(api_key="agent-key")

    monkeypatch.setattr("avoi_cli.auth._refresh_access_token", _fake_refresh_access_token)
    monkeypatch.setattr("avoi_cli.auth._mint_agent_key", _fake_mint_agent_key)

    creds = resolve_avoi_runtime_credentials(min_key_ttl_seconds=300)
    assert creds["api_key"] == "agent-key"
    assert refresh_calls == ["refresh-old", "refresh-1"]


# =============================================================================
# _login_nous: "Skip (keep current)" must preserve prior provider + model
# =============================================================================


class TestLoginNousSkipKeepsCurrent:
    """When a user runs `avoi model` → AVOI Portal → Skip (keep current) after
    a successful OAuth login, the prior provider and model MUST be preserved.

    Regression: previously, _update_config_for_provider was called
    unconditionally after login, which flipped model.provider to "avoi" while
    keeping the old model.default (e.g. anthropic/claude-opus-4.6 from
    OpenRouter), leaving the user with a mismatched provider/model pair.
    """

    def _setup_home_with_openrouter(self, tmp_path, monkeypatch):
        import yaml
        avoi_home = tmp_path / "avoi"
        avoi_home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("avoi_HOME", str(avoi_home))

        config_path = avoi_home / "config.yaml"
        config_path.write_text(yaml.safe_dump({
            "model": {
                "provider": "openrouter",
                "default": "anthropic/claude-opus-4.6",
            },
        }, sort_keys=False))

        auth_path = avoi_home / "auth.json"
        auth_path.write_text(json.dumps({
            "version": 1,
            "active_provider": "openrouter",
            "providers": {"openrouter": {"api_key": "sk-or-fake"}},
        }))
        return avoi_home, config_path, auth_path

    def _patch_login_internals(self, monkeypatch, *, prompt_returns):
        """Patch OAuth + model-list + prompt so _login_nous doesn't hit network."""
        import avoi_cli.auth as auth_mod
        import avoi_cli.models as models_mod
        import avoi_cli.avoi_subscription as ns

        fake_auth_state = {
            "access_token": "fake-avoi-token",
            "agent_key": "fake-agent-key",
            "inference_base_url": "https://inference-api.AVOI-CEO.com",
            "portal_base_url": "https://portal.AVOI-CEO.com",
            "refresh_token": "fake-refresh",
            "token_expires_at": 9999999999,
        }
        monkeypatch.setattr(
            auth_mod, "_avoi_device_code_login",
            lambda **kwargs: dict(fake_auth_state),
        )
        monkeypatch.setattr(
            auth_mod, "_prompt_model_selection",
            lambda *a, **kw: prompt_returns,
        )
        monkeypatch.setattr(models_mod, "get_pricing_for_provider", lambda p: {})
        monkeypatch.setattr(models_mod, "filter_avoi_free_models", lambda ids, p: ids)
        monkeypatch.setattr(models_mod, "check_avoi_free_tier", lambda: None)
        monkeypatch.setattr(
            models_mod, "partition_avoi_models_by_tier",
            lambda ids, p, free_tier=False: (ids, []),
        )
        monkeypatch.setattr(ns, "prompt_enable_tool_gateway", lambda cfg: None)

    def test_skip_keep_current_preserves_provider_and_model(self, tmp_path, monkeypatch):
        """User picks Skip → config.yaml untouched, AVOI creds still saved."""
        import argparse
        import yaml
        from avoi_cli.auth import PROVIDER_REGISTRY, _login_nous

        avoi_home, config_path, auth_path = self._setup_home_with_openrouter(
            tmp_path, monkeypatch,
        )
        self._patch_login_internals(monkeypatch, prompt_returns=None)

        args = argparse.Namespace(
            portal_url=None, inference_url=None, client_id=None, scope=None,
            no_browser=True, timeout=15.0, ca_bundle=None, insecure=False,
        )
        _login_nous(args, PROVIDER_REGISTRY["avoi"])

        # config.yaml model section must be unchanged
        cfg_after = yaml.safe_load(config_path.read_text())
        assert cfg_after["model"]["provider"] == "openrouter"
        assert cfg_after["model"]["default"] == "anthropic/claude-opus-4.6"
        assert "base_url" not in cfg_after["model"]

        # auth.json: active_provider restored to openrouter, but AVOI creds saved
        auth_after = json.loads(auth_path.read_text())
        assert auth_after["active_provider"] == "openrouter"
        assert "avoi" in auth_after["providers"]
        assert auth_after["providers"]["avoi"]["access_token"] == "fake-avoi-token"
        # Existing openrouter creds still intact
        assert auth_after["providers"]["openrouter"]["api_key"] == "sk-or-fake"

    def test_picking_model_switches_to_nous(self, tmp_path, monkeypatch):
        """User picks an AVOI model → provider flips to avoi with that model."""
        import argparse
        import yaml
        from avoi_cli.auth import PROVIDER_REGISTRY, _login_nous

        avoi_home, config_path, auth_path = self._setup_home_with_openrouter(
            tmp_path, monkeypatch,
        )
        self._patch_login_internals(
            monkeypatch, prompt_returns="xiaomi/mimo-v2-pro",
        )

        args = argparse.Namespace(
            portal_url=None, inference_url=None, client_id=None, scope=None,
            no_browser=True, timeout=15.0, ca_bundle=None, insecure=False,
        )
        _login_nous(args, PROVIDER_REGISTRY["avoi"])

        cfg_after = yaml.safe_load(config_path.read_text())
        assert cfg_after["model"]["provider"] == "avoi"
        assert cfg_after["model"]["default"] == "xiaomi/mimo-v2-pro"

        auth_after = json.loads(auth_path.read_text())
        assert auth_after["active_provider"] == "avoi"

    def test_skip_with_no_prior_active_provider_clears_it(self, tmp_path, monkeypatch):
        """Fresh install (no prior active_provider) → Skip clears active_provider
        instead of leaving it as avoi."""
        import argparse
        import yaml
        from avoi_cli.auth import PROVIDER_REGISTRY, _login_nous

        avoi_home = tmp_path / "avoi"
        avoi_home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("avoi_HOME", str(avoi_home))

        config_path = avoi_home / "config.yaml"
        config_path.write_text(yaml.safe_dump({"model": {}}, sort_keys=False))

        # No auth.json yet — simulates first-run before any OAuth
        self._patch_login_internals(monkeypatch, prompt_returns=None)

        args = argparse.Namespace(
            portal_url=None, inference_url=None, client_id=None, scope=None,
            no_browser=True, timeout=15.0, ca_bundle=None, insecure=False,
        )
        _login_nous(args, PROVIDER_REGISTRY["avoi"])

        auth_path = avoi_home / "auth.json"
        auth_after = json.loads(auth_path.read_text())
        # active_provider should NOT be set to "avoi" after Skip
        assert auth_after.get("active_provider") in (None, "")
        # But AVOI creds are still saved
        assert "avoi" in auth_after.get("providers", {})


# =============================================================================
# persist_avoi_credentials: shared helper for CLI + web dashboard login paths
# =============================================================================


def _full_state_fixture() -> dict:
    """Shape of the dict returned by _avoi_device_code_login /
    refresh_avoi_oauth_from_state. Used as helper input."""
    return {
        "portal_base_url": "https://portal.example.com",
        "inference_base_url": "https://inference.example.com/v1",
        "client_id": "avoi-cli",
        "scope": "inference:mint_agent_key",
        "token_type": "Bearer",
        "access_token": "access-tok",
        "refresh_token": "refresh-tok",
        "obtained_at": "2026-04-17T22:00:00+00:00",
        "expires_at": "2026-04-17T22:15:00+00:00",
        "expires_in": 900,
        "agent_key": "agent-key-value",
        "agent_key_id": "ak-id",
        "agent_key_expires_at": "2026-04-18T22:00:00+00:00",
        "agent_key_expires_in": 86400,
        "agent_key_reused": False,
        "agent_key_obtained_at": "2026-04-17T22:00:10+00:00",
        "tls": {"insecure": False, "ca_bundle": None},
    }


def test_persist_avoi_credentials_writes_both_pool_and_providers(tmp_path, monkeypatch):
    """Helper must populate BOTH credential_pool.avoi AND providers.avoi.

    Regression guard: before this helper existed, `avoi auth add avoi`
    wrote only the pool. After the AVOI agent_key's 24h TTL expired, the
    401-recovery path in run_agent.py called resolve_avoi_runtime_credentials
    which reads providers.avoi, found it empty, raised AuthError, and the
    agent failed with "Non-retryable client error". Both stores must stay
    in sync at write time.
    """
    from avoi_cli.auth import persist_avoi_credentials, AVOI_DEVICE_CODE_SOURCE

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    entry = persist_avoi_credentials(_full_state_fixture())

    assert entry is not None
    assert entry.provider == "avoi"
    assert entry.source == AVOI_DEVICE_CODE_SOURCE

    payload = json.loads((avoi_home / "auth.json").read_text())

    # providers.avoi populated with the full state (new behaviour)
    singleton = payload["providers"]["avoi"]
    assert singleton["access_token"] == "access-tok"
    assert singleton["refresh_token"] == "refresh-tok"
    assert singleton["agent_key"] == "agent-key-value"
    assert singleton["agent_key_expires_at"] == "2026-04-18T22:00:00+00:00"

    # credential_pool.avoi has exactly one canonical device_code entry
    pool_entries = payload["credential_pool"]["avoi"]
    assert len(pool_entries) == 1, pool_entries
    pool_entry = pool_entries[0]
    assert pool_entry["source"] == AVOI_DEVICE_CODE_SOURCE
    assert pool_entry["agent_key"] == "agent-key-value"
    assert pool_entry["inference_base_url"] == "https://inference.example.com/v1"


def test_persist_avoi_credentials_allows_recovery_from_401(tmp_path, monkeypatch):
    """End-to-end: after persisting via the helper, resolve_avoi_runtime_credentials
    must succeed (not raise "avoi is not logged into AVOI Portal").

    This is the exact path that run_agent.py's `_try_refresh_avoi_client_credentials`
    calls after an AVOI 401 — before the fix it would raise AuthError because
    providers.avoi was empty.
    """
    from avoi_cli.auth import persist_avoi_credentials, resolve_avoi_runtime_credentials

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    persist_avoi_credentials(_full_state_fixture())

    # Stub the network-touching steps so we don't actually contact the
    # portal — the point of this test is that state lookup succeeds and
    # doesn't raise "avoi is not logged into AVOI Portal".
    def _fake_refresh_access_token(*, client, portal_base_url, client_id, refresh_token):
        return {
            "access_token": "access-new",
            "refresh_token": "refresh-new",
            "expires_in": 900,
            "token_type": "Bearer",
        }

    def _fake_mint_agent_key(*, client, portal_base_url, access_token, min_ttl_seconds):
        return _mint_payload(api_key="new-agent-key")

    monkeypatch.setattr("avoi_cli.auth._refresh_access_token", _fake_refresh_access_token)
    monkeypatch.setattr("avoi_cli.auth._mint_agent_key", _fake_mint_agent_key)

    creds = resolve_avoi_runtime_credentials(min_key_ttl_seconds=300, force_mint=True)
    assert creds["api_key"] == "new-agent-key"


def test_persist_avoi_credentials_idempotent_no_duplicate_pool_entries(tmp_path, monkeypatch):
    """Re-running persist must upsert — not accumulate duplicate device_code rows.

    Regression guard for the review comment on PR #11858: before normalisation,
    the helper wrote `manual:device_code` while `_seed_from_singletons` wrote
    `device_code`, so the pool grew a second duplicate entry on every
    ``load_pool()``. The helper now writes providers.avoi and lets seeding
    materialise the pool entry under the canonical ``device_code`` source, so
    two persists still leave the pool with exactly one row.
    """
    from avoi_cli.auth import persist_avoi_credentials, AVOI_DEVICE_CODE_SOURCE

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    first = _full_state_fixture()
    persist_avoi_credentials(first)

    second = _full_state_fixture()
    second["access_token"] = "access-second"
    second["agent_key"] = "agent-key-second"
    persist_avoi_credentials(second)

    payload = json.loads((avoi_home / "auth.json").read_text())

    # providers.avoi reflects the latest write (singleton semantics)
    assert payload["providers"]["avoi"]["access_token"] == "access-second"
    assert payload["providers"]["avoi"]["agent_key"] == "agent-key-second"

    # credential_pool.avoi has exactly one entry, carrying the latest agent_key
    pool_entries = payload["credential_pool"]["avoi"]
    assert len(pool_entries) == 1, pool_entries
    assert pool_entries[0]["source"] == AVOI_DEVICE_CODE_SOURCE
    assert pool_entries[0]["agent_key"] == "agent-key-second"
    # And no stray `manual:device_code` / `manual:dashboard_device_code` rows
    assert not any(
        e["source"].startswith("manual:") for e in pool_entries
    )


def test_persist_avoi_credentials_reloads_pool_after_singleton_write(tmp_path, monkeypatch):
    """The entry returned by the helper must come from a fresh ``load_pool`` so
    callers observe the canonical seeded state, including any legacy entries
    that ``_seed_from_singletons`` pruned or upserted.
    """
    from avoi_cli.auth import persist_avoi_credentials, AVOI_DEVICE_CODE_SOURCE

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    entry = persist_avoi_credentials(_full_state_fixture())
    assert entry is not None
    assert entry.source == AVOI_DEVICE_CODE_SOURCE
    # Label derived by _seed_from_singletons via label_from_token; we don't
    # assert its exact value, just that the helper returned a real entry.
    assert entry.access_token == "access-tok"
    assert entry.agent_key == "agent-key-value"


def test_persist_avoi_credentials_embeds_custom_label(tmp_path, monkeypatch):
    """User-supplied ``--label`` round-trips through providers.avoi and the pool.

    Previously `avoi auth add avoi --type oauth --label <name>` silently
    dropped the label because persist_avoi_credentials() ignored it and
    _seed_from_singletons always auto-derived via label_from_token().  The
    fix stashes the label inside providers.avoi so seeding prefers it.
    """
    from avoi_cli.auth import persist_avoi_credentials, AVOI_DEVICE_CODE_SOURCE

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    entry = persist_avoi_credentials(_full_state_fixture(), label="my-personal")
    assert entry is not None
    assert entry.source == AVOI_DEVICE_CODE_SOURCE
    assert entry.label == "my-personal"

    # providers.avoi carries the label so re-seeding on the next load_pool
    # doesn't overwrite it with the auto-derived fingerprint.
    payload = json.loads((avoi_home / "auth.json").read_text())
    assert payload["providers"]["avoi"]["label"] == "my-personal"


def test_persist_avoi_credentials_custom_label_survives_reseed(tmp_path, monkeypatch):
    """Reopening the pool (which re-runs _seed_from_singletons) must keep the
    user-chosen label instead of clobbering it with label_from_token output.
    """
    from avoi_cli.auth import persist_avoi_credentials
    from agent.credential_pool import load_pool

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    persist_avoi_credentials(_full_state_fixture(), label="work-acct")

    # Second load_pool triggers _seed_from_singletons again.  Without the
    # fix, this call overwrote the label with label_from_token(access_token).
    pool = load_pool("avoi")
    entries = pool.entries()
    assert len(entries) == 1
    assert entries[0].label == "work-acct"


def test_persist_avoi_credentials_no_label_uses_auto_derived(tmp_path, monkeypatch):
    """When the caller doesn't pass ``label``, the auto-derived fingerprint
    is used (unchanged default behaviour — regression guard).
    """
    from avoi_cli.auth import persist_avoi_credentials

    avoi_home = tmp_path / "avoi"
    avoi_home.mkdir(parents=True, exist_ok=True)
    (avoi_home / "auth.json").write_text(json.dumps({
        "version": 1, "providers": {},
    }))
    monkeypatch.setenv("avoi_HOME", str(avoi_home))

    entry = persist_avoi_credentials(_full_state_fixture())
    assert entry is not None
    # label_from_token derives from the access_token; exact value depends on
    # the fingerprinter but it must not be empty and must not equal an
    # arbitrary user string we never passed.
    assert entry.label
    assert entry.label != "my-personal"

    # No "label" key embedded in providers.avoi when the caller didn't supply one.
    payload = json.loads((avoi_home / "auth.json").read_text())
    assert "label" not in payload["providers"]["avoi"]
