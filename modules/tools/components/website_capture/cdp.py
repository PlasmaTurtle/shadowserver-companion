"""Minimal bounded WebSocket client for a browser spawned by this process.

Only the loopback endpoint from its temporary profile is accepted. No origin
relaxation, session cookies, remote endpoint, or user-controlled protocol command.
"""

import base64
import hashlib
import json
import os
import socket
import select
import struct
import time
from urllib.parse import urlsplit

MAX_MESSAGE = 24 * 1024 * 1024


class CDP:
    def __init__(self, url, deadline):
        p = urlsplit(url)
        if (
            p.scheme != "ws"
            or p.hostname != "127.0.0.1"
            or not p.port
            or not p.path.startswith("/devtools/browser/")
            or p.query
            or p.fragment
            or p.username
        ):
            raise ValueError("Invalid local capture endpoint")
        self.cancel_event = None
        self.deadline = deadline
        self.socket = socket.create_connection(("127.0.0.1", p.port), timeout=2)
        self.buffer = bytearray()
        self.sequence = 0
        self.session = None
        self.events = []
        self.results = {}
        key = base64.b64encode(os.urandom(16)).decode()
        try:
            self.socket.sendall(
                (
                    f"GET {p.path} HTTP/1.1\r\nHost: 127.0.0.1:{p.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
                ).encode()
            )
            head = bytearray()
            while not head.endswith(b"\r\n\r\n"):
                head.extend(self._read(1))
                if len(head) > 8192:
                    raise ValueError("Invalid browser handshake")
            lines = head.decode("ascii").split("\r\n")
            headers = {
                line.split(":", 1)[0].lower(): line.split(":", 1)[1].strip()
                for line in lines[1:]
                if ":" in line
            }
            accept = base64.b64encode(
                hashlib.sha1(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(), usedforsecurity=False
                ).digest()
            ).decode()
            if (
                not lines[0].startswith("HTTP/1.1 101 ")
                or headers.get("sec-websocket-accept", "").strip() != accept
            ):
                raise ValueError("Browser handshake failed")
        except BaseException:
            self.close()
            raise

    def _read(self, count):
        while len(self.buffer) < count:
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise ValueError("Website capture cancelled")
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Website capture timed out")
            self.socket.settimeout(min(remaining, 0.25))
            try:
                data = self.socket.recv(min(65536, count - len(self.buffer)))
            except socket.timeout:
                continue
            if not data:
                raise ValueError("Capture browser disconnected")
            self.buffer.extend(data)
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data

    def _send(self, payload, opcode=1):
        mask = os.urandom(4)
        n = len(payload)
        if n > MAX_MESSAGE:
            raise ValueError("Capture message exceeds limit")
        header = bytes([0x80 | opcode])
        header += (
            bytes([0x80 | n])
            if n < 126
            else bytes([0xFE]) + struct.pack("!H", n)
            if n <= 65535
            else bytes([0xFF]) + struct.pack("!Q", n)
        )
        self.socket.settimeout(max(0.01, min(2, self.deadline - time.monotonic())))
        self.socket.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def receive(self):
        # A timeout is allowed only before a message starts; mid-message timeout
        # fails capture, avoiding parser state corruption and unbounded waits.
        if not self.buffer and not select.select([self.socket], [], [], 0.1)[0]:
            raise socket.timeout()
        first = self._read(1)[0]
        second = self._read(1)[0]
        data = bytearray()
        opcode = first & 15
        while True:
            length = second & 127
            if second & 128 or first & 0x70:
                raise ValueError("Invalid browser frame")
            if length == 126:
                length = struct.unpack("!H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read(8))[0]
            if length + len(data) > MAX_MESSAGE:
                raise ValueError("Browser message exceeds limit")
            chunk = self._read(length)
            if opcode == 8:
                raise ValueError("Capture browser closed")
            if opcode == 9:
                self._send(chunk, 10)
                return
            if opcode == 10:
                return
            if opcode not in (0, 1):
                raise ValueError("Invalid browser message")
            data.extend(chunk)
            if first & 128:
                break
            first, second = self._read(2)
            opcode = first & 15
            if opcode != 0:
                raise ValueError("Invalid fragmented browser message")
        message = json.loads(data)
        if "id" in message:
            self.results[message["id"]] = message
        elif "method" in message:
            self.events.append(message)

    def send(self, method, params=None, *, browser=False):
        self.sequence += 1
        message = {"id": self.sequence, "method": method, "params": params or {}}
        if self.session and not browser:
            message["sessionId"] = self.session
        self._send(json.dumps(message, separators=(",", ":")).encode())
        return self.sequence

    def call(self, method, params=None, *, browser=False):
        identity = self.send(method, params, browser=browser)
        while identity not in self.results:
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise ValueError("Website capture cancelled")
            try:
                self.receive()
            except socket.timeout:
                if time.monotonic() >= self.deadline:
                    raise TimeoutError("Website capture timed out") from None
        response = self.results.pop(identity)
        if "error" in response:
            raise ValueError("Capture browser could not complete " + method)
        return response.get("result", {})

    def close(self):
        self.socket.close()
