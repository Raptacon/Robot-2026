"""Auto-build helper for the SPA.

A fresh checkout already includes the compiled bundle under ``static/``,
so the server runs without Node installed.  But when a contributor edits
the Svelte sources, we'd like the next ``python -m host.controller_web_editor``
invocation to pick up their changes without making them remember
``npm run build``.

This module compares ``web/src/`` mtimes against ``static/`` mtimes and
runs the build if the sources are newer.  When Node isn't on PATH or the
``CONTROLLER_WEB_EDITOR_SKIP_BUILD`` env var is set, the build is
silently skipped (the checked-in artifacts still work).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path


log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
WEB_DIR = HERE / "web"
SRC_DIR = WEB_DIR / "src"
STATIC_DIR = HERE / "static"
NODE_MODULES = WEB_DIR / "node_modules"


def _latest_mtime(root: Path) -> float:
    """Highest mtime under ``root`` (recursive), or 0.0 if empty/missing."""
    if not root.exists():
        return 0.0
    best = 0.0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                m = path.stat().st_mtime
            except OSError:
                continue
            if m > best:
                best = m
    return best


def _resolve_npm() -> str | None:
    """Return the absolute path to ``npm`` or ``None`` if not on PATH.

    Windows installs npm as ``npm.cmd``; ``shutil.which`` finds either
    once PATHEXT is honored, which it is by default.
    """
    return shutil.which("npm")


def _run(cmd: list[str], cwd: Path) -> bool:
    log.info("running %s in %s", " ".join(cmd), cwd)
    try:
        subprocess.run(cmd, cwd=cwd, check=True, shell=False)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        log.warning("build step failed: %s", exc)
        return False


def maybe_build_spa() -> str:
    """Build the SPA if sources are newer than the checked-in bundle.

    Returns one of: ``"skipped"``, ``"already_fresh"``, ``"built"``, or
    ``"failed"``.  Never raises -- this is a best-effort convenience.
    """
    if os.environ.get("CONTROLLER_WEB_EDITOR_SKIP_BUILD"):
        log.debug("skipping SPA build (CONTROLLER_WEB_EDITOR_SKIP_BUILD set)")
        return "skipped"

    if not WEB_DIR.is_dir():
        log.debug("no web/ directory; nothing to build")
        return "skipped"

    npm = _resolve_npm()
    if not npm:
        if not (STATIC_DIR / "index.html").is_file():
            log.warning(
                "npm not found and static/index.html missing -- the SPA "
                "won't load.  Easiest fix: re-run scripts/controller_editor/"
                "launch.{ps1,sh}, which auto-installs Node.  Or install "
                "Node.js manually from https://nodejs.org and run "
                "'npm install && npm run build' in %s", WEB_DIR)
        else:
            log.debug("npm not on PATH; using existing static/ bundle")
        return "skipped"

    src_mtime = max(
        _latest_mtime(SRC_DIR),
        (WEB_DIR / "index.html").stat().st_mtime if (WEB_DIR / "index.html").is_file() else 0.0,
        (WEB_DIR / "package.json").stat().st_mtime if (WEB_DIR / "package.json").is_file() else 0.0,
        (WEB_DIR / "vite.config.ts").stat().st_mtime if (WEB_DIR / "vite.config.ts").is_file() else 0.0,
    )
    static_mtime = _latest_mtime(STATIC_DIR)

    if static_mtime >= src_mtime and (STATIC_DIR / "index.html").is_file():
        log.debug("static/ is fresh (mtime %.0f >= %.0f)",
                  static_mtime, src_mtime)
        return "already_fresh"

    log.info("SPA sources newer than static/; rebuilding")
    if not NODE_MODULES.is_dir():
        # First-run npm install can take minutes -- drop --silent so the
        # user sees progress instead of staring at a frozen terminal.
        log.info("installing npm dependencies (first run, this may take a minute)")
        if not _run([npm, "install"], cwd=WEB_DIR):
            return "failed"

    if not _run([npm, "run", "build"], cwd=WEB_DIR):
        return "failed"
    return "built"


__all__ = ["maybe_build_spa"]
