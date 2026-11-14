"""Actual server binds determine availability, without client connection probes."""

import asyncio
import errno
import socket
import sys

import pytest

import run
from test_chaos_isolation_0981 import helper


@pytest.fixture
def launcher(monkeypatch):
    desktop = helper("desktop")
    monkeypatch.setattr(desktop, "configure_logging", lambda workspace: None)
    monkeypatch.setattr(desktop, "hold_installation_mutex", lambda: None)
    monkeypatch.setattr(desktop, "existing_instance", lambda *args: None)
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    return desktop


def test_live_listener_is_rejected_by_actual_bind(launcher, tmp_path, monkeypatch):
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = listener.getsockname()[1]

        async def bind():
            await asyncio.get_running_loop().create_server(
                asyncio.Protocol, host="127.0.0.1", port=port
            )

        monkeypatch.setattr(run, "main", lambda: asyncio.run(bind()))
        with pytest.raises(OSError):
            launcher.main(["--data-dir", str(tmp_path), "--port", str(port), "--no-browser"])
        assert listener.fileno() >= 0


@pytest.mark.skipif(sys.platform != "linux", reason="Reproduce Linux TCP TIME_WAIT regression")
def test_immediate_restart_after_server_connection_closes(launcher, tmp_path, monkeypatch):
    # Close the server side first, as a graceful Uvicorn shutdown does. This
    # leaves the server port in TIME_WAIT even though no process is listening.
    with socket.create_server(("127.0.0.1", 0)) as listener:
        address = listener.getsockname()
        with socket.create_connection(address, timeout=1) as client:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(1)
                connection.shutdown(socket.SHUT_WR)
                assert client.recv(1) == b""
                client.shutdown(socket.SHUT_WR)
                assert connection.recv(1) == b""
    with socket.socket() as old_preflight:
        with pytest.raises(OSError) as failure:
            old_preflight.bind(address)
        assert failure.value.errno == errno.EADDRINUSE

    started = []

    async def rebind():
        # Uvicorn uses the event loop's create_server with its platform defaults.
        server = await asyncio.get_running_loop().create_server(
            asyncio.Protocol, host=address[0], port=address[1]
        )
        try:
            assert server.is_serving()
            started.append(True)
        finally:
            server.close()
            await server.wait_closed()

    monkeypatch.setattr(run, "main", lambda: asyncio.run(rebind()))
    assert (
        launcher.main(["--data-dir", str(tmp_path), "--port", str(address[1]), "--no-browser"]) == 0
    )
    assert started == [True]


@pytest.mark.parametrize("error", [TimeoutError("Timed out"), PermissionError("Denied")])
def test_client_connection_failure_does_not_block_server_start(
    launcher, tmp_path, monkeypatch, error
):
    started = []
    monkeypatch.setattr(run, "main", lambda: started.append(True))

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(socket, "create_connection", fail)
    assert launcher.main(["--data-dir", str(tmp_path), "--port", "8881", "--no-browser"]) == 0
    assert started == [True]
