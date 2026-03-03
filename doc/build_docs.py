#!/usr/bin/env python3
"""Build project documentation using pdoc.

Dynamically discovers all top-level source modules and packages, then
generates HTML docs. Modules or submodules that fail to import (e.g. due
to deprecated APIs or missing hardware dependencies) are skipped with a
warning rather than crashing the entire build.

Usage:
    python doc/build_docs.py [output_dir]
    # default output_dir is 'docs/'
"""

import glob
import os
import sys
import warnings
from pathlib import Path

# Ensure the project root (parent of doc/) is on sys.path and is the cwd
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Directories that should NOT be documented
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".github",
    ".venv",
    "venv",
    "ctre_sim",
    "deploy",
    "deploy_utils",
    "doc",
    "examples",
    "logs",
    "tests",
}


def discover_top_level():
    """Find top-level modules (.py files) and packages (directories with .py files).

    Only returns top-level names — pdoc walks packages automatically.
    """
    modules = []

    # Top-level .py files (skip private/internal files)
    for f in sorted(glob.glob("*.py")):
        name = os.path.splitext(f)[0]
        if name.startswith("_") or name in ("setup", "conftest"):
            continue
        modules.append(name)

    # Source directories containing .py files
    for entry in sorted(os.listdir(".")):
        if not os.path.isdir(entry):
            continue
        if entry in EXCLUDE_DIRS or entry.startswith("."):
            continue
        py_files = glob.glob(os.path.join(entry, "**", "*.py"), recursive=True)
        if py_files:
            modules.append(entry)

    return modules


def build_docs(modules, output_directory):
    """Build pdoc documentation, skipping modules that fail to import.

    pdoc's walk_specs discovers submodules fine but pdoc() crashes when
    it tries to load a discovered submodule that has import errors.
    We patch the pdoc() loop to catch and skip those failures.
    """
    import pdoc
    import pdoc.doc
    import pdoc.extract
    import pdoc.render

    # Phase 1: Let pdoc discover all module names (walk_specs handles errors)
    module_names = pdoc.extract.walk_specs(modules)
    print(f"pdoc discovered {len(module_names)} modules (including submodules)")

    # Phase 2: Load each module, skipping any that fail to import
    all_modules = {}
    for module_name in module_names:
        try:
            all_modules[module_name] = pdoc.doc.Module.from_name(module_name)
        except Exception as e:
            warnings.warn(f"Skipping {module_name}: {e}")

    if not all_modules:
        print("::error::No modules could be loaded for documentation")
        sys.exit(1)

    print(f"Loaded {len(all_modules)}/{len(module_names)} modules successfully")

    # Phase 3: Render HTML (copied from pdoc.pdoc with output_directory set)
    output_directory.mkdir(parents=True, exist_ok=True)
    for module in all_modules.values():
        out = pdoc.render.html_module(module, all_modules)
        outfile = output_directory / f"{module.fullname.replace('.', '/')}.html"
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_bytes(out.encode())

    index = pdoc.render.html_index(all_modules)
    if index:
        (output_directory / "index.html").write_bytes(index.encode())

    search = pdoc.render.search_index(all_modules)
    if search:
        (output_directory / "search.js").write_bytes(search.encode())


def main():
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs")

    candidates = discover_top_level()
    print(f"Discovered {len(candidates)} top-level modules: {' '.join(candidates)}")

    build_docs(candidates, output_dir)
    print(f"\nDocumentation written to {output_dir}/")


if __name__ == "__main__":
    main()
