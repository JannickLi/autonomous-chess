#!/usr/bin/env python3
"""
detect_worker.py - YOLOv8 detection worker that connects to ROS2 bridge via TCP.

This script runs in a conda environment with ultralytics/YOLOv8 installed.
It connects to the perception_bridge.py ROS2 node via TCP on port 9998.

Usage:
    conda activate <yolo-env>
    python3 detect_worker.py --weights runs/detect/chess/weights/best.pt --camera 0
"""

import argparse
from datetime import datetime
import json
import os
import socket
import struct
import sys
import time
from pathlib import Path
from typing import Optional

os.environ['QT_QPA_FONTDIR'] = '/usr/share/fonts/truetype'

import cv2




def find_chessnotation():
    """Add scripts directory to path for chessnotation import."""
    script_dir = Path(__file__).parent.parent / 'scripts'
    if script_dir.exists():
        sys.path.insert(0, str(script_dir))


find_chessnotation()

from chessnotation import board_state_to_fen


class DetectionWorker:
    """YOLOv8 detection worker with integrated camera."""

    TCP_HOST = 'localhost'
    TCP_PORT = 9997
    RECONNECT_DELAY = 2.0
    MAX_DETECT_RETRIES = 10
    RETRY_DELAY = 0.5

    def __init__(self, weights_path: str, camera_index: int = 0,
                 conf_threshold: float = 0.25, imgsz: int = 1280,
                 debug: bool = False):
        self.weights_path = weights_path
        self.camera_index = camera_index
        self.conf_threshold = conf_threshold
        self.imgsz = imgsz
        self.debug = debug

        # Lazy-load YOLO model
        self._model = None
        self._camera: Optional[cv2.VideoCapture] = None
        self._sock: Optional[socket.socket] = None

    @property
    def model(self):
        """Lazy-load YOLOv8 model."""
        if self._model is None:
            from ultralytics import YOLO
            print(f'Loading model from {self.weights_path}')
            self._model = YOLO(self.weights_path)
        return self._model

    def connect(self) -> bool:
        """Connect to the ROS2 perception bridge."""
        while True:
            try:
                print(f'Connecting to perception bridge at {self.TCP_HOST}:{self.TCP_PORT}...')
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.connect((self.TCP_HOST, self.TCP_PORT))
                print('Connected to perception bridge')
                return True
            except ConnectionRefusedError:
                print(f'Connection refused, retrying in {self.RECONNECT_DELAY}s...')
                time.sleep(self.RECONNECT_DELAY)
            except Exception as e:
                print(f'Connection error: {e}, retrying in {self.RECONNECT_DELAY}s...')
                time.sleep(self.RECONNECT_DELAY)

    def open_camera(self) -> bool:
        """Open the camera device."""
        if self._camera is not None:
            return True

        print(f'Opening camera {self.camera_index}...')
        self._camera = cv2.VideoCapture(self.camera_index)

        if not self._camera.isOpened():
            print(f'Failed to open camera {self.camera_index}')
            return False

        # Set camera resolution (optional, adjust as needed)
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        print(f'Camera opened: {int(self._camera.get(cv2.CAP_PROP_FRAME_WIDTH))}x'
              f'{int(self._camera.get(cv2.CAP_PROP_FRAME_HEIGHT))}')
        return True

    def run(self):
        """Main loop: wait for capture requests and process them."""
        self.connect()

        # Pre-load model
        _ = self.model
        print('Detection model loaded and ready to receive requests')

        while True:
            try:
                # Wait for capture request
                data = self._recv_message()
                if data is None:
                    print('Connection lost, reconnecting...')
                    self.connect()
                    continue

                if data.get('capture'):
                    print('Received capture request')
                    result = None
                    for attempt in range(1, self.MAX_DETECT_RETRIES + 1):
                        result, frame, yolo_result = self._detect()
                        if self.debug and frame is not None:
                            self._show_debug(frame, yolo_result, result, attempt)
                        if result.get('success'):
                            print(f'Detection successful (attempt {attempt}/{self.MAX_DETECT_RETRIES}): '
                                  f'FEN={result.get("fen")} '
                                  f'confidence={result.get("confidence", 0):.2f} '
                                  f'pieces={len(result.get("pieces", {}))}')
                            break
                        print(f'Attempt {attempt}/{self.MAX_DETECT_RETRIES} failed: '
                              f'{result.get("error", "unknown error")}')
                        if attempt < self.MAX_DETECT_RETRIES:
                            time.sleep(self.RETRY_DELAY)
                    else:
                        print('All detection attempts failed, sending last error')
                    self._send_message(result)

            except KeyboardInterrupt:
                print('Shutting down...')
                break
            except Exception as e:
                print(f'Error in main loop: {e}')
                time.sleep(1.0)

    def _detect(self) -> tuple:
        """Capture image and run YOLOv8 detection.

        Returns:
            (result_dict, frame_or_None, yolo_result_or_None)
        """
        # Ensure camera is open
        if not self.open_camera():
            return {
                'success': False,
                'error': f'Failed to open camera {self.camera_index}',
                'fen': '',
                'pieces': {},
                'confidence': 0.0
            }, None, None

        # Flush stale frames from the internal buffer so we get a fresh capture
        for _ in range(5):
            self._camera.grab()

        # Capture frame
        ret, frame = self._camera.read()
        if not ret or frame is None:
            return {
                'success': False,
                'error': 'Failed to capture frame',
                'fen': '',
                'pieces': {},
                'confidence': 0.0
            }, None, None

        # Resize to square before inference (matches camera_infer.py)
        frame_resized = cv2.resize(frame, (self.imgsz, self.imgsz))
        cv2.waitKey(1)

        # Run YOLOv8 inference
        try:
            results = self.model.predict(
                frame_resized,
                imgsz=self.imgsz,
                conf=self.conf_threshold,
                verbose=False
            )

            if not results or len(results) == 0:
                return self._error_result('No detection results', frame_resized), frame_resized, None

            # Convert to board state
            yolo_result = results[0]
            fen, pieces, confidence = board_state_to_fen(yolo_result)

            if fen is None:
                return self._error_result('Could not locate board corners', frame_resized), frame_resized, yolo_result

            return {
                'success': True,
                'fen': fen,
                'pieces': pieces,
                'confidence': confidence,
                'error': ''
            }, frame_resized, yolo_result

        except Exception as e:
            return self._error_result(f'Detection error: {str(e)}', frame_resized), frame_resized, None

    def _show_debug(self, frame, yolo_result, result: dict, attempt: int):
        """Show a debug window with detection overlay."""
        import numpy as np

        overlay = frame.copy()
        h, w = overlay.shape[:2]

        # Draw YOLO bounding boxes
        if yolo_result is not None and yolo_result.boxes is not None:
            boxes = yolo_result.boxes
            names = yolo_result.names
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label = f'{names[cls_id]} {conf:.2f}'

                # Color by piece type: white pieces green, black pieces red, other blue
                name = names[cls_id].lower()
                if name.startswith('w') or name[0].isupper():
                    color = (0, 200, 0)
                elif name.startswith('b') or name[0].islower():
                    color = (0, 0, 200)
                else:
                    color = (200, 150, 0)

                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
                # Label background
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(overlay, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
                cv2.putText(overlay, label, (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Status bar at the top
        status_color = (0, 180, 0) if result.get('success') else (0, 0, 220)
        cv2.rectangle(overlay, (0, 0), (w, 36), (0, 0, 0), -1)

        if result.get('success'):
            status = f'Attempt {attempt}: OK | FEN: {result.get("fen", "?")} | conf: {result.get("confidence", 0):.2f}'
        else:
            status = f'Attempt {attempt}: FAILED | {result.get("error", "unknown")}'

        cv2.putText(overlay, status, (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)

        # Piece count at bottom
        n_detections = 0
        if yolo_result is not None and yolo_result.boxes is not None:
            n_detections = len(yolo_result.boxes)
        count_text = f'Detections: {n_detections}'
        cv2.rectangle(overlay, (0, h - 30), (w, h), (0, 0, 0), -1)
        cv2.putText(overlay, count_text, (8, h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        cv2.imshow('Detection Debug', overlay)
        cv2.waitKey(1)

    def _error_result(self, error: str, frame) -> dict:
        """Build an error result and save the frame for debugging."""
        debug_dir = Path('debug_frames')
        debug_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = debug_dir / f'error_{timestamp}.jpg'
        cv2.imwrite(str(filepath), frame)
        print(f'Saved debug frame: {filepath}')
        return {
            'success': False,
            'error': error,
            'fen': '',
            'pieces': {},
            'confidence': 0.0
        }

    def _send_message(self, data: dict):
        """Send JSON message with length prefix."""
        payload = json.dumps(data).encode('utf-8')
        header = struct.pack('!I', len(payload))
        self._sock.sendall(header + payload)

    def _recv_message(self) -> Optional[dict]:
        """Receive JSON message with length prefix."""
        try:
            # Read 4-byte length header
            header = self._recv_exact(4)
            if not header:
                return None

            length = struct.unpack('!I', header)[0]
            if length > 10 * 1024 * 1024:  # 10MB sanity check
                print(f'Message too large: {length} bytes')
                return None

            # Read payload
            payload = self._recv_exact(length)
            if not payload:
                return None

            return json.loads(payload.decode('utf-8'))

        except Exception as e:
            print(f'Receive error: {e}')
            return None

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """Receive exactly n bytes from socket."""
        data = b''
        while len(data) < n:
            chunk = self._sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def close(self):
        """Clean up resources."""
        if self._camera is not None:
            self._camera.release()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        if self.debug:
            cv2.destroyAllWindows()


def list_cameras(max_index: int = 10):
    """Probe camera indices and print info for each available device."""
    print(f'Probing camera indices 0-{max_index - 1}...\n')
    found = 0

    # Suppress noisy OpenCV warnings during probing
    stderr_fd = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)

    try:
        for i in range(max_index):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                backend = cap.getBackendName()
                ret, _ = cap.read()
                readable = 'yes' if ret else 'no'
                # Restore stderr briefly to print our output
                os.dup2(stderr_fd, 2)
                print(f'  Camera {i}: {w}x{h} @ {fps:.0f}fps  backend={backend}  readable={readable}')
                os.dup2(devnull, 2)
                found += 1
                cap.release()
            else:
                cap.release()
    finally:
        os.dup2(stderr_fd, 2)
        os.close(stderr_fd)
        os.close(devnull)

    if found == 0:
        print('  No cameras found.')
    else:
        print(f'\n{found} camera(s) found. Use --camera <index> to select one.')


def main():
    parser = argparse.ArgumentParser(description='Chess piece detection worker')
    parser.add_argument(
        '--weights', '-w',
        type=str,
        default='runs/detect/chess/weights/best.pt',
        help='Path to YOLOv8 weights file'
    )
    parser.add_argument(
        '--camera', '-c',
        type=int,
        default=0,
        help='Camera device index'
    )
    parser.add_argument(
        '--conf', '-t',
        type=float,
        default=0.25,
        help='Detection confidence threshold'
    )
    parser.add_argument(
        '--imgsz',
        type=int,
        default=1280,
        help='Inference image size (frame is resized to imgsz x imgsz)'
    )
    parser.add_argument(
        '--list-cameras',
        action='store_true',
        help='List available cameras and exit'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Show debug window with detection overlay'
    )
    args = parser.parse_args()

    if args.list_cameras:
        list_cameras()
        sys.exit(0)

    # Validate weights path
    if not os.path.exists(args.weights):
        print(f'Error: weights file not found: {args.weights}')
        sys.exit(1)

    worker = DetectionWorker(
        weights_path=args.weights,
        camera_index=args.camera,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
        debug=args.debug
    )

    try:
        worker.run()
    finally:
        worker.close()


if __name__ == '__main__':
    main()
