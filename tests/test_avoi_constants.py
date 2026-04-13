"""Tests for avoi_constants module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from avoi_constants import get_default_avoi_root


class TestGetDefaultAvoiRoot:
    """Tests for get_default_avoi_root() — Docker/custom deployment awareness."""

    def test_no_avoi_home_returns_native(self, tmp_path, monkeypatch):
        """When AVOI_HOME is not set, returns ~/.avoi."""
        monkeypatch.delenv("AVOI_HOME", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert get_default_avoi_root() == tmp_path / ".avoi"

    def test_avoi_home_is_native(self, tmp_path, monkeypatch):
        """When AVOI_HOME = ~/.avoi, returns ~/.avoi."""
        native = tmp_path / ".avoi"
        native.mkdir()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("AVOI_HOME", str(native))
        assert get_default_avoi_root() == native

    def test_avoi_home_is_profile(self, tmp_path, monkeypatch):
        """When AVOI_HOME is a profile under ~/.avoi, returns ~/.avoi."""
        native = tmp_path / ".avoi"
        profile = native / "profiles" / "coder"
        profile.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("AVOI_HOME", str(profile))
        assert get_default_avoi_root() == native

    def test_avoi_home_is_docker(self, tmp_path, monkeypatch):
        """When AVOI_HOME points outside ~/.avoi (Docker), returns AVOI_HOME."""
        docker_home = tmp_path / "opt" / "data"
        docker_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("AVOI_HOME", str(docker_home))
        assert get_default_avoi_root() == docker_home

    def test_avoi_home_is_custom_path(self, tmp_path, monkeypatch):
        """Any AVOI_HOME outside ~/.avoi is treated as the root."""
        custom = tmp_path / "my-avoi-data"
        custom.mkdir()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("AVOI_HOME", str(custom))
        assert get_default_avoi_root() == custom

    def test_docker_profile_active(self, tmp_path, monkeypatch):
        """When a Docker profile is active (AVOI_HOME=<root>/profiles/<name>),
        returns the Docker root, not the profile dir."""
        docker_root = tmp_path / "opt" / "data"
        profile = docker_root / "profiles" / "coder"
        profile.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("AVOI_HOME", str(profile))
        assert get_default_avoi_root() == docker_root
