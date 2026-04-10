"""Plot stick transform point clouds from CSV logged by LogStickTransforms.

Usage:
    python -m utils.plot_stick_transforms logs/stick_transform_<timestamp>.csv

Produces a figure with three scatter plots side by side:
  1. Raw HID input (pre-pipeline)
  2. Shaped input (post-pipeline: deadband, curve, scale)
  3. Circle-to-square output

Each point is colored by its angle from center to show directional coverage.
A unit circle and unit square are overlaid for reference.
"""

import csv
import sys

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np


def load_csv(path: str):
    """Load stick transform CSV into numpy arrays."""
    rows = []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    def col(name):
        return np.array([float(r[name]) for r in rows])

    return {
        "raw_x": col("left_raw_x"),
        "raw_y": col("left_raw_y"),
        "shaped_x": col("left_shaped_x"),
        "shaped_y": col("left_shaped_y"),
        "c2s_x": col("left_c2s_x"),
        "c2s_y": col("left_c2s_y"),
    }


def plot_panel(ax, x, y, title, colors):
    """Draw one scatter panel with reference shapes."""
    # Unit square
    sq = patches.Rectangle((-1, -1), 2, 2, linewidth=1,
                           edgecolor='gray', facecolor='none',
                           linestyle='--', label='Unit square')
    ax.add_patch(sq)
    # Unit circle
    circ = plt.Circle((0, 0), 1, linewidth=1,
                       edgecolor='gray', facecolor='none',
                       linestyle=':', label='Unit circle')
    ax.add_patch(circ)

    ax.scatter(x, y, c=colors, s=2, alpha=0.6, cmap='hsv')
    ax.set_xlim(-1.15, 1.15)
    ax.set_ylim(-1.15, 1.15)
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.axhline(0, color='lightgray', linewidth=0.5)
    ax.axvline(0, color='lightgray', linewidth=0.5)
    ax.grid(True, alpha=0.3)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m utils.plot_stick_transforms <csv_file>")
        sys.exit(1)

    data = load_csv(sys.argv[1])

    # Color by angle from center (shows directional coverage)
    angles = np.arctan2(data["raw_y"], data["raw_x"])
    # Normalize to [0, 1] for colormap
    colors = (angles + np.pi) / (2 * np.pi)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Joystick Input Transform Comparison", fontsize=14)

    plot_panel(axes[0], data["raw_x"], data["raw_y"],
               "Raw HID Input", colors)
    plot_panel(axes[1], data["shaped_x"], data["shaped_y"],
               "Shaped (pipeline)", colors)
    plot_panel(axes[2], data["c2s_x"], data["c2s_y"],
               "Circle → Square", colors)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
