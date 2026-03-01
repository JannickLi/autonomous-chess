"""TCP-based ROS bridge for decoupled operation.

Connects to a standalone ros_bridge_server.py process (running under system
Python with ROS2 sourced) via a simple newline-delimited JSON protocol.
This decouples the backend's Python version from ROS2's Python version.

Protocol (newline-delimited JSON):
  Client → Server:
    {"type": "publish",   "topic": "...", "data": {...}}
    {"type": "subscribe", "topic": "..."}
    {"type": "ping"}

  Server → Client:
    {"type": "message", "topic": "...", "data": {...}}
    {"type": "pong"}
    {"type": "error",   "message": "..."}
"""

import asyncio
import json
import logging
import socket
import threading
import time
from queue import Empty, Queue
from typing import Any, Callable

from backend.external.ros.bridge import ROSBridgeBase, ROSMessage

logger = logging.getLogger(__name__)


class TCPROSBridge(ROSBridgeBase):
    """ROS bridge that communicates with a remote ros_bridge_server.py over TCP.

    The server runs under system Python with ROS2 sourced; this client runs
    inside the backend's venv without any ROS dependency.
    """

    def __init__(
        self,
        host: str,
        port: int = 9998,
        reconnect_interval: float = 2.0,
    ) -> None:
        self._host = host
        self._port = port
        self._reconnect_interval = reconnect_interval

        self._socket: socket.socket | None = None
        self._socket_lock = threading.Lock()
        self._connected = False
        self._shutdown_flag = threading.Event()

        # Topic → list of queues for wait_for_message callers
        self._message_queues: dict[str, list[Queue[ROSMessage]]] = {}
        self._queue_lock = threading.Lock()

        # Persistent callbacks from subscribe()
        self._callbacks: dict[str, list[Callable[[ROSMessage], None]]] = {}

        # Topics for which we have sent a subscribe request to the server
        self._subscribed_topics: set[str] = set()

        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="tcp-ros-reader"
        )
        self._reader_thread.start()
        logger.info(f"TCPROSBridge started, targeting {host}:{port}")

    # ------------------------------------------------------------------
    # Internal connection management
    # ------------------------------------------------------------------

    def _connect(self) -> bool:
        """Attempt a single connection to the bridge server."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self._host, self._port))
            sock.settimeout(1.0)  # Non-blocking reads
            with self._socket_lock:
                self._socket = sock
                self._connected = True
            logger.info(f"TCPROSBridge connected to {self._host}:{self._port}")
            self._resubscribe()
            return True
        except Exception as e:
            logger.debug(f"TCPROSBridge connection failed: {e}")
            return False

    def _resubscribe(self) -> None:
        """Re-send subscribe messages for all known topics after reconnect."""
        for topic in list(self._subscribed_topics):
            self._send_raw({"type": "subscribe", "topic": topic})

    def _send_raw(self, message: dict[str, Any]) -> bool:
        """Send a single JSON line to the server (thread-safe)."""
        with self._socket_lock:
            if self._socket is None:
                return False
            try:
                data = (json.dumps(message) + "\n").encode()
                self._socket.sendall(data)
                return True
            except Exception as e:
                logger.warning(f"TCPROSBridge send error: {e}")
                self._socket = None
                self._connected = False
                return False

    def _ensure_subscribed(self, topic: str) -> None:
        """Send subscribe request for a topic if not already done."""
        if topic not in self._subscribed_topics:
            self._subscribed_topics.add(topic)
            self._send_raw({"type": "subscribe", "topic": topic})

    # ------------------------------------------------------------------
    # Background reader
    # ------------------------------------------------------------------

    def _reader_loop(self) -> None:
        """Background thread: maintains connection and dispatches messages."""
        buffer = ""
        while not self._shutdown_flag.is_set():
            if not self._connected:
                if not self._connect():
                    time.sleep(self._reconnect_interval)
                    buffer = ""
                    continue

            try:
                with self._socket_lock:
                    sock = self._socket
                if sock is None:
                    continue

                chunk = sock.recv(4096).decode("utf-8", errors="replace")
                if not chunk:
                    logger.warning("TCPROSBridge: server closed connection")
                    with self._socket_lock:
                        self._socket = None
                        self._connected = False
                    buffer = ""
                    continue

                buffer += chunk
                lines = buffer.split("\n")
                buffer = lines[-1]  # Last entry may be incomplete

                for line in lines[:-1]:
                    line = line.strip()
                    if line:
                        self._dispatch(line)

            except socket.timeout:
                continue  # Expected during idle periods
            except Exception as e:
                if not self._shutdown_flag.is_set():
                    logger.error(f"TCPROSBridge reader error: {e}")
                with self._socket_lock:
                    self._socket = None
                    self._connected = False
                buffer = ""

    def _dispatch(self, line: str) -> None:
        """Parse and route a received JSON line."""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            logger.warning(f"TCPROSBridge: invalid JSON from server: {e}")
            return

        msg_type = msg.get("type")

        if msg_type == "message":
            topic = msg.get("topic", "")
            data = msg.get("data", {})
            ros_msg = ROSMessage(topic=topic, data=data, timestamp=time.time())

            # Deliver to one-shot queues (wait_for_message callers)
            with self._queue_lock:
                for q in self._message_queues.get(topic, []):
                    q.put(ros_msg)

            # Deliver to persistent callbacks (subscribe callers)
            for cb in self._callbacks.get(topic, []):
                try:
                    cb(ros_msg)
                except Exception as e:
                    logger.error(f"TCPROSBridge callback error on {topic}: {e}")

        elif msg_type == "pong":
            logger.debug("TCPROSBridge: pong received")

        elif msg_type == "error":
            logger.warning(f"TCPROSBridge server error: {msg.get('message')}")

    # ------------------------------------------------------------------
    # ROSBridgeBase interface
    # ------------------------------------------------------------------

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        self._send_raw({"type": "publish", "topic": topic, "data": message})

    async def wait_for_message(
        self, topic: str, timeout: float = 10.0
    ) -> ROSMessage | None:
        # Make sure the server will forward messages on this topic
        self._ensure_subscribed(topic)

        # Register a one-shot queue
        q: Queue[ROSMessage] = Queue()
        with self._queue_lock:
            self._message_queues.setdefault(topic, []).append(q)

        loop = asyncio.get_event_loop()
        try:
            msg = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: q.get(timeout=timeout)),
                timeout=timeout,
            )
            return msg
        except (Empty, asyncio.TimeoutError):
            logger.warning(f"TCPROSBridge: timeout waiting for {topic}")
            return None
        finally:
            with self._queue_lock:
                queues = self._message_queues.get(topic, [])
                if q in queues:
                    queues.remove(q)

    def subscribe(
        self, topic: str, callback: Callable[[ROSMessage], None]
    ) -> None:
        self._callbacks.setdefault(topic, []).append(callback)
        with self._queue_lock:
            self._message_queues.setdefault(topic, [])
        self._ensure_subscribed(topic)

    async def is_connected(self) -> bool:
        return self._connected

    def shutdown(self) -> None:
        logger.info("TCPROSBridge shutting down")
        self._shutdown_flag.set()
        with self._socket_lock:
            if self._socket:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
        self._connected = False
