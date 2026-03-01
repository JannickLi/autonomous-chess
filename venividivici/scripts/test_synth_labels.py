#!/usr/bin/env python3
"""Quick test: generate one synthetic sample and print YOLO labels."""
import random
from pathlib import Path

from scripts.augment import load_board_data, synth_one


def main():
    board = "chessboard_one"
    empty, crops = load_board_data(board)
    rng = random.Random(12345)
    img, labels = synth_one(empty, crops, (1, 6), rng)
    print(f"Generated {len(labels)} label(s):")
    for l in labels:
        print(l)


if __name__ == "__main__":
    main()
