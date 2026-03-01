"""VoiceOut module - Text-to-speech for agent opinions.

Wraps the standalone ChessTTS to speak agent opinions with
piece-specific voices. The teacher speaks independently via its own TTS.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Optional

from chess_manager.config import VoiceConfig
from chess_manager.models import SpeakRequest

logger = logging.getLogger(__name__)

# Re-export for use by callers that need voice IDs
CHESS_VOICES: dict[str, str] = {}


def _load_voices() -> dict[str, str]:
    """Load CHESS_VOICES from the TTS module, with fallback."""
    global CHESS_VOICES
    try:
        from chess_manager.voice.chess_tts import CHESS_VOICES as _voices

        CHESS_VOICES.update(_voices)
    except ImportError:
        logger.debug("voice.chess_tts not available, CHESS_VOICES empty")
    return CHESS_VOICES


class VoiceOut:
    """Text-to-speech module for speaking agent opinions with piece voices."""

    def __init__(self, config: VoiceConfig, speak_queue: asyncio.Queue) -> None:
        self._config = config
        self._speak_queue = speak_queue
        self._tts = None  # Lazy import to avoid hard dep when disabled
        self._run_task: asyncio.Task | None = None
        self._on_voice_event: Optional[Callable[[dict], None]] = None

        if config.enabled:
            try:
                from chess_manager.voice.chess_tts import ChessTTS

                _load_voices()
                self._tts = ChessTTS(api_key=os.getenv("ELEVENLABS_API_KEY", ""))
                logger.info("VoiceOut initialized with ChessTTS backend")
            except Exception as e:
                logger.error(f"Failed to initialize ChessTTS: {e}")
                self._tts = None
        else:
            logger.info("VoiceOut disabled")

    async def speak(self, text: str, piece_type: str = "king") -> None:
        """Speak text using the voice mapped to the given piece type.

        Args:
            text: Text to speak.
            piece_type: Chess piece type (king, queen, rook, bishop, knight, pawn).
        """
        if not self._config.enabled or not self._tts:
            return
        voice_id = CHESS_VOICES.get(piece_type or "king", CHESS_VOICES.get("king", ""))
        if not voice_id:
            logger.warning(f"No voice ID for piece_type={piece_type}, skipping")
            return
        logger.debug(f"[VoiceOut] Speaking as {piece_type}: {text[:60]}...")
        await self._tts.speak(text, voice_id)
        logger.debug(f"[VoiceOut] Finished speaking as {piece_type}")

    def _emit_voice_event(self, status: str, piece_type: str | None = None) -> None:
        """Emit a TTS voice status event via the callback."""
        if self._on_voice_event:
            data: dict = {"category": "tts", "status": status}
            if piece_type:
                data["piece_type"] = piece_type
            self._on_voice_event(data)

    async def run(self) -> None:
        """Main loop: consume SpeakRequests from queue and speak them."""
        if not self._config.enabled:
            return
        while True:
            try:
                request: SpeakRequest = await self._speak_queue.get()
                self._emit_voice_event("speaking", request.content_type)
                try:
                    await self.speak(request.text_to_speak, request.content_type)
                finally:
                    self._emit_voice_event("idle")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"VoiceOut speak error: {e}")

    def start(self) -> None:
        """Start the queue consumer as a background task."""
        if self._config.enabled:
            self._run_task = asyncio.create_task(self.run())

    def shutdown(self) -> None:
        """Clean up resources."""
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            self._run_task = None
