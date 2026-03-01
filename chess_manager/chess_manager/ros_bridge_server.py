#!/usr/bin/env python3
"""ROS2 TCP Bridge Server for Chess Manager.

Run this script with system Python (where ROS2 is sourced) to allow the
Chess Manager (running in a venv) to communicate with ROS2 topics over TCP.

This is the Chess Manager's dedicated bridge — separate from the
animated-knight bridge (port 9998).

Usage:
    source /opt/ros/humble/setup.bash
    source chess_msgs/install/setup.bash
    python3 chess_manager/ros_bridge_server.py [--host 0.0.0.0] [--port 9996]

Protocol (newline-delimited JSON):
  Client → Server:
    {"type": "publish",   "topic": "...", "data": {...}}
    {"type": "subscribe", "topic": "..."}
    {"type": "ping"}

  Server → Client:
    {"type": "message", "topic": "...", "data": {...}}
    {"type": "pong"}
    {"type": "error",   "message": "..."}

Supported ROS2 message types:
  - std_msgs/Empty       for trigger topics (capture, home)
  - std_msgs/String      for generic JSON payloads
  - chess_msgs/BoardState    for board detection results
  - chess_msgs/MoveCommand   for robot move commands
  - chess_msgs/MoveResult    for robot move results
  - chess_msgs/AgentRequest  for agent move requests
  - chess_msgs/AgentOpinions for agent deliberation results
"""

import argparse
import json
import logging
import socket
import threading
import time
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chess_manager_bridge")

# ---------------------------------------------------------------------------
# ROS2 imports
# ---------------------------------------------------------------------------
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile
    from std_msgs.msg import Empty as EmptyMsg
    from std_msgs.msg import String as StringMsg

    ROS2_AVAILABLE = True
except ImportError as e:
    logger.error(f"rclpy not available: {e}")
    logger.error("Source your ROS2 installation before running this script.")
    raise SystemExit(1)

try:
    from chess_msgs.msg import BoardState, MoveCommand, MoveResult

    CHESS_MSGS_AVAILABLE = True
except ImportError:
    logger.warning("chess_msgs not available — chess topics will use std_msgs/String")
    CHESS_MSGS_AVAILABLE = False

try:
    from chess_msgs.msg import AgentOpinion, AgentOpinions, AgentRequest

    AGENT_MSGS_AVAILABLE = True
except ImportError:
    AGENT_MSGS_AVAILABLE = False
    logger.info("AgentOpinion/AgentOpinions/AgentRequest msgs not available yet")

# ---------------------------------------------------------------------------
# Topic → message type mapping
# ---------------------------------------------------------------------------

_TOPIC_TYPES: dict[str, str] = {
    # Trigger topics (Empty)
    "/capture": "empty",
    "/chess/capture": "empty",
    "/chess/board/capture": "empty",
    "/robot_home": "empty",
    "/chess/robot/home": "empty",
}

if CHESS_MSGS_AVAILABLE:
    _TOPIC_TYPES.update({
        "/chess/board/state": "board_state",
        "/chess/move/command": "move_command",
        "/chess/move/result": "move_result",
        "/chess/perception_result": "board_state",
        "/chess/move_request": "move_command",
        "/chess/move_result": "move_result",
    })

if AGENT_MSGS_AVAILABLE:
    _TOPIC_TYPES.update({
        "/chess/agent_opinions": "agent_opinions",
        "/chess/agent_request": "agent_request",
    })


def _topic_type(topic: str) -> str:
    """Return the type tag for a topic, defaulting to 'string'."""
    return _TOPIC_TYPES.get(topic, "string")


def _msg_class_for(topic: str) -> Any:
    """Return the ROS2 message class for a topic."""
    tt = _topic_type(topic)
    if tt == "empty":
        return EmptyMsg
    if tt == "board_state":
        return BoardState
    if tt == "move_command":
        return MoveCommand
    if tt == "move_result":
        return MoveResult
    if tt == "agent_opinions" and AGENT_MSGS_AVAILABLE:
        return AgentOpinions
    if tt == "agent_request" and AGENT_MSGS_AVAILABLE:
        return AgentRequest
    return StringMsg


# ---------------------------------------------------------------------------
# chess_msgs ↔ dict conversion helpers
# ---------------------------------------------------------------------------

def _board_state_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "success": msg.success,
        "fen": msg.fen,
        "squares": list(msg.squares),
        "pieces": list(msg.pieces),
        "confidence": float(msg.confidence),
        "error": msg.error,
    }


def _move_command_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "move_uci": msg.move_uci,
        "from_square": msg.from_square,
        "to_square": msg.to_square,
        "piece_type": msg.piece_type,
        "piece_color": msg.piece_color,
        "is_capture": msg.is_capture,
        "is_castling": msg.is_castling,
        "is_en_passant": msg.is_en_passant,
        "is_promotion": msg.is_promotion,
        "promotion_piece": msg.promotion_piece,
        "captured_piece": msg.captured_piece,
        "castling_type": msg.castling_type,
        "board_fen": msg.board_fen,
    }


def _move_result_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "move_uci": msg.move_uci,
        "success": msg.success,
        "error": msg.error,
        "execution_time_sec": float(msg.execution_time_sec),
    }


def _dict_to_move_command(data: dict[str, Any]) -> "MoveCommand":
    msg = MoveCommand()
    msg.move_uci = data.get("move_uci") or ""
    msg.from_square = data.get("from_square") or ""
    msg.to_square = data.get("to_square") or ""
    msg.piece_type = data.get("piece_type") or ""
    msg.piece_color = data.get("piece_color") or ""
    msg.is_capture = bool(data.get("is_capture", False))
    msg.is_castling = bool(data.get("is_castling", False))
    msg.is_en_passant = bool(data.get("is_en_passant", False))
    msg.is_promotion = bool(data.get("is_promotion", False))
    msg.promotion_piece = data.get("promotion_piece") or ""
    msg.captured_piece = data.get("captured_piece") or ""
    msg.castling_type = data.get("castling_type") or ""
    msg.board_fen = data.get("board_fen") or ""
    return msg


def _dict_to_move_result(data: dict[str, Any]) -> "MoveResult":
    msg = MoveResult()
    msg.move_uci = data.get("move_uci", "")
    msg.success = data.get("success", False)
    msg.error = data.get("error", "")
    msg.execution_time_sec = float(data.get("execution_time_sec", 0.0))
    return msg


def _dict_to_board_state(data: dict[str, Any]) -> "BoardState":
    msg = BoardState()
    msg.success = data.get("success", False)
    msg.fen = data.get("fen", "")
    squares = data.get("squares", [])
    pieces = data.get("pieces", [])
    msg.squares = (squares + [""] * 64)[:64]
    msg.pieces = (pieces + [""] * 64)[:64]
    msg.confidence = float(data.get("confidence", 0.0))
    msg.error = data.get("error", "")
    return msg


def _agent_opinion_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "piece_type": msg.piece_type,
        "piece_color": msg.piece_color,
        "proposed_move": msg.proposed_move,
        "reasoning": msg.reasoning,
        "confidence": float(msg.confidence),
        "vote_weight": int(msg.vote_weight),
    }


def _agent_opinions_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "opinions": [_agent_opinion_to_dict(o) for o in msg.opinions],
        "selected_move_uci": msg.selected_move_uci,
        "selected_move_san": msg.selected_move_san,
        "vote_confidence": float(msg.vote_confidence),
        "voting_summary": msg.voting_summary,
    }


def _dict_to_agent_opinion(data: dict[str, Any]) -> "AgentOpinion":
    msg = AgentOpinion()
    msg.piece_type = data.get("piece_type", "")
    msg.piece_color = data.get("piece_color", "")
    msg.proposed_move = data.get("proposed_move", "")
    msg.reasoning = data.get("reasoning", "")
    msg.confidence = float(data.get("confidence", 0.0))
    msg.vote_weight = int(data.get("vote_weight", 1))
    return msg


def _dict_to_agent_opinions(data: dict[str, Any]) -> "AgentOpinions":
    msg = AgentOpinions()
    msg.opinions = [
        _dict_to_agent_opinion(o) for o in data.get("opinions", [])
    ]
    msg.selected_move_uci = data.get("selected_move_uci", "")
    msg.selected_move_san = data.get("selected_move_san", "")
    msg.vote_confidence = float(data.get("vote_confidence", 0.0))
    msg.voting_summary = data.get("voting_summary", "")
    return msg


def _agent_request_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "fen": msg.fen,
        "strategy": msg.strategy,
    }


def _dict_to_agent_request(data: dict[str, Any]) -> "AgentRequest":
    msg = AgentRequest()
    msg.fen = data.get("fen", "")
    msg.strategy = data.get("strategy", "")
    return msg


# ---------------------------------------------------------------------------
# ROS2 node
# ---------------------------------------------------------------------------

class ChessManagerBridgeNode(Node):
    """ROS2 node that bridges Chess Manager ↔ ROS2 topics over TCP."""

    def __init__(self) -> None:
        super().__init__("chess_manager_bridge")

        volatile_qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            durability=QoSDurabilityPolicy.VOLATILE,
        )

        self._pub_map: dict[str, Any] = {}
        self._pub_lock = threading.Lock()
        self._subscribers: dict[str, Any] = {}
        self._sub_lock = threading.Lock()
        self._ros_callbacks: dict[str, list] = {}
        self._cb_lock = threading.Lock()
        self._volatile_qos = volatile_qos
        self.get_logger().info("ChessManagerBridgeNode initialized")

    # ------------------------------------------------------------------
    # Publishing (client → ROS)
    # ------------------------------------------------------------------

    def publish_to_ros(self, topic: str, data: dict[str, Any]) -> None:
        with self._pub_lock:
            if topic not in self._pub_map:
                self._pub_map[topic] = self._create_publisher(topic)

        pub = self._pub_map.get(topic)
        if pub is None:
            self.get_logger().warn(f"No publisher for topic: {topic}")
            return

        tt = _topic_type(topic)
        if tt == "empty":
            pub.publish(EmptyMsg())
        elif tt == "move_command":
            pub.publish(_dict_to_move_command(data))
        elif tt == "move_result":
            pub.publish(_dict_to_move_result(data))
        elif tt == "board_state":
            pub.publish(_dict_to_board_state(data))
        elif tt == "agent_opinions" and AGENT_MSGS_AVAILABLE:
            pub.publish(_dict_to_agent_opinions(data))
        elif tt == "agent_request" and AGENT_MSGS_AVAILABLE:
            pub.publish(_dict_to_agent_request(data))
        else:
            msg = StringMsg()
            msg.data = json.dumps(data)
            pub.publish(msg)

        self.get_logger().debug(f"Published to {topic}")

    def _create_publisher(self, topic: str) -> Any:
        msg_cls = _msg_class_for(topic)
        return self.create_publisher(msg_cls, topic, self._volatile_qos)

    # ------------------------------------------------------------------
    # Subscribing (ROS → client)
    # ------------------------------------------------------------------

    def add_ros_subscription(self, topic: str, callback: Any) -> None:
        with self._cb_lock:
            if topic not in self._ros_callbacks:
                self._ros_callbacks[topic] = []
            self._ros_callbacks[topic].append(callback)

        with self._sub_lock:
            if topic in self._subscribers:
                return

            tt = _topic_type(topic)
            msg_cls = _msg_class_for(topic)

            if tt == "empty":
                cb = lambda msg, t=topic: self._on_empty(t, msg)
            elif tt in ("board_state", "move_command", "move_result", "agent_opinions", "agent_request"):
                cb = lambda msg, t=topic, tag=tt: self._on_chess_msg(t, tag, msg)
            else:
                cb = lambda msg, t=topic: self._on_string(t, msg)

            sub = self.create_subscription(msg_cls, topic, cb, self._volatile_qos)
            self._subscribers[topic] = sub
            self.get_logger().info(f"Subscribed to ROS topic: {topic} ({msg_cls.__name__})")

    def remove_ros_callback(self, topic: str, callback: Any) -> None:
        with self._cb_lock:
            callbacks = self._ros_callbacks.get(topic, [])
            if callback in callbacks:
                callbacks.remove(callback)

    def _on_empty(self, topic: str, _msg: Any) -> None:
        self._dispatch_ros_message(topic, {})

    def _on_string(self, topic: str, msg: Any) -> None:
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            data = {"raw": msg.data}
        self._dispatch_ros_message(topic, data)

    def _on_chess_msg(self, topic: str, tag: str, msg: Any) -> None:
        if tag == "board_state":
            data = _board_state_to_dict(msg)
        elif tag == "move_command":
            data = _move_command_to_dict(msg)
        elif tag == "move_result":
            data = _move_result_to_dict(msg)
        elif tag == "agent_opinions" and AGENT_MSGS_AVAILABLE:
            data = _agent_opinions_to_dict(msg)
        elif tag == "agent_request" and AGENT_MSGS_AVAILABLE:
            data = _agent_request_to_dict(msg)
        else:
            data = {}
        self._dispatch_ros_message(topic, data)

    def _dispatch_ros_message(self, topic: str, data: dict[str, Any]) -> None:
        with self._cb_lock:
            callbacks = list(self._ros_callbacks.get(topic, []))
        for cb in callbacks:
            try:
                cb(topic, data)
            except Exception as e:
                self.get_logger().error(f"Callback error on {topic}: {e}")


# ---------------------------------------------------------------------------
# Per-client handler
# ---------------------------------------------------------------------------

class ClientHandler(threading.Thread):
    """Handles one TCP client connection."""

    def __init__(
        self,
        conn: socket.socket,
        addr: tuple,
        node: ChessManagerBridgeNode,
    ) -> None:
        super().__init__(daemon=True, name=f"cm-client-{addr}")
        self._conn = conn
        self._addr = addr
        self._node = node
        self._send_lock = threading.Lock()
        self._running = True
        self._subscribed_topics: set[str] = set()

    def send(self, message: dict[str, Any]) -> None:
        if not self._running:
            return
        try:
            with self._send_lock:
                data = (json.dumps(message) + "\n").encode()
                self._conn.sendall(data)
        except Exception as e:
            logger.debug(f"Send to {self._addr} failed: {e}")
            self._running = False

    def _on_ros_message(self, topic: str, data: dict[str, Any]) -> None:
        self.send({"type": "message", "topic": topic, "data": data})

    def run(self) -> None:
        logger.info(f"Client connected: {self._addr}")
        buffer = ""
        self._conn.settimeout(1.0)

        try:
            while self._running:
                try:
                    chunk = self._conn.recv(4096).decode("utf-8", errors="replace")
                    if not chunk:
                        break
                    buffer += chunk
                    lines = buffer.split("\n")
                    buffer = lines[-1]
                    for line in lines[:-1]:
                        line = line.strip()
                        if line:
                            self._handle_line(line)
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.debug(f"Recv from {self._addr}: {e}")
                    break
        finally:
            self._cleanup()
            logger.info(f"Client disconnected: {self._addr}")

    def _handle_line(self, line: str) -> None:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            self.send({"type": "error", "message": "Invalid JSON"})
            return

        msg_type = msg.get("type")

        if msg_type == "publish":
            topic = msg.get("topic", "")
            data = msg.get("data", {})
            try:
                self._node.publish_to_ros(topic, data)
            except Exception as e:
                logger.error(f"Failed to publish to {topic}: {e}")
                self.send({"type": "error", "message": f"Publish failed: {e}"})

        elif msg_type == "subscribe":
            topic = msg.get("topic", "")
            if topic and topic not in self._subscribed_topics:
                try:
                    self._subscribed_topics.add(topic)
                    self._node.add_ros_subscription(topic, self._on_ros_message)
                    logger.info(f"{self._addr} subscribed to {topic}")
                except Exception as e:
                    self._subscribed_topics.discard(topic)
                    logger.error(f"Failed to subscribe to {topic}: {e}")
                    self.send({"type": "error", "message": f"Subscribe failed: {e}"})

        elif msg_type == "ping":
            self.send({"type": "pong"})

        else:
            self.send({"type": "error", "message": f"Unknown type: {msg_type}"})

    def _cleanup(self) -> None:
        self._running = False
        for topic in self._subscribed_topics:
            self._node.remove_ros_callback(topic, self._on_ros_message)
        try:
            self._conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# TCP server
# ---------------------------------------------------------------------------

class TCPBridgeServer:
    """Accepts TCP connections and spawns ClientHandler threads."""

    def __init__(self, host: str, port: int, node: ChessManagerBridgeNode) -> None:
        self._host = host
        self._port = port
        self._node = node
        self._server_socket: socket.socket | None = None

    def run(self) -> None:
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self._host, self._port))
        self._server_socket.listen(5)
        logger.info(f"Chess Manager bridge listening on {self._host}:{self._port}")

        try:
            while True:
                try:
                    conn, addr = self._server_socket.accept()
                    handler = ClientHandler(conn, addr, self._node)
                    handler.start()
                except Exception as e:
                    logger.error(f"Accept error: {e}")
                    time.sleep(0.1)
        finally:
            if self._server_socket:
                self._server_socket.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ROS2 TCP bridge server for Chess Manager (port 9996)"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9996, help="Bind port (default: 9996)")
    args = parser.parse_args()

    rclpy.init()
    node = ChessManagerBridgeNode()

    # Spin ROS2 in a background thread
    spin_thread = threading.Thread(
        target=lambda: rclpy.spin(node), daemon=True, name="ros2-spin"
    )
    spin_thread.start()

    server = TCPBridgeServer(args.host, args.port, node)
    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
