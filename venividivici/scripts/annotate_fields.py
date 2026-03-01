"""
annotate_fields.py  —  Step 2a

For each empty board image in real_data/<board>/empty/, display the image and
let the user click the 4 corners of the board in order:
  1. a8-corner  (top-left from White's view)
  2. h8-corner  (top-right)
  3. h1-corner  (bottom-right)
  4. a1-corner  (bottom-left)

After 4 clicks the script warps an 8×8 grid and overlays all 64 square-center
labels.  Press Enter to accept or R to redo the current image.

Outputs (one entry per image, keyed by filename):
  representation_data/<board>/board_corners.json
  representation_data/<board>/field_centers.json

Usage:
  python scripts/annotate_fields.py [--board chessboard_one]
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

# ── constants ─────────────────────────────────────────────────────────────────

FILES_DIR = Path(__file__).resolve().parent.parent  # chessReID/
REAL_DATA = FILES_DIR / "real_data"
REPR_DATA = FILES_DIR / "representation_data"

# Square names: col a-h, row 8-1  (so index (row, col) → rank = 8-row)
def square_name(row: int, col: int) -> str:
    return "abcdefgh"[col] + str(8 - row)

# ── homography helpers ────────────────────────────────────────────────────────

def compute_centers(corners: list) -> dict:
    """
    corners: [[x,y] × 4]  in order a8, h8, h1, a1
    Returns dict { "a1": [x, y], ..., "h8": [x, y] }
    """
    # Source: unit square corners in board space (col 0-8, row 0-8)
    src = np.float32([[0, 0], [8, 0], [8, 8], [0, 8]])
    dst = np.float32(corners)
    M = cv2.getPerspectiveTransform(src, dst)

    centers = {}
    for row in range(8):
        for col in range(8):
            # Center of square at (col+0.5, row+0.5) in board space
            pt = np.float32([[[col + 0.5, row + 0.5]]])
            warped = cv2.perspectiveTransform(pt, M)[0][0]
            name = square_name(row, col)
            centers[name] = [float(warped[0]), float(warped[1])]
    return centers

# ── drawing ───────────────────────────────────────────────────────────────────

CORNER_LABELS = ["a8", "h8", "h1", "a1"]
COLORS = [(0, 255, 255), (0, 200, 255), (0, 100, 255), (0, 0, 255)]

def draw_state(img: np.ndarray, corners: list, centers: dict) -> np.ndarray:
    vis = img.copy()
    # Draw clicked corners
    for i, (x, y) in enumerate(corners):
        cv2.circle(vis, (int(x), int(y)), 8, COLORS[i], -1)
        cv2.putText(vis, CORNER_LABELS[i], (int(x) + 10, int(y) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLORS[i], 2)
    # Draw 64 square centers
    for name, (x, y) in centers.items():
        cv2.circle(vis, (int(x), int(y)), 4, (0, 255, 0), -1)
        cv2.putText(vis, name, (int(x) + 5, int(y) - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 255, 200), 1)
    # HUD
    remaining = 4 - len(corners)
    if remaining > 0:
        msg = f"Click corner {len(corners)+1}/4: {CORNER_LABELS[len(corners)]}"
    else:
        msg = "Enter=accept  R=redo"
    cv2.putText(vis, msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
    return vis

# ── annotation loop ───────────────────────────────────────────────────────────

def annotate_image(img_path: Path) -> tuple:
    """Returns (corners, centers) or raises SystemExit if window closed."""
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"[WARN] Cannot read {img_path}, skipping.")
        return None, None

    # Scale down for display if very large
    h, w = img.shape[:2]
    max_dim = 1200
    scale = min(max_dim / w, max_dim / h, 1.0)
    display_img = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img.copy()
    inv_scale = 1.0 / scale

    corners = []
    centers = {}
    win = f"annotate_fields — {img_path.name}"

    def on_click(event, x, y, flags, param):
        nonlocal corners, centers
        if event == cv2.EVENT_LBUTTONDOWN and len(corners) < 4:
            # Map display coords back to original image coords
            orig_x = x * inv_scale
            orig_y = y * inv_scale
            corners.append([orig_x, orig_y])
            if len(corners) == 4:
                centers = compute_centers(corners)
            # Redraw
            vis = draw_state(display_img, [[cx * scale, cy * scale] for cx, cy in corners],
                             {n: [px * scale, py * scale] for n, (px, py) in centers.items()})
            cv2.imshow(win, vis)

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, on_click)
    cv2.imshow(win, draw_state(display_img, [], {}))

    while True:
        key = cv2.waitKey(30) & 0xFF
        if key == 255:
            # No key — check if window closed
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                cv2.destroyAllWindows()
                raise SystemExit("Window closed by user.")
            continue

        if key in (13, 10):  # Enter
            if len(corners) == 4:
                cv2.destroyWindow(win)
                return corners, centers
            else:
                print(f"  Need all 4 corners first ({len(corners)}/4 clicked).")

        elif key in (ord('r'), ord('R')):
            corners.clear()
            centers.clear()
            cv2.imshow(win, draw_state(display_img, [], {}))

        elif key == 27:  # Esc
            cv2.destroyAllWindows()
            raise SystemExit("Cancelled by user (Esc).")

        # Redraw continuously so display stays fresh after resize
        vis = draw_state(display_img,
                         [[cx * scale, cy * scale] for cx, cy in corners],
                         {n: [px * scale, py * scale] for n, (px, py) in centers.items()})
        cv2.imshow(win, vis)

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Annotate board corners for empty board images.")
    parser.add_argument("--board", default="chessboard_one",
                        help="Board folder name inside real_data/ and representation_data/")
    args = parser.parse_args()

    empty_dir = REAL_DATA / args.board / "empty"
    repr_dir = REPR_DATA / args.board
    repr_dir.mkdir(parents=True, exist_ok=True)

    corners_path = repr_dir / "board_corners.json"
    centers_path = repr_dir / "field_centers.json"

    # Load existing data
    corners_data = json.loads(corners_path.read_text()) if corners_path.exists() else {}
    centers_data = json.loads(centers_path.read_text()) if centers_path.exists() else {}

    images = sorted(empty_dir.glob("*.jpg")) + sorted(empty_dir.glob("*.png")) + \
             sorted(empty_dir.glob("*.jpeg")) + sorted(empty_dir.glob("*.JPG")) + \
             sorted(empty_dir.glob("*.PNG"))

    if not images:
        print(f"No images found in {empty_dir}")
        print("Place your empty-board photos there (jpg/png) then re-run.")
        sys.exit(0)

    print(f"Found {len(images)} image(s) in {empty_dir}")
    print("Instructions: click corners in order: a8 → h8 → h1 → a1")
    print("              Enter=accept  R=redo  Esc=quit\n")

    for img_path in images:
        key = img_path.name
        if key in corners_data:
            resp = input(f"  {key} already annotated. Re-annotate? [y/N] ").strip().lower()
            if resp != "y":
                print(f"  Skipping {key}.")
                continue

        print(f"Annotating: {key}")
        try:
            corners, centers = annotate_image(img_path)
        except SystemExit as e:
            print(str(e))
            break

        if corners is None:
            continue

        corners_data[key] = {"corners": corners, "centers": centers}
        centers_data[key] = centers

        # Save after each image so partial progress is preserved
        corners_path.write_text(json.dumps(corners_data, indent=2))
        centers_path.write_text(json.dumps(centers_data, indent=2))
        print(f"  Saved {key}: 64 centers computed.")

    print("\nDone. Outputs:")
    print(f"  {corners_path}")
    print(f"  {centers_path}")


if __name__ == "__main__":
    main()
