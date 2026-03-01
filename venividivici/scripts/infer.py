"""
infer.py — Run inference on synthetic images, one at a time.

    python scripts/infer.py
    python scripts/infer.py --boards chessboard_one --conf 0.3 --seed 42

Keyboard:
    Any key  — next image
    Esc      — quit
"""

import argparse
import random
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--boards",  nargs="+", default=["chessboard_one"])
    parser.add_argument("--weights", default=None,
                        help="Path to .pt (default: runs/detect/chess_20260225_073956/weights/best.pt)")
    parser.add_argument("--conf",    type=float, default=0.25)
    parser.add_argument("--imgsz",   type=int,   default=1280)
    parser.add_argument("--seed",    type=int,   default=None,
                        help="Fixed seed for reproducible images (omit for random)")
    parser.add_argument("--match-gravity", choices=["up", "down"], default="up",
                        help="Match piece to field under top (up) or bottom (down) of its box")
    args = parser.parse_args()

    weights = (Path(args.weights) if args.weights
               else ROOT / "runs" / "detect" / "chess_20260225_073956" / "weights" / "best.pt")
    if not weights.exists():
        sys.exit(f"ERROR: weights not found: {weights}")

    from ultralytics import YOLO
    import ultralytics.utils as _uu
    import logging
    if hasattr(_uu, "LOGGER"):
        _uu.LOGGER.setLevel(logging.WARNING)

    from augment import load_board_data, synth_one
    from chessnotation import board_notation

    all_empty, all_crops = [], {}
    for board in args.boards:
        empty_imgs, crops = load_board_data(board)
        all_empty.extend(empty_imgs)
        for label, c in crops.items():
            all_crops.setdefault(label, []).extend(c)

    model = YOLO(str(weights))
    rng   = random.Random(args.seed)
    i     = 0

    print(f"Weights: {weights}   conf={args.conf}   imgsz={args.imgsz}")
    print("Any key = next image   Esc = quit\n")

    while True:
        i += 1
        img_pil, _ = synth_one(all_empty, all_crops, (1, 32), rng)
        img_bgr    = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        img_bgr    = cv2.resize(img_bgr, (args.imgsz, args.imgsz))

        result     = model.predict(img_bgr, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]

        notation = board_notation(result, gravity=args.match_gravity)
        if notation:
            print(f"\n--- image {i} ---\n{notation}\n")
        else:
            print(f"\n--- image {i}: corners not detected ---\n")

        annotated  = result.plot()

        max_dim = 1200
        h, w = annotated.shape[:2]
        if max(h, w) > max_dim:
            scale     = max_dim / max(h, w)
            annotated = cv2.resize(annotated, (int(w * scale), int(h * scale)),
                                   interpolation=cv2.INTER_AREA)

        cv2.imshow(f"infer [{i}]  any key=next  Esc=quit", annotated)
        if cv2.waitKey(0) == 27:
            break
        cv2.destroyAllWindows()

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
