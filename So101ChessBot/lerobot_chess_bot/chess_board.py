"""
Chess board calibration and square navigation via joint-angle lookup table.

Calibration:
    Teleoperate gripper ABOVE each square center (hover height).
    Records 5 joint angles (excluding gripper) per square.
    Also records one "transit" position safely above the board for travel.

    The recorded positions are for navigation only.
    Grabbing/releasing will be handled by a separate model later.

Usage:
    python chess_board.py calibrate

    from chess_board import ChessBoard
    board = ChessBoard()
    board.load_calibration()
    joints = board.get_joints("e4")
    transit = board.get_transit_joints()
"""

import json
import sys
import time
import random
from pathlib import Path
from datetime import datetime

from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

# ── Config ────────────────────────────────────────────────────────────────────

JOINT_KEYS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
]

ACTION_KEYS = JOINT_KEYS + ["gripper.pos"]

CALIBRATION_DIR = Path("./.calibrations")
CALIBRATION_PATH = CALIBRATION_DIR / "joint_calibration.json"

GRIPPER_OPEN_THRESHOLD = 25.0  # degrees — above this = open = record
COMMS_RETRY_PAUSE = 0.1  # seconds to wait after a serial read/write error
COMMS_MAX_RETRIES = 10  # consecutive errors before giving up

DEFAULT_PIECE_HEIGHTS = {
    "pawn": 0.020,
    "rook": 0.030,
    "knight": 0.030,
    "bishop": 0.030,
    "queen": 0.035,
    "king": 0.040,
    "default": 0.015,
}


# ── ChessBoard class ─────────────────────────────────────────────────────────


class ChessBoard:
    FILES = "abcdefgh"
    RANKS = "12345678"

    def __init__(self, piece_heights=None):
        self.squares = {}  # {"a1": {5 joint angles}, ...}
        self.transit = None  # {5 joint angles}
        self.piece_heights = piece_heights or dict(DEFAULT_PIECE_HEIGHTS)

    # ── Square lookup ────────────────────────────────────────────────────────

    def get_joints(self, square):
        """Return 5-joint angle dict for a square."""
        square = square.lower()
        if square not in self.squares:
            raise KeyError(f"Square {square} not in calibration data.")
        return dict(self.squares[square])

    def get_transit_joints(self):
        """Return 5-joint angle dict for the transit (above-board) position."""
        if self.transit is None:
            raise RuntimeError("Transit position not calibrated.")
        return dict(self.transit)

    def is_valid_square(self, square):
        square = square.lower()
        return len(square) == 2 and square[0] in self.FILES and square[1] in self.RANKS

    def is_calibrated(self, square):
        return square.lower() in self.squares

    # ── Save / Load ──────────────────────────────────────────────────────────

    def save_calibration(self, path=CALIBRATION_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        cal = {
            "format_version": 1,
            "calibrated_at": datetime.now().isoformat(),
            "transit": self.transit,
            "squares": self.squares,
            "piece_heights": self.piece_heights,
        }
        with open(path, "w") as f:
            json.dump(cal, f, indent=2)
        print(f"Calibration saved to {path}")

    def load_calibration(self, path=CALIBRATION_PATH):
        with open(path) as f:
            cal = json.load(f)
        self.transit = cal["transit"]
        self.squares = cal["squares"]
        self.piece_heights = cal.get("piece_heights", dict(DEFAULT_PIECE_HEIGHTS))
        print(
            f"Loaded calibration: {len(self.squares)} squares, "
            f"transit={'yes' if self.transit else 'no'}"
        )


# ── Calibration helpers ──────────────────────────────────────────────────────


def _all_squares_randomized():
    """Return all 64 squares in random order."""
    squares = [f"{f}{r}" for f in "abcdefgh" for r in "12345678"]
    random.shuffle(squares)
    return squares


def _teleop_cycle(leader, follower):
    """Run one leader->follower teleop cycle. Returns obs or None on comms error."""
    try:
        action = leader.get_action()
        action["wrist_roll.pos"] -= 50
        follower.send_action(action)
        return follower.get_observation()
    except (ConnectionError, OSError) as e:
        print(f"\n   [comms error: {e}] retrying...")
        time.sleep(COMMS_RETRY_PAUSE)
        return None


def _wait_for_record(leader, follower):
    """Block until user opens gripper past threshold, record 5 joint angles."""
    gripper_was_closed = True
    error_count = 0

    while True:
        obs = _teleop_cycle(leader, follower)
        if obs is None:
            error_count += 1
            if error_count >= COMMS_MAX_RETRIES:
                raise ConnectionError(
                    f"Lost connection after {COMMS_MAX_RETRIES} consecutive errors"
                )
            continue
        error_count = 0

        gripper_deg = float(obs["gripper.pos"])
        gripper_open = gripper_deg > GRIPPER_OPEN_THRESHOLD

        # Print current joint state
        joints_str = "  ".join(
            f"{k.split('.')[0][:4]}={float(obs[k]):+.1f}" for k in JOINT_KEYS
        )
        print(f"   {joints_str}  grip={gripper_deg:.1f}", end="\r")

        if gripper_open and gripper_was_closed:
            # Record the 5 joint angles (exclude gripper)
            joints = {k: float(obs[k]) for k in JOINT_KEYS}
            print()  # newline after \r

            # Wait for gripper close before returning
            print("   Close gripper to continue...")
            while True:
                obs = _teleop_cycle(leader, follower)
                if obs is None:
                    continue  # skip cycle on error
                if float(obs["gripper.pos"]) <= GRIPPER_OPEN_THRESHOLD:
                    break
                time.sleep(0.02)

            return joints

        gripper_was_closed = not gripper_open
        time.sleep(0.02)


def _joints_summary(joints):
    """Short string summary of joint angles."""
    return " ".join(f"{v:+.1f}" for v in joints.values())


# ── Calibration entry point ──────────────────────────────────────────────────


def run_calibration(save_path=CALIBRATION_PATH):
    follower = SO101Follower(
        config=SO101FollowerConfig(
            id="w_so101_follower",
            port="/dev/ttyACM0",
            disable_torque_on_disconnect=True,
            cameras={},
        )
    )
    leader = SO101Leader(
        config=SO101LeaderConfig(id="w_so101_leader", port="/dev/ttyACM1")
    )

    follower.connect()
    leader.connect()

    board = ChessBoard()
    sequence = _all_squares_randomized()

    print("\n" + "=" * 60)
    print("CHESS BOARD CALIBRATION (Joint Angle Lookup)")
    print("=" * 60)
    print("Teleoperate gripper ABOVE each square (hover height).")
    print("OPEN gripper to record, close gripper to advance.")
    print("=" * 60)

    try:
        # ── Step 1: Record transit position ──────────────────────────
        print("\n>>> TRANSIT POSITION <<<")
        print("Move arm to a safe position ABOVE the board.")
        print("Must be high enough to clear the tallest piece (king).")
        print("Open gripper to record.")

        transit_joints = _wait_for_record(leader, follower)
        board.transit = transit_joints
        print(f"   Transit recorded: {_joints_summary(transit_joints)}")

        # ── Step 2: Record all 64 squares ────────────────────────────
        for i, square in enumerate(sequence):
            print(f"\n[{i + 1}/64]  Move to {square.upper()}")
            print("   Position gripper tip ABOVE square center (hover height).")
            print("   Open gripper to record.")

            joints = _wait_for_record(leader, follower)
            board.squares[square] = joints
            print(f"   Recorded {square}: {_joints_summary(joints)}")

            # Save incrementally
            board.save_calibration(save_path)

        print(f"\nCalibration complete: {len(board.squares)} squares + transit")
        return board

    except KeyboardInterrupt:
        print(f"\n\nInterrupted after {len(board.squares)} squares.")
        if board.squares:
            board.save_calibration(save_path)
            print("Partial calibration saved.")
        return board if board.squares else None

    finally:
        follower.disconnect()
        leader.disconnect()


# ── Patch specific squares ───────────────────────────────────────────────────


def recalibrate_squares(squares: list[str], save_path=CALIBRATION_PATH):
    """Re-record specific squares and patch them into the existing calibration."""
    if not Path(save_path).exists():
        print(f"Error: {save_path} not found. Run full calibration first.")
        return

    follower = SO101Follower(
        config=SO101FollowerConfig(
            id="w_so101_follower",
            port="/dev/ttyACM0",
            disable_torque_on_disconnect=True,
            cameras={},
        )
    )
    leader = SO101Leader(
        config=SO101LeaderConfig(id="w_so101_leader", port="/dev/ttyACM1")
    )

    follower.connect()
    leader.connect()

    board = ChessBoard()
    board.load_calibration(save_path)

    print(f"\nRe-calibrating {len(squares)} square(s): {[s.upper() for s in squares]}")
    print("Open gripper to record, close gripper to advance.\n")

    try:
        for i, square in enumerate(squares):
            square = square.lower()
            print(f"[{i + 1}/{len(squares)}]  Move to {square.upper()}")
            if board.is_calibrated(square):
                old = _joints_summary(board.squares[square])
                print(f"   Current: {old}")
            print("   Open gripper to record.")

            joints = _wait_for_record(leader, follower)
            board.squares[square] = joints
            board.save_calibration(save_path)
            print(f"   Saved {square}: {_joints_summary(joints)}")

    except KeyboardInterrupt:
        print("\nInterrupted.")

    finally:
        follower.disconnect()
        leader.disconnect()


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        run_calibration()
    elif len(sys.argv) > 1 and sys.argv[1] == "--squares":
        recalibrate_squares(sys.argv[2:])
    else:
        # Self-test with dummy data
        print("Self-test with dummy calibration data...")
        board = ChessBoard()
        board.transit = {k: 0.0 for k in JOINT_KEYS}
        for f in "abcdefgh":
            for r in "12345678":
                board.squares[f"{f}{r}"] = {
                    k: float(i + ord(f) + int(r)) for i, k in enumerate(JOINT_KEYS)
                }

        print(f"  Squares: {len(board.squares)}")
        print(f"  e4 joints: {board.get_joints('e4')}")
        print(f"  Transit: {board.get_transit_joints()}")
        print(f"  Valid 'e4': {board.is_valid_square('e4')}")
        print(f"  Valid 'z9': {board.is_valid_square('z9')}")
        print(f"  Calibrated 'e4': {board.is_calibrated('e4')}")

        # Test save/load round-trip
        test_path = Path("/tmp/test_joint_calibration.json")
        board.save_calibration(test_path)
        board2 = ChessBoard()
        board2.load_calibration(test_path)
        assert board2.squares["e4"] == board.squares["e4"]
        assert board2.transit == board.transit
        print("  Save/load round-trip: OK")
        test_path.unlink()
        print("Self-test passed.")
