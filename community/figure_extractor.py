from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import fitz
except ModuleNotFoundError as exc:  # pragma: no cover - import guard for CLI users
    raise SystemExit("PyMuPDF is required. Install with: python -m pip install PyMuPDF") from exc


CAPTION_RE = re.compile(
    r"^\s*(?P<label>(?:(?:fig(?:ure)?\.?)\s*(?:[A-Z]?\d+(?:[.\-–—]\d+)*[A-Za-z]?|[A-Z]\d+)"
    r"(?:\s*\([A-Za-z0-9]+\))?|图\s*\d+[A-Za-z]?))\s*[:.\-–—]?\s*(?P<caption>.*)",
    re.IGNORECASE,
)


@dataclass
class RectData:
    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def from_rect(cls, rect: fitz.Rect) -> "RectData":
        return cls(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))

    def to_rect(self) -> fitz.Rect:
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)


@dataclass
class FigureCandidate:
    id: str
    page_index: int
    page_number: int
    label: str
    caption: str
    bbox: RectData
    caption_bbox: RectData
    crop_path: str
    page_path: str
    confidence: float
    method: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class TextBlock:
    rect: fitz.Rect
    text: str


@dataclass
class CaptionHit:
    label: str
    caption: str
    rect: fitz.Rect


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _rect_area(rect: fitz.Rect) -> float:
    width = max(0.0, rect.x1 - rect.x0)
    height = max(0.0, rect.y1 - rect.y0)
    return width * height


def _rect_union(rects: Iterable[fitz.Rect]) -> fitz.Rect | None:
    iterator = iter(rects)
    try:
        result = fitz.Rect(next(iterator))
    except StopIteration:
        return None
    for rect in iterator:
        result |= rect
    return result


def _inflate(rect: fitz.Rect, amount: float, page_rect: fitz.Rect) -> fitz.Rect:
    inflated = fitz.Rect(rect.x0 - amount, rect.y0 - amount, rect.x1 + amount, rect.y1 + amount)
    return inflated & page_rect


def _horizontal_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    return overlap / max(1.0, min(a.width, b.width))


def _block_text(block: dict) -> str:
    parts: list[str] = []
    for line in block.get("lines", []):
        line_text = "".join(span.get("text", "") for span in line.get("spans", []))
        if line_text.strip():
            parts.append(line_text)
    return _clean_text(" ".join(parts))


def _text_blocks(page: fitz.Page) -> list[TextBlock]:
    data = page.get_text("dict")
    blocks: list[TextBlock] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        text = _block_text(block)
        if text:
            blocks.append(TextBlock(rect=fitz.Rect(block["bbox"]), text=text))
    return blocks


def _image_blocks(page: fitz.Page) -> list[fitz.Rect]:
    data = page.get_text("dict")
    rects: list[fitz.Rect] = []
    for block in data.get("blocks", []):
        if block.get("type") == 1 and "bbox" in block:
            rect = fitz.Rect(block["bbox"])
            if _rect_area(rect) >= 400:
                rects.append(rect)
    return rects


def _drawing_blocks(page: fitz.Page) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing.get("rect", fitz.Rect()))
        if not rect.is_valid or rect.is_empty:
            continue
        area = _rect_area(rect)
        if area < 150 or rect.width < 8 or rect.height < 8:
            continue
        rects.append(rect)
    return rects


def _find_captions(blocks: list[TextBlock]) -> list[CaptionHit]:
    hits: list[CaptionHit] = []
    for index, block in enumerate(blocks):
        match = CAPTION_RE.match(block.text)
        if not match:
            continue

        label = _clean_text(match.group("label")).rstrip(":")
        caption_parts = [_clean_text(match.group("caption"))]

        # Captions sometimes continue in the next text block when the PDF columns wrap.
        # Keep this conservative: a larger gap usually means the next paragraph has started.
        for next_block in blocks[index + 1 : index + 3]:
            if next_block.rect.y0 - block.rect.y1 > 10:
                break
            if CAPTION_RE.match(next_block.text):
                break
            if abs(next_block.rect.x0 - block.rect.x0) <= 18:
                caption_parts.append(next_block.text)

        caption = _clean_text(" ".join(part for part in caption_parts if part))
        hits.append(CaptionHit(label=label, caption=caption, rect=block.rect))
    return hits


def _candidate_graphics_near_caption(
    caption_rect: fitz.Rect,
    graphic_rects: list[fitz.Rect],
    page_rect: fitz.Rect,
) -> list[fitz.Rect]:
    if not graphic_rects:
        return []

    above: list[tuple[float, fitz.Rect]] = []
    below: list[tuple[float, fitz.Rect]] = []
    max_distance = max(120.0, page_rect.height * 0.45)

    for rect in graphic_rects:
        if _horizontal_overlap(rect, caption_rect) < 0.08 and rect.width < page_rect.width * 0.45:
            continue
        if rect.y1 <= caption_rect.y0 + 6:
            distance = caption_rect.y0 - rect.y1
            if 0 <= distance <= max_distance:
                above.append((distance, rect))
        elif rect.y0 >= caption_rect.y1 - 6:
            distance = rect.y0 - caption_rect.y1
            if 0 <= distance <= max_distance * 0.5:
                below.append((distance, rect))

    preferred = above if above else below
    if not preferred:
        return []

    preferred.sort(key=lambda item: item[0])
    nearest_distance = preferred[0][0]
    threshold = max(36.0, nearest_distance + 90.0)
    selected = [rect for distance, rect in preferred if distance <= threshold]
    if not selected:
        return []

    # Keep the cluster around the nearest graphic to avoid swallowing the whole page.
    nearest = selected[0]
    cluster = [nearest]
    for rect in selected[1:]:
        expanded = _inflate(_rect_union(cluster) or nearest, 36, page_rect)
        if expanded.intersects(rect) or _horizontal_overlap(expanded, rect) >= 0.2:
            cluster.append(rect)
    return cluster


def _fallback_bbox(caption_rect: fitz.Rect, page_rect: fitz.Rect) -> fitz.Rect:
    if caption_rect.y0 > page_rect.height * 0.35:
        y0 = max(page_rect.y0, caption_rect.y0 - page_rect.height * 0.38)
        y1 = min(page_rect.y1, caption_rect.y1 + 8)
    else:
        y0 = max(page_rect.y0, caption_rect.y0 - 8)
        y1 = min(page_rect.y1, caption_rect.y1 + page_rect.height * 0.38)
    return fitz.Rect(page_rect.x0 + 24, y0, page_rect.x1 - 24, y1)


def _infer_figure_bbox(
    caption: CaptionHit,
    graphic_rects: list[fitz.Rect],
    page_rect: fitz.Rect,
) -> tuple[fitz.Rect, float, str, list[str]]:
    warnings: list[str] = []
    nearby = _candidate_graphics_near_caption(caption.rect, graphic_rects, page_rect)

    if nearby:
        graphics_box = _rect_union(nearby) or caption.rect
        bbox = _rect_union([graphics_box, caption.rect]) or caption.rect
        bbox = _inflate(bbox, 8, page_rect)
        confidence = 0.82 if len(nearby) > 1 else 0.72
        return bbox, confidence, "caption_nearby_graphics", warnings

    warnings.append("No nearby image/vector graphics found; used caption-relative page crop.")
    bbox = _fallback_bbox(caption.rect, page_rect)
    return bbox, 0.45, "caption_fallback_region", warnings


def _render_rect(page: fitz.Page, rect: fitz.Rect, output_path: Path, dpi: int) -> None:
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pixmap = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(output_path))


def extract_figures(pdf_path: Path, output_dir: Path, dpi: int = 180, max_pages: int | None = None) -> list[FigureCandidate]:
    pdf_path = pdf_path.resolve()
    output_dir = output_dir.resolve()
    pages_dir = output_dir / "pages"
    figures_dir = output_dir / "figures"
    pages_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[FigureCandidate] = []
    with fitz.open(str(pdf_path)) as document:
        page_count = len(document) if max_pages is None else min(len(document), max_pages)
        for page_index in range(page_count):
            page = document[page_index]
            page_number = page_index + 1
            page_rect = page.rect
            page_path = pages_dir / f"page_{page_number:03d}.png"
            _render_rect(page, page_rect, page_path, dpi=dpi)

            text_blocks = _text_blocks(page)
            captions = _find_captions(text_blocks)
            graphic_rects = _image_blocks(page) + _drawing_blocks(page)

            for caption in captions:
                bbox, confidence, method, warnings = _infer_figure_bbox(caption, graphic_rects, page_rect)
                figure_id = f"fig_{len(candidates) + 1:03d}_page_{page_number:03d}"
                crop_path = figures_dir / f"{figure_id}.png"
                _render_rect(page, bbox, crop_path, dpi=dpi)
                candidates.append(
                    FigureCandidate(
                        id=figure_id,
                        page_index=page_index,
                        page_number=page_number,
                        label=caption.label,
                        caption=caption.caption,
                        bbox=RectData.from_rect(bbox),
                        caption_bbox=RectData.from_rect(caption.rect),
                        crop_path=str(crop_path.relative_to(output_dir)),
                        page_path=str(page_path.relative_to(output_dir)),
                        confidence=round(confidence, 3),
                        method=method,
                        warnings=warnings,
                    )
                )

    manifest = {
        "pdf_path": str(pdf_path),
        "output_dir": str(output_dir),
        "dpi": dpi,
        "figure_count": len(candidates),
        "figures": [asdict(candidate) for candidate in candidates],
    }
    (output_dir / "figures.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return candidates


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract figure candidates from a research paper PDF.")
    parser.add_argument("pdf", type=Path, help="Path to the input PDF")
    parser.add_argument("--output", type=Path, required=True, help="Output directory for crops and manifest")
    parser.add_argument("--dpi", type=int, default=180, help="Render DPI for page and crop images")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional limit for quick smoke tests")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.dpi < 72:
        raise SystemExit("--dpi must be at least 72")
    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    figures = extract_figures(args.pdf, args.output, dpi=args.dpi, max_pages=args.max_pages)
    fallback_count = sum(1 for figure in figures if figure.method.endswith("fallback_region"))
    print(f"Extracted {len(figures)} figure candidate(s) into {args.output}")
    if fallback_count:
        print(f"{fallback_count} candidate(s) used fallback crops and should be reviewed.")


if __name__ == "__main__":
    main()
