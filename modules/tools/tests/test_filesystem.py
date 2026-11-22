"""Filesystem tools publish complete bytes and read only requested contained data."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import threading

import pytest

from modules.tools.components import filesystem
from tests.filesystem_helpers import create_test_symlink


def test_atomic_publication_preserves_bytes_and_cleans_up(tmp_path):
    target = tmp_path / "state.json"
    for body in (b"first\x00\xff\r\n", b'{"next":true}\n'):
        assert filesystem.atomic_write(target, body) is None
        assert target.read_bytes() == body
        assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("stage", ["write", "fsync", "replace"])
def test_failed_publication_retains_old_target_and_removes_temp(tmp_path, monkeypatch, stage):
    target = tmp_path / "state.json"
    target.write_bytes(b"previous state")

    def fail(*args, **kwargs):
        raise OSError("synthetic publication failure")

    if stage == "write":
        original = filesystem.tempfile.NamedTemporaryFile

        def failing_file(**kwargs):
            stream = original(**kwargs)
            stream.write = fail
            return stream

        monkeypatch.setattr(filesystem.tempfile, "NamedTemporaryFile", failing_file)
    else:
        monkeypatch.setattr(filesystem.os, stage, fail)
    with pytest.raises(OSError, match="synthetic publication failure"):
        filesystem.atomic_write(target, b"replacement")
    assert target.read_bytes() == b"previous state"
    assert list(tmp_path.iterdir()) == [target]


def test_independent_publications_with_same_stem_do_not_share_temps(tmp_path, monkeypatch):
    targets = [tmp_path / "state.json", tmp_path / "state.bin"]
    for target in targets:
        target.write_bytes(b"old")
    replace = filesystem.os.replace
    ready = threading.Barrier(2, timeout=10)
    temporary_paths = []

    def publish(source, destination):
        if destination in targets:
            temporary_paths.append(source)
            assert source.parent == tmp_path
            ready.wait()
        replace(source, destination)

    monkeypatch.setattr(filesystem.os, "replace", publish)
    bodies = [b"a" * 128_000, b"b" * 256_000]
    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [
            executor.submit(filesystem.atomic_write, target, body)
            for target, body in zip(targets, bodies)
        ]
        for task in tasks:
            task.result(timeout=15)
    assert len(set(temporary_paths)) == 2
    assert [target.read_bytes() for target in targets] == bodies
    assert set(tmp_path.iterdir()) == set(targets)


def test_callers_coordinate_writers_to_one_destination(tmp_path):
    # Concurrent native replacements of one destination can raise WinError 5.
    # The shared tool documents caller coordination; it does not retry or lock.
    target = tmp_path / "state.json"
    target.write_bytes(b"old")
    ready = threading.Barrier(2, timeout=10)
    lock = threading.Lock()
    bodies = [b"a" * 128_000, b"b" * 256_000]

    def write(body):
        ready.wait()
        with lock:
            filesystem.atomic_write(target, body)

    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [executor.submit(write, body) for body in bodies]
        for task in tasks:
            task.result(timeout=15)
    assert target.read_bytes() in bodies
    assert list(tmp_path.iterdir()) == [target]


def test_read_nested_file_checks_requested_digest_and_limit(tmp_path):
    folder = tmp_path / "nested"
    folder.mkdir()
    body = "Café\r\n".encode()
    (folder / "body.bin").write_bytes(body)
    assert filesystem.contained_directory(tmp_path, "nested") == folder
    assert filesystem.contained_directory(tmp_path, ".") == tmp_path
    assert (
        filesystem.read_contained_file(
            tmp_path,
            "nested/body.bin",
            sha256=hashlib.sha256(body).hexdigest(),
            max_bytes=len(body),
        )
        == body
    )
    with pytest.raises(filesystem.DigestMismatch):
        filesystem.read_contained_file(tmp_path, "nested/body.bin", sha256="0" * 64)
    with pytest.raises(filesystem.FileTooLarge):
        filesystem.read_contained_file(tmp_path, "nested/body.bin", max_bytes=len(body) - 1)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../outside",
        "/outside",
        "./body",
        "nested//body",
        "body/",
        "body.",
        "body ",
        "body:stream",
        "nested\\body",
        "bad\x00name",
    ],
)
def test_noncanonical_file_paths_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        filesystem.contained_file(tmp_path, name)


def test_missing_file_and_directory_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        filesystem.contained_file(tmp_path, "missing")
    with pytest.raises(ValueError):
        filesystem.contained_directory(tmp_path, "missing")
    with pytest.raises(ValueError):
        filesystem.contained_file(tmp_path, ".")


@pytest.mark.parametrize("linked", ["file", "directory", "root"])
def test_symbolic_links_are_rejected(tmp_path, linked):
    root = tmp_path / "root"
    root.mkdir()
    folder = root / "real"
    folder.mkdir()
    (folder / "body.bin").write_bytes(b"content")
    if linked == "file":
        create_test_symlink(root / "linked.bin", folder / "body.bin")
        relative = "linked.bin"
    elif linked == "directory":
        create_test_symlink(root / "linked", folder, target_is_directory=True)
        relative = "linked/body.bin"
        with pytest.raises(ValueError):
            filesystem.contained_directory(root, "linked")
    else:
        create_test_symlink(tmp_path / "linked", root, target_is_directory=True)
        root = tmp_path / "linked"
        relative = "real/body.bin"
    with pytest.raises(ValueError):
        filesystem.read_contained_file(root, relative)
