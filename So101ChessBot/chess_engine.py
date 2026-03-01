#!/usr/bin/env python3
"""
Chess Engine ROS2 Node (LEGACY — uses deprecated topics)

Plays chess against itself using Stockfish.
Publishes ONE move at a time to /chess/next_move.
Waits for /chess/move_done before publishing the next move.

NOTE: This node uses legacy topics (/chess/next_move, /chess/move_done).
      The new architecture uses /chess/move_request and /chess/move_result
      with chess_msgs/MoveCommand and chess_msgs/MoveResult.
      This node is kept for standalone demo/debug purposes and will be
      superseded by the Chess Manager + Teacher flow.

Install:
    sudo apt install stockfish
    pip install python-chess

Run:
    source /opt/ros/humble/setup.bash
    python3 chess_engine_node.py --skill 3 --think-time 0.5

Topics:
    Publishes:  /chess/next_move    std_msgs/String  e.g. "e2e4"  (DEPRECATED)
    Subscribes: /chess/move_done    std_msgs/String  e.g. "e2e4"  (DEPRECATED)
    Subscribes: /chess/board_state  std_msgs/String  FEN (optional external sync)
"""

import argparse
import chess
import chess.engine
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSDurabilityPolicy
from std_msgs.msg import String

STOCKFISH_PATH = "/usr/games/stockfish"
DEFAULT_THINK_TIME = 0.5
DEFAULT_SKILL = 5

volatile_qos = QoSProfile(
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
    durability=QoSDurabilityPolicy.VOLATILE,
)


class ChessEngineNode(Node):
    def __init__(self, think_time, skill_level):
        super().__init__("chess_engine")

        self.think_time = think_time
        self.skill_level = skill_level

        self.board = chess.Board()
        self.engine = None
        self.waiting = False  # True = move published, waiting for done
        self.move_ready = False  # True = time to compute and publish next move
        self.game_started = False
        self.game_over = False

        # Publishers
        self.pub_move = self.create_publisher(String, "/chess/next_move", 10)

        # Subscribers
        self.create_subscription(
            String, "/chess/move_done", self.on_move_done, volatile_qos
        )
        self.create_subscription(String, "/chess/board_state", self.on_board_state, 10)

        # Start engine
        self.get_logger().info(f"Starting Stockfish...")
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
            self.engine.configure({"Skill Level": self.skill_level})
            self.get_logger().info(
                f"Stockfish ready. Skill={skill_level} Think={think_time}s"
            )
        except Exception as e:
            self.get_logger().error(f"Failed to start Stockfish: {e}")
            raise

        # Main loop timer — polls move_ready flag, never called recursively
        self.create_timer(0.1, self._tick)

        # One-shot startup delay
        self._start_timer = self.create_timer(2.0, self._start_game)

    # ── Startup ───────────────────────────────────────────────────────────────

    def _start_game(self):
        self._start_timer.cancel()
        self.game_started = True
        self.get_logger().info("Game started — White to move.")
        self._print_board()
        self.move_ready = True  # signal tick to make first move

    # ── Main tick — only place moves are computed and published ───────────────

    def _tick(self):
        if not self.move_ready or self.waiting or self.game_over:
            return

        self.move_ready = False

        if self.board.is_game_over():
            self._log_result()
            self.game_over = True
            return

        side = "White" if self.board.turn == chess.WHITE else "Black"
        self.get_logger().info(f"\n{'='*40}\n{side} thinking...\n{'='*40}")

        result = self.engine.play(self.board, chess.engine.Limit(time=self.think_time))
        move = result.move
        self.board.push(move)

        move_str = move.uci()
        self.get_logger().info(f"{side} plays: {move_str}")
        self._print_board()

        # Publish and lock — nothing happens until move_done received
        self.waiting = True
        msg = String()
        msg.data = move_str
        self.pub_move.publish(msg)
        self.get_logger().info(f"Waiting for robot to execute {move_str}...")

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_move_done(self, msg):
        print(f"Received move_done: {msg.data}")
        if not self.game_started:
            self.get_logger().warn(
                f"Ignoring stale move_done before game start: {msg.data}"
            )
            return
        if not self.waiting:
            self.get_logger().warn(
                f"move_done received but not waiting — ignoring: {msg.data}"
            )
            return

        self.get_logger().info(f"Robot done: '{msg.data}' — scheduling next move.")
        self.waiting = False
        self.move_ready = True  # let tick handle the next move

    def on_board_state(self, msg):
        try:
            self.board = chess.Board(msg.data)
            self.get_logger().info(f"Board synced from FEN: {msg.data}")
            self._print_board()
        except Exception as e:
            self.get_logger().warn(f"Invalid FEN: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _print_board(self):
        self.get_logger().info(f"\n{self.board}\nFEN: {self.board.fen()}")

    def _log_result(self):
        outcome = self.board.outcome()
        result = self.board.result()
        if outcome and outcome.winner == chess.WHITE:
            self.get_logger().info(f"Game over — White wins! ({result})")
        elif outcome and outcome.winner == chess.BLACK:
            self.get_logger().info(f"Game over — Black wins! ({result})")
        else:
            self.get_logger().info(f"Game over — Draw! ({result})")

    def destroy_node(self):
        if self.engine:
            self.engine.quit()
        super().destroy_node()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--think-time", type=float, default=DEFAULT_THINK_TIME)
    parser.add_argument("--skill", type=int, default=DEFAULT_SKILL)
    args = parser.parse_args()

    rclpy.init()
    node = ChessEngineNode(think_time=args.think_time, skill_level=args.skill)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
