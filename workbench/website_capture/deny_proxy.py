"""A per-capture loopback sink: un-intercepted browser traffic never forwards."""

import socket
import threading


class DenyProxy:
    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(8)
        self.socket.settimeout(0.2)
        self.port = self.socket.getsockname()[1]
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name="capture-deny-proxy", daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stopped.is_set():
            try:
                connection, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(0.1)
                try:
                    connection.sendall(
                        b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                except OSError:
                    pass

    def close(self):
        self.stopped.set()
        self.socket.close()
        self.thread.join(timeout=0.5)
