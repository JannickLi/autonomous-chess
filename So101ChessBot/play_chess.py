"""
Listen for chess moves via ROS2 bridge and execute them physically.

Receives MoveCommand messages from /chess/move_request via ros_bridge.py,
executes the physical move on the robot arm, then sends back move_done.

Usage (conda env, from repo root):
    python3 play_chess.py
    python3 play_chess.py --dataset lerobot_demo_dataset_new_calib
"""

import argparse
import time
from pathlib import Path

from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot_chess_bot.chess_board import ChessBoard
from lerobot_chess_bot.chess_mover import ChessMover
from lerobot_chess_bot.ros2_bridge_client import ROS2BridgeClient

FOLLOWER_PORT    = "/dev/ttyACM0"
CALIBRATION_PATH = Path(".calibrations/joint_calibration.json")
DATASET_ROOT     = "lerobot_demo_dataset_new_calib"

CAMERA_CONFIG = OpenCVCameraConfig(index_or_path=0, width=640, height=480, fps=30)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DATASET_ROOT,
                        help="Path to LeRobot demo dataset")
    args = parser.parse_args()

    # Load board calibration
    chess_board = ChessBoard()
    chess_board.load_calibration(CALIBRATION_PATH)

    # Connect robot arm
    follower = SO101Follower(config=SO101FollowerConfig(
        id="w_so101_follower",
        port=FOLLOWER_PORT,
        disable_torque_on_disconnect=False,
        cameras={}, # {"camera1": CAMERA_CONFIG},
    ))
    follower.connect(calibrate=False)
    print("Follower connected.")

    # Load demo dataset
    mover = ChessMover(follower, chess_board, dataset_root=args.dataset, speed=1.63)

    # Connect to ROS2 bridge (ros_bridge.py must already be running)
    bridge = ROS2BridgeClient()
    bridge.connect()

    print("\nReady. Waiting for moves...\n")

    try:
        while True:
            move_data = bridge.get_next_move()
            if move_data is None:
                time.sleep(0.05)
                continue

            print(f"\nReceived: {move_data.move_uci}")
            try:
                mover.execute_move(move_data)
                bridge.publish_move_done(move_data.move_uci, success=True)
                print(f"Move done: {move_data.move_uci}")
                mover.move_home()  # Move back to home after each move for safety
            except Exception as e:
                print(f"Error executing {move_data.move_uci}: {e}")
                bridge.publish_move_done(move_data.move_uci, success=False, error=str(e))

    except KeyboardInterrupt:
        print("\nInterrupted.")

    finally:
        bridge.disconnect()
        follower.disconnect()
        print("Done.")


if __name__ == "__main__":
    raise SystemExit(main())
