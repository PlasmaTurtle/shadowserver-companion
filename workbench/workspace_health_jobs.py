"""Single-flight, cancellable read checks without holding application write locks."""

from copy import deepcopy
import threading

from .primitives import now
from .workspace_health import inspect_workspace, InspectionStopped


class WorkspaceHealthJobs:
    def __init__(self, root):
        self.root = root
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.record = {"status": "idle"}
        self.thread = None

    def busy(self):
        with self.lock:
            return self.record["status"] == "running"

    def get(self):
        with self.lock:
            return deepcopy(self.record)

    def start(self):
        with self.lock:
            if self.busy():
                return self.get()
            self.stop.clear()
            self.record = {
                "status": "running",
                "started_at": now(),
                "phase": "Opening read-only database snapshots",
            }
            self.thread = threading.Thread(target=self._run, daemon=True, name="workspace-health")
            self.thread.start()
            return self.get()

    def _run(self):
        def progress(message):
            with self.lock:
                self.record["phase"] = message

        try:
            result = inspect_workspace(self.root, progress=progress, cancelled=self.stop.is_set)
            with self.lock:
                self.record.update(status="completed", result=result)
        except InspectionStopped as error:
            with self.lock:
                self.record.update(
                    status="cancelled" if self.stop.is_set() else "incomplete", message=str(error)
                )
        except Exception:
            with self.lock:
                self.record.update(
                    status="failed",
                    message="Workspace check could not complete. Saved data was not changed. Use offline recovery to inspect the workspace.",
                )
        finally:
            with self.lock:
                self.record["finished_at"] = now()

    def cancel(self):
        self.stop.set()
        return self.get()

    def shutdown(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
