"""
chessnotation.py — Map YOLO inference results to a chess board notation grid.

When all 4 corner locators are detected (corner-a8=12, corner-h8=13,
corner-h1=14, corner-a1=15) the piece centres are projected through the
inverse board-to-image homography, giving correct square assignment even
for heavily skewed/perspective-distorted views.

Falls back to the diagonal AABB method when only 2 opposite corners are
available (accuracy degrades for strongly skewed boards).
"""

import cv2
import numpy as np

# Class IDs for the 4 corner locators
CORNER_A8 = 12
CORNER_H8 = 13
CORNER_H1 = 14
CORNER_A1 = 15
CORNER_IDS = {CORNER_A8, CORNER_H8, CORNER_H1, CORNER_A1}

# Board-space coordinates for each corner (board is 8×8 units)
# a8=(0,0), h8=(8,0), h1=(8,8), a1=(0,8)
_CORNER_ORDER = [CORNER_A8, CORNER_H8, CORNER_H1, CORNER_A1]
_BOARD_PTS = np.float32([[0, 0], [8, 0], [8, 8], [0, 8]])

PIECE_CHARS = {
    0: 'P', 1: 'R', 2: 'N', 3: 'B', 4: 'Q', 5: 'K',
    6: 'p', 7: 'r', 8: 'n', 9: 'b', 10: 'q', 11: 'k',
}

FILES = list("abcdefgh")
RANKS = list("87654321")


def board_notation(result, gravity: str = "up") -> str | None:
    """Return a text chess-board grid, or None if corners cannot be localised.

    gravity: "up"   — match piece to the field under the top    of its bounding box
             "down" — match piece to the field under the bottom of its bounding box
    """
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None

    cls_ids = boxes.cls.cpu().int().tolist()
    xyxy    = boxes.xyxy.cpu().tolist()

    def _sample_y(box):
        return box[1] if gravity == "up" else box[3]

    # Collect corner centre-points (take the first occurrence if duplicated)
    corner_img = {}          # cls_id → [cx, cy]
    for cls, box in zip(cls_ids, xyxy):
        if cls in CORNER_IDS and cls not in corner_img:
            corner_img[cls] = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]

    grid = [['.' for _ in range(8)] for _ in range(8)]

    if len(corner_img) == 4:
        # ── Full homography path ──────────────────────────────────────────────
        # M maps image space → board space (inversion of the forward transform)
        img_pts = np.float32([corner_img[c] for c in _CORNER_ORDER])
        M = cv2.getPerspectiveTransform(img_pts, _BOARD_PTS)

        piece_entries = []
        for cls, box in zip(cls_ids, xyxy):
            if cls not in PIECE_CHARS:
                continue
            cx = (box[0] + box[2]) / 2
            cy = _sample_y(box)
            piece_entries.append((cls, cx, cy))

        if piece_entries:
            pts = np.float32([[cx, cy] for _, cx, cy in piece_entries])
            board_pts = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), M).reshape(-1, 2)
            for (cls, _, _), (bx, by) in zip(piece_entries, board_pts):
                if not (0 <= bx < 8 and 0 <= by < 8):
                    continue
                grid[int(by)][int(bx)] = PIECE_CHARS[cls]

    elif {CORNER_A8, CORNER_H1}.issubset(corner_img):
        # ── Fallback: diagonal AABB (approximation for skewed boards) ─────────
        bx1, by1 = corner_img[CORNER_A8]
        bx2, by2 = corner_img[CORNER_H1]
        bw = bx2 - bx1
        bh = by2 - by1
        if bw <= 0 or bh <= 0:
            return None
        for cls, box in zip(cls_ids, xyxy):
            if cls not in PIECE_CHARS:
                continue
            cx = (box[0] + box[2]) / 2
            cy = _sample_y(box)
            col = (cx - bx1) / bw * 8
            row = (cy - by1) / bh * 8
            if not (0 <= col < 8 and 0 <= row < 8):
                continue
            grid[int(row)][int(col)] = PIECE_CHARS[cls]

    else:
        return None

    header = "  " + " ".join(FILES)
    lines  = [header]
    for r, rank_label in enumerate(RANKS):
        lines.append(f"{rank_label} " + " ".join(grid[r]))
    return "\n".join(lines)
