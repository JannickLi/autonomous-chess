#!/usr/bin/env python3
"""
Standalone ROS2 recorder — subscribes to camera path topics and copies frames to disk.
No lerobot dependency. Run with system Python (ROS2 sourced).

Usage:
    source /opt/ros/humble/setup.bash
    python3 record.py
    python3 record.py --duration 60 --make-video
"""

import argparse
import subprocess
import shutil
import time
import threading
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class RecorderNode(Node):
    def __init__(self, output_dir, fps, duration):
        super().__init__("recorder")

        self.out = Path(output_dir)
        self.cam1_dir = self.out / "camera1"
        self.cam2_dir = self.out / "camera2"
        self.cam1_dir.mkdir(parents=True, exist_ok=True)
        self.cam2_dir.mkdir(parents=True, exist_ok=True)

        self.fps = fps
        self.duration = duration
        self.frame_index = 0
        self.start_time = None
        self.done = False

        self._latest_cam1_path = None
        self._latest_cam2_path = None
        self._lock = threading.Lock()

        # Subscribe to path topics
        self.create_subscription(String, "/camera1/image_path", self._cb_cam1, 10)
        self.create_subscription(String, "/camera2/image_path", self._cb_cam2, 10)

        self.create_timer(1.0 / fps, self._save_frame)

        self.get_logger().info(f"Recording to {self.out} at {fps}fps")
        if duration:
            self.get_logger().info(f"Will stop after {duration}s")

    def _cb_cam1(self, msg):
        with self._lock:
            self._latest_cam1_path = msg.data

    def _cb_cam2(self, msg):
        with self._lock:
            self._latest_cam2_path = msg.data

    def _save_frame(self):
        if self.done:
            return

        if self.start_time is None:
            self.start_time = time.time()

        with self._lock:
            p1 = self._latest_cam1_path
            p2 = self._latest_cam2_path

        if p1 is None and p2 is None:
            return

        name = f"{self.frame_index:06d}.jpg"

        if p1 and Path(p1).exists():
            shutil.copy2(p1, self.cam1_dir / name)
        if p2 and Path(p2).exists():
            shutil.copy2(p2, self.cam2_dir / name)

        self.frame_index += 1
        print(f"  Frame {self.frame_index}", end="\r")

        if self.duration and (time.time() - self.start_time) >= self.duration:
            self.get_logger().info(
                f"Duration reached. Recorded {self.frame_index} frames."
            )
            self.done = True


def make_video(
    recording_dir="./recording", output="clip.mp4", fps=30, side_by_side=True
):
    out = Path(recording_dir)
    cam1_dir = out / "camera1"
    cam2_dir = out / "camera2"

    if side_by_side and cam2_dir.exists() and any(cam2_dir.iterdir()):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(cam1_dir / "%06d.jpg"),
                "-framerate",
                str(fps),
                "-i",
                str(cam2_dir / "%06d.jpg"),
                "-filter_complex",
                "hstack",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                output,
            ],
            check=True,
        )
    else:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(cam1_dir / "%06d.jpg"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                output,
            ],
            check=True,
        )

    print(f"Video saved to {output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--output-dir", default="./recording")
    parser.add_argument("--make-video", action="store_true")
    parser.add_argument("--video-output", default="clip.mp4")
    args = parser.parse_args()

    rclpy.init()
    node = RecorderNode(args.output_dir, args.fps, args.duration)

    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\nStopped. Recorded {node.frame_index} frames to {args.output_dir}")
        node.destroy_node()
        rclpy.shutdown()

    if args.make_video and node.frame_index > 0:
        make_video(args.output_dir, output=args.video_output, fps=args.fps)


if __name__ == "__main__":
    main()
