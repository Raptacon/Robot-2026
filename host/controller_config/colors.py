"""Shared color palette for controller config GUI canvas drawing.

Centralizes color hex values used by multiple editor widgets
(curve_editor_widget, spline_editor, segment_editor, preview_widget)
so they stay consistent and easy to update in one place.
"""

# Canvas backgrounds
BG_WHITE = "#ffffff"
BG_INACTIVE = "#f0f0f0"

# Grid lines
GRID_MINOR = "#e8e8e8"
GRID_MAJOR = "#c8c8c8"
GRID_AXIS = "#909090"

# Labels
LABEL_COLOR = "#505050"

# Curve / line drawing
CURVE_LINE = "#2060c0"

# Control point colors (spline + segment editors)
POINT_FILL = "#c02020"
POINT_OUTLINE = "#801010"
ENDPOINT_FILL = "#802020"

# Tangent handle colors (spline editor)
HANDLE_FILL = "#40a040"
HANDLE_LINE = "#80c080"

# Mirror / inversion preview
MIRROR_LINE = "#c0a0a0"
