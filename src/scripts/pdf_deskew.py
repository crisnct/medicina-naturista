"""Detect per-page skew and rotate original PDF content without rasterizing it."""

from __future__ import annotations

import math

import numpy as np
import pymupdf


def estimate_skew(
    x: np.ndarray,
    y: np.ndarray,
    max_angle: float = 30.0,
    bin_size: float = 2.0,
    min_gain: float = 1.06,
) -> float:
    """Find the baseline direction by maximizing horizontal projection peaks.

    Works with independently positioned OCR glyphs whose matrices say zero
    rotation even though their baselines follow a tilted scanned page.
    """
    if len(x) < 30 or max_angle == 0 or np.ptp(x) < 20:
        return 0.0
    # Bounded work for very dense pages; deterministic sampling.
    if len(x) > 12000:
        indexes = np.linspace(0, len(x) - 1, 12000, dtype=int)
        x, y = x[indexes], y[indexes]
    x, y = x - np.median(x), y - np.median(y)

    def score(angle: float) -> float:
        rad = math.radians(angle)
        projected = -math.sin(rad) * x + math.cos(rad) * y
        bins = np.floor((projected - projected.min()) / bin_size).astype(int)
        counts = np.bincount(bins)
        return float(np.dot(counts.astype(float), counts))

    coarse = np.linspace(-max_angle, max_angle, max(3, int(max_angle * 4) + 1))
    best = max(coarse, key=score)
    fine = np.linspace(max(-max_angle, best - 0.5), min(max_angle, best + 0.5), 21)
    best = float(max(fine, key=score))
    # Prefer no transformation when there is no convincing improvement.
    return best if abs(best) >= 0.15 and score(best) > score(0) * min_gain else 0.0


def estimate_page_skew(rendered_page, max_angle: float) -> float:
    """Analyze a bounded preview; the rendered pixels never replace PDF content."""
    scale = min(1.5, 1000 / max(rendered_page.rect.width, rendered_page.rect.height))
    pixmap = rendered_page.get_pixmap(
        matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY
    )
    values = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)
    height, width = values.shape
    # Ignore scanner borders, matching the existing OCR deskew algorithm.
    mask = (
        values[
            int(height * 0.1) : int(height * 0.9),
            int(width * 0.1) : int(width * 0.9),
        ]
        < 150
    )
    if not mask.size:
        return 0.0
    mask[:, mask.mean(axis=0) > 0.45] = False
    mask[mask.mean(axis=1) > 0.45, :] = False
    y, x = np.nonzero(mask)
    if len(x) < 100:
        return 0.0
    return estimate_skew(x.astype(float), y.astype(float), max_angle, 1.5, min_gain=1.005)


def deskew_page(page: pymupdf.Page, angle: float) -> pymupdf.Page:
    """Rotate original PDF streams, boxes and link coordinates entirely in memory."""
    if not angle:
        return page
    document = page.parent

    def numbers(values) -> str:
        return " ".join(f"{value:.10f}".rstrip("0").rstrip(".") or "0" for value in values)

    def inherited_box(name: str, fallback=None):
        xref = page.xref
        while xref:
            kind, value = document.xref_get_key(xref, name)
            if kind == "array":
                return pymupdf.Rect([float(item) for item in value.strip("[]").split()])
            parent_kind, parent = document.xref_get_key(xref, "Parent")
            xref = int(parent.split()[0]) if parent_kind == "xref" else 0
        return fallback

    # Matrix coordinates below are PDF coordinates (y upwards). Preserve /Rotate.
    rotation = pymupdf.Matrix(angle)
    media = inherited_box("MediaBox")
    bounds = media * rotation
    transform = rotation * pymupdf.Matrix(1, 0, 0, 1, -bounds.x0, -bounds.y0)
    crop = inherited_box("CropBox", media)
    boxes = {"MediaBox": media, "CropBox": crop}
    for name in ("BleedBox", "TrimBox", "ArtBox"):
        box = inherited_box(name)
        if box is not None:
            boxes[name] = box

    page.wrap_contents()
    content = b"q\n" + numbers(transform).encode("ascii") + b" cm\n"
    content += page.read_contents() + b"\nQ\n"
    xref = document.get_new_xref()
    document.update_object(xref, "<<>>")
    document.update_stream(xref, content)
    page.set_contents(xref)
    for name, box in boxes.items():
        document.xref_set_key(page.xref, name, "[" + numbers(box * transform) + "]")
    for xref, *_ in page.annot_xrefs():
        kind, value = document.xref_get_key(xref, "Rect")
        if kind == "array":
            rect = pymupdf.Rect([float(item) for item in value.strip("[]").split()])
            document.xref_set_key(xref, "Rect", "[" + numbers(rect * transform) + "]")
        kind, value = document.xref_get_key(xref, "QuadPoints")
        if kind == "array":
            points = [float(item) for item in value.strip("[]").split()]
            mapped = [
                coordinate
                for index in range(0, len(points), 2)
                for coordinate in pymupdf.Point(points[index : index + 2]) * transform
            ]
            document.xref_set_key(xref, "QuadPoints", "[" + numbers(mapped) + "]")
    return document.reload_page(page)
