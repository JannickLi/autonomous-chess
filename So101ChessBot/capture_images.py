"""
Moves the robot to home position, then saves a camera image each time
you press SPACE. Press 'q' to quit.

Usage (conda env):
    sudo chmod 777 /dev/ttyACM0
    python3 capture_images.py
"""

import os
import sys
import time
import cv2
import termios
import tty

from lerobot_chess_bot.so101_ik import SO101IKController
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera

SAVE_DIR = "./captured_images"
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30


def get_key():
    """Read a single keypress without waiting for Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def main():
    os.makedirs(SAVE_DIR, exist_ok=True)

    # Connect camera
    camera = OpenCVCamera(
        config=OpenCVCameraConfig(
            index_or_path=CAMERA_INDEX,
            width=CAMERA_WIDTH,
            height=CAMERA_HEIGHT,
            fps=CAMERA_FPS,
        )
    )
    camera.connect()
    print("Camera connected.")

    # Connect robot and move home
    robot = SO101IKController(port="/dev/ttyACM0")
    robot.connect()
    robot.move_to_home()
    print("Robot at home position.")

    frame_count = 0
    print("\nPress SPACE to capture an image, 'q' to quit.")

    try:
        while True:
            key = get_key()
            if key == " ":
                frame = camera.async_read()
                filename = f"{str(frame_count).zfill(5)}.png"
                filepath = os.path.join(SAVE_DIR, filename)
                cv2.imwrite(filepath, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                frame_count += 1
                print(f"Saved {filepath} ({frame_count} total)")
            elif key == "q":
                print("\nQuitting...")
                break
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        camera.disconnect()
        robot.disconnect()
        print(f"Done. {frame_count} images saved to {SAVE_DIR}/")


if __name__ == "__main__":
    main()
