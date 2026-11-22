"""Offline migration checks allow native event-loop IPC, never external sockets."""

import asyncio
import socket
import sys

import pytest

from modules.workspace.tools.verify_upgrade import loopback_only


def test_offline_guard_supports_real_native_socketpair_and_event_loop(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", loopback_only(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", loopback_only(socket.socket.connect_ex))
    first, second = socket.socketpair()
    try:
        first.sendall(b"native local IPC")
        assert second.recv(64) == b"native local IPC"
    finally:
        first.close()
        second.close()

    async def started():
        if sys.platform == "win32":
            assert isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop)
        await asyncio.sleep(0)
        return "native event loop ready"

    assert asyncio.run(started()) == "native event loop ready"


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
@pytest.mark.parametrize(
    "host", ["example.org", "localhost", "192.0.2.1", "192.168.1.1", "0.0.0.0", "2001:db8::1", "::"]
)
def test_offline_guard_rejects_external_or_unresolved_destinations_before_os_call(
    monkeypatch, method, host
):
    def attempted_network(*args):
        pytest.fail("The offline guard reached a network operation")

    monkeypatch.setattr(socket.socket, method, loopback_only(attempted_network))
    with socket.socket() as connection, pytest.raises(AssertionError, match="remain offline"):
        getattr(connection, method)((host, 443))
