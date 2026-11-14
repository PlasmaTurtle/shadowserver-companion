"""Capture failure visibility and alternate validated endpoint behavior."""

import asyncio
import socket
import ssl

from workbench.website_capture.diagnostics import network_error, navigation_error
from workbench.website_capture import transport


def test_safe_diagnostics_do_not_disclose_exception_urls():
    secret = "https://user:secret@example.com/?token=private"
    assert network_error(socket.gaierror(secret)) == "DNS resolution failed"
    assert (
        network_error(ssl.SSLCertVerificationError(secret)) == "TLS certificate validation failed"
    )
    assert network_error(TimeoutError(secret)) == "Network request timed out"
    assert "secret" not in network_error(ValueError(secret))
    message = navigation_error(
        {"result": {"errorText": "net::ERR_BLOCKED_BY_CLIENT " + secret}}, "DNS resolution failed"
    )
    assert "net::ERR_BLOCKED_BY_CLIENT" in message and "DNS resolution failed" in message
    assert "secret" not in message


def test_unreachable_public_address_does_not_prevent_next_address(monkeypatch):
    class Socket:
        def __init__(self, *args):
            self.closed = False

        def setblocking(self, value):
            pass

        def close(self):
            self.closed = True

    sockets = []

    def make_socket(*args):
        value = Socket()
        sockets.append(value)
        return value

    async def run():
        loop = asyncio.get_running_loop()
        attempted = []

        async def connect(raw, address):
            attempted.append(address)
            if len(attempted) == 1:
                raise OSError(101, "Network unreachable")

        monkeypatch.setattr(loop, "sock_connect", connect)
        monkeypatch.setattr(transport.socket, "socket", make_socket)
        answers = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
        ]
        connected = await transport.connect_public(answers)
        assert connected is sockets[1] and sockets[0].closed
        assert attempted == [item[4] for item in answers]
        connected.close()

    asyncio.run(run())
