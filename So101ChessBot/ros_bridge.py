#!/usr/bin/env python3
"""
ROS2 Bridge Node — system Python, ROS2 sourced.
Receives camera + joint data from lerobot conda process and publishes to ROS2 topics.

Protocol: JSON header + raw image bytes (no pickle, no numpy version dependency)

Run:
    source /opt/ros/humble/setup.bash
    source chess_msgs/install/setup.bash
    python3 ros_bridge.py

Topics published:
    /camera1/image_path     std_msgs/String
    /camera2/image_path     std_msgs/String
    /robot/joint_states     sensor_msgs/JointState
    /chess/move_done        std_msgs/String (legacy, deprecated)
    /chess/move_result      chess_msgs/MoveResult

Topics subscribed:
    /chess/next_move        std_msgs/String (legacy, deprecated)
    /chess/move_request     chess_msgs/MoveCommand
"""

import socket
import struct
import json
import threading
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import String

# Try to import custom chess messages (requires chess_msgs package)
try:
    from chess_msgs.msg import MoveCommand, MoveResult
    HAS_CHESS_MSGS = True
except ImportError:
    HAS_CHESS_MSGS = False
    print("Warning: chess_msgs not found, external move commands disabled")

HOST = "localhost"
PORT = 9999

JOINT_NAMES = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def recv_all(conn, n):
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionResetError("Socket closed")
        data += chunk
    return data


class ROS2BridgeNode(Node):
    def __init__(self):
        super().__init__("robot_bridge")

        self.pub_cam1 = self.create_publisher(String, "/camera1/image_path", 10)
        self.pub_cam2 = self.create_publisher(String, "/camera2/image_path", 10)
        self.pub_joints = self.create_publisher(JointState, "/robot/joint_states", 10)

        from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSDurabilityPolicy

        volatile_qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self.pub_move_done = self.create_publisher(
            String, "/chess/move_done", volatile_qos
        )

        self.sub_move = self.create_subscription(
            String, "/chess/next_move", self.on_next_move, 10
        )

        # External move command support (chess_msgs)
        if HAS_CHESS_MSGS:
            print("chess_msgs found, enabling external move command support")
            self.sub_external_move = self.create_subscription(
                MoveCommand, "/chess/move_request", self.on_external_move_command, 10
            )
            self.pub_move_result = self.create_publisher(
                MoveResult, "/chess/move_result", 10
            )
            self.get_logger().info("External move command support enabled")
        else:
            self.sub_external_move = None
            self.pub_move_result = None

        # Track pending moves for result publishing
        self._pending_move: str | None = None
        self._move_start_time: float = 0.0

        self.latest = None
        self.latest_lock = threading.Lock()
        self.conn = None

        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((HOST, PORT))
        self.server_sock.listen(1)

        self.recv_thread = threading.Thread(target=self._accept_and_recv, daemon=True)
        self.recv_thread.start()

        self.create_timer(1.0 / 30.0, self.publish_latest)
        self.get_logger().info("ROS2 Bridge Node started.")

    # ── Receive loop ──────────────────────────────────────────────────────────

    def _parse_packet(self, payload):
        """Parse plain JSON packet — contains paths and joints only."""
        return json.loads(payload.decode())

    def _accept_and_recv(self):
        """Loops on accept — reconnects automatically after disconnect."""
        while True:
            self.get_logger().info(f"Waiting for lerobot process on {HOST}:{PORT} ...")
            try:
                self.conn, addr = self.server_sock.accept()
            except OSError:
                break
            self.get_logger().info(f"lerobot process connected from {addr}")

            while True:
                try:
                    # Outer length
                    header = recv_all(self.conn, 4)
                    length = struct.unpack("!I", header)[0]
                    payload = recv_all(self.conn, length)
                    data = self._parse_packet(payload)

                    with self.latest_lock:
                        self.latest = data

                except (ConnectionResetError, EOFError, OSError):
                    self.get_logger().warn(
                        "lerobot process disconnected. Waiting for reconnect..."
                    )
                    self.conn = None
                    break

    # ── Publish ───────────────────────────────────────────────────────────────

    def publish_latest(self):
        with self.latest_lock:
            data = self.latest

        if data is None:
            return

        now = self.get_clock().now().to_msg()

        if "camera1_path" in data:
            msg = String()
            msg.data = data["camera1_path"]
            self.pub_cam1.publish(msg)

        if "camera2_path" in data:
            msg = String()
            msg.data = data["camera2_path"]
            self.pub_cam2.publish(msg)

        if "joints" in data:
            msg = JointState()
            msg.header.stamp = now
            msg.name = JOINT_NAMES
            msg.position = [float(v) for v in data["joints"]]
            self.pub_joints.publish(msg)

        if "move_done" in data:
            msg = String()
            msg.data = data["move_done"]
            self.pub_move_done.publish(msg)
            self.get_logger().info(f"Move done: {data['move_done']}")
            with self.latest_lock:
                self.latest.pop("move_done", None)
                self.latest.pop("success", None)
                self.latest.pop("error", None)

            # Also publish MoveResult if we have a pending move
            if HAS_CHESS_MSGS and self.pub_move_result and self._pending_move:
                result_msg = MoveResult()
                result_msg.header.stamp = now
                result_msg.move_uci = self._pending_move
                result_msg.success = data.get("success", True)
                result_msg.error = data.get("error", "")
                result_msg.execution_time_sec = float(time.time() - self._move_start_time)
                self.pub_move_result.publish(result_msg)
                self.get_logger().info(
                    f"Published MoveResult: {result_msg.move_uci}, "
                    f"success={result_msg.success}, time={result_msg.execution_time_sec:.2f}s"
                )
                self._pending_move = None

    # ── Forward chess moves back to lerobot ───────────────────────────────────

    def on_next_move(self, msg):
        """Handle legacy /chess/next_move topic."""
        self.get_logger().info(f"Forwarding move: {msg.data}")
        if self.conn:
            try:
                payload = json.dumps({"move": msg.data}).encode()
                self.conn.sendall(struct.pack("!I", len(payload)) + payload)
            except OSError:
                self.get_logger().warn("Could not forward move to lerobot process.")

    def on_external_move_command(self, msg: "MoveCommand"):
        """Handle /chess/move_request topic with full move metadata."""
        self.get_logger().info(
            f"Received external move command: {msg.move_uci} "
            f"({msg.piece_color} {msg.piece_type} from {msg.from_square} to {msg.to_square})"
        )

        # Track pending move for result publishing
        self._pending_move = msg.move_uci
        self._move_start_time = time.time()

        if self.conn:
            try:
                # Send enriched move data to conda process
                move_data = {
                    "move": msg.move_uci,
                    "from_square": msg.from_square,
                    "to_square": msg.to_square,
                    "piece_type": msg.piece_type,
                    "piece_color": msg.piece_color,
                    "is_capture": msg.is_capture,
                    "captured_piece": msg.captured_piece,
                    "is_castling": msg.is_castling,
                    "castling_type": msg.castling_type,
                    "is_en_passant": msg.is_en_passant,
                    "is_promotion": msg.is_promotion,
                    "promotion_piece": msg.promotion_piece,
                    "board_fen": msg.board_fen,
                }
                payload = json.dumps(move_data).encode()
                self.conn.sendall(struct.pack("!I", len(payload)) + payload)
                self.get_logger().info(f"Forwarded move command to lerobot process")
            except OSError as e:
                self.get_logger().error(f"Could not forward move to lerobot process: {e}")
                # Publish error result
                if self.pub_move_result:
                    result_msg = MoveResult()
                    result_msg.header.stamp = self.get_clock().now().to_msg()
                    result_msg.move_uci = msg.move_uci
                    result_msg.success = False
                    result_msg.error = f"Connection error: {e}"
                    result_msg.execution_time_sec = 0.0
                    self.pub_move_result.publish(result_msg)
                    self._pending_move = None
        else:
            self.get_logger().error("No lerobot process connected")
            # Publish error result
            if self.pub_move_result:
                result_msg = MoveResult()
                result_msg.header.stamp = self.get_clock().now().to_msg()
                result_msg.move_uci = msg.move_uci
                result_msg.success = False
                result_msg.error = "No lerobot process connected"
                result_msg.execution_time_sec = 0.0
                self.pub_move_result.publish(result_msg)
                self._pending_move = None


def main():
    rclpy.init()
    node = ROS2BridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
