"""Teacher module - Chess move analysis using Stockfish + Mistral.

Wraps the standalone ChessTeacher to provide educational feedback on
human moves. The teacher handles its own TTS (bishop voice).
"""

from __future__ import annotations

import logging
from typing import Optional

from chess_manager.config import TeacherConfig

logger = logging.getLogger(__name__)


class Teacher:
    """Analyzes chess moves using Stockfish + Mistral for educational feedback."""

    def __init__(self, config: TeacherConfig, tts=None) -> None:
        self._config = config
        self._teacher = None  # Lazy import to avoid hard dep when disabled
        if config.enabled:
            try:
                from chess_manager.chess_teacher import ChessTeacher

                self._teacher = ChessTeacher(
                    model_id=config.model_id,
                    analysis_depth=config.analysis_depth,
                    tts=tts,
                )
                logger.info("Teacher initialized with ChessTeacher backend")
            except Exception as e:
                logger.error(f"Failed to initialize ChessTeacher: {e}")
                self._teacher = None
        else:
            logger.info("Teacher disabled")

    async def analyze_move(
        self,
        board_fen: str,
        move_uci: str,
    ) -> Optional[str]:
        """Analyze a move and return/speak educational feedback.

        The ChessTeacher.teach() method handles Stockfish analysis,
        Mistral commentary generation, and TTS playback internally.

        Args:
            board_fen: FEN of the position BEFORE the move.
            move_uci: The move in UCI notation.

        Returns:
            Commentary string, or None on failure.
        """
        if not self._config.enabled or not self._teacher:
            return None

        try:
            logger.debug(f"[Teacher] Analyzing move {move_uci} on FEN {board_fen[:30]}...")
            commentary = await self._teacher.teach(
                fen=board_fen, move=move_uci, validate_legal=True
            )
            logger.debug(f"[Teacher] Commentary: {commentary[:80]}...")
            return commentary
        except Exception as e:
            logger.error(f"Teacher analysis failed: {e}")
            logger.error(f"Failed State: FEN={board_fen}, Move={move_uci}")
            return None

    async def shutdown(self) -> None:
        """Clean up Stockfish engine."""
        if self._teacher:
            try:
                await self._teacher.close()
            except Exception:
                pass
