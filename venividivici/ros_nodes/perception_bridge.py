#!/usr/bin/env python3
"""
perception_bridge.py - ROS2 node that bridges to conda detection process via TCP.

This node runs in system Python with ROS2 and communicates with the detection
worker (running in conda with ultralytics/YOLOv8) via TCP socket on port 9998.

Usage:
    source /opt/ros/humble/setup.bash
    source chess_msgs/install/setup.bash
    python3 perception_bridge.py
"""

import json
import socket
import struct
import threading
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty

# Import custom message - requires chess_msgs package to be built and sourced
from chess_msgs.msg import BoardState


class PerceptionBridgeNode(Node):
    """ROS2 node that bridges perception requests to conda detection worker."""

    TCP_PORT = 9997
    RECV_TIMEOUT = 30.0  # seconds

    def __init__(self):
        super().__init__('chess_perception_bridge')

        # ROS2 publishers and subscribers
        self.capture_sub = self.create_subscription(
            Empty,
            '/chess/capture',
            self._on_capture_request,
            10
        )
        self.state_pub = self.create_publisher(
            BoardState,
            '/chess/perception_result',
            10
        )

        # TCP server for conda process
        self._server_sock: Optional[socket.socket] = None
        self._client_sock: Optional[socket.socket] = None
        self._client_lock = threading.Lock()

        # Start TCP server in background thread
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()

        self.get_logger().info(f'Perception bridge started, waiting for worker on port {self.TCP_PORT}')

    def _run_server(self):
        """Run TCP server to accept connections from detection worker."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(('localhost', self.TCP_PORT))
        self._server_sock.listen(1)

        while rclpy.ok():
            try:
                self.get_logger().info('Waiting for detection worker connection...')
                client, addr = self._server_sock.accept()
                self.get_logger().info(f'Detection worker connected from {addr}')

                with self._client_lock:
                    if self._client_sock:
                        try:
                            self._client_sock.close()
                        except Exception:
                            pass
                    self._client_sock = client
                    self._client_sock.settimeout(self.RECV_TIMEOUT)

            except Exception as e:
                if rclpy.ok():
                    self.get_logger().error(f'Server error: {e}')

    def _on_capture_request(self, msg: Empty):
        """Handle capture request from ROS2 topic."""
        self.get_logger().info('Received capture request')

        with self._client_lock:
            if self._client_sock is None:
                self.get_logger().warn('No detection worker connected')
                self._publish_error('No detection worker connected')
                return

            try:
                # Send capture command to worker
                self._send_to_worker({'capture': True})

                # Wait for detection result
                result = self._recv_from_worker()
                if result:
                    self._publish_board_state(result)
                else:
                    self._publish_error('No response from detection worker')

            except socket.timeout:
                self.get_logger().error('Detection worker timeout')
                self._publish_error('Detection timeout')
            except Exception as e:
                self.get_logger().error(f'Detection error: {e}')
                self._publish_error(str(e))

    def _send_to_worker(self, data: dict):
        """Send JSON message to detection worker with length prefix."""
        payload = json.dumps(data).encode('utf-8')
        header = struct.pack('!I', len(payload))
        self._client_sock.sendall(header + payload)

    def _recv_from_worker(self) -> Optional[dict]:
        """Receive JSON message from detection worker."""
        # Read 4-byte length header
        header = self._recv_exact(4)
        if not header:
            return None

        length = struct.unpack('!I', header)[0]
        if length > 10 * 1024 * 1024:  # 10MB sanity check
            self.get_logger().error(f'Message too large: {length} bytes')
            return None

        # Read payload
        payload = self._recv_exact(length)
        if not payload:
            return None

        return json.loads(payload.decode('utf-8'))

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """Receive exactly n bytes from socket."""
        data = b''
        while len(data) < n:
            chunk = self._client_sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _publish_board_state(self, data: dict):
        """Publish detection result to ROS2 topic."""
        msg = BoardState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.success = data.get('success', False)
        msg.fen = data.get('fen', '')
        msg.confidence = float(data.get('confidence', 0.0))
        msg.error = data.get('error', '')

        # Fill squares and pieces arrays
        squares = []
        pieces = []
        pieces_dict = data.get('pieces', {})

        for rank in '87654321':
            for file in 'abcdefgh':
                square = file + rank
                squares.append(square)
                pieces.append(pieces_dict.get(square, ''))

        msg.squares = squares
        msg.pieces = pieces

        self.state_pub.publish(msg)
        self.get_logger().info(f'Published board state: success={msg.success}, fen={msg.fen[:30]}...')

    def _publish_error(self, error: str):
        """Publish error state to ROS2 topic."""
        msg = BoardState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.success = False
        msg.error = error
        msg.squares = [f'{f}{r}' for r in '87654321' for f in 'abcdefgh']
        msg.pieces = [''] * 64
        self.state_pub.publish(msg)

    def destroy_node(self):
        """Clean up resources."""
        with self._client_lock:
            if self._client_sock:
                try:
                    self._client_sock.close()
                except Exception:
                    pass
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PerceptionBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
