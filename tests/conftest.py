import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import data.fred_data as fred_data  # noqa: E402
from fakes import FakeFred  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail any test that reaches the internet (FRED, Yahoo, RSS, OpenAI). Localhost stays allowed (Kaleido)."""
    import socket

    real_connect = socket.socket.connect

    def guarded_connect(sock, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("127."):
            raise RuntimeError(f"Test tried to reach the network: {address}")
        return real_connect(sock, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def fake_fred(monkeypatch):
    """Route every FRED call to synthetic data (no network, no key needed)."""
    monkeypatch.setattr(config, "FRED_API_KEY", "fake")
    monkeypatch.setattr(fred_data, "_get_fred_client", lambda: FakeFred())
    return FakeFred()


@pytest.fixture
def no_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
