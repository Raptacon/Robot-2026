"""Off-screen PIL renderer for controller config export.

Renders controller layouts to PIL Images for PNG/PDF export.
Mirrors the visual style of controller_canvas.py but draws entirely
with PIL so it works headlessly (no tkinter window needed).
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from utils.controller.model import ControllerConfig, FullConfig
from .layout_coords import (
    XBOX_INPUTS, XBOX_INPUT_MAP, InputCoord, _IMG_W, _IMG_H,
)
from .controller_canvas import (
    _find_image_path, _find_gear_icon, _find_rumble_icon,
    LINE_COLOR, BOX_OUTLINE, BOX_FILL, BOX_FILL_ASSIGNED,
    UNASSIGNED_TEXT, UNASSIGNED_COLOR, ASSIGNED_COLOR,
    AXIS_INDICATOR_COLORS,
)

# Print-specific box dimensions (larger than screen for readability)
BOX_WIDTH = 185
BOX_HEIGHT = 42
BOX_PAD = 6
ACTION_LINE_H = 26  # vertical spacing per action line

try:
    import cairosvg
    HAS_CAIROSVG = True
except (ImportError, OSError):
    HAS_CAIROSVG = False

# Page sizes at 150 DPI (US Letter 8.5 x 11 inches)
DPI = 150
PAGE_W_PORTRAIT = int(8.5 * DPI)   # 1275
PAGE_H_PORTRAIT = int(11 * DPI)    # 1650
PAGE_W_LANDSCAPE = int(11 * DPI)   # 1650
PAGE_H_LANDSCAPE = int(8.5 * DPI)  # 1275

# Margins
MARGIN = int(0.4 * DPI)  # 60px at 150 DPI


def _get_font(size: int, bold: bool = False):
    """Load a TrueType font with fallback to default.

    Prefers Verdana for its wide, heavy strokes that stay readable
    at small sizes and in print.
    """
    if bold:
        names = ["verdanab.ttf", "Verdana Bold.ttf",
                 "arialbd.ttf", "Arial Bold.ttf"]
    else:
        names = ["verdana.ttf", "Verdana.ttf",
                 "arial.ttf", "Arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            pass
    # Fallback
    return ImageFont.load_default()


def _load_controller_image() -> Image.Image:
    """Load the Xbox controller image for rendering."""
    img_path = _find_image_path()
    if img_path.suffix == ".svg" and HAS_CAIROSVG:
        png_data = cairosvg.svg2png(
            url=str(img_path), output_width=744, output_height=500,
        )
        return Image.open(io.BytesIO(png_data)).convert("RGBA")
    png_path = img_path.with_suffix(".svg.png")
    if not png_path.exists():
        png_path = img_path
    return Image.open(str(png_path)).convert("RGBA")


def _load_gear_icon() -> Image.Image | None:
    """Load the team gear logo."""
    path = _find_gear_icon()
    if path:
        try:
            return Image.open(str(path)).convert("RGBA")
        except Exception:
            pass
    return None


def _load_rumble_icon() -> Image.Image | None:
    """Load the rumble icon."""
    path = _find_rumble_icon()
    if not path:
        return None
    try:
        if path.suffix == ".svg" and HAS_CAIROSVG:
            data = cairosvg.svg2png(
                url=str(path), output_width=64, output_height=64,
            )
            return Image.open(io.BytesIO(data)).convert("RGBA")
        elif path.suffix != ".svg":
            return Image.open(str(path)).convert("RGBA")
    except Exception:
        pass  # Non-fatal: caller falls back to generated icon
    return None


def _make_rumble_fallback(size: int) -> Image.Image:
    """Draw a simple rumble icon when SVG can't be loaded."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 24
    d.rectangle([s * 2, s * 5, s * 15, s * 16], fill=(0, 0, 0, 255))
    d.rectangle([s * 17, s * 8, s * 18, s * 11.5], fill=(0, 0, 0, 255))
    d.rectangle([s * 17, s * 9.5, s * 22, s * 11.5], fill=(0, 0, 0, 255))
    for y_top in [7, 9, 11, 13]:
        d.rectangle([s * 5, s * y_top, s * 14, s * (y_top + 0.8)],
                    fill=(255, 255, 255, 255))
    d.rectangle([s * 3, s * 17, s * 16, s * 19], fill=(0, 0, 0, 255))
    return img


def render_controller(
    ctrl: ControllerConfig,
    width: int,
    height: int,
    label_positions: dict[str, tuple[int, int]] | None = None,
    hide_unassigned: bool = False,
) -> Image.Image:
    """Render a single controller layout to a PIL Image.

    Args:
        ctrl: Controller config with bindings.
        width: Target image width in pixels.
        height: Target image height in pixels.
        label_positions: Optional custom label positions (img pixel coords).
        hide_unassigned: If True, skip inputs with no bindings.

    Returns:
        RGB PIL Image with the rendered controller layout.
    """
    label_positions = label_positions or {}
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)

    # Fonts
    title_font = _get_font(28, bold=True)
    label_font = _get_font(14, bold=True)
    action_font = _get_font(19, bold=True)
    unassigned_font = _get_font(16)

    # Title
    title = ctrl.name or f"Controller {ctrl.port}"
    title_text = f"{title} (Port {ctrl.port})"
    draw.text((MARGIN, 4), title_text, fill="#333333", font=title_font)
    title_h = 40

    # Available area below title
    area_top = title_h
    area_w = width
    area_h = height - area_top

    # Load and scale controller image
    ctrl_img = _load_controller_image()
    img_w, img_h = ctrl_img.size

    pad_x = BOX_WIDTH + 30
    avail_w = area_w - 2 * pad_x
    avail_h = area_h - 40

    scale = min(avail_w / img_w, avail_h / img_h, 1.5)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)

    resized = ctrl_img.resize((new_w, new_h), Image.LANCZOS)

    # Center the image in the area
    img_left = (area_w - new_w) // 2
    img_top = area_top + (area_h - new_h) // 2

    page.paste(resized, (img_left, img_top), resized)

    # Coordinate mapping helpers
    def map_frac(frac_x, frac_y):
        return (img_left + frac_x * new_w, img_top + frac_y * new_h)

    def map_label(inp: InputCoord):
        if inp.name in label_positions:
            px, py = label_positions[inp.name]
            lx = img_left + (px / _IMG_W) * new_w
            ly = img_top + (py / _IMG_H) * new_h
        else:
            lx = img_left + inp.label_x * new_w
            ly = img_top + inp.label_y * new_h
        lx = max(2, min(lx, width - BOX_WIDTH - 2))
        ly = max(2, min(ly, height - BOX_HEIGHT - 2))
        return lx, ly

    # Draw rumble icons on the controller
    rumble_icon = _load_rumble_icon()
    if rumble_icon is None:
        rumble_icon = _make_rumble_fallback(64)
    icon_size = BOX_WIDTH // 4
    rumble_resized = rumble_icon.resize((icon_size, icon_size), Image.LANCZOS)
    for name in ["rumble_left", "rumble_both", "rumble_right"]:
        inp = XBOX_INPUT_MAP.get(name)
        if inp:
            cx, cy = map_frac(inp.anchor_x, inp.anchor_y)
            ix = int(cx - icon_size / 2)
            iy = int(cy - icon_size / 2)
            page.paste(rumble_resized, (ix, iy), rumble_resized)

    # Draw gear logo in top-right
    gear_img = _load_gear_icon()
    if gear_img:
        logo_size = 72
        gear_resized = gear_img.resize((logo_size, logo_size), Image.LANCZOS)
        page.paste(gear_resized,
                   (width - logo_size - 8, 4), gear_resized)

    # Draw each input's leader line and binding box
    for inp in XBOX_INPUTS:
        actions = ctrl.bindings.get(inp.name, [])
        has_actions = len(actions) > 0

        if hide_unassigned and not has_actions:
            continue

        ax, ay = map_frac(inp.anchor_x, inp.anchor_y)
        lx, ly = map_label(inp)
        box_cx = lx + BOX_WIDTH / 2
        box_cy = ly + BOX_HEIGHT / 2

        # Leader line
        line_w = 4 if has_actions else 1
        draw.line([(ax, ay), (box_cx, box_cy)],
                  fill=LINE_COLOR, width=line_w)

        fill = BOX_FILL_ASSIGNED if has_actions else BOX_FILL
        label_h = 21  # space for input label row
        total_height = (label_h + len(actions) * ACTION_LINE_H
                        if has_actions else BOX_HEIGHT)

        # Box background
        draw.rectangle(
            [lx, ly, lx + BOX_WIDTH, ly + total_height],
            fill=fill, outline=BOX_OUTLINE, width=1,
        )

        # Axis color indicator
        axis_tag = None
        if inp.name.endswith("_x"):
            axis_tag = "X"
        elif inp.name.endswith("_y"):
            axis_tag = "Y"
        label_color = (AXIS_INDICATOR_COLORS[axis_tag]
                       if axis_tag else "#555555")

        # Input label
        draw.text((lx + BOX_PAD, ly + 1), inp.display_name,
                  fill=label_color, font=label_font)

        # Action names or unassigned
        if has_actions:
            for i, action in enumerate(actions):
                draw.text((lx + BOX_PAD, ly + label_h + i * ACTION_LINE_H),
                          action, fill=ASSIGNED_COLOR, font=action_font)
        else:
            draw.text((lx + BOX_PAD, ly + label_h),
                      UNASSIGNED_TEXT, fill=UNASSIGNED_COLOR,
                      font=unassigned_font)

    return page


def render_portrait_page(
    controllers: list[ControllerConfig],
    label_positions: dict[str, tuple[int, int]] | None = None,
    hide_unassigned: bool = False,
) -> Image.Image:
    """Render up to 2 controllers stacked vertically on a portrait page."""
    page = Image.new("RGB", (PAGE_W_PORTRAIT, PAGE_H_PORTRAIT), "white")
    slot_h = (PAGE_H_PORTRAIT - MARGIN) // 2

    for i, ctrl in enumerate(controllers[:2]):
        ctrl_img = render_controller(
            ctrl, PAGE_W_PORTRAIT, slot_h, label_positions,
            hide_unassigned)
        page.paste(ctrl_img, (0, i * slot_h + (MARGIN // 2)))

    return page


def render_landscape_page(
    ctrl: ControllerConfig,
    label_positions: dict[str, tuple[int, int]] | None = None,
    hide_unassigned: bool = False,
) -> Image.Image:
    """Render 1 controller on a landscape page."""
    return render_controller(
        ctrl, PAGE_W_LANDSCAPE, PAGE_H_LANDSCAPE, label_positions,
        hide_unassigned)


def export_pages(
    config: FullConfig,
    orientation: str,
    output_path: str | Path,
    label_positions: dict[str, tuple[int, int]] | None = None,
    hide_unassigned: bool = False,
):
    """Export all controllers as PNG or multi-page PDF.

    Args:
        config: Full controller configuration.
        orientation: "portrait" (2 per page) or "landscape" (1 per page).
        output_path: Destination file path (.png or .pdf).
        label_positions: Optional custom label positions.
        hide_unassigned: If True, skip inputs with no bindings.
    """
    output_path = Path(output_path)
    fmt = output_path.suffix.lower().lstrip(".")
    if fmt not in ("png", "pdf"):
        raise ValueError(f"Unsupported format: {fmt} (use .png or .pdf)")

    controllers = [config.controllers[p]
                   for p in sorted(config.controllers.keys())]
    if not controllers:
        raise ValueError("No controllers to export")

    pages: list[Image.Image] = []

    if orientation == "portrait":
        # Group controllers in pairs
        for i in range(0, len(controllers), 2):
            batch = controllers[i:i + 2]
            pages.append(render_portrait_page(
                batch, label_positions, hide_unassigned))
    else:
        for ctrl in controllers:
            pages.append(render_landscape_page(
                ctrl, label_positions, hide_unassigned))

    if fmt == "pdf":
        # Pillow multi-page PDF
        first = pages[0]
        rest = pages[1:] if len(pages) > 1 else []
        first.save(str(output_path), "PDF", resolution=DPI,
                   save_all=True, append_images=rest)
    else:
        # PNG — single page or numbered pages
        if len(pages) == 1:
            pages[0].save(str(output_path), "PNG")
        else:
            stem = output_path.stem
            parent = output_path.parent
            for i, page in enumerate(pages, 1):
                name = f"{stem}_page{i}.png"
                page.save(str(parent / name), "PNG")
