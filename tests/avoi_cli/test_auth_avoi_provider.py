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
        monkeypatch.delenv("AVOI_CA_BUNDLE", raising=False)
        result = _resolve_verify(auth_state={"tls": {}})
        assert result is True

    def test_missing_avoi_ca_bundle_env_falls_back(self, monkeypatch):
        from avoi_cli.auth import _resolve_verify

        monkeypatch.setenv("AVOI_CA_BUNDLE", "/nonexistent/avoi-ca.pem")
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

        monkeypatch.delenv("AVOI_CA_BUNDLE", raising=False)
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


def test_refresh_token_persisted_when_mint_returns_insufficient_credits(tmp_path, monkeypatch):
    avoi_home = tmp_path / "avoi"
    _setup_avoi_auth(avoi_home, refresh_token="refresh-old")
    monkeypatch.setenv("AVOI_HOME", str(avoi_home))

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
    monkeypatch.setenv("AVOI_HOME", str(avoi_home))

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
    monkeypatch.setenv("AVOI_HOME", str(avoi_home))

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

