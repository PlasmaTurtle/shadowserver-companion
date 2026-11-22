"""Real native Chromium loading against controlled loopback HTTP sites."""

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import random
import socket
import threading
import time

from PIL import Image
import pytest

from modules.tools.components.website_capture import browser, navigation
from modules.tools.components.website_capture.cdp import CDP


def html(body, status=200, **headers):
    return (
        status,
        {"Content-Type": "text/html; charset=utf-8", **headers},
        ("<!doctype html>" + body).encode(),
    )


@pytest.fixture
def sites():
    servers = []

    def serve(routes):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def handle(self):
                try:
                    super().handle()
                except ConnectionResetError:
                    pass

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                requests.append((self.command, self.path, dict(self.headers), body))
                result = routes.get(
                    (self.command, self.path), routes.get(self.path, html("Missing", 404))
                )
                if callable(result):
                    result = result(self, body)
                status, headers, data = result
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_GET = do_POST = do_OPTIONS = respond

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}", requests

    yield serve
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def native_capture(monkeypatch, tmp_path):
    try:
        executable = os.environ.get("CHROMIUM_EXECUTABLE") or browser.find_browser()
    except ValueError:
        pytest.skip("Native browser checks require installed Edge/Chrome or CHROMIUM_EXECUTABLE")
    if not Path(executable).is_file():
        pytest.skip("The selected native capture browser is not installed")
    actual_cdp, actual_popen = browser.CDP, browser.subprocess.Popen
    actual_profile, actual_loader = browser.tempfile.mkdtemp, browser.load_page
    commands, profiles, processes = [], [], []

    class ObservedCDP(actual_cdp):
        def send(self, method, params=None, **kwargs):
            commands.append((method, params))
            return super().send(method, params, **kwargs)

    def profile(**kwargs):
        value = actual_profile(dir=tmp_path, **kwargs)
        profiles.append(Path(value))
        return value

    def popen(*args, **kwargs):
        process = actual_popen(*args, **kwargs)
        processes.append(process)
        return process

    def load(*args, **kwargs):
        try:
            return actual_loader(*args, **kwargs)
        except Exception:
            path = tmp_path / "navigation-failure.json"
            path.write_text(
                json.dumps({"metadata": kwargs["metadata"], "commands": commands}, indent=2),
                encoding="utf-8",
            )
            print("Native navigation evidence:", path)
            print(json.dumps(kwargs["metadata"], indent=2))
            raise

    monkeypatch.setattr(browser, "CDP", ObservedCDP)
    monkeypatch.setattr(browser.tempfile, "mkdtemp", profile)
    monkeypatch.setattr(browser.subprocess, "Popen", popen)
    monkeypatch.setattr(browser, "load_page", load)
    monkeypatch.setattr(browser, "MAX_SECONDS", 15)

    def run(url, **kwargs):
        return browser.capture_website(url, executable=executable, **kwargs)

    yield run, commands
    assert all(process.poll() is not None for process in processes)
    assert all(not profile.exists() for profile in profiles)
    assert not any(method.startswith("Fetch.") for method, _ in commands)


def test_candidate_order_preserves_reported_host_path_and_private_suffix():
    assert list(navigation.navigation_candidates("http://mail.tenant.github.io/a?q=2#part")) == [
        ("http://mail.tenant.github.io/a?q=2#part", False),
        ("https://mail.tenant.github.io/a?q=2#part", False),
        ("https://tenant.github.io/", True),
        ("https://www.tenant.github.io/", True),
        ("http://tenant.github.io/", True),
        ("http://www.tenant.github.io/", True),
    ]
    assert navigation.extract_root_domain("shop.example.co.il") == "example.co.il"
    assert len(list(navigation.navigation_candidates("http://127.0.0.1:1234/a"))) == 2
    assert len(list(navigation.navigation_candidates("http://localhost:1234/"))) == 2


def test_rendered_page_policy_can_reject_a_200_and_select_main_site(
    sites, native_capture, monkeypatch
):
    origin, _ = sites(
        {
            "/reported": (302, {"Location": "/signin"}, b""),
            "/signin": html('<title>Sign in</title><h1>Sign in</h1><input type="password">'),
            "/main": html(
                '<meta property="og:site_name" content="Oak Manufacturing"><h1>Oak Manufacturing</h1>'
            ),
        }
    )
    monkeypatch.setattr(
        navigation, "navigation_candidates", lambda url: [(url, False), (origin + "/main", True)]
    )
    observed = []

    def identify(page):
        observed.append((page["final_url"], page["http_status"], page["heading"]))
        return None if page["site_name"] == "Oak Manufacturing" else "website_unidentified"

    run, _ = native_capture
    png, meta = run(origin + "/reported", require_usable=True, page_check=identify)
    assert png.startswith(b"\x89PNG")
    assert observed == [
        (origin + "/signin", 200, "Sign in"),
        (origin + "/main", 200, "Oak Manufacturing"),
    ]
    assert meta["fallback_used"] and meta["final_url"] == origin + "/main"
    assert meta["attempts"][0]["reason"] == "website_unidentified"
    assert "page_text" not in json.dumps(meta)


def test_native_redirect_cookie_relative_assets_and_original_identity(sites, native_capture):
    output = BytesIO()
    Image.new("RGB", (100, 100), "green").save(output, "PNG")
    routes = {
        "/reported": (
            302,
            {"Location": "/site/index.html", "Set-Cookie": "capture_session=yes; Path=/"},
            b"",
        ),
        "/site/index.html": html(
            '<link rel="stylesheet" href="style.css"><h1>Reported site</h1><img src="logo.png">'
        ),
        "/site/style.css": (200, {"Content-Type": "text/css"}, b"body{background:rgb(0,128,0)}"),
        "/site/logo.png": (200, {"Content-Type": "image/png"}, output.getvalue()),
    }
    origin, requests = sites(routes)
    run, _ = native_capture
    png, metadata = run(origin + "/reported")
    assert metadata["requested_url"] == origin + "/reported"
    assert metadata["final_url"] == origin + "/site/index.html"
    assert metadata["redirects"] == [origin + "/reported", origin + "/site/index.html"]
    assert metadata["attempted_urls"] == [origin + "/reported"] and not metadata["fallback_used"]
    assert metadata["capture_status"] == "captured"
    assert any(
        path == "/site/index.html" and "capture_session=yes" in headers.get("Cookie", "")
        for _, path, headers, _ in requests
    )
    assert Image.open(BytesIO(png)).convert("RGB").getpixel((900, 700)) == (0, 128, 0)
    assert metadata["content_scanning"] == "not_performed"


def test_native_page_renders_while_attachment_download_is_canceled(sites, native_capture):
    filename = "capture-fixture.txt"
    origin, requests = sites(
        {
            "/": html(
                "<title>Download fixture</title><style>body{background:rgb(0,128,0)}</style>"
                '<h1>Download fixture</h1><iframe hidden src="/attachment"></iframe>'
            ),
            "/attachment": (
                200,
                {
                    "Content-Type": "text/plain",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
                b"Harmless capture test attachment.\n",
            ),
        }
    )
    run, _ = native_capture
    png, metadata = run(origin + "/", require_usable=True)
    assert metadata["capture_status"] == "captured" and metadata["title"] == "Download fixture"
    assert Image.open(BytesIO(png)).convert("RGB").getpixel((900, 700)) == (0, 128, 0)
    assert any(path == "/attachment" for _, path, _, _ in requests)
    activity = metadata["download_activity"]
    assert not activity["truncated"]
    assert [attempt["outcome"] for attempt in activity["attempts"]] == ["canceled"]
    assert filename not in json.dumps(activity)


def test_native_cross_origin_preflight_post_and_json_render(sites, native_capture):
    def preflight(request, body):
        return (
            204,
            {
                "Access-Control-Allow-Origin": request.headers["Origin"],
                "Access-Control-Allow-Methods": "POST",
                "Access-Control-Allow-Headers": "content-type",
            },
            b"",
        )

    def api(request, body):
        assert json.loads(body) == {"viewport": True}
        assert request.headers["Accept"] == "application/json"
        return (
            200,
            {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": request.headers["Origin"],
            },
            b'{"title":"Rendered POST response"}',
        )

    api_origin, api_requests = sites({("OPTIONS", "/map"): preflight, ("POST", "/map"): api})
    origin, _ = sites(
        {
            "/": html(
                '<h1>Native API</h1><script>fetch("'
                + api_origin
                + '/map",{method:"POST",headers:{"Content-Type":"application/json",Accept:"application/json"},body:JSON.stringify({viewport:true})}).then(r=>r.json()).then(d=>{document.title=d.title;document.body.append(d.title)})</script>'
            )
        }
    )
    run, _ = native_capture
    _, metadata = run(origin + "/")
    assert metadata["capture_status"] == "captured"
    assert metadata["title"] == "Rendered POST response"
    assert [method for method, path, _, _ in api_requests if path == "/map"] == ["OPTIONS", "POST"]


def test_native_large_image_is_decoded_and_captured(sites, native_capture):
    image = Image.frombytes("RGB", (1440, 1100), random.Random(7).randbytes(1440 * 1100 * 3))
    image.paste((0, 128, 0), (0, 0, 200, 200))
    output = BytesIO()
    image.save(output, "PNG")
    assert len(output.getvalue()) > 4 * 1024 * 1024
    origin, _ = sites(
        {
            "/": html('<style>body{margin:0}</style><img src="/large.png">'),
            "/large.png": (200, {"Content-Type": "image/png"}, output.getvalue()),
        }
    )
    run, _ = native_capture
    png, metadata = run(origin + "/")
    assert metadata["capture_status"] == "captured"
    assert metadata["load_readiness"]["images_ready"]
    assert Image.open(BytesIO(png)).convert("RGB").getpixel((100, 100)) == (0, 128, 0)


def test_native_javascript_redirect_and_history_keep_actual_url(sites, native_capture):
    origin, requests = sites(
        {
            "/start": html('<script>location.replace("/app/index.html")</script>'),
            "/app/index.html": html(
                '<h1>Loaded application</h1><script>history.replaceState({},"","/app/home#panel")</script>'
            ),
        }
    )
    run, _ = native_capture
    _, metadata = run(origin + "/start")
    assert metadata["capture_status"] == "captured"
    assert metadata["final_url"] == origin + "/app/home#panel"
    assert metadata["attempted_urls"] == [origin + "/start"]
    assert not any(path == "/app/home" for _, path, _, _ in requests)


def test_native_iframe_and_worker_load_without_interception(sites, native_capture):
    child, _ = sites(
        {
            "/frame": html(
                "<style>body{margin:0;background:rgb(0,128,0)}</style><h1>Child frame</h1>"
            )
        }
    )
    origin, _ = sites(
        {
            "/": html(
                '<iframe style="border:0;width:400px;height:300px" src="'
                + child
                + '/frame"></iframe><script>new Worker("/worker.js").onmessage=e=>{document.title=e.data;document.body.append(e.data)}</script>'
            ),
            "/worker.js": (
                200,
                {"Content-Type": "text/javascript"},
                b'postMessage("Worker rendered");',
            ),
        }
    )
    run, _ = native_capture
    png, metadata = run(origin + "/")
    assert metadata["capture_status"] == "captured", metadata
    assert metadata["title"] == "Worker rendered"
    assert Image.open(BytesIO(png)).convert("RGB").getpixel((200, 200)) == (0, 128, 0)


def test_failed_reported_page_uses_main_site_only_after_failure(sites, native_capture, monkeypatch):
    origin, requests = sites({"/main": html("<h1>Main business site</h1>")})
    requested, main = origin + "/missing", origin + "/main"
    monkeypatch.setattr(
        navigation, "navigation_candidates", lambda _: [(requested, False), (main, True)]
    )
    run, _ = native_capture
    _, metadata = run(requested)
    assert metadata["capture_status"] == "captured" and metadata["fallback_used"]
    assert metadata["requested_url"] == requested and metadata["final_url"] == main
    assert [attempt["outcome"] for attempt in metadata["attempts"]] == ["load_failed", "captured"]


def test_all_failed_pages_do_not_save_a_screenshot(sites, native_capture, monkeypatch):
    origin, _ = sites({})
    requested = origin + "/missing"
    monkeypatch.setattr(navigation, "navigation_candidates", lambda _: [(requested, False)])
    run, commands = native_capture
    with pytest.raises(ValueError, match="could not be loaded"):
        run(requested)
    assert not any(method == "Page.captureScreenshot" for method, _ in commands)


@pytest.mark.parametrize("kind", ["blank", "challenge"])
def test_qualification_fallback_reaches_functioning_site_after_unusable_page(
    sites, native_capture, monkeypatch, tmp_path, kind
):
    first = html("") if kind == "blank" else html("<h1>Verify you are human</h1>", 403)
    origin, _ = sites(
        {
            "/reported": first,
            "/main": html(
                "<title>Qualified entity</title><style>body{background:rgb(0,128,0)}</style><h1>Functioning entity</h1>"
            ),
        }
    )
    requested, main = origin + "/reported", origin + "/main"
    monkeypatch.setattr(
        navigation, "navigation_candidates", lambda _: [(requested, False), (main, True)]
    )
    monkeypatch.setattr(navigation, "NAVIGATION_SECONDS", 3)
    run, _ = native_capture
    png, metadata = run(requested, require_usable=True)
    assert metadata["final_url"] == main
    assert metadata["capture_status"] == "captured"
    assert metadata["attempted_urls"] == [requested, main]
    assert metadata["fallback_used"]
    assert metadata["attempts"][0]["outcome"] == ("load_failed" if kind == "blank" else "challenge")
    assert Image.open(BytesIO(png)).convert("RGB").getpixel((500, 500)) == (0, 128, 0)
    (tmp_path / (kind + "-qualified.png")).write_bytes(png)
    (tmp_path / (kind + "-qualified.json")).write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


def test_qualification_accepts_rendered_login_and_skips_already_attempted_urls(
    sites, native_capture, monkeypatch, tmp_path
):
    origin, requests = sites(
        {
            "/login": html(
                '<title>Entity login</title><h1>Entity login</h1><label>Password<input type="password"></label>'
            )
        }
    )
    skipped, login = origin + "/already-tried", origin + "/login"
    monkeypatch.setattr(
        navigation, "navigation_candidates", lambda _: [(skipped, True), (login, False)]
    )
    run, _ = native_capture
    png, metadata = run(login, require_usable=True, skip_urls={skipped})
    assert metadata["capture_status"] == "login_required"
    assert metadata["attempted_urls"] == [login]
    assert not any(path == "/already-tried" for _, path, _, _ in requests)
    (tmp_path / "login-qualified.png").write_bytes(png)


def test_qualification_target_failure_returns_attempt_provenance(
    sites, native_capture, monkeypatch
):
    origin, _ = sites({})
    requested = origin + "/missing"
    monkeypatch.setattr(navigation, "navigation_candidates", lambda _: [(requested, False)])
    run, commands = native_capture
    with pytest.raises(navigation.WebsiteLoadError) as failure:
        run(requested, require_usable=True)
    assert failure.value.attempted_urls == (requested,)
    assert failure.value.metadata["attempts"][0]["outcome"] == "load_failed"
    assert not any(method == "Page.captureScreenshot" for method, _ in commands)


def test_native_cancellation_closes_browser_and_profile(sites, native_capture):
    entered = threading.Event()
    release = threading.Event()

    def slow(request, body):
        entered.set()
        release.wait(3)
        return html("<h1>Cancelled page</h1>")

    origin, _ = sites({"/": slow})
    run, commands = native_capture
    cancel = threading.Event()

    def stop():
        entered.wait(3)
        cancel.set()

    thread = threading.Thread(target=stop)
    thread.start()
    try:
        with pytest.raises(ValueError, match="cancelled"):
            run(origin + "/", cancel_event=cancel)
    finally:
        release.set()
        thread.join(timeout=4)
    assert not any(method == "Page.captureScreenshot" for method, _ in commands)


def test_idle_cdp_command_observes_user_cancellation():
    peer = object.__new__(CDP)
    peer.cancel_event = threading.Event()
    peer.deadline = time.monotonic() + 30
    peer.results = {}
    peer.send = lambda *a, **k: 1

    def idle():
        peer.cancel_event.set()
        raise socket.timeout()

    peer.receive = idle
    with pytest.raises(ValueError, match="cancelled"):
        peer.call("Runtime.evaluate")


def test_persistent_background_request_does_not_hold_rendered_viewport(sites, native_capture):
    release = threading.Event()

    def background(request, body):
        release.wait(12)
        return 200, {"Content-Type": "text/plain"}, b"finished"

    origin, _ = sites(
        {
            "/": html('<h1>Fully rendered viewport</h1><script>fetch("/background")</script>'),
            "/background": background,
        }
    )
    run, _ = native_capture
    started = time.monotonic()
    try:
        _, metadata = run(origin + "/")
    finally:
        release.set()
    assert metadata["capture_status"] == "captured", metadata
    assert metadata["load_readiness"]["pending_requests"] >= 1
    assert time.monotonic() - started < 9


@pytest.mark.parametrize("status,outcome", [(200, "captured"), (403, "challenge")])
def test_hidden_unfinished_iframe_does_not_hold_parent_viewport(
    sites, native_capture, status, outcome
):
    release = threading.Event()

    def hidden(request, body):
        release.wait(12)
        return html("<h1>Background widget</h1>")

    child, _ = sites({"/widget": hidden})
    origin, _ = sites(
        {
            "/": html(
                '<h1>Complete parent viewport</h1><iframe style="display:none" src="'
                + child
                + '/widget"></iframe>',
                status,
            )
        }
    )
    run, _ = native_capture
    started = time.monotonic()
    try:
        _, metadata = run(origin + "/")
    finally:
        release.set()
    assert metadata["capture_status"] == outcome, metadata
    assert metadata["load_readiness"]["document_ready"]
    assert time.monotonic() - started < 9


def test_broken_visible_image_settles_promptly_with_truthful_partial(sites, native_capture):
    origin, _ = sites(
        {"/": html('<h1>Rendered page</h1><img width="100" height="100" src="/missing.png">')}
    )
    run, _ = native_capture
    started = time.monotonic()
    _, metadata = run(origin + "/")
    assert metadata["capture_status"] == "partial"
    assert not metadata["load_readiness"]["images_ready"]
    assert time.monotonic() - started < 8


@pytest.mark.parametrize("valid", [True, False])
def test_native_poster_decode_and_hidden_password_modal(sites, native_capture, valid):
    output = BytesIO()
    Image.new("RGB", (320, 240), "green").save(output, "PNG")
    routes = {
        "/": html(
            '<h1>Public homepage</h1><div style="display:none"><input type="password"></div><video width="320" height="240" preload="none" poster="/poster.png" src="/not-started.webm"></video>'
        )
    }
    if valid:
        routes["/poster.png"] = 200, {"Content-Type": "image/png"}, output.getvalue()
    origin, _ = sites(routes)
    run, _ = native_capture
    _, metadata = run(origin + "/")
    assert metadata["capture_status"] == ("captured" if valid else "partial"), metadata
    assert metadata["load_readiness"]["media_ready"] == valid


def test_slow_native_css_background_finishes_before_screenshot(sites, native_capture):
    output = BytesIO()
    Image.new("RGB", (200, 200), "green").save(output, "PNG")

    def hero(request, body):
        time.sleep(5)
        return 200, {"Content-Type": "image/png"}, output.getvalue()

    origin, _ = sites(
        {
            "/": html("<style>body{height:900px;background-image:url(/hero.png)}</style>"),
            "/hero.png": hero,
        }
    )
    run, _ = native_capture
    png, metadata = run(origin + "/")
    assert metadata["capture_status"] == "captured", metadata
    assert Image.open(BytesIO(png)).convert("RGB").getpixel((300, 300)) == (0, 128, 0)


def test_native_http_video_plays_a_real_first_frame(sites, native_capture):
    # Two inert green VP8 frames; generated offline with the existing Pillow encoder.
    data = (Path(__file__).parent / "fixtures" / "website_capture_green.webm").read_bytes()

    def video(request, body):
        start = int(request.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
        return (
            206,
            {
                "Content-Type": "video/webm",
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}",
            },
            data[start:],
        )

    origin, requests = sites(
        {
            "/video": html(
                '<style>body{margin:0}</style><video width="320" height="240" autoplay muted loop playsinline src="/clip.webm"></video>'
            ),
            "/clip.webm": video,
        }
    )
    run, _ = native_capture
    png, metadata = run(origin + "/video")
    assert metadata["capture_status"] == "captured", metadata
    assert metadata["load_readiness"]["media_ready"]
    assert any(path == "/clip.webm" and headers.get("Range") for _, path, headers, _ in requests)
    pixel = Image.open(BytesIO(png)).convert("RGB").getpixel((100, 100))
    # Lossy VP8 color conversion varies slightly by native decoder.
    assert pixel[1] > 100 and pixel[1] > 2 * max(pixel[0], pixel[2])
