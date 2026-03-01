"""VoiceIn module - Speech recognition for human move input.

Wraps the standalone ChessSTT to listen for spoken chess moves
during the human's turn and push recognized moves to a queue.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Optional

from chess_manager.config import VoiceConfig

logger = logging.getLogger(__name__)


class VoiceIn:
    """Speech recognition module for capturing human voice commands."""

    def __init__(self, config: VoiceConfig, command_queue: asyncio.Queue) -> None:
        self._config = config
        self._command_queue = command_queue
        self._stt = None  # Lazy import to avoid hard dep when disabled
        self._listen_task: asyncio.Task | None = None
        self._on_voice_event: Optional[Callable[[dict], None]] = None

        if config.enabled:
            try:
                from chess_manager.voice.chess_stt import ChessSTT

                self._stt = ChessSTT(
                    elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
                    mistral_api_key=os.getenv("MISTRAL_API_KEY", ""),
                )
                logger.info("VoiceIn initialized with ChessSTT backend")
            except Exception as e:
                logger.error(f"Failed to initialize ChessSTT: {e}")
                self._stt = None
        else:
            logger.info("VoiceIn disabled")

    def _emit_voice_event(self, status: str) -> None:
        """Emit an STT voice status event via the callback."""
        if self._on_voice_event:
            self._on_voice_event({"category": "stt", "status": status})

    @property
    def is_listening(self) -> bool:
        """Whether a listen task is currently active (or disabled, meaning don't retry)."""
        if not self._config.enabled or not self._stt:
            return True  # Treat disabled as "already handled" to prevent repeated calls
        return self._listen_task is not None and not self._listen_task.done()

    async def start_listening(self, fen: str) -> None:
        """Start listening for a spoken chess move.

        Runs listen_parsed in a background task. When a move is detected,
        converts it to UCI and pushes it to the command queue.

        Args:
            fen: Current board FEN (used for move disambiguation).
        """
        if not self._config.enabled or not self._stt:
            self._emit_voice_event("disabled")
            return
        self.stop_listening()  # cancel any prior task
        logger.debug("[VoiceIn] Starting STT listener for human turn")
        self._emit_voice_event("listening")
        self._listen_task = asyncio.create_task(self._listen_loop(fen))

    async def _listen_loop(self, fen: str) -> None:
        """Listen for one spoken move and push it to the queue."""
        try:
            logger.debug("[VoiceIn] listen_parsed() started, mic open")
            move = await self._stt.listen_parsed(fen=fen)
            if move:
                self._emit_voice_event("processing")
                uci = f"{move.from_field}{move.to_field}"
                logger.debug(f"[VoiceIn] Parsed move: {move.from_field}->{move.to_field} ({move.san_notation})")
                logger.info(f"VoiceIn detected move: {uci}")
                await self._command_queue.put(uci)
                self._emit_voice_event("idle")
            else:
                logger.debug("[VoiceIn] listen_parsed() returned None (no move detected)")
                self._emit_voice_event("idle")
        except asyncio.CancelledError:
            logger.debug("VoiceIn listen task cancelled")
        except Exception as e:
            logger.error(f"VoiceIn listen error: {e}")
            self._emit_voice_event("idle")

    def stop_listening(self) -> None:
        """Cancel any active listening task."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            self._listen_task = None
            self._emit_voice_event("idle")

    def shutdown(self) -> None:
        """Clean up resources."""
        self.stop_listening()
