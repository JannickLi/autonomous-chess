"""TCP clients for communicating with ROS2 bridges.

The Chess Manager connects to ROS2 bridge processes via TCP:
- Robot Manager bridge (port 9999): length-prefixed binary JSON
- Perception bridge (port 9997): length-prefixed binary JSON
- Agent bridge (port 9998): newline-delimited JSON

Each bridge runs in system Python with ROS2 sourced.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class BridgeMessage:
    """Message received from a ROS2 bridge."""

    topic: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class LengthPrefixedBridgeClient:
    """TCP client for length-prefixed binary JSON protocol.

    Used for communicating with ros_bridge.py (robot, port 9999)
    and perception_bridge.py (port 9997).

    Protocol:
        4-byte big-endian length + JSON payload
    """

    def __init__(self, host: str = "localhost", port: int = 9999) -> None:
        self._host = host
        self._port = port
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._shutdown = threading.Event()
        self._send_lock = threading.Lock()

        self._callbacks: dict[str, list[Callable[[BridgeMessage], None]]] = {}
        self._message_queues: dict[str, list[Queue[BridgeMessage]]] = {}
        self._queue_lock = threading.Lock()

        self._reader_thread: Optional[threading.Thread] = None

    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to the bridge server."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(timeout)
            self._socket.connect((self._host, self._port))
            self._socket.settimeout(1.0)
            self._connected = True

            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                daemon=True,
                name=f"lp-bridge-reader-{self._port}",
            )
            self._reader_thread.start()

            logger.info(f"Connected to bridge at {self._host}:{self._port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to bridge at {self._host}:{self._port}: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from the bridge."""
        self._shutdown.set()
        self._connected = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def send(self, data: dict[str, Any]) -> bool:
        """Send a length-prefixed JSON message."""
        with self._send_lock:
            if not self._socket or not self._connected:
                return False
            try:
                payload = json.dumps(data).encode()
                self._socket.sendall(struct.pack("!I", len(payload)) + payload)
                return True
            except Exception as e:
                logger.error(f"Send error: {e}")
                self._connected = False
                return False

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """Receive exactly n bytes."""
        data = b""
        while len(data) < n:
            chunk = self._socket.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _reader_loop(self) -> None:
        """Background reader thread for length-prefixed messages."""
        while not self._shutdown.is_set():
            try:
                if not self._socket:
                    break
                header = self._recv_exact(4)
                if not header:
                    logger.warning("Bridge server closed connection")
                    self._connected = False
                    break

                length = struct.unpack("!I", header)[0]
                if length > 10 * 1024 * 1024:
                    logger.error(f"Message too large: {length}")
                    continue

                payload = self._recv_exact(length)
                if not payload:
                    self._connected = False
                    break

                data = json.loads(payload.decode("utf-8"))
                # Length-prefixed protocol sends raw data dicts
                topic = data.pop("_topic", "")
                msg = BridgeMessage(topic=topic, data=data)
                self._dispatch(msg)

            except socket.timeout:
                continue
            except Exception as e:
                if not self._shutdown.is_set():
                    logger.error(f"Reader error: {e}")
                self._connected = False
                break

    def _dispatch(self, msg: BridgeMessage) -> None:
        """Dispatch a received message to callbacks and queues."""
        topic = msg.topic

        with self._queue_lock:
            for q in self._message_queues.get(topic, []):
                q.put(msg)

        for cb in self._callbacks.get(topic, []):
            try:
                cb(msg)
            except Exception as e:
                logger.error(f"Callback error on {topic}: {e}")

    @property
    def is_connected(self) -> bool:
        return self._connected


class NewlineDelimitedBridgeClient:
    """TCP client for newline-delimited JSON protocol (ros_bridge_server.py).

    Used for communicating with ROS2 bridge servers. Features auto-reconnect
    modeled after TCPROSBridge: if the connection drops, the background reader
    thread will automatically attempt to reconnect and re-subscribe.

    Protocol:
        Client -> Server: {"type": "publish", "topic": "...", "data": {...}}\\n
        Client -> Server: {"type": "subscribe", "topic": "..."}\\n
        Server -> Client: {"type": "message", "topic": "...", "data": {...}}\\n
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9998,
        reconnect_interval: float = 2.0,
        name: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._reconnect_interval = reconnect_interval
        self._name = name or f"bridge-{port}"

        self._socket: Optional[socket.socket] = None
        self._socket_lock = threading.Lock()
        self._connected = False
        self._shutdown = threading.Event()

        self._message_queues: dict[str, list[Queue[BridgeMessage]]] = {}
        self._callbacks: dict[str, list[Callable[[BridgeMessage], None]]] = {}
        self._queue_lock = threading.Lock()
        self._subscribed_topics: set[str] = set()

        self._reader_thread: Optional[threading.Thread] = None

    def _connect_once(self) -> bool:
        """Attempt a single connection to the bridge server."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self._host, self._port))
            sock.settimeout(1.0)
            with self._socket_lock:
                self._socket = sock
                self._connected = True
            logger.info(f"[{self._name}] Connected to {self._host}:{self._port}")
            self._resubscribe()
            return True
        except Exception as e:
            logger.debug(f"[{self._name}] Connection to {self._host}:{self._port} failed: {e}")
            return False

    def _resubscribe(self) -> None:
        """Re-send subscribe messages for all known topics after reconnect."""
        for topic in list(self._subscribed_topics):
            self._send_raw({"type": "subscribe", "topic": topic})

    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to the bridge server and start background reader.

        The reader thread auto-reconnects on disconnect, so an initial
        failure here is non-fatal — the thread will keep retrying.
        """
        result = self._connect_once()

        # Always start the reader thread (it handles reconnection)
        if self._reader_thread is None or not self._reader_thread.is_alive():
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                daemon=True,
                name=f"{self._name}-reader",
            )
            self._reader_thread.start()

        if not result:
            logger.warning(
                f"[{self._name}] Initial connection to {self._host}:{self._port} failed; "
                f"will auto-reconnect every {self._reconnect_interval}s"
            )
        return result

    def disconnect(self) -> None:
        """Disconnect from the bridge."""
        self._shutdown.set()
        with self._socket_lock:
            self._connected = False
            if self._socket:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None

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
                logger.warning(f"[{self._name}] Send error: {e}")
                self._socket = None
                self._connected = False
                return False

    def _ensure_subscribed(self, topic: str) -> None:
        """Send subscribe request for a topic if not already done."""
        if topic not in self._subscribed_topics:
            self._subscribed_topics.add(topic)
            self._send_raw({"type": "subscribe", "topic": topic})

    async def publish(self, topic: str, data: dict[str, Any]) -> bool:
        """Publish a message to a ROS2 topic via the bridge."""
        return self._send_raw({"type": "publish", "topic": topic, "data": data})

    def subscribe(self, topic: str, callback: Callable[[BridgeMessage], None]) -> None:
        """Subscribe to a ROS2 topic with a callback."""
        self._callbacks.setdefault(topic, []).append(callback)
        with self._queue_lock:
            self._message_queues.setdefault(topic, [])
        self._ensure_subscribed(topic)

    async def wait_for_message(
        self, topic: str, timeout: float = 10.0
    ) -> Optional[BridgeMessage]:
        """Wait for a single message on a topic."""
        self._ensure_subscribed(topic)

        q: Queue[BridgeMessage] = Queue()
        with self._queue_lock:
            self._message_queues.setdefault(topic, []).append(q)

        loop = asyncio.get_running_loop()
        try:
            msg = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: q.get(timeout=timeout)),
                timeout=timeout,
            )
            return msg
        except (Empty, asyncio.TimeoutError):
            logger.warning(f"Timeout waiting for message on {topic}")
            return None
        finally:
            with self._queue_lock:
                queues = self._message_queues.get(topic, [])
                if q in queues:
                    queues.remove(q)

    def _reader_loop(self) -> None:
        """Background thread: maintains connection and dispatches messages."""
        buffer = ""
        while not self._shutdown.is_set():
            # Auto-reconnect if disconnected
            if not self._connected:
                if not self._connect_once():
                    # Wait for reconnect interval OR shutdown signal
                    self._shutdown.wait(timeout=self._reconnect_interval)
                    buffer = ""
                    continue

            try:
                with self._socket_lock:
                    sock = self._socket
                if sock is None:
                    continue

                chunk = sock.recv(4096).decode("utf-8", errors="replace")
                if not chunk:
                    logger.warning(f"[{self._name}] Server closed connection")
                    with self._socket_lock:
                        self._socket = None
                        self._connected = False
                    buffer = ""
                    continue

                buffer += chunk
                lines = buffer.split("\n")
                buffer = lines[-1]

                for line in lines[:-1]:
                    line = line.strip()
                    if line:
                        self._dispatch_line(line)

            except socket.timeout:
                continue
            except Exception as e:
                if not self._shutdown.is_set():
                    logger.error(f"[{self._name}] Reader error: {e}")
                with self._socket_lock:
                    self._socket = None
                    self._connected = False
                buffer = ""

    def _dispatch_line(self, line: str) -> None:
        """Parse and route a received JSON line."""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from bridge: {line[:100]}")
            return

        msg_type = msg.get("type")

        if msg_type == "message":
            topic = msg.get("topic", "")
            data = msg.get("data", {})
            bridge_msg = BridgeMessage(topic=topic, data=data)

            with self._queue_lock:
                for q in self._message_queues.get(topic, []):
                    q.put(bridge_msg)

            for cb in self._callbacks.get(topic, []):
                try:
                    cb(bridge_msg)
                except Exception as e:
                    logger.error(f"Callback error on {topic}: {e}")

        elif msg_type == "pong":
            logger.debug("Bridge pong received")

        elif msg_type == "error":
            logger.warning(f"Bridge server error: {msg.get('message')}")

    @property
    def is_connected(self) -> bool:
        return self._connected


class ROSClientManager:
    """Manages connections to all ROS2 bridges."""

    def __init__(
        self,
        robot_port: int = 9999,
        perception_port: int = 9997,
        agents_port: int = 9998,
        host: str = "localhost",
    ) -> None:
        self._host = host
        self.robot = LengthPrefixedBridgeClient(host, robot_port)
        self.perception = LengthPrefixedBridgeClient(host, perception_port)
        self.agents = NewlineDelimitedBridgeClient(host, agents_port)

    def connect_all(self, timeout: float = 5.0) -> dict[str, bool]:
        """Attempt to connect to all bridges. Returns connection status."""
        return {
            "robot": self.robot.connect(timeout),
            "perception": self.perception.connect(timeout),
            "agents": self.agents.connect(timeout),
        }

    def disconnect_all(self) -> None:
        """Disconnect from all bridges."""
        self.robot.disconnect()
        self.perception.disconnect()
        self.agents.disconnect()

    @property
    def status(self) -> dict[str, bool]:
        return {
            "robot": self.robot.is_connected,
            "perception": self.perception.is_connected,
            "agents": self.agents.is_connected,
        }
