"""Build reference contact sheets from vertical webtoon slices for adaptation studies (P0.1).

Stitches slices, runs gutter XY-cut panel detection, and outputs contact sheets with
panel bounding boxes, indices, and dimensions to assist side-by-side human analysis.
Media stays local in data/scratch/ and is never committed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

from echotales.pipeline.comic.panels import detect_panels


def build_ref_sheet(
    slice_dir: Path,
    output_path: Path,
    *,
    thumb_width: int = 320,
    columns: int = 5,
    max_slices: int = 70,
) -> int:
    """Read slices in order, detect panels, and compile a contact sheet."""
    slice_files = sorted([p for p in slice_dir.glob("*.jpg") if not p.name.startswith(".")], key=lambda p: p.stem)
    if not slice_files:
        print(f"No .jpg slices found in {slice_dir}", file=sys.stderr)
        return 0

    if max_slices > 0:
        slice_files = slice_files[:max_slices]

    panel_records: list[tuple[Image.Image, str]] = []

    for s_idx, s_path in enumerate(slice_files, start=1):
        try:
            with Image.open(s_path) as im:
                im_rgb = im.convert("RGB")
                detected = detect_panels(im_rgb)
                if not detected:
                    detected_boxes = [(0, 0, im_rgb.width, im_rgb.height)]
                else:
                    detected_boxes = [p.box for p in detected]

                for p_idx, box in enumerate(detected_boxes, start=1):
                    pw = box[2] - box[0]
                    ph = box[3] - box[1]
                    if pw < 80 or ph < 60:
                        continue
                    cropped = im_rgb.crop(box)
                    aspect = ph / max(1, pw)
                    thumb_h = max(1, int(thumb_width * aspect))
                    if thumb_h > thumb_width * 3:
                        thumb_h = thumb_width * 3
                    thumb = cropped.resize((thumb_width, thumb_h), Image.Resampling.LANCZOS)

                    label = f"S{s_idx:02d}-P{p_idx} ({pw}x{ph})"
                    panel_records.append((thumb, label))
        except Exception as exc:
            print(f"Warning: Failed processing {s_path.name}: {exc}", file=sys.stderr)

    if not panel_records:
        print("No panels extracted.", file=sys.stderr)
        return 0

    num_panels = len(panel_records)
    rows = (num_panels + columns - 1) // columns
    cell_w = thumb_width + 16
    thumb_heights = [im.height for im, _ in panel_records]
    avg_cell_h = int(sum(thumb_heights) / len(thumb_heights)) + 36
    sheet_w = columns * cell_w
    sheet_h = rows * avg_cell_h

    sheet = Image.new("RGB", (sheet_w, sheet_h), (24, 24, 27))
    draw = ImageDraw.Draw(sheet)

    for i, (thumb, label) in enumerate(panel_records):
        col = i % columns
        row = i // columns
        x = col * cell_w + 8
        y = row * avg_cell_h + 8

        draw.rectangle([x, y, x + thumb_width, y + avg_cell_h - 10], fill=(39, 39, 42), outline=(63, 63, 70))
        paste_x = x + (thumb_width - thumb.width) // 2
        sheet.paste(thumb, (paste_x, y + 4))

        text_y = y + avg_cell_h - 28
        draw.text((x + 6, text_y), label, fill=(228, 228, 231))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=85)
    print(f"Saved contact sheet with {num_panels} panels to {output_path}")
    return num_panels


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build reference contact sheet from manhua slices.")
    parser.add_argument("slice_dir", type=Path, help="Path to directory containing slice JPGs")
    parser.add_argument("--out", type=Path, default=Path("data/scratch/reference/ref_sheet_ch01.jpg"), help="Output path")
    parser.add_argument("--cols", type=int, default=5, help="Columns in sheet")
    parser.add_argument("--max-slices", type=int, default=70, help="Max slices to analyze")
    args = parser.parse_args()

    count = build_ref_sheet(args.slice_dir, args.out, columns=args.cols, max_slices=args.max_slices)
    sys.exit(0 if count > 0 else 1)
