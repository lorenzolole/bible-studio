"""
Still RGBA layers composited over the video: foreground figures (the "Jesus in front"
edit), frame decorations and the fullscreen vignette.

They are built once with Pillow and cached, so FFmpeg only overlays a static frame
instead of blurring or drawing it on every frame.
"""
import hashlib
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIGURES_DIR = os.path.join(BASE_DIR, "assets", "figures")
LAYERS_CACHE_DIR = os.path.join(BASE_DIR, "cache", "layers")
LAYER_VERSION = "v5"

GOLD = (201, 164, 92)
WARM_GLOW = (255, 214, 150)

def _cached(kind: str, *parts) -> str:
    key = hashlib.sha1("|".join(str(p) for p in (LAYER_VERSION, kind) + parts).encode()).hexdigest()[:16]
    os.makedirs(LAYERS_CACHE_DIR, exist_ok=True)
    return os.path.join(LAYERS_CACHE_DIR, f"{kind}_{key}.png")

def _save_atomic(image: Image.Image, path: str):
    tmp = f"{path}.part.png"
    image.save(tmp)
    os.replace(tmp, path)

def luma_alpha(image: Image.Image, low: float = 10, high: float = 45) -> Image.Image:
    """
    Alpha for a figure painted on black (chiaroscuro): the black background turns transparent.
    Soft alpha comes from luminance; dark areas enclosed by the figure (eye sockets, beard,
    robe folds) stay opaque because only darkness connected to the image border counts as background.
    """
    rgb = image.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32)
    luma = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]

    # Painted "black" backgrounds carry texture (luma ~10-35), so thresholds follow the background
    # level, measured on the top and side borders (a bust usually runs through the bottom edge)
    border = np.concatenate([luma[:4].ravel(), luma[:, :4].ravel(), luma[:, -4:].ravel()])
    background_level = float(np.percentile(border, 90))
    low = max(low, background_level + 4)
    high = max(high, low + 35)
    soft = np.clip((luma - low) / (high - low), 0.0, 1.0) ** 0.8

    # Background = dark pixels connected to the border: grow from the border through dark pixels
    # (on a small copy for speed) until nothing changes
    small_w = 256
    small_h = max(1, round(rgb.height * small_w / rgb.width))
    small_luma = np.asarray(rgb.convert("L").resize((small_w, small_h), Image.Resampling.BILINEAR))
    dark = small_luma < low + 2
    # Close thin dark channels (hair strands, beard edges) so the background can't flood into the face
    figure_mask = ~dark
    for _ in range(3):
        grown_figure = figure_mask.copy()
        grown_figure[1:] |= figure_mask[:-1]
        grown_figure[:-1] |= figure_mask[1:]
        grown_figure[:, 1:] |= figure_mask[:, :-1]
        grown_figure[:, :-1] |= figure_mask[:, 1:]
        figure_mask = grown_figure
    dark = ~figure_mask
    background = np.zeros_like(dark)
    background[0, :], background[-1, :] = dark[0, :], dark[-1, :]
    background[:, 0] |= dark[:, 0]
    background[:, -1] |= dark[:, -1]
    while True:
        grown = background.copy()
        grown[1:] |= background[:-1]
        grown[:-1] |= background[1:]
        grown[:, 1:] |= background[:, :-1]
        grown[:, :-1] |= background[:, 1:]
        grown &= dark
        if np.array_equal(grown, background):
            break
        background = grown
    silhouette = Image.fromarray(np.where(background, 0, 255).astype(np.uint8))
    silhouette = silhouette.filter(ImageFilter.MinFilter(3)).resize(rgb.size, Image.Resampling.BILINEAR)
    solid = np.asarray(silhouette.filter(ImageFilter.GaussianBlur(6))).astype(np.float32) / 255.0

    alpha = np.maximum(soft, solid)
    return Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))

def fade_bottom_edge(alpha: Image.Image, fraction: float = 0.18) -> Image.Image:
    """A figure cut by the bottom of its image would end in a hard line; fade its last rows out."""
    a = np.asarray(alpha).astype(np.float32)
    if a[-3:].mean() < 20:
        return alpha
    h = a.shape[0]
    ramp_h = max(1, int(h * fraction))
    ramp = np.ones(h, dtype=np.float32)
    ramp[h - ramp_h:] = np.linspace(1.0, 0.0, ramp_h) ** 1.5
    return Image.fromarray((a * ramp[:, None]).astype(np.uint8))

def load_figure_rgba(figure_path: str) -> Image.Image:
    """Figure with transparency: PNG alpha if it has any, otherwise keyed out of a dark background."""
    image = Image.open(figure_path)
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        if rgba.getchannel("A").getextrema()[0] < 250:
            return rgba
    rgba = image.convert("RGBA")
    rgba.putalpha(luma_alpha(image))
    return rgba

def figure_layer(figure_path: str, width: int) -> str:
    """Cached RGBA layer: the figure scaled to `width` with a warm glow baked behind it."""
    out = _cached("figure", os.path.abspath(figure_path), os.path.getmtime(figure_path), width)
    if os.path.exists(out):
        return out
    fig = load_figure_rgba(figure_path)
    height = max(1, round(fig.height * width / fig.width))
    fig = fig.resize((width, height), Image.Resampling.LANCZOS)
    alpha = fade_bottom_edge(fig.getchannel("A"))
    fig.putalpha(alpha)

    pad = int(width * 0.08)
    canvas = Image.new("RGBA", (width + 2 * pad, height + pad), (0, 0, 0, 0))
    padded_alpha = Image.new("L", canvas.size, 0)
    padded_alpha.paste(alpha, (pad, pad))
    glow_alpha = padded_alpha.filter(ImageFilter.GaussianBlur(pad * 0.6)).point(lambda v: int(v * 0.55))
    glow = Image.new("RGBA", canvas.size, WARM_GLOW + (0,))
    glow.putalpha(glow_alpha)
    canvas.alpha_composite(glow)
    canvas.alpha_composite(fig, (pad, pad))
    _save_atomic(canvas, out)
    return out

def frame_decoration(width: int, height: int, radius: int, style: str, scale: float = 1.0) -> str | None:
    """Cached layer for the artwork frame finish: 'vintage' gold hairline ring, 'glow' warm halo.
    scale shrinks the ring width and halo size along with a smaller (preview) canvas."""
    if style not in ("vintage", "glow"):
        return None
    out = _cached("frame", style, width, height, radius, round(scale, 3))
    if os.path.exists(out):
        return out
    if style == "vintage":
        ss = 2  # supersampling for a smooth hairline
        ring = Image.new("RGBA", (width * ss, height * ss), (0, 0, 0, 0))
        ImageDraw.Draw(ring).rounded_rectangle(
            [(0, 0), (width * ss - 1, height * ss - 1)], radius=radius * ss,
            outline=GOLD + (235,), width=max(1, round(3 * scale * ss)))
        layer = ring.resize((width, height), Image.Resampling.LANCZOS)
    else:
        pad = max(8, round(70 * scale))
        layer = Image.new("RGBA", (width + 2 * pad, height + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            [(pad, pad), (pad + width - 1, pad + height - 1)], radius=radius, fill=(240, 200, 120, 150))
        layer = layer.filter(ImageFilter.GaussianBlur(max(4, 32 * scale)))
    _save_atomic(layer, out)
    return out

def fullscreen_vignette(width: int = 1080, height: int = 1920) -> str:
    """Cached top/bottom darkening gradient for full-bleed framing (keeps subtitles readable)."""
    out = _cached("vignette", width, height)
    if os.path.exists(out):
        return out
    alpha = np.zeros(height, dtype=np.float32)
    top = int(height * 0.24)
    bottom = int(height * 0.40)
    alpha[:top] = 0.45 * (1 - np.linspace(0, 1, top)) ** 1.6
    alpha[height - bottom:] = 0.68 * np.linspace(0, 1, bottom) ** 1.4
    column = (alpha * 255).astype(np.uint8)
    a = Image.fromarray(np.tile(column[:, None], (1, width)))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.putalpha(a)
    _save_atomic(layer, out)
    return out

def catalog() -> list[dict]:
    """Foreground figures in assets/figures (PNG with transparency), named via catalog.json when present."""
    names = {}
    catalog_path = os.path.join(FIGURES_DIR, "catalog.json")
    if os.path.exists(catalog_path):
        with open(catalog_path, "r", encoding="utf-8") as f:
            names = json.load(f)
    figures = []
    if os.path.isdir(FIGURES_DIR):
        for name in sorted(os.listdir(FIGURES_DIR)):
            if not name.lower().endswith(".png"):
                continue
            meta = names.get(name, {})
            figures.append({
                "id": name,
                "name": meta.get("name") or os.path.splitext(name)[0].replace("_", " ").title(),
                "path": f"assets/figures/{name}",
                "url": f"/assets/figures/{name}",
                "source": meta.get("source"),
            })
    return figures

def source_image(figure_path: str) -> str | None:
    """Artwork a figure was cut out of (catalog.json "source"), so a montage doesn't show it twice."""
    name = os.path.basename(figure_path)
    return next((f["source"] for f in catalog() if f["id"] == name), None)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        sys.exit("Usage: python3 figures.py <dark_background_image> <output.png>\n"
                 "Cuts a figure painted on black out into a PNG with transparency.")
    src, dst = sys.argv[1], sys.argv[2]
    rgba = load_figure_rgba(src)
    rgba.putalpha(fade_bottom_edge(rgba.getchannel("A")))
    rgba.save(dst)
    print(f"Saved {dst} ({rgba.width}x{rgba.height})")
