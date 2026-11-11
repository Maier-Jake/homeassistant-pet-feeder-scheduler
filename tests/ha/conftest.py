"""Fixtures for tests that run inside a real (test) Home Assistant instance.

These tests need ``pytest-homeassistant-custom-component`` plus ZHA's Python
requirements (see ``requirements-test-ha.txt``). Without them, every test in
this folder is skipped and the HA-free tests in ``tests/`` still run.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
pytest.importorskip("zha")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from ``custom_components/``."""
