"""
augment.py  —  Step 3

Synthesise training images by pasting random piece crops onto empty board
photos and writing YOLO-format labels.

Usage — generate dataset:
  python scripts/augment.py [--boards chessboard_one [chessboard_two ...]]
                            [--n 2000] [--val-split 0.1] [--seed 42]
                            [--jitter 0.20] [--flip-prob 0.5]
                            [--scale-var 0.15] [--rot-deg 10]
                            [--blur-max 1.0] [--skew-max 0.08]

Usage — demo mode (no files written, visualise augmentation interactively):
  python scripts/augment.py --demo [--boards chessboard_one]
                            [--min-pieces 1] [--max-pieces 32]
                            [--jitter 0.20] [--flip-prob 0.5]
                            [--scale-var 0.15] [--rot-deg 10]
                            [--blur-max 1.0] [--skew-max 0.08]
  Press Enter for the next sample, Esc to quit.

Outputs (generate mode only):
  dataset/images/train/synth_NNNNN.jpg
  dataset/labels/train/synth_NNNNN.txt
  dataset/images/val/synth_NNNNN.jpg
  dataset/labels/val/synth_NNNNN.txt
  dataset/data.yaml
"""

import argparse
import json
import math
import random
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter
import io

# ── paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
REPR_DATA = ROOT / "representation_data"
DATASET = ROOT / "dataset"

LABELS = [
    "white-pawn", "white-rook", "white-knight", "white-bishop",
    "white-queen", "white-king",
    "black-pawn", "black-rook", "black-knight", "black-bishop",
    "black-queen", "black-king",
    "corner-a8", "corner-h8", "corner-h1", "corner-a1",   # IDs 12-15
]
LABEL_TO_ID = {l: i for i, l in enumerate(LABELS)}

# Decomposed label spaces for two-attribute training
COLOR_LABELS = ["white", "black", "corner"]          # corner covers IDs 12-15
TYPE_LABELS  = ["pawn", "rook", "knight", "bishop", "queen", "king", "corner"]

# Maps combined index → color index (white=0, black=1, corner=2)
_COMBINED_TO_COLOR = {
    **{i: 0 for i in range(6)},    # white pieces
    **{i: 1 for i in range(6, 12)}, # black pieces
    **{i: 2 for i in range(12, 16)}, # corner markers
}
# Maps combined index → type index (pawn=0…king=5, corner=6)
_COMBINED_TO_TYPE = {
    **{i: i % 6 for i in range(12)},
    **{i: 6 for i in range(12, 16)},
}


def translate_labels(yolo_labels: list, mode: str) -> list:
    """Re-map combined YOLO class IDs to a decomposed class space.

    mode:
      "combined" → no change (white-pawn=0 … corner-a1=15)
      "color"    → white=0, black=1, corner=2
      "type"     → pawn=0, rook=1, knight=2, bishop=3, queen=4, king=5, corner=6
    """
    if mode == "combined":
        return yolo_labels
    mapping = _COMBINED_TO_COLOR if mode == "color" else _COMBINED_TO_TYPE
    result = []
    for line in yolo_labels:
        parts = line.split()
        result.append(f"{mapping[int(parts[0])]} {' '.join(parts[1:])}")
    return result

# Default augmentation parameters
OFFSET_FRAC = 0.15   # max XY jitter as fraction of square size
SCALE_VAR   = 0.0    # scale variation around 1.0 — 0 means no scaling
ROT_DEG     = 5      # rotation drawn from U[-k, k]
FLIP_PROB   = 0.5    # probability of horizontal flip per piece
BOARD_ROT_DEG     = 3     # max board rotation in degrees
BOARD_JITTER_FRAC = 0.02  # max board XY shift as fraction of image size
BLUR_MAX = 1.0   # max Gaussian blur radius in pixels (0 = off)
SKEW_MAX = 0.08  # max affine shear magnitude as a fraction of crop size (0 = off)

# ── data loading ──────────────────────────────────────────────────────────────

def load_board_data(board: str, working_res: int = 1280) -> tuple:
    """
    Pre-loads and pre-scales all board data into RAM at a working resolution.

    Original photos are typically 6240×4160 (15 MB each).  Compositing at that
    resolution and then discarding 99 % of the pixels wastes IO and CPU.
    Setting working_res=1280 scales everything down by ~5× before any synthetic
    image is generated, making each synth_one call ~25× cheaper (area ratio).

    The scale factor is derived from the first empty image so that piece crops
    and field coordinates are all consistent with one another.

    Returns:
      empty_images: list of (img_bgr_array, centers_dict, corners_list)
                    — images are already at working resolution, in RAM
      piece_crops:  dict { label: list of PIL RGBA Images }
                    — crops are pre-scaled to match working resolution
    """
    board_dir = REPR_DATA / board
    centers_path = board_dir / "field_centers.json"
    pieces_json = board_dir / "pieces" / "pieces.json"
    corners_json = board_dir / "board_corners.json"

    if not centers_path.exists():
        raise FileNotFoundError(f"Missing {centers_path}  — run annotate_fields.py first.")
    if not pieces_json.exists():
        raise FileNotFoundError(f"Missing {pieces_json}  — run annotate_pieces.py first.")

    centers_all: dict = json.loads(centers_path.read_text())

    corners_all: dict = {}
    if corners_json.exists():
        corners_all = json.loads(corners_json.read_text())
    else:
        print(f"  [WARN] {corners_json} not found — corner labels will be skipped.")

    real_empty = ROOT / "real_data" / board / "empty"

    # ── Determine scale from the first readable empty image ───────────────────
    # All photos on the same board share the same camera / resolution, so one
    # scale factor covers every empty image and every piece crop.
    scale = 1.0
    for fname in centers_all:
        probe = real_empty / fname
        if probe.exists():
            probe_bgr = cv2.imread(str(probe))
            if probe_bgr is not None:
                h, w = probe_bgr.shape[:2]
                scale = min(working_res / max(h, w), 1.0)   # never upscale
                print(f"  [{board}] source {w}x{h} -> working {int(w*scale)}x{int(h*scale)}"
                      f"  (scale {scale:.4f}, working_res={working_res})")
                break

    # ── Load, resize, and store empty board images ────────────────────────────
    empty_images = []
    for fname, centers in centers_all.items():
        img_path = real_empty / fname
        if not img_path.exists():
            print(f"  [WARN] Empty image not found: {img_path}")
            continue

        board_bgr = cv2.imread(str(img_path))
        if board_bgr is None:
            print(f"  [WARN] Cannot read {img_path}")
            continue

        if scale < 1.0:
            h, w = board_bgr.shape[:2]
            board_bgr = cv2.resize(board_bgr,
                                   (int(w * scale), int(h * scale)),
                                   interpolation=cv2.INTER_AREA)

        scaled_centers = {sq: [x * scale, y * scale]
                          for sq, (x, y) in centers.items()}

        corners_list = []
        if fname in corners_all:
            raw_corners = corners_all[fname].get("corners", [])
            if len(raw_corners) != 4:
                print(f"  [WARN] {fname}: expected 4 corners, got {len(raw_corners)} — skipping corners.")
            else:
                corners_list = [[x * scale, y * scale] for x, y in raw_corners]
        else:
            if corners_all:
                print(f"  [WARN] {fname}: no entry in board_corners.json — corners will be skipped.")

        empty_images.append((board_bgr, scaled_centers, corners_list))

    if not empty_images:
        raise RuntimeError(f"No usable empty images for board '{board}'.")

    # ── Load and resize piece crops ───────────────────────────────────────────
    meta: list = json.loads(pieces_json.read_text())
    piece_crops: dict = {l: [] for l in LABELS}
    for entry in meta:
        label = entry["label"]
        crop_path = board_dir / entry["file"]
        if not crop_path.exists():
            print(f"  [WARN] Crop not found: {crop_path}")
            continue
        crop = Image.open(str(crop_path)).convert("RGBA")
        if scale < 1.0:
            new_w = max(1, int(crop.width  * scale))
            new_h = max(1, int(crop.height * scale))
            crop = crop.resize((new_w, new_h), Image.LANCZOS)
        piece_crops[label].append(crop)

    piece_labels = LABELS[:12]   # corner classes have no crops
    missing = [l for l in piece_labels if not piece_crops[l]]
    if missing:
        print(f"  [WARN] No crops for: {missing}")

    return empty_images, piece_crops

# ── augmentation helpers ──────────────────────────────────────────────────────

def square_size_estimate(centers: dict) -> float:
    """Estimate the pixel size of one square from adjacent-square centers."""
    pts = list(centers.values())
    if len(pts) < 2:
        return 50.0
    if "a1" in centers and "b1" in centers:
        a, b = centers["a1"], centers["b1"]
        return math.hypot(b[0] - a[0], b[1] - a[1])
    dists = [math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
             for i in range(len(pts)-1)]
    return float(np.median(dists))


def transform_board(board_bgr: np.ndarray, centers: dict, corners: list,
                    rng: random.Random,
                    board_rot_deg: float, board_jitter_frac: float):
    """
    Apply a small random rotation and translation to the board image,
    updating field centers and board corners with the same affine transform.
    Returns (transformed_bgr, updated_centers, updated_corners).
    """
    h, w = board_bgr.shape[:2]
    angle = rng.uniform(-board_rot_deg, board_rot_deg)
    dx    = rng.uniform(-board_jitter_frac, board_jitter_frac) * w
    dy    = rng.uniform(-board_jitter_frac, board_jitter_frac) * h

    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    M[0, 2] += dx
    M[1, 2] += dy

    out_bgr = cv2.warpAffine(board_bgr, M, (w, h),
                             flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)

    new_centers = {sq: [M[0, 0] * x + M[0, 1] * y + M[0, 2],
                        M[1, 0] * x + M[1, 1] * y + M[1, 2]]
                   for sq, (x, y) in centers.items()}
    new_corners = [[M[0, 0] * x + M[0, 1] * y + M[0, 2],
                    M[1, 0] * x + M[1, 1] * y + M[1, 2]]
                   for (x, y) in corners]
    return out_bgr, new_centers, new_corners


def piece_augment(crop: Image.Image, rng: random.Random,
                  blur_max: float = 0.0,
                  skew_max: float = 0.0) -> Image.Image:
    """Apply optional Gaussian blur and/or affine skew to a piece crop (RGBA)."""
    # Gaussian blur
    if blur_max > 0:
        radius = rng.uniform(0.0, blur_max)
        if radius > 0.1:
            crop = crop.filter(ImageFilter.GaussianBlur(radius=radius))

    # Affine shear, centred on the crop so the piece stays in frame
    if skew_max > 0:
        w, h = crop.size
        sx = rng.uniform(-skew_max, skew_max)   # horizontal shear
        sy = rng.uniform(-skew_max, skew_max)   # vertical shear
        # PIL AFFINE uses inverse mapping: x_in = a*x_out + b*y_out + c
        cx, cy = w / 2.0, h / 2.0
        coeffs = (1.0,  sx, -sx * cy,
                  sy,  1.0, -sy * cx)
        crop = crop.transform(crop.size, Image.AFFINE, coeffs,
                              resample=Image.BICUBIC)
    return crop


def paste_piece(board_rgba: Image.Image, crop_rgba: Image.Image,
                cx: float, cy: float,
                scale: float, angle: float) -> tuple:
    """
    Paste `crop_rgba` onto `board_rgba` centred at (cx, cy).
    Returns (x0, y0, x1, y1) bounding box in board pixels, or None if outside.
    """
    new_w = max(1, int(crop_rgba.width * scale))
    new_h = max(1, int(crop_rgba.height * scale))
    resized = crop_rgba.resize((new_w, new_h), Image.LANCZOS)
    rotated = resized.rotate(angle, expand=True, resample=Image.BICUBIC)
    rw, rh  = rotated.size

    paste_x = int(round(cx - rw / 2))
    paste_y = int(round(cy - rh / 2))
    board_rgba.paste(rotated, (paste_x, paste_y), rotated)

    bw, bh = board_rgba.size
    x0 = max(0, paste_x);          y0 = max(0, paste_y)
    x1 = min(bw, paste_x + rw);    y1 = min(bh, paste_y + rh)
    return None if x0 >= x1 or y0 >= y1 else (x0, y0, x1, y1)


def synth_one(empty_images: list, piece_crops: dict,
              n_pieces_range: tuple, rng: random.Random,
              offset_frac: float = OFFSET_FRAC,
              scale_var:   float = SCALE_VAR,
              rot_deg:     float = ROT_DEG,
              flip_prob:   float = FLIP_PROB,
              board_rot_deg:     float = BOARD_ROT_DEG,
              board_jitter_frac: float = BOARD_JITTER_FRAC,
              blur_max: float = BLUR_MAX,
              skew_max: float = SKEW_MAX) -> tuple:
    """
    Generate one synthetic image.

    Returns (PIL RGB image, list of "class cx cy w h" YOLO label strings).

    Parameters
    ----------
    offset_frac : max XY jitter as a fraction of the square size
    scale_var   : piece scale drawn from U[1-k, 1+k] × base_scale
    rot_deg     : rotation drawn from U[-k, k] degrees
    flip_prob   : probability of flipping each piece crop horizontally
    blur_max  : max Gaussian blur radius for each piece (0 = off)
    skew_max  : max affine shear magnitude for each piece (0 = off)
    """
    board_bgr_src, centers, corners = rng.choice(empty_images)
    board_bgr = board_bgr_src.copy()   # don't mutate the cached original

    board_bgr, centers, corners = transform_board(
        board_bgr, centers, corners, rng, board_rot_deg, board_jitter_frac)

    board_h, board_w = board_bgr.shape[:2]
    board_rgba = Image.fromarray(
        cv2.cvtColor(board_bgr, cv2.COLOR_BGR2RGB)
    ).convert("RGBA")

    sq_size = square_size_estimate(centers)

    available_squares = list(centers.keys())
    rng.shuffle(available_squares)
    n_pieces = rng.randint(*n_pieces_range)
    chosen_squares = available_squares[:min(n_pieces, len(available_squares))]

    available_labels = [l for l in LABELS[:12] if piece_crops[l]]
    if not available_labels:
        raise RuntimeError("No piece crops available. Run annotate_pieces.py first.")

    yolo_labels = []

    for sq in chosen_squares:
        label = rng.choice(available_labels)
        crop  = rng.choice(piece_crops[label])

        # Horizontal flip
        if rng.random() < flip_prob:
            crop = crop.transpose(Image.FLIP_LEFT_RIGHT)

        # Subtle blur + skew applied to each crop independently
        crop = piece_augment(crop, rng, blur_max=blur_max, skew_max=skew_max)

        cx_base, cy_base = centers[sq]
        dx = rng.uniform(-offset_frac, offset_frac) * sq_size
        dy = rng.uniform(-offset_frac, offset_frac) * sq_size
        cx = cx_base + dx
        cy = cy_base + dy

        scale = rng.uniform(1 - scale_var, 1 + scale_var)
        angle = rng.uniform(-rot_deg, rot_deg)

        bbox = paste_piece(board_rgba, crop, cx, cy, scale, angle)
        if bbox is None:
            continue

        x0, y0, x1, y1 = bbox
        bcx = ((x0 + x1) / 2) / board_w
        bcy = ((y0 + y1) / 2) / board_h
        bw  = (x1 - x0) / board_w
        bh  = (y1 - y0) / board_h
        yolo_labels.append(
            f"{LABEL_TO_ID[label]} {bcx:.6f} {bcy:.6f} {bw:.6f} {bh:.6f}"
        )

    # Emit 4 small corner locator boxes
    # corner order matches board_corners.json: [a8, h8, h1, a1]
    _CORNER_LABEL_ORDER = ["corner-a8", "corner-h8", "corner-h1", "corner-a1"]
    if len(corners) == 4:
        half = sq_size * 0.25          # quarter-square radius → small discriminative box
        for corner_pt, corner_label in zip(corners, _CORNER_LABEL_ORDER):
            cx_pt, cy_pt = corner_pt
            x0c = max(0.0,            cx_pt - half)
            y0c = max(0.0,            cy_pt - half)
            x1c = min(float(board_w), cx_pt + half)
            y1c = min(float(board_h), cy_pt + half)
            if x0c < x1c and y0c < y1c:
                bcx = ((x0c + x1c) / 2) / board_w
                bcy = ((y0c + y1c) / 2) / board_h
                bw  = (x1c - x0c) / board_w
                bh  = (y1c - y0c) / board_h
                yolo_labels.append(
                    f"{LABEL_TO_ID[corner_label]} {bcx:.6f} {bcy:.6f} {bw:.6f} {bh:.6f}"
                )

    return board_rgba.convert("RGB"), yolo_labels

# ── demo mode ──────────────────────────────────────────────────────────────────

def demo_loop(empty_images: list, piece_crops: dict,
              n_pieces_range: tuple, aug_params: dict, show_boxes: bool = False) -> None:
    """
    Interactively display synthetic images one by one.
    Press Enter for the next sample, Esc to quit.
    """
    rng = random.Random()   # unseeded — fresh every run
    win = "augment --demo    Enter=next  Esc=quit"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    sample = 0
    while True:
        img_pil, labels = synth_one(empty_images, piece_crops,
                                    n_pieces_range, rng, **aug_params)
        try:
            img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        except Exception:
            # Fallback: encode PIL image to PNG bytes and decode with OpenCV
            buf = io.BytesIO()
            img_pil.save(buf, format="PNG")
            arr = np.frombuffer(buf.getvalue(), dtype=np.uint8)
            img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img_bgr is None:
                raise RuntimeError("cv2.imdecode failed to convert PIL image to OpenCV format")

        # Scale to fit screen
        h, w  = img_bgr.shape[:2]
        scale = min(1280 / w, 900 / h, 1.0)
        disp  = cv2.resize(img_bgr, (int(w * scale), int(h * scale)))

        # Draw boxes from YOLO-format labels if requested
        if show_boxes and labels:
            for lab in labels:
                parts = lab.split()
                if len(parts) < 5:
                    continue
                try:
                    cls = int(parts[0])
                    cx = float(parts[1])
                    cy = float(parts[2])
                    bw = float(parts[3])
                    bh = float(parts[4])
                except Exception:
                    continue
                # Convert normalized coords to pixel coords on original image
                cx_px = cx * w
                cy_px = cy * h
                bw_px = bw * w
                bh_px = bh * h
                x0 = int(round(cx_px - bw_px / 2.0))
                y0 = int(round(cy_px - bh_px / 2.0))
                x1 = int(round(cx_px + bw_px / 2.0))
                y1 = int(round(cy_px + bh_px / 2.0))
                # Scale to display size
                x0s = int(round(x0 * scale))
                y0s = int(round(y0 * scale))
                x1s = int(round(x1 * scale))
                y1s = int(round(y1 * scale))
                # Color: corners (last class) distinct
                try:
                    label_name = LABELS[cls]
                except Exception:
                    label_name = str(cls)
                if label_name == 'a8h1' or 'corner' in label_name:
                    color = (0, 0, 255)
                else:
                    color = (0, 255, 0)
                cv2.rectangle(disp, (x0s, y0s), (x1s, y1s), color, 2)
                # put label text
                txt = label_name
                cv2.putText(disp, txt, (x0s, max(0, y0s - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # HUD
        info = (f"sample {sample + 1}   pieces: {len(labels)}"
                f"   jitter:{aug_params['offset_frac']:.2f}"
                f"  flip:{aug_params['flip_prob']:.1f}"
                f"  scale±:{aug_params['scale_var']:.2f}"
                f"  rot±:{aug_params['rot_deg']:.0f}°"
        f"  blur:{aug_params.get('blur_max', 0):.1f}"
        f"  skew:{aug_params.get('skew_max', 0):.2f}")
        for col, t in [((0, 0, 0), 3), ((0, 220, 255), 1)]:
            cv2.putText(disp, info, (10, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, t)
        cv2.putText(disp, "Enter = next   Esc = quit", (10, disp.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow(win, disp)

        while True:
            key = cv2.waitKey(0) & 0xFF
            if key == 27:               # Esc
                cv2.destroyAllWindows()
                return
            if key in (13, 10):         # Enter
                break
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                return

        sample += 1

# ── data.yaml ─────────────────────────────────────────────────────────────────

def write_data_yaml(dataset_dir: Path):
    yaml_content = f"# Auto-generated by augment.py\npath: {dataset_dir.resolve().as_posix()}\ntrain: images/train\nval: images/val\n\nnc: {len(LABELS)}\nnames:\n"
    for i, label in enumerate(LABELS):
        yaml_content += f"  {i}: {label}\n"
    (dataset_dir / "data.yaml").write_text(yaml_content)

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic YOLO training data (or preview with --demo).")

    # ── dataset options ───────────────────────────────────────────────────────
    parser.add_argument("--boards", nargs="+", default=["chessboard_one"])
    parser.add_argument("--n", type=int, default=2000,
                        help="Total images to generate (ignored in --demo mode)")
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--min-pieces", type=int, default=1)
    parser.add_argument("--max-pieces", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed (ignored in --demo mode)")
    parser.add_argument("--clear", action="store_true",
                        help="Clear existing dataset before generating")

    # ── augmentation options ──────────────────────────────────────────────────
    parser.add_argument("--jitter", type=float, default=OFFSET_FRAC,
                        help=f"Max XY jitter as fraction of square size (default {OFFSET_FRAC})")
    parser.add_argument("--flip-prob", type=float, default=FLIP_PROB,
                        help=f"Probability of flipping each piece horizontally (default {FLIP_PROB})")
    parser.add_argument("--scale-var", type=float, default=SCALE_VAR,
                        help=f"Scale variation: piece scale drawn from U[1-k, 1+k] (default {SCALE_VAR})")
    parser.add_argument("--rot-deg", type=float, default=ROT_DEG,
                        help=f"Max rotation in degrees U[-k, k] (default {ROT_DEG})")
    parser.add_argument("--board-rot-deg", type=float, default=BOARD_ROT_DEG,
                        help=f"Max board rotation in degrees U[-k, k] (default {BOARD_ROT_DEG})")
    parser.add_argument("--board-jitter", type=float, default=BOARD_JITTER_FRAC,
                        help=f"Max board XY shift as fraction of image size (default {BOARD_JITTER_FRAC})")
    parser.add_argument("--blur-max", type=float, default=BLUR_MAX,
                        help=f"Max Gaussian blur radius for piece crops (0=off, default {BLUR_MAX})")
    parser.add_argument("--skew-max", type=float, default=SKEW_MAX,
                        help=f"Max affine shear for piece crops (0=off, default {SKEW_MAX})")

    # ── demo mode ─────────────────────────────────────────────────────────────
    parser.add_argument("--demo", action="store_true",
                        help="Preview augmented images interactively; no files are written")
    parser.add_argument("--boxes", action="store_true",
                        help="Show YOLO-format boxes in demo view")

    args = parser.parse_args()

    aug_params = dict(
        offset_frac       = args.jitter,
        flip_prob         = args.flip_prob,
        scale_var         = args.scale_var,
        rot_deg           = args.rot_deg,
        board_rot_deg     = args.board_rot_deg,
        board_jitter_frac = args.board_jitter,
        blur_max          = args.blur_max,
        skew_max          = args.skew_max,
    )

    # ── load board data ───────────────────────────────────────────────────────
    all_empty_images = []
    all_piece_crops: dict = {l: [] for l in LABELS}

    for board in args.boards:
        print(f"Loading board: {board}")
        empty_imgs, piece_crops = load_board_data(board)
        all_empty_images.extend(empty_imgs)
        for label, crops in piece_crops.items():
            all_piece_crops[label].extend(crops)

    print(f"Loaded {len(all_empty_images)} empty image(s)")
    for l in LABELS:
        n = len(all_piece_crops[l])
        if n:
            print(f"  {l}: {n} crop(s)")

    n_pieces_range = (args.min_pieces, args.max_pieces)

    # ── demo mode ─────────────────────────────────────────────────────────────
    if args.demo:
        print("\nDemo mode — Enter=next  Esc=quit\n")
        demo_loop(all_empty_images, all_piece_crops, n_pieces_range, aug_params, args.boxes)
        return

    # ── generate mode ─────────────────────────────────────────────────────────
    rng = random.Random(args.seed)

    for split in ("train", "val"):
        (DATASET / "images" / split).mkdir(parents=True, exist_ok=True)
        (DATASET / "labels" / split).mkdir(parents=True, exist_ok=True)

    if args.clear:
        print("Clearing existing dataset...")
        for split in ("train", "val"):
            for d in (DATASET / "images" / split, DATASET / "labels" / split):
                shutil.rmtree(d, ignore_errors=True)
                d.mkdir(parents=True)

    n_val   = max(1, int(args.n * args.val_split))
    n_train = args.n - n_val
    print(f"\nGenerating {n_train} train + {n_val} val images ...")
    print(f"  jitter={args.jitter}  flip={args.flip_prob}"
          f"  scale±{args.scale_var}  rot±{args.rot_deg}°\n")

    global_idx = 0
    for split, count in [("train", n_train), ("val", n_val)]:
        img_dir = DATASET / "images" / split
        lbl_dir = DATASET / "labels" / split
        for i in range(count):
            img_pil, labels = synth_one(
                all_empty_images, all_piece_crops, n_pieces_range, rng,
                **aug_params
            )
            stem = f"synth_{global_idx:05d}"
            img_pil.save(str(img_dir / f"{stem}.jpg"), quality=92)
            (lbl_dir / f"{stem}.txt").write_text("\n".join(labels))
            global_idx += 1
            if (i + 1) % 100 == 0 or (i + 1) == count:
                print(f"  {split}: {i+1}/{count}")

    write_data_yaml(DATASET)
    print(f"\nDone. Dataset → {DATASET}")


if __name__ == "__main__":
    main()
