"""
Convert STEP files to GLTF/GLB for the camera visualizer.

Usage:
    python cad/convert_step.py cad/2026rev2.step cad/2026rev2.glb

Tries these backends in order:
  1. FreeCAD headless (best assembly fidelity, preserves part names)
  2. trimesh + cascadio (pip install trimesh[easy] cascadio)

If neither is available, prints instructions for manual export from Onshape.
"""

import os
import sys


def convert_freecad(step_path: str, output_path: str) -> bool:
    """Convert using FreeCAD's Python API (headless)."""
    try:
        import FreeCAD
        import Part
        import MeshPart
        import Mesh
    except ImportError:
        return False

    print(f"Using FreeCAD backend...")
    doc = FreeCAD.newDocument("convert")
    Part.insert(step_path, doc.Name)

    meshes = []
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.Shape.Faces:
            mesh = MeshPart.meshFromShape(
                obj.Shape,
                LinearDeflection=0.1,
                AngularDeflection=0.5,
            )
            meshes.append(mesh)

    if not meshes:
        print("Error: No geometry found in STEP file")
        return False

    combined = meshes[0]
    for m in meshes[1:]:
        combined.addMesh(m)

    # FreeCAD exports in mm, GLTF expects meters
    mat = FreeCAD.Matrix()
    mat.scale(0.001, 0.001, 0.001)
    combined.transform(mat)

    combined.write(output_path)
    print(f"Wrote {output_path} ({os.path.getsize(output_path)} bytes)")
    return True


def convert_trimesh(step_path: str, output_path: str) -> bool:
    """Convert using trimesh with cascadio backend."""
    try:
        import trimesh
    except ImportError:
        return False

    try:
        import cascadio  # noqa: F401 — registers as trimesh backend
    except ImportError:
        print("trimesh found but cascadio not installed.")
        print("Install with: pip install cascadio")
        return False

    print(f"Using trimesh + cascadio backend...")
    scene = trimesh.load(step_path)

    if isinstance(scene, trimesh.Scene):
        # Export scene as GLB (preserves hierarchy)
        data = scene.export(file_type='glb')
    elif isinstance(scene, trimesh.Trimesh):
        data = scene.export(file_type='glb')
    else:
        print(f"Error: Unexpected type {type(scene)}")
        return False

    with open(output_path, 'wb') as f:
        f.write(data)

    print(f"Wrote {output_path} ({os.path.getsize(output_path)} bytes)")
    return True


def main():
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <input.step> <output.glb>")
        sys.exit(1)

    step_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.isfile(step_path):
        print(f"Error: {step_path} not found")
        sys.exit(1)

    # Try backends in order
    if convert_freecad(step_path, output_path):
        return
    if convert_trimesh(step_path, output_path):
        return

    # Neither backend available
    print()
    print("=" * 60)
    print("No conversion backend available.")
    print()
    print("Option 1: Export GLTF directly from Onshape")
    print("  1. Open the assembly in Onshape")
    print("  2. Click the Export button (or right-click the assembly tab)")
    print("  3. Select 'GLTF' format")
    print("  4. Download and place the .gltf file in the cad/ directory")
    print()
    print("Option 2: Install a conversion backend")
    print("  pip install trimesh[easy] cascadio")
    print("  Then re-run this script.")
    print()
    print("Option 3: Install FreeCAD")
    print("  Download from https://www.freecadweb.org/")
    print("  Run: FreeCADcmd cad/convert_step.py <input> <output>")
    print("=" * 60)
    sys.exit(1)


if __name__ == '__main__':
    main()
