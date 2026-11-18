"""Bounded launcher logs and safe streams for Windows windowless processes.

Log files live outside replaceable workspaces. A missing console is a normal
pythonw launch condition, never a reason to lose a scheduled run or its error.
"""

from contextlib import contextmanager
import io
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import tempfile
import traceback


_SENSITIVE_FIELD = re.compile(
    r"""(?ix)(["']?\b(?:api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|
        launch(?:er)?(?:[-_ ]?(?:token|key))?|secret|password|authorization|
        x-workbench-launcher|token|key)\b["']?\s*[:=]\s*)
        (?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;&}\]]+)"""
)
_AUTHORIZATION = re.compile(r"(?i)(\bauthorization\s*:\s*)(?:Bearer|Basic)\s+[^\s,;]+")
_UUID = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def redact(value):
    """Remove credential-shaped fields from messages, URLs and tracebacks."""
    text = str(value)
    text = _AUTHORIZATION.sub(r"\1[redacted]", text)
    text = _SENSITIVE_FIELD.sub(r"\1[redacted]", text)
    return _UUID.sub("[redacted identifier]", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


class QuietStreamHandler(logging.StreamHandler):
    def handleError(self, record):
        # A detached/closed Windows console must not cause recursive logging
        # errors. The rotating file remains the diagnostic record.
        return


class QuietRotatingFileHandler(RotatingFileHandler):
    def handleError(self, record):
        # logging's default diagnostic dumps the original record arguments,
        # bypassing the redacting formatter when a disk/rotation write fails.
        safe_write(sys.stderr, "Companion could not write its diagnostic log.\n")


class NullTextStream(io.TextIOBase):
    """Discard incidental prints without persisting tokens or growing memory."""

    @property
    def encoding(self):
        return "utf-8"

    def writable(self):
        return True

    def write(self, value):
        return len(value)

    def flush(self):
        return None


def stream_available(stream):
    try:
        return (
            stream is not None and not getattr(stream, "closed", False) and callable(stream.write)
        )
    except (AttributeError, OSError, ValueError):
        return False


def safe_write(stream, message):
    """Best-effort console output; never replace a useful original failure."""
    if not stream_available(stream):
        return False
    try:
        stream.write(str(message))
        stream.flush()
        return True
    except (AttributeError, OSError, ValueError):
        return False


@contextmanager
def windowless_streams():
    """Supply bounded sinks only where pythonw omitted standard text streams."""
    originals = {name: getattr(sys, name) for name in ("stdout", "stderr")}
    replacements = {}
    for name, stream in originals.items():
        if not stream_available(stream):
            try:
                # A real null device also supports buffer/fileno for imported
                # libraries that expect a complete standard-stream interface.
                replacements[name] = open(os.devnull, "w", encoding="utf-8")
            except OSError:
                replacements[name] = NullTextStream()
            setattr(sys, name, replacements[name])
    try:
        yield
    finally:
        for name, stream in replacements.items():
            setattr(sys, name, originals[name])
            stream.close()


def _folders(workspace, app_id, fallback_folder):
    folders = []
    if workspace is not None:
        workspace = Path(workspace).resolve()
        folders.append(workspace.parent / (workspace.name + "-logs"))
    elif fallback_folder is not None:
        # The installed desktop can retain its established bootstrap location.
        folders.append(Path(fallback_folder))
    local = os.environ.get("LOCALAPPDATA")
    if local and Path(local).is_absolute():
        folders.append(Path(local) / app_id / "logs")
    else:
        try:
            folders.append(Path.home() / ".shadowserver-companion" / app_id / "logs")
        except (OSError, RuntimeError):
            pass
    folders.append(Path(tempfile.gettempdir()) / (app_id + "-startup"))
    return list(dict.fromkeys(folders))


def configure_runtime_logging(
    workspace=None,
    *,
    app_id="ShadowserverCompanion",
    name="application",
    console=True,
    level=logging.INFO,
    fallback_folder=None,
):
    """Configure persistent rotating diagnostics; return their containing folder."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", app_id) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,40}", name
    ):
        raise ValueError("Invalid runtime log identity")
    failure = None
    for folder in _folders(workspace, app_id, fallback_folder):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            handler = QuietRotatingFileHandler(
                folder / (name + ".log"),
                maxBytes=2_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            break
        except OSError as error:
            failure = error
    else:
        raise OSError("Persistent runtime logging is unavailable") from failure
    handlers = [handler]
    if console and stream_available(sys.stderr) and not isinstance(sys.stderr, NullTextStream):
        handlers.append(QuietStreamHandler(sys.stderr))
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    for item in handlers:
        item.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=handlers, force=True)
    return folder


def log_failure(logger, message, error):
    """Record locations and type without arbitrary provider/credential values.

    Windowless startup diagnostics need the failing operation and stack, not
    untrusted exception arguments, locals, or source lines that may hold secrets.
    """
    frames = traceback.extract_tb(error.__traceback__)
    locations = "\n".join(
        f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}' for frame in frames
    )
    number = getattr(error, "errno", None)
    errno = f" (errno={number})" if isinstance(number, int) else ""
    logger.error("%s: %s%s\n%s", message, type(error).__name__, errno, locations)
