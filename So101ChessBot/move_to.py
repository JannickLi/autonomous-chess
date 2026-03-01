#!/usr/bin/env python3
"""
Demo move sender — publishes chess moves to play_chess.py via ROS.

Flow: move_to.py → /chess/move_request → ros_bridge.py → play_chess.py

Usage (system Python, ROS2 sourced):
    source /opt/ros/humble/setup.bash
    python3 move_to.py e2e4
    python3 move_to.py e2e4:pawn
    python3 move_to.py e2e4:pawn e7e5:pawn g1f3:rook
"""

import sys
import time
import threading
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSDurabilityPolicy
from std_msgs.msg import String
from chess_msgs.msg import MoveCommand

volatile_qos = QoSProfile(
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
    durability=QoSDurabilityPolicy.VOLATILE,
)


class MoveSender(Node):
    def __init__(self):
        super().__init__("move_to")
        self._done = threading.Event()
        self.pub = self.create_publisher(MoveCommand, "/chess/move_request", 10)
        self.create_subscription(String, "/chess/move_done", self._on_done, volatile_qos)

    def send(self, arg: str):
        """Publish a MoveCommand and block until move_done comes back.

        arg format: <uci>[:<piece_type>]  e.g. "e2e4:pawn"
        """
        uci, _, piece = arg.strip().lower().partition(":")
        msg = MoveCommand()
        msg.move_uci    = uci
        msg.from_square = uci[:2]
        msg.to_square   = uci[2:4]
        msg.piece_type  = piece  # empty string if not provided

        self._done.clear()
        self.pub.publish(msg)
        print(f"→ {uci}" + (f" ({piece})" if piece else ""))
        self._done.wait()

    def _on_done(self, msg: String):
        print(f"✓ done: {msg.data}")
        self._done.set()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 move_to.py <uci_move> [<uci_move> ...]")
        print("Example: python3 move_to.py e2e4")
        sys.exit(1)

    rclpy.init()
    node = MoveSender()

    # Spin in background so _on_done can fire while main thread blocks in send()
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()
    time.sleep(0.5)  # let publisher connect

    try:
        for uci in sys.argv[1:]:
            node.send(uci)
    finally:
        rclpy.shutdown()


if __name__ == "__main__":
    main()
