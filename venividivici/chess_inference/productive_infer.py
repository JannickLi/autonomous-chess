"""productive_infer.py — Chess board recognition from a photo.

    python productive_infer.py 2026-02-28-100812.jpg
    python productive_infer.py image.jpg --debug
    python productive_infer.py image.jpg --weights path/to/best.pt

Outputs the chess notation grid to stdout.
With --debug: also opens a window with YOLO detections and perspective grid overlay.
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = HERE / "weights" / "best.pt"

sys.path.insert(0, str(HERE))
from chessnotation import (
    board_notation, CORNER_IDS, _CORNER_ORDER, _BOARD_PTS,
)


def _draw_grid(img: np.ndarray, corner_img: dict) -> np.ndarray:
    """Overlay a perspective-correct 8×8 grid using the 4 detected corner points."""
    img_pts = np.float32([corner_img[c] for c in _CORNER_ORDER])
    # M_inv maps board space (0–8, 0–8) → image pixel space
    M_inv = cv2.getPerspectiveTransform(_BOARD_PTS, img_pts)
    out = img.copy()
    for i in range(9):
        # horizontal line at board-row i
        p1 = cv2.perspectiveTransform(np.float32([[[0, i]]]), M_inv)[0][0].astype(int)
        p2 = cv2.perspectiveTransform(np.float32([[[8, i]]]), M_inv)[0][0].astype(int)
        cv2.line(out, tuple(p1), tuple(p2), (0, 255, 0), 1, cv2.LINE_AA)
        # vertical line at board-col i
        p3 = cv2.perspectiveTransform(np.float32([[[i, 0]]]), M_inv)[0][0].astype(int)
        p4 = cv2.perspectiveTransform(np.float32([[[i, 8]]]), M_inv)[0][0].astype(int)
        cv2.line(out, tuple(p3), tuple(p4), (0, 255, 0), 1, cv2.LINE_AA)
    return out


def run(image_path: str, weights: Path, conf: float, imgsz: int, debug: bool, gravity: str = "up"):
    img_path = Path(image_path)
    if not img_path.exists():
        sys.exit(f"ERROR: image not found: {img_path}")

    from ultralytics import YOLO
    import ultralytics.utils as _uu
    if hasattr(_uu, "LOGGER"):
        _uu.LOGGER.setLevel(logging.WARNING)

    model = YOLO(str(weights))

    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        sys.exit(f"ERROR: could not read image: {img_path}")

    img_bgr = cv2.resize(img_bgr, (imgsz, imgsz))
    result = model.predict(img_bgr, imgsz=imgsz, conf=conf, verbose=False)[0]

    notation = board_notation(result, gravity=gravity)
    if notation:
        print(notation)
    else:
        print("corners not detected")

    if debug:
        annotated = result.plot()

        # Overlay grid if all 4 corners were found
        boxes = result.boxes
        if boxes is not None and len(boxes) > 0:
            cls_ids = boxes.cls.cpu().int().tolist()
            xyxy    = boxes.xyxy.cpu().tolist()
            corner_img = {}
            for cls, box in zip(cls_ids, xyxy):
                if cls in CORNER_IDS and cls not in corner_img:
                    corner_img[cls] = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
            if len(corner_img) == 4:
                annotated = _draw_grid(annotated, corner_img)

        max_dim = 1200
        h, w = annotated.shape[:2]
        if max(h, w) > max_dim:
            scale     = max_dim / max(h, w)
            annotated = cv2.resize(annotated, (int(w * scale), int(h * scale)),
                                   interpolation=cv2.INTER_AREA)

        cv2.imshow("chess inference  [any key to close]", annotated)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Chess board recognition")
    parser.add_argument("image", nargs="?", default="debug_image.jpg", help="Path to input image")
    parser.add_argument("--weights", default="./weights/best.pt",      help="Path to YOLO .pt weights file")
    parser.add_argument("--conf",    type=float, default=0.25)
    parser.add_argument("--imgsz",   type=int,   default=1280)
    parser.add_argument("--debug",   action="store_true", default=False,
                        help="Show annotated image with grid overlay")
    parser.add_argument("--match-gravity", choices=["up", "down"], default="up",
                        help="Match piece to field under top (up) or bottom (down) of its box")
    args = parser.parse_args()

    weights = Path(args.weights) if args.weights else DEFAULT_WEIGHTS
    if not weights.exists():
        sys.exit(
            f"ERROR: weights not found at {weights}\n"
            f"Place best.pt in the weights/ folder or pass --weights <path>"
        )

    run(args.image, weights, args.conf, args.imgsz, args.debug, args.match_gravity)


if __name__ == "__main__":
    main()
