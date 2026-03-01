"""
ROS2 Bridge Client — runs in conda/lerobot process.
Writes camera images to /tmp atomically, sends JSON with paths to bridge node.

Supports both legacy move format (simple UCI string) and new enriched format
with piece type, capture info, castling, etc.
"""

import os
import socket
import struct
import json
import threading
import queue
import numpy as np
import cv2

HOST = "localhost"
PORT = 9999

ACTION_KEYS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]


def recv_all(conn, n):
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionResetError("Socket closed")
        data += chunk
    return data


class MoveData:
    """Container for move command data (both legacy and new format)."""

    def __init__(self, data: dict):
        # Core move info (always present)
        self.move_uci: str = data.get("move", "")

        # Extended info (new format, may be empty for legacy)
        self.from_square: str = data.get("from_square", "")
        self.to_square: str = data.get("to_square", "")
        self.piece_type: str = data.get("piece_type", "")
        self.piece_color: str = data.get("piece_color", "")
        self.is_capture: bool = data.get("is_capture", False)
        self.captured_piece: str = data.get("captured_piece", "")
        self.is_castling: bool = data.get("is_castling", False)
        self.castling_type: str = data.get("castling_type", "")
        self.is_en_passant: bool = data.get("is_en_passant", False)
        self.is_promotion: bool = data.get("is_promotion", False)
        self.promotion_piece: str = data.get("promotion_piece", "")
        self.board_fen: str = data.get("board_fen", "")

        # Parse from/to from UCI if not provided
        if not self.from_square and len(self.move_uci) >= 4:
            self.from_square = self.move_uci[:2]
            self.to_square = self.move_uci[2:4]

    def __str__(self):
        return f"MoveData({self.move_uci}, {self.piece_color} {self.piece_type})"


class ROS2BridgeClient:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.sock = None
        self._move_queue = queue.Queue()
        self._recv_thread = None
        self._connected = False

    def connect(self, retries=10, delay=1.0):
        import time

        for attempt in range(retries):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, self.port))
                self._connected = True
                print(f"Connected to ROS2 bridge on {self.host}:{self.port}")
                self._recv_thread = threading.Thread(
                    target=self._recv_loop, daemon=True
                )
                self._recv_thread.start()
                return
            except ConnectionRefusedError:
                print(f"Bridge not ready, retrying ({attempt+1}/{retries})...")
                time.sleep(delay)
        raise RuntimeError("Could not connect to ROS2 bridge node.")

    def disconnect(self):
        self._connected = False
        if self.sock:
            self.sock.close()
            self.sock = None

    # ── Send ──────────────────────────────────────────────────────────────────

    def send(self, obs, joints_deg_dict=None):
        if not self._connected:
            return

        header = {}

        if "camera1" in obs:
            tmp = "/tmp/robot_cam1_latest.tmp.jpg"
            path = "/tmp/robot_cam1_latest.jpg"
            cv2.imwrite(
                tmp, cv2.cvtColor(np.asarray(obs["camera1"]), cv2.COLOR_RGB2BGR)
            )
            os.replace(tmp, path)  # atomic — reader never sees partial file
            header["camera1_path"] = path

        if "camera2" in obs:
            tmp = "/tmp/robot_cam2_latest.tmp.jpg"
            path = "/tmp/robot_cam2_latest.jpg"
            cv2.imwrite(
                tmp, cv2.cvtColor(np.asarray(obs["camera2"]), cv2.COLOR_RGB2BGR)
            )
            os.replace(tmp, path)
            header["camera2_path"] = path

        if joints_deg_dict is not None:
            header["joints"] = [float(joints_deg_dict[k]) for k in ACTION_KEYS]

        payload = json.dumps(header).encode()
        try:
            self.sock.sendall(struct.pack("!I", len(payload)) + payload)
        except OSError as e:
            print(f"ROS2 bridge send error: {e}")
            self._connected = False

    # ── Receive chess moves back from bridge ──────────────────────────────────

    def _recv_loop(self):
        while self._connected:
            try:
                header = recv_all(self.sock, 4)
                length = struct.unpack("!I", header)[0]
                payload = recv_all(self.sock, length)
                data = json.loads(payload.decode())
                if "move" in data:
                    # Wrap in MoveData for unified access
                    move_data = MoveData(data)
                    self._move_queue.put(move_data)
                    print(f"[ROS2 Bridge] Received: {move_data}")
            except (ConnectionResetError, EOFError, OSError):
                self._connected = False
                break

    def get_next_move(self) -> MoveData | None:
        """Get the next move command, or None if queue is empty.

        Returns:
            MoveData object with move details, or None
        """
        try:
            return self._move_queue.get_nowait()
        except queue.Empty:
            return None

    def get_next_move_uci(self) -> str | None:
        """Legacy method: get just the UCI string.

        Returns:
            UCI move string (e.g., "e2e4"), or None
        """
        move_data = self.get_next_move()
        return move_data.move_uci if move_data else None

    def publish_move_done(self, move_str: str = "ok", success: bool = True, error: str = ""):
        """Publish move completion notification.

        Args:
            move_str: The move that was completed (UCI notation)
            success: Whether the move was executed successfully
            error: Error message if success=False
        """
        payload = json.dumps({
            "move_done": move_str,
            "success": success,
            "error": error
        }).encode()
        self.sock.sendall(struct.pack("!I", len(payload)) + payload)

    def publish_move_error(self, move_str: str, error: str):
        """Publish move failure notification.

        Args:
            move_str: The move that failed
            error: Error description
        """
        self.publish_move_done(move_str, success=False, error=error)

    def has_move(self) -> bool:
        return not self._move_queue.empty()
