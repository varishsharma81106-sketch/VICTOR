"""
test_cli_import.py — CLI import regression tests (v4.9)

These five tests exist because cli.py shipped broken on every invocation
path from v4.6 through v4.8: a bare `from config import VictorConfig`
crashed whether invoked as `python -m victor.cli`, `from victor import cli`,
or through the installed console script. None of the prior 142 tests imported
cli.py, so the suite stayed green while the product's primary entry point
was completely broken.

Lesson encoded as tests, not just documentation:
  - At minimum one test must import each module the way a real user would
    invoke it (for CLI modules: as a module-level import, not just
    `from X import Y` for a single function).
  - A green test count is evidence about the modules actually imported,
    not about the product as a whole.

Ref: PRD v3.3 Section 5 (CLI status), Section 17 (risk: green suite ≠
     working product), P0-F007.
"""

import importlib
import subprocess
import sys


# ---------------------------------------------------------------------------
# 1. Module-level import
# ---------------------------------------------------------------------------

def test_cli_module_importable():
    """
    `from victor import cli` must not raise ImportError.

    This is the check that would have caught the v4.6-v4.8 bare-import bug
    (`from config import VictorConfig` instead of `from .config import
    VictorConfig`) on first run.
    """
    # If this raises, the bug is back.
    from victor import cli  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Attribute presence — the main Click group must exist
# ---------------------------------------------------------------------------

def test_cli_has_main_group():
    """
    victor.cli must expose a `main` Click group (the root command).
    Absence means the module loaded but the command wiring is broken.
    """
    from victor import cli
    assert hasattr(cli, "cli"), (
        "victor.cli has no `cli` attribute — the Click group is missing"
    )


# ---------------------------------------------------------------------------
# 3. importlib.import_module path
# ---------------------------------------------------------------------------

def test_cli_importlib_path():
    """
    importlib.import_module('victor.cli') must succeed.
    This mirrors what `python -m victor.cli` uses internally.
    """
    mod = importlib.import_module("victor.cli")
    assert mod is not None


# ---------------------------------------------------------------------------
# 4. `python -m victor.cli --help` exits 0
# ---------------------------------------------------------------------------

def test_cli_subprocess_help():
    """
    `python -m victor.cli --help` must exit with return code 0.

    This is the closest-to-real-user-invocation test: it runs the CLI
    as a subprocess (not inside the current Python process), which catches
    issues that bare `import` checks miss (e.g. __main__.py missing,
    console_script entry point not wired, PATH issues after `pip install -e .`).
    """
    result = subprocess.run(
        [sys.executable, "-m", "victor.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"`python -m victor.cli --help` exited {result.returncode}.\n"
        f"stdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )
    # Basic sanity: help output should mention 'victor' or 'Usage'
    combined = result.stdout + result.stderr
    assert "victor" in combined.lower() or "usage" in combined.lower(), (
        "Help output doesn't look like a CLI help page"
    )


# ---------------------------------------------------------------------------
# 5. No stale bare-import pattern in cli.py source
# ---------------------------------------------------------------------------

def test_cli_no_bare_config_import():
    """
    Directly check that the fixed import line is present and the broken
    bare-import is absent.  This test makes the fix self-documenting and
    prevents the bug from being silently reintroduced during a refactor.
    """
    import inspect
    from victor import cli
    source = inspect.getsource(cli)

    # The broken form (v4.6-v4.8) must be absent
    assert "from config import VictorConfig" not in source, (
        "Bare-import bug reintroduced: found `from config import VictorConfig` "
        "in victor/cli.py — must be `from .config import VictorConfig`"
    )
    # The fixed form must be present
    assert "from .config import VictorConfig" in source, (
        "Expected `from .config import VictorConfig` not found in victor/cli.py"
    )
