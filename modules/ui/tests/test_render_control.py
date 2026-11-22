"""Shared layout accepts caller control without importing report workflows."""

from contextvars import Context
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from modules.ui.components.vector_layout import _wrap
from modules.ui.helpers.render_control import check_rendering, rendering_checks


def test_layout_runs_without_investigations_or_web_frameworks():
    root = Path(__file__).resolve().parents[3]
    program = textwrap.dedent(
        """
        import sys

        class UnavailableWorkflow:
            def find_spec(self, fullname, path=None, target=None):
                if (fullname == "modules.investigations"
                    or fullname.startswith("modules.investigations.")
                    or fullname.split(".")[0] in {
                        "fastapi", "starlette", "pydantic", "pydantic_core"
                    }):
                    raise ImportError("Shared layout requested " + fullname)

        sys.path.insert(0, sys.argv[1])
        sys.meta_path.insert(0, UnavailableWorkflow())
        from modules.ui.components.vector_layout import _wrap
        assert _wrap("plain reusable layout", 200) == ["plain reusable layout"]
        """
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", program, str(root)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_caller_checkpoint_stops_long_layout_and_is_removed_after_failure():
    checks = []

    def stop_during_layout():
        checks.append(True)
        if len(checks) == 2:
            raise RuntimeError("caller cancelled rendering")

    with pytest.raises(RuntimeError, match="caller cancelled rendering"):
        with rendering_checks(stop_during_layout):
            _wrap("x" * 10_000, 40)
    assert len(checks) == 2
    assert _wrap("subsequent render", 200) == ["subsequent render"]
    assert len(checks) == 2


def test_scopes_restore_previous_check_and_keep_contexts_independent():
    checked = []

    def inner():
        checked.append("inner")
        raise RuntimeError("inner stopped")

    with rendering_checks(lambda: checked.append("outer")):
        check_rendering()
        Context().run(check_rendering)
        assert checked == ["outer"]
        with pytest.raises(RuntimeError, match="inner stopped"):
            with rendering_checks(inner):
                check_rendering()
        check_rendering()
    check_rendering()
    assert checked == ["outer", "inner", "outer"]
