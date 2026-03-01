"""
Chess piece mover using recorded pick+place demos.

Replaces the old joint-offset approach with demo replay:
  - _navigate_to() interpolates joints to a calibrated square position
  - _replay_episode() plays back a recorded pick or place demo
  - execute_move() handles full move logic: captures, en passant, castling

Usage:
    from lerobot_chess_bot.chess_mover import ChessMover
    mover = ChessMover(follower, chess_board, dataset_root="lerobot_demo_dataset_new_calib")
    mover.execute_move(move_data)   # MoveData from ROS2BridgeClient
"""

import json
import time
import numpy as np
import pandas as pd
from pathlib import Path

from lerobot_chess_bot.chess_board import ChessBoard, JOINT_KEYS
from lerobot_chess_bot.ros2_bridge_client import MoveData

FPS        = 30
CONTROL_HZ = 50
MOVE_DURATION = 2.0
HOVER_GRIPPER = 1.0
GRIPPER_OPEN  = 20.0

ACTION_KEYS = JOINT_KEYS + ["gripper.pos"]

GY_TOP  = {"white": "gy_w_top",  "black": "gy_b_top"}
GY_DROP = {"white": "gy_w_drop", "black": "gy_b_drop"}

# Hardcode Pawn for now.
PIECE_DEMO_NAMES = {
    "pawn":   "Pawn",
    "knight": "Pawn",
    "bishop": "Rook",
    "rook":   "Rook",
    "queen":  "Rook",
    "king":   "Rook",
}

CASTLING_ROOK_SQUARES = {
    ("white", "kingside"):  ("h1", "f1"),
    ("white", "queenside"): ("a1", "d1"),
    ("black", "kingside"):  ("h8", "f8"),
    ("black", "queenside"): ("a8", "d8"),
}

HOME_DEGREES = {
  "shoulder_pan.pos": -0,
  "shoulder_lift.pos": -99,
  "elbow_flex.pos": 22,
  "wrist_flex.pos": 99,
  "wrist_roll.pos": -45,
  "gripper.pos": 5
}


class ChessMover:
    def __init__(self, follower, chess_board: ChessBoard, dataset_root: str | Path, speed: float = 1.0):
        self.follower = follower
        self.chess_board = chess_board
        self.speed = speed

        dataset_root = Path(dataset_root)
        self.index = json.loads((dataset_root / "demo_index.json").read_text())

        parquet_files = sorted((dataset_root / "data").glob("chunk-*/*.parquet"))
        self.df = pd.concat([pd.read_parquet(p) for p in parquet_files], ignore_index=True)
        print(f"Loaded {len(parquet_files)} parquet file(s) from {dataset_root}")

    # ── Low-level robot helpers ───────────────────────────────────────────────

    def _interpolate_to(self, target: dict, duration: float = MOVE_DURATION):
        obs = self.follower.get_observation()
        current = {k: float(obs[k]) for k in ACTION_KEYS}
        duration = duration / self.speed
        steps = max(1, int(duration * CONTROL_HZ))
        for i in range(steps + 1):
            alpha = i / steps
            interp = {k: current[k] + alpha * (target[k] - current[k]) for k in current}
            self.follower.send_action(interp)
            time.sleep(1.0 / CONTROL_HZ)

    def _navigate_to(self, square: str, keep_gripper: bool = False):
        target = self.chess_board.get_joints(square)
        if keep_gripper:
            target["gripper.pos"] = float(self.follower.get_observation()["gripper.pos"])
        else:
            target["gripper.pos"] = HOVER_GRIPPER
        print(f"    navigate → {square.upper()}")
        self._interpolate_to(target)

    def _open_gripper(self):
        obs = self.follower.get_observation()
        action = {k: float(obs[k]) for k in ACTION_KEYS}
        action["gripper.pos"] = GRIPPER_OPEN
        self.follower.send_action(action)
        time.sleep(0.5 / self.speed)

    # ── Demo replay ───────────────────────────────────────────────────────────

    def _load_episode_actions(self, episode_idx: int) -> list[np.ndarray]:
        rows = self.df[self.df["episode_index"] == episode_idx].sort_values("frame_index")
        return [np.array(a, dtype=np.float32) for a in rows["action"]]

    def _replay_episode(self, actions: list[np.ndarray], label: str):
        dt = 1.0 / (FPS * self.speed)
        print(f"    replay {label}  ({len(actions)} frames)", end="", flush=True)
        for i, action in enumerate(actions):
            t0 = time.monotonic()
            action_dict = {k: float(action[j]) for j, k in enumerate(ACTION_KEYS)}
            self.follower.send_action(action_dict)
            elapsed = time.monotonic() - t0
            if dt - elapsed > 0:
                time.sleep(dt - elapsed)
            if (i + 1) % 30 == 0:
                print(".", end="", flush=True)
        print()

    # ── Pick / place / graveyard ──────────────────────────────────────────────

    def _pick(self, square: str, piece_name: str):
        """Navigate to square and replay pick demo."""
        key = f"{piece_name}_{square}"
        if key not in self.index or "pick" not in self.index[key]:
            raise ValueError(f"No pick demo for {key}")
        actions = self._load_episode_actions(self.index[key]["pick"])
        self._navigate_to(square)
        time.sleep(0.3 / self.speed)
        self._replay_episode(actions, f"pick {square.upper()}")

    def _place(self, square: str, piece_name: str):
        """Navigate to square (gripper unchanged) and replay place demo."""
        key = f"{piece_name}_{square}"
        if key not in self.index or "place" not in self.index[key]:
            raise ValueError(f"No place demo for {key}")
        actions = self._load_episode_actions(self.index[key]["place"])
        self._navigate_to(square, keep_gripper=True)
        time.sleep(0.3 / self.speed)
        self._replay_episode(actions, f"place {square.upper()}")

    def _graveyard(self, color: str):
        """Navigate to graveyard, lower, release piece, raise back up."""
        top_joints  = self.chess_board.get_joints(GY_TOP[color])
        drop_joints = self.chess_board.get_joints(GY_DROP[color])

        top_joints["gripper.pos"] = float(self.follower.get_observation()["gripper.pos"])
        print("    navigate → graveyard top")
        self._interpolate_to(top_joints)
        time.sleep(0.3 / self.speed)

        drop_joints["gripper.pos"] = float(self.follower.get_observation()["gripper.pos"])
        print("    lower → graveyard drop")
        self._interpolate_to(drop_joints, duration=0.8)
        time.sleep(0.2 / self.speed)

        print("    open gripper → release")
        self._open_gripper()

        top_joints["gripper.pos"] = float(self.follower.get_observation()["gripper.pos"])
        print("    raise → graveyard top")
        self._interpolate_to(top_joints, duration=0.8)

    # ── Main entry point ──────────────────────────────────────────────────────

    def execute_move(self, move_data: MoveData):
        """Execute a chess move physically from a MoveData command."""
        from_sq   = move_data.from_square.lower()
        to_sq     = move_data.to_square.lower()
        color     = move_data.piece_color.lower()
        pname     = PIECE_DEMO_NAMES[move_data.piece_type.lower()]

        print(f"\n{'═'*60}")
        print(f"  {color.capitalize()} {pname}: {from_sq.upper()} → {to_sq.upper()}", end="")

        # ── Castling ──────────────────────────────────────────────────────────
        if move_data.is_castling:
            ctype = move_data.castling_type.lower()
            print(f"  [{'0-0' if ctype == 'kingside' else '0-0-0'}]")
            print(f"{'═'*60}")
            rook_from, rook_to = CASTLING_ROOK_SQUARES[(color, ctype)]
            for sq_from, sq_to, pn in [
                (from_sq, to_sq, PIECE_DEMO_NAMES["king"]),
                (rook_from, rook_to, PIECE_DEMO_NAMES["rook"]),
            ]:
                self._pick(sq_from, pn)
                self._place(sq_to, pn)
            return

        # ── Capture (including en passant) ────────────────────────────────────
        cap_sq        = to_sq
        cap_name      = None
        cap_color     = "black" if color == "white" else "white"

        if move_data.is_en_passant:
            cap_sq   = to_sq[0] + from_sq[1]   # same file as to, same rank as from
            cap_name = PIECE_DEMO_NAMES["pawn"]
            print(f"  [en passant, captured on {cap_sq.upper()}]")
        elif move_data.is_capture:
            cap_name = PIECE_DEMO_NAMES[move_data.captured_piece.lower()]
            print(f"  [captures {cap_name}]")
        else:
            print()

        print(f"{'═'*60}")

        if cap_name:
            print(f"\n  Remove {cap_name} from {cap_sq.upper()} → graveyard")
            self._pick(cap_sq, cap_name)
            self._graveyard(cap_color)

        # ── Main move ─────────────────────────────────────────────────────────
        place_name = PIECE_DEMO_NAMES[move_data.promotion_piece.lower()] \
                     if move_data.is_promotion and move_data.promotion_piece else pname
        print(f"\n  Move {pname} {from_sq.upper()} → {to_sq.upper()}")
        self._pick(from_sq, pname)
        self._place(to_sq, place_name)

    def move_home(self):
        """Move arm back to a safe home position."""
        print("\nMoving to home position...")
        self._interpolate_to(HOME_DEGREES, duration=1.0)
