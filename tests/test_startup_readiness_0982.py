"""The browser follows this Uvicorn server, never another listener on its port."""

from types import SimpleNamespace
import logging
from logging.handlers import RotatingFileHandler
import socket
import sys
import threading

import pytest
import uvicorn

import run
from test_chaos_isolation_0981 import helper


class MinimalApp:
    def __init__(self):
        self.state = SimpleNamespace(
            sessions=SimpleNamespace(issue_launch=lambda: "synthetic-launch"),
            software_updates=SimpleNamespace(shutdown=None),
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        else:
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})


@pytest.fixture
def startup(tmp_path, monkeypatch):
    import workbench.api
    import workbench.local_session

    instance = tmp_path / "instance.json"

    def write_instance(*args):
        instance.write_text("synthetic")
        return instance

    monkeypatch.setattr(workbench.api, "create_app", lambda *args, **kwargs: MinimalApp())
    monkeypatch.setattr(workbench.local_session, "write_instance", write_instance)
    opened = []
    monkeypatch.setattr(run.webbrowser, "open", lambda url: opened.append(url))
    return SimpleNamespace(
        args=SimpleNamespace(port=0, host="127.0.0.1", demo=False, no_browser=False),
        workspace=tmp_path,
        instance=instance,
        opened=opened,
    )


def assert_browser_thread_stopped():
    assert not any(thread.name == "workbench-browser" for thread in threading.enumerate())


@pytest.fixture
def desktop_errors(monkeypatch):
    desktop = helper("desktop")
    dialogs = []
    # The real MessageBoxW waits for a click on Windows CI's unattended desktop.
    monkeypatch.setattr(
        desktop,
        "ctypes",
        SimpleNamespace(
            windll=SimpleNamespace(
                user32=SimpleNamespace(MessageBoxW=lambda *args: dialogs.append(args) or 1)
            )
        ),
    )
    return desktop, dialogs


def test_browser_opens_once_after_own_server_binds_despite_connect_timeout(startup, monkeypatch):
    servers = []
    server_class = uvicorn.Server

    def server_factory(config):
        assert config.host == "127.0.0.1" and config.workers == 1
        assert config.log_config is None
        server = server_class(config)
        servers.append(server)
        return server

    def open_browser(url):
        assert servers[0].started
        assert servers[0].servers[0].is_serving()
        startup.opened.append(url)
        servers[0].config.app.state.software_updates.shutdown()

    def blocked_connect(*args, **kwargs):
        raise TimeoutError("Windows client connection timed out")

    monkeypatch.setattr(uvicorn, "Server", server_factory)
    monkeypatch.setattr(run.webbrowser, "open", open_browser)
    monkeypatch.setattr(socket, "create_connection", blocked_connect)
    # Prevent a regression from hanging the suite if no browser is opened.
    watchdog = threading.Timer(5, lambda: setattr(servers[0], "should_exit", True))
    watchdog.start()
    try:
        run.serve(startup.args, startup.workspace, False)
    finally:
        watchdog.cancel()
        watchdog.join()
    assert startup.opened == ["http://127.0.0.1:0/#launch=synthetic-launch"]
    assert not startup.instance.exists()
    assert_browser_thread_stopped()


def test_occupied_port_exits_without_opening_browser(startup):
    with socket.create_server(("127.0.0.1", 0)) as unrelated:
        startup.args.port = unrelated.getsockname()[1]
        with pytest.raises(RuntimeError, match="Could not start the local server") as failure:
            run.serve(startup.args, startup.workspace, False)
        assert isinstance(failure.value.__cause__, SystemExit)
        assert failure.value.__cause__.code != 0
        assert unrelated.fileno() >= 0
    assert startup.opened == []
    assert not startup.instance.exists()
    assert_browser_thread_stopped()


def test_occupied_port_entrypoint_retains_actual_bind_error_in_application_log(
    startup, monkeypatch, desktop_errors
):
    desktop, dialogs = desktop_errors
    log_path = startup.workspace / "application.log"
    handler = RotatingFileHandler(log_path, encoding="utf-8")
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    monkeypatch.setattr(desktop, "configure_logging", lambda workspace: startup.workspace)
    monkeypatch.setattr(desktop, "hold_installation_mutex", lambda: None)
    monkeypatch.setattr(desktop, "existing_instance", lambda *args: None)
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    try:
        with socket.create_server(("127.0.0.1", 0)) as unrelated:
            port = unrelated.getsockname()[1]
            monkeypatch.setattr(
                sys,
                "argv",
                ["desktop.py", "--data-dir", str(startup.workspace), "--port", str(port)],
            )
            assert desktop.entrypoint() == 1
            assert unrelated.fileno() >= 0
        handler.flush()
        log = log_path.read_text()
        assert "error while attempting to bind on address" in log
        assert str(port) in log
        assert "Could not start the local server" in log
        assert "SystemExit" in log
        assert startup.opened == []
        assert not startup.instance.exists()
        assert_browser_thread_stopped()
        if sys.platform == "win32":
            assert len(dialogs) == 1
            owner, message, title, flags = dialogs[0]
            assert owner is None and title == desktop.APP_NAME and flags == 0x10
            assert "Could not start the local server" in message
        else:
            assert dialogs == []
    finally:
        root_logger.removeHandler(handler)
        handler.close()
        root_logger.setLevel(previous_level)


def test_windows_entrypoint_reports_error_dialog_and_returns_failure(
    desktop_errors, monkeypatch, caplog
):
    desktop, dialogs = desktop_errors
    # Exercise Windows error presentation on Linux too, without changing the
    # process-wide platform or loading a native GUI library.
    monkeypatch.setattr(desktop, "sys", SimpleNamespace(platform="win32", stderr=sys.stderr))
    monkeypatch.setattr(desktop, "configure_logging", lambda: None)

    def fail_startup():
        raise RuntimeError("Synthetic startup failure")

    monkeypatch.setattr(desktop, "main", fail_startup)
    assert desktop.entrypoint() == 1
    assert dialogs == [(None, "Synthetic startup failure", desktop.APP_NAME, 0x10)]
    assert "Synthetic startup failure" in caplog.text


@pytest.mark.parametrize("started,code", [(False, 0), (True, 3)])
def test_non_startup_exits_keep_their_original_status(startup, monkeypatch, started, code):
    class ExitingServer:
        def __init__(self, config):
            self.started = started

        def run(self):
            raise SystemExit(code)

    startup.args.no_browser = True
    monkeypatch.setattr(uvicorn, "Server", ExitingServer)
    with pytest.raises(SystemExit) as failure:
        run.serve(startup.args, startup.workspace, False)
    assert failure.value.code == code
    assert not startup.instance.exists()
    assert_browser_thread_stopped()


def test_server_failure_stops_readiness_thread(startup, monkeypatch):
    class FailedServer:
        started = False

        def __init__(self, config):
            pass

        def run(self):
            raise PermissionError("Bind denied")

    monkeypatch.setattr(uvicorn, "Server", FailedServer)
    with pytest.raises(PermissionError, match="Bind denied"):
        run.serve(startup.args, startup.workspace, False)
    assert startup.opened == []
    assert not startup.instance.exists()
    assert_browser_thread_stopped()


def test_no_browser_does_not_start_readiness_thread(startup, monkeypatch):
    class HeadlessServer:
        started = False

        def __init__(self, config):
            pass

        def run(self):
            assert_browser_thread_stopped()

    startup.args.no_browser = True
    monkeypatch.setattr(uvicorn, "Server", HeadlessServer)
    run.serve(startup.args, startup.workspace, False)
    assert startup.opened == []
    assert not startup.instance.exists()
    assert_browser_thread_stopped()
