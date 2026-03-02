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
import subprocess
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


def generate_controller_maps(output_directory):
    """Generate landscape controller map PNGs for each config in data/inputs/.

    Returns a list of (stem, [png_filenames]) tuples for successfully
    generated maps.  Multi-controller configs produce ``_page1``,
    ``_page2`` etc.; single-controller configs produce one file.
    """
    inputs_dir = Path("data/inputs")
    if not inputs_dir.is_dir():
        warnings.warn("data/inputs/ directory not found, skipping map generation")
        return []

    assets_dir = output_directory / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for yaml_file in sorted(inputs_dir.glob("*.yaml")):
        stem = yaml_file.stem
        map_stem = f"{stem}_controller_map"
        out_path = assets_dir / f"{map_stem}.png"
        try:
            subprocess.run([
                sys.executable, "-m", "host.controller_config",
                str(yaml_file),
                "--export", str(out_path),
                "--orientation", "landscape"
            ], check=True)

            # Collect actual output files (single or multi-page)
            if out_path.exists():
                pages = [out_path.name]
            else:
                pages = sorted(
                    p.name for p in assets_dir.glob(f"{map_stem}_page*.png"))

            if pages:
                print(f"Controller map generated: {', '.join(pages)}")
                generated.append((stem, pages))
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            warnings.warn(
                f"Could not generate controller map for "
                f"{yaml_file.name}: {e}")
    return generated


def generate_controller_docs_module(generated_maps):
    """Auto-generate controller_maps.py with a section for each controller map.

    This module is picked up by pdoc and rendered as a documentation page.
    """
    lines = [
        '"""Controller Maps',
        '',
        'Auto-generated by ``doc/build_docs.py``. Do not edit manually.',
        '',
        'Each controller configuration in ``data/inputs/`` is rendered as a',
        'landscape map image below.',
    ]

    for stem, pages in generated_maps:
        title = stem.replace("_", " ").title()
        lines.append('')
        lines.append(f'## {title}')
        for page_file in pages:
            lines.append('')
            lines.append(f'![{title} Controller Map](./assets/{page_file})')

    if not generated_maps:
        lines.append('')
        lines.append('*No controller maps were generated.*')

    lines.append('"""')
    lines.append('')

    module_path = Path("controller_maps.py")
    module_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {module_path} with {len(generated_maps)} controller map(s)")


def main():
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs")

    generated = generate_controller_maps(output_dir)
    generate_controller_docs_module(generated)

    candidates = discover_top_level()
    print(f"Discovered {len(candidates)} top-level modules: {' '.join(candidates)}")

    build_docs(candidates, output_dir)
    print(f"\nDocumentation written to {output_dir}/")


if __name__ == "__main__":
    main()
