"""Path resolution chokepoint.

All file paths accepted from the web client flow through ``safe_resolve``.
v1 allowlists ``data/`` under the repo root.  Widening the scope later is a
one-line change here.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories under REPO_ROOT that the editor may read/write.
ALLOWED_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "data",
)


class PathNotAllowedError(ValueError):
    """Raised when a requested path falls outside the allowlist."""


def safe_resolve(repo_relative: str) -> Path:
    """Resolve a client-supplied path against the repo root.

    The path must be relative and, after resolution, must live inside one
    of ``ALLOWED_ROOTS``.  Symlinks are followed; traversal via ``..`` is
    rejected because the resolved path leaves the allowed root.
    """
    if not repo_relative:
        raise PathNotAllowedError("empty path")
    candidate = (REPO_ROOT / repo_relative).resolve()
    for root in ALLOWED_ROOTS:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        return candidate
    raise PathNotAllowedError(
        f"path '{repo_relative}' is outside the allowed roots")


def list_yaml_configs() -> list[str]:
    """Return repo-relative YAML paths under every allowed root."""
    results: list[str] = []
    for root in ALLOWED_ROOTS:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.yaml")):
            results.append(str(p.relative_to(REPO_ROOT)).replace("\\", "/"))
    return results
