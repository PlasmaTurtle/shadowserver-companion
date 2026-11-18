"""Windows sharing races must not strand cooperative workspace handoff."""

from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from workbench import schedule_handoff as handoff
from workbench.workspace_lock import acquire_lock


def sharing_error(code=32):
    error = PermissionError("Synthetic Windows sharing violation")
    error.winerror = code
    return error


class HandoffTests(unittest.TestCase):
    def test_reader_collision_during_cleanup_still_releases_workspace(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            marker, request = handoff._paths(root)
            ready, stop = threading.Event(), threading.Event()
            failures, collisions = [], set()
            unlink = Path.unlink

            def collide_once(path, *args, **kwargs):
                if path in (marker, request) and path not in collisions:
                    collisions.add(path)
                    raise sharing_error()
                return unlink(path, *args, **kwargs)

            def owner():
                try:
                    with closing(acquire_lock(root.parent, ".workspace-companion.lock")):
                        with handoff.scheduled_ownership(root, stop):
                            ready.set()
                            if not stop.wait(5):
                                raise AssertionError("Foreground did not request handoff")
                except BaseException as error:
                    failures.append(error)

            with patch.object(Path, "unlink", collide_once):
                worker = threading.Thread(target=owner)
                worker.start()
                try:
                    self.assertTrue(ready.wait(5))
                    self.assertTrue(handoff.request_handoff(root, timeout=5))
                    with closing(acquire_lock(root.parent, ".workspace-companion.lock")):
                        pass
                finally:
                    stop.set()
                    worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(collisions, {marker, request})
            self.assertFalse(marker.exists())
            self.assertFalse(request.exists())

    def test_atomic_write_retries_reader_collision_and_removes_temporary_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "marker.json"
            path.write_text('{"nonce": "old"}')
            replace = handoff.os.replace
            calls = []

            def collide_once(source, target):
                calls.append((source, target))
                if len(calls) == 1:
                    self.assertEqual(json.loads(path.read_text()), {"nonce": "old"})
                    raise sharing_error(33)
                return replace(source, target)

            with patch.object(handoff.os, "replace", collide_once):
                handoff._write(path, {"nonce": "new"})
            self.assertEqual(len(calls), 2)
            self.assertEqual(json.loads(path.read_text()), {"nonce": "new"})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_cleanup_rechecks_owner_after_collision(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "marker.json"
            expected = {"nonce": "old"}
            replacement = {"nonce": "new"}
            path.write_text(json.dumps(expected))

            def changed_owner(*args, **kwargs):
                path.write_text(json.dumps(replacement))
                raise sharing_error()

            with patch.object(Path, "unlink", side_effect=changed_owner) as unlink:
                handoff._remove_owned(path, expected)
                self.assertEqual(unlink.call_count, 1)
            self.assertEqual(json.loads(path.read_text()), replacement)

    def test_persistent_sharing_error_is_bounded_and_propagates(self):
        error = sharing_error()
        with patch.object(handoff.time, "sleep") as sleep:
            operation = unittest.mock.Mock(side_effect=error)
            with self.assertRaises(PermissionError) as caught:
                handoff._retry_sharing_violation(operation)
        self.assertIs(caught.exception, error)
        self.assertEqual(operation.call_count, 20)
        self.assertEqual(sleep.call_count, 19)

    def test_unrelated_permission_error_is_not_retried(self):
        error = PermissionError("Access denied")
        error.winerror = 5
        with patch.object(handoff.time, "sleep") as sleep:
            operation = unittest.mock.Mock(side_effect=error)
            with self.assertRaises(PermissionError) as caught:
                handoff._retry_sharing_violation(operation)
        self.assertIs(caught.exception, error)
        self.assertEqual(operation.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
