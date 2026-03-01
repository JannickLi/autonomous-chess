"""camera_infer.py — Live chess board recognition from a camera feed.

    python camera_infer.py
    python camera_infer.py --camera 1          # use camera index 1
    python camera_infer.py --weights path/to/best.pt
    python camera_infer.py --conf 0.3 --imgsz 640

Press 'q' or ESC to quit.
Press 'p' to print the current board notation to stdout.
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
    M_inv = cv2.getPerspectiveTransform(_BOARD_PTS, img_pts)
    out = img.copy()
    for i in range(9):
        p1 = cv2.perspectiveTransform(np.float32([[[0, i]]]), M_inv)[0][0].astype(int)
        p2 = cv2.perspectiveTransform(np.float32([[[8, i]]]), M_inv)[0][0].astype(int)
        cv2.line(out, tuple(p1), tuple(p2), (0, 255, 0), 1, cv2.LINE_AA)
        p3 = cv2.perspectiveTransform(np.float32([[[i, 0]]]), M_inv)[0][0].astype(int)
        p4 = cv2.perspectiveTransform(np.float32([[[i, 8]]]), M_inv)[0][0].astype(int)
        cv2.line(out, tuple(p3), tuple(p4), (0, 255, 0), 1, cv2.LINE_AA)
    return out


def _extract_corners(result) -> dict:
    """Return corner_img dict (cls_id → [cx, cy]) from a YOLO result."""
    corner_img = {}
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return corner_img
    cls_ids = boxes.cls.cpu().int().tolist()
    xyxy = boxes.xyxy.cpu().tolist()
    for cls, box in zip(cls_ids, xyxy):
        if cls in CORNER_IDS and cls not in corner_img:
            corner_img[cls] = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
    return corner_img


def run(camera_idx: int, weights: Path, conf: float, imgsz: int, gravity: str):
    from ultralytics import YOLO
    import ultralytics.utils as _uu
    if hasattr(_uu, "LOGGER"):
        _uu.LOGGER.setLevel(logging.WARNING)

    model = YOLO(str(weights))

    cap = cv2.VideoCapture(camera_idx)
    if not cap.isOpened():
        sys.exit(f"ERROR: cannot open camera index {camera_idx}")

    # Try to set a reasonable capture resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    window = "Chess inference  [q/ESC=quit  p=print notation]"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    print("Camera open. Press 'q' or ESC to quit, 'p' to print board notation.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("WARNING: failed to grab frame")
            break

        # Resize to the model's expected size before inference
        frame_resized = cv2.resize(frame, (imgsz, imgsz))
        result = model.predict(frame_resized, imgsz=imgsz, conf=conf, verbose=False)[0]

        # Build annotated frame
        annotated = result.plot()

        # Overlay grid if all 4 corners detected
        corner_img = _extract_corners(result)
        if len(corner_img) == 4:
            annotated = _draw_grid(annotated, corner_img)
            status = "corners OK"
            status_color = (0, 200, 0)
        else:
            status = f"corners: {len(corner_img)}/4"
            status_color = (0, 100, 255)

        # HUD overlay — status line
        cv2.putText(
            annotated, status,
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2, cv2.LINE_AA,
        )

        cv2.imshow(window, annotated)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):  # q or ESC
            break
        elif key == ord('p'):
            notation = board_notation(result, gravity=gravity)
            print("\n--- Board notation ---")
            print(notation if notation else "corners not detected")
            print("----------------------")

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Live chess board recognition from camera")
    parser.add_argument("--camera",  type=int,   default=0,          help="Camera device index (default 0)")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS),   help="Path to YOLO .pt weights file")
    parser.add_argument("--conf",    type=float, default=0.25,        help="Detection confidence threshold")
    parser.add_argument("--imgsz",   type=int,   default=1280,        help="Inference image size")
    parser.add_argument("--match-gravity", choices=["up", "down"], default="up",
                        help="Match piece to field under top (up) or bottom (down) of its box")
    args = parser.parse_args()

    weights = Path(args.weights)
    if not weights.exists():
        sys.exit(
            f"ERROR: weights not found at {weights}\n"
            f"Place best.pt in the weights/ folder or pass --weights <path>"
        )

    run(args.camera, weights, args.conf, args.imgsz, args.match_gravity)


if __name__ == "__main__":
    main()
