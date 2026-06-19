"""Tests for normsync.mcp_server module-level initialization and _require_mcp."""
from __future__ import annotations

import sys
import unittest.mock as mock

import pytest


def test_mcp_server_importable():
    """Importing mcp_server initializes the module-level _store and _monitor."""

    import normsync.mcp_server as mcp_mod

    # Module-level _store and _monitor should be initialized
    assert mcp_mod._store is not None
    assert mcp_mod._monitor is not None


@pytest.mark.skipif(
    sys.modules.get("mcp") is not None
    or __import__("importlib.util", fromlist=["find_spec"]).find_spec("mcp") is not None,
    reason="mcp is installed; _require_mcp will not call sys.exit(1)",
)
def test_require_mcp_raises_when_absent():
    """_require_mcp calls sys.exit(1) when the mcp package is not installed."""
    import normsync.mcp_server as mcp_mod

    with mock.patch.dict(sys.modules, {"mcp": None, "mcp.server": None, "mcp.server.stdio": None, "mcp.types": None}):
        with mock.patch("sys.exit") as mock_exit:
            # suppress the stderr print
            with mock.patch("sys.stderr"):
                try:
                    mcp_mod._require_mcp()
                except Exception:
                    pass
            mock_exit.assert_called_once_with(1)
