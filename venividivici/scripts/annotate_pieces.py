"""
annotate_pieces.py  —  Step 2b

For every piece-type folder found in real_data/<board>/pieces/<piece-type>/,
open each image and let the user draw a polygon around the piece.

Controls (draw mode)
--------------------
  Left-click       — add polygon vertex
  Backspace        — remove last vertex
  Enter            — close polygon and save crop
  R                — reset current polygon
  S                — skip this image (no save)
  Ctrl + scroll    — zoom in / out at cursor
  Right-click drag — pan the view
  Esc              — quit entirely

Controls (review mode — image already annotated)
-------------------------------------------------
  Enter / S  — keep existing annotation, move to next image
  X          — delete this annotation and re-draw
  Esc        — quit

Outputs
-------
  representation_data/<board>/pieces/<label>/piece_NNN.png  (RGBA, polygon mask)
  representation_data/<board>/pieces/pieces.json

Usage
-----
  python scripts/annotate_pieces.py [--board chessboard_one]
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# ── paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
REAL_DATA = ROOT / "real_data"
REPR_DATA = ROOT / "representation_data"

LABELS = [
    "white-pawn", "white-rook", "white-knight", "white-bishop",
    "white-queen", "white-king",
    "black-pawn", "black-rook", "black-knight", "black-bishop",
    "black-queen", "black-king",
]

def normalise_label(folder_name: str) -> str | None:
    candidate = folder_name.lower().replace("_", "-")
    return candidate if candidate in LABELS else None

# ── zoom / pan helpers ────────────────────────────────────────────────────────

ZOOM_MIN = 0.5
ZOOM_MAX = 20.0
ZOOM_STEP = 1.15


def clamp_pan(s: dict) -> None:
    """Keep pan within image bounds."""
    eff = s["initial_scale"] * s["zoom"]
    view_w = s["win_w"] / eff
    view_h = s["win_h"] / eff
    s["pan_x"] = max(0.0, min(max(0.0, s["img_w"] - view_w), s["pan_x"]))
    s["pan_y"] = max(0.0, min(max(0.0, s["img_h"] - view_h), s["pan_y"]))


def do_zoom(s: dict, cursor_dx: int, cursor_dy: int, factor: float) -> None:
    new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, s["zoom"] * factor))
    eff_old = s["initial_scale"] * s["zoom"]
    eff_new = s["initial_scale"] * new_zoom
    # Keep the original-image point under the cursor fixed
    ox = s["pan_x"] + cursor_dx / eff_old
    oy = s["pan_y"] + cursor_dy / eff_old
    s["pan_x"] = ox - cursor_dx / eff_new
    s["pan_y"] = oy - cursor_dy / eff_new
    s["zoom"] = new_zoom
    clamp_pan(s)


def disp_to_orig(dx: float, dy: float, s: dict) -> tuple:
    eff = s["initial_scale"] * s["zoom"]
    return s["pan_x"] + dx / eff, s["pan_y"] + dy / eff


def orig_to_disp(ox: float, oy: float, s: dict) -> tuple:
    eff = s["initial_scale"] * s["zoom"]
    return (ox - s["pan_x"]) * eff, (oy - s["pan_y"]) * eff


def render_view(img_bgr: np.ndarray, s: dict) -> np.ndarray:
    """Crop and scale the portion of the original image that is currently in view."""
    eff = s["initial_scale"] * s["zoom"]
    view_w = s["win_w"] / eff
    view_h = s["win_h"] / eff

    ox0 = s["pan_x"]
    oy0 = s["pan_y"]
    H, W = img_bgr.shape[:2]

    ix0 = int(max(0, ox0))
    iy0 = int(max(0, oy0))
    ix1 = int(min(W, np.ceil(ox0 + view_w)))
    iy1 = int(min(H, np.ceil(oy0 + view_h)))

    if ix1 <= ix0 or iy1 <= iy0:
        return np.zeros((s["win_h"], s["win_w"], 3), dtype=np.uint8)

    patch = img_bgr[iy0:iy1, ix0:ix1]

    # Compute where patch lands in display space
    pdx0 = int((ix0 - ox0) * eff)
    pdy0 = int((iy0 - oy0) * eff)
    pdw = max(1, int((ix1 - ix0) * eff))
    pdh = max(1, int((iy1 - iy0) * eff))

    resized = cv2.resize(patch, (pdw, pdh), interpolation=cv2.INTER_LINEAR)

    canvas = np.zeros((s["win_h"], s["win_w"], 3), dtype=np.uint8)
    cx0 = max(0, pdx0)
    cy0 = max(0, pdy0)
    cx1 = min(s["win_w"], pdx0 + pdw)
    cy1 = min(s["win_h"], pdy0 + pdh)
    rx0 = cx0 - pdx0
    ry0 = cy0 - pdy0
    canvas[cy0:cy1, cx0:cx1] = resized[ry0:ry0 + (cy1 - cy0), rx0:rx0 + (cx1 - cx0)]
    return canvas

# ── crop ──────────────────────────────────────────────────────────────────────

def make_polygon_crop(img_bgr: np.ndarray, polygon: list) -> tuple:
    pts = np.array(polygon, dtype=np.float32)
    x0, y0 = np.floor(pts.min(axis=0)).astype(int)
    x1, y1 = np.ceil(pts.max(axis=0)).astype(int)
    H, W = img_bgr.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        return None, None
    patch_rgb = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
    mask = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    shifted = (pts - np.array([x0, y0])).astype(np.int32)
    cv2.fillPoly(mask, [shifted], 255)
    return Image.fromarray(np.dstack([patch_rgb, mask]), mode="RGBA"), (int(x0), int(y0), int(x1), int(y1))

# ── drawing ───────────────────────────────────────────────────────────────────

def draw_polygon_on(vis: np.ndarray, polygon: list, s: dict,
                    color_vertex=(255, 80, 0), color_edge=(0, 255, 0),
                    color_close=(0, 255, 255)) -> None:
    """Draw polygon onto vis in-place using current zoom/pan state."""
    if not polygon:
        return
    pts_disp = [orig_to_disp(x, y, s) for x, y in polygon]

    # Edges
    for i in range(len(pts_disp) - 1):
        p1 = (int(pts_disp[i][0]), int(pts_disp[i][1]))
        p2 = (int(pts_disp[i + 1][0]), int(pts_disp[i + 1][1]))
        cv2.line(vis, p1, p2, color_edge, 1, cv2.LINE_AA)

    # Closing preview line
    if len(pts_disp) >= 2:
        p_first = (int(pts_disp[0][0]), int(pts_disp[0][1]))
        p_last = (int(pts_disp[-1][0]), int(pts_disp[-1][1]))
        cv2.line(vis, p_last, p_first, color_close, 1, cv2.LINE_AA)

    # Vertices — small: radius 3
    for i, (dx, dy) in enumerate(pts_disp):
        pt = (int(dx), int(dy))
        c = (0, 0, 255) if i == 0 else color_vertex
        cv2.circle(vis, pt, 3, c, -1)


def draw_hud(vis: np.ndarray, polygon: list, s: dict,
             label: str, img_name: str, mode: str,
             existing_polygon: list | None) -> np.ndarray:
    zoom_pct = int(s["zoom"] * s["initial_scale"] * 100)

    if mode == "review":
        if existing_polygon:
            draw_polygon_on(vis, existing_polygon, s,
                            color_vertex=(180, 180, 0),
                            color_edge=(0, 200, 200),
                            color_close=(0, 200, 200))
        lines = [
            f"{label}  [{img_name}]  zoom:{zoom_pct}%",
            "Already annotated.",
            "Enter/S=keep  X=delete+redo  Esc=quit",
        ]
    else:
        draw_polygon_on(vis, polygon, s)
        v = len(polygon)
        lines = [
            f"{label}  [{img_name}]  zoom:{zoom_pct}%  vertices:{v}",
            "Left-click=add  Backspace=undo  R=reset",
            "Enter=save  S=skip  Ctrl+scroll=zoom  RMB drag=pan  Esc=quit",
        ]

    for i, line in enumerate(lines):
        y = 20 + i * 20
        cv2.putText(vis, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 3)
        cv2.putText(vis, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 220, 255), 1)

    return vis

# ── annotation loop ───────────────────────────────────────────────────────────

def next_index(out_dir: Path) -> int:
    return len(list(out_dir.glob("piece_*.png")))


def annotate_image(img_path: Path, label: str, img_bgr: np.ndarray,
                   existing_entry: dict | None) -> tuple:
    """
    Interactive loop for one image.

    Returns:
      ("save",   polygon)   — new polygon to save
      ("keep",   None)      — keep existing entry unchanged
      ("delete", None)      — delete existing entry
      ("skip",   None)      — skip (no change, no save)
    Raises SystemExit on Esc.
    """
    H, W = img_bgr.shape[:2]
    initial_scale = min(1280 / W, 900 / H, 1.0)
    win_w = int(W * initial_scale)
    win_h = int(H * initial_scale)

    mode = "review" if existing_entry else "draw"
    existing_polygon = existing_entry["polygon"] if existing_entry else None

    s = {
        "zoom": 1.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "win_w": win_w,
        "win_h": win_h,
        "img_w": W,
        "img_h": H,
        "initial_scale": initial_scale,
        "drag_start": None,
        "drag_pan_start": None,
    }
    polygon: list = []

    win = f"{label} — {img_path.name}"

    def on_mouse(event, x, y, flags, param):
        nonlocal mode
        ctrl = bool(flags & cv2.EVENT_FLAG_CTRLKEY)

        if event == cv2.EVENT_MOUSEWHEEL and ctrl:
            factor = ZOOM_STEP if flags > 0 else 1.0 / ZOOM_STEP
            do_zoom(s, x, y, factor)

        elif event == cv2.EVENT_LBUTTONDOWN:
            if mode == "draw":
                ox, oy = disp_to_orig(x, y, s)
                polygon.append([ox, oy])

        elif event == cv2.EVENT_RBUTTONDOWN:
            s["drag_start"] = (x, y)
            s["drag_pan_start"] = (s["pan_x"], s["pan_y"])

        elif event == cv2.EVENT_MOUSEMOVE:
            if s["drag_start"] is not None:
                dx = x - s["drag_start"][0]
                dy = y - s["drag_start"][1]
                eff = s["initial_scale"] * s["zoom"]
                s["pan_x"] = s["drag_pan_start"][0] - dx / eff
                s["pan_y"] = s["drag_pan_start"][1] - dy / eff
                clamp_pan(s)

        elif event == cv2.EVENT_RBUTTONUP:
            s["drag_start"] = None
            s["drag_pan_start"] = None

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, win_w, win_h)
    cv2.setMouseCallback(win, on_mouse)

    while True:
        base = render_view(img_bgr, s)
        vis = draw_hud(base, polygon, s, label, img_path.name, mode, existing_polygon)
        cv2.imshow(win, vis)
        key = cv2.waitKey(30) & 0xFF

        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            cv2.destroyAllWindows()
            raise SystemExit("Window closed.")

        if key == 255:
            continue

        if key == 27:  # Esc
            cv2.destroyAllWindows()
            raise SystemExit("Cancelled.")

        # ── review mode keys ──────────────────────────────────────────────────
        if mode == "review":
            if key in (13, 10, ord('s'), ord('S')):   # keep
                cv2.destroyWindow(win)
                return "keep", None
            if key in (ord('x'), ord('X')):            # delete + redo
                mode = "draw"
                polygon.clear()
                continue

        # ── draw mode keys ────────────────────────────────────────────────────
        else:
            if key in (ord('s'), ord('S')):            # skip
                cv2.destroyWindow(win)
                return "skip", None

            if key in (ord('r'), ord('R')):            # reset
                polygon.clear()

            if key == 8:                               # Backspace — undo
                if polygon:
                    polygon.pop()

            if key in (13, 10):                        # Enter — save
                if len(polygon) < 3:
                    print("  Need at least 3 vertices.")
                else:
                    cv2.destroyWindow(win)
                    return "save", polygon

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Polygon-annotate chess pieces from per-type image folders.")
    parser.add_argument("--board", default="chessboard_one")
    args = parser.parse_args()

    pieces_src_root = REAL_DATA / args.board / "pieces"
    repr_pieces = REPR_DATA / args.board / "pieces"
    pieces_json_path = repr_pieces / "pieces.json"

    if not pieces_src_root.exists():
        print(f"Source folder not found: {pieces_src_root}")
        print("Create it with sub-folders per piece type:")
        print("  real_data/chessboard_one/pieces/white-pawn/  (5 images)")
        sys.exit(1)

    repr_pieces.mkdir(parents=True, exist_ok=True)
    pieces_meta: list = json.loads(pieces_json_path.read_text()) \
        if pieces_json_path.exists() else []

    # Index existing entries as (label, source_image) → entry
    def build_index(meta):
        return {(e["label"], e["source_image"]): e for e in meta}

    # Discover piece-type folders
    found_types = []
    for folder in sorted(pieces_src_root.iterdir()):
        if not folder.is_dir():
            continue
        label = normalise_label(folder.name)
        if label is None:
            print(f"  [WARN] Unrecognised folder '{folder.name}', skipping.")
            continue
        found_types.append((label, folder))

    if not found_types:
        print(f"No recognised piece-type folders in {pieces_src_root}")
        sys.exit(0)

    print(f"Found {len(found_types)} piece type(s)\n")

    for label, src_folder in found_types:
        images = sorted({
            img
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG", "*.JPEG")
            for img in src_folder.glob(ext)
        })
        if not images:
            print(f"  [WARN] No images in {src_folder}, skipping.")
            continue

        out_dir = repr_pieces / label
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"--- {label} ({len(images)} image(s)) ---")

        for img_path in images:
            idx = build_index(pieces_meta)
            existing = idx.get((label, img_path.name))

            img_bgr = cv2.imread(str(img_path))
            if img_bgr is None:
                print(f"  [WARN] Cannot read {img_path}, skipping.")
                continue

            H, W = img_bgr.shape[:2]
            print(f"  {'[annotated] ' if existing else ''}{img_path.name}  ({W}×{H})")

            try:
                action, polygon = annotate_image(img_path, label, img_bgr, existing)
            except SystemExit as e:
                print(str(e))
                pieces_json_path.write_text(json.dumps(pieces_meta, indent=2))
                sys.exit(0)

            if action == "keep":
                print(f"  Kept existing annotation.")
                continue

            if action == "skip":
                print(f"  Skipped.")
                continue

            if action == "delete":
                # Shouldn't reach here — delete transitions to draw mode internally
                continue

            # action == "save": remove old entry (if any), save new crop
            if existing:
                old_file = repr_pieces / existing["file"]
                if old_file.exists():
                    old_file.unlink()
                    print(f"  Deleted old crop: {old_file.name}")
                pieces_meta = [e for e in pieces_meta
                               if not (e["label"] == label and e["source_image"] == img_path.name)]

            crop, bbox = make_polygon_crop(img_bgr, polygon)
            if crop is None:
                print("  [WARN] Degenerate polygon, skipping.")
                continue

            piece_idx = next_index(out_dir)
            fname = f"piece_{piece_idx:03d}.png"
            rel_path = f"pieces/{label}/{fname}"
            crop.save(str(out_dir / fname))

            pieces_meta.append({
                "file": rel_path,
                "label": label,
                "source_image": img_path.name,
                "polygon": [[float(x), float(y)] for x, y in polygon],
                "bbox": list(bbox),
            })
            print(f"  Saved: {rel_path}  (vertices={len(polygon)}, bbox={bbox})")

        pieces_json_path.write_text(json.dumps(pieces_meta, indent=2))
        print()

    print("Done.")
    print(f"  pieces.json: {pieces_json_path}  ({len(pieces_meta)} entries)")


if __name__ == "__main__":
    main()
