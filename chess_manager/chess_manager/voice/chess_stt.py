import asyncio
import base64

import chess
import pyaudio
from elevenlabs import ElevenLabs, RealtimeAudioOptions, RealtimeEvents
from elevenlabs.realtime import AudioFormat, CommitStrategy
from mistralai import Mistral
from pydantic import BaseModel

_CHUNK = 4096
_RATE = 16000


class ChessMove(BaseModel):
    from_field: str  # source square, e.g. "e2"
    to_field: str    # destination square, e.g. "e4"
    san_notation: str    # SAN notation, e.g. "e4" or "Nf3"


class _MoveDetection(BaseModel):
    found: bool
    from_field: str = ""
    to_field: str = ""
    san_notation: str = ""


class ChessSTT:
    """
    Realtime speech-to-text listener that stops when a legal chess move is detected.

    Usage:
        stt = ChessSTT(elevenlabs_api_key="...", mistral_api_key="...")
        move = await stt.listen(fen=board.fen())  # returns ChessMove or None
    """

    def __init__(
        self,
        elevenlabs_api_key: str,
        mistral_api_key: str,
        stop_delay: float = 1.0,
    ):
        self._el_client = ElevenLabs(api_key=elevenlabs_api_key)
        self._mistral = Mistral(api_key=mistral_api_key)
        self._stop_delay = stop_delay

    def _detect_move(self, text: str, unicode_board: str, legal_sans: list[str], legal_ucis: list[str]) -> ChessMove | None:
        """Use Mistral to check if transcript mentions a legal move and parse it."""
        response = self._mistral.chat.parse(
            model="mistral-large-latest",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a chess move parser. "
                        "Given a list of legal moves in SAN notation and a spoken transcript, "
                        "determine if the user is describing one of those legal moves. "
                        "If yes, set found=true and fill in from_field, to_field, and san_notation "
                        "Fill out from and to using algebraic notation (e.g. e2, f3), and san_notation using standard SAN (e.g. e4, Nf3). Make sure this is correct. "
                        "using the exact SAN from the legal moves list. Make sure it is a legal move from the given SAN list. "
                        "If the transcript does not refer to any legal move, set found=false."
                        "Transcript may be imperfect due to speech recognition errors, so use best judgement to find a match. "
                        "Also speech input can be very informal, so be flexible in interpreting it. For example, 'knight to f3' could match 'Nf3', and 'e two e four' could match 'e4'."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Legal moves sans: {', '.join(legal_sans)}\n"
                        f"Legal moves uci: {', '.join(legal_ucis)}\n"
                        f"Board Unicode: {unicode_board}\n"
                        f"Spoken transcript: {text}"
                    ),
                },
            ],
            response_format=_MoveDetection,
            temperature=0,
        )
        result = response.choices[0].message.parsed
        if not result.found:
            return None
        return ChessMove(
            from_field=result.from_field,
            to_field=result.to_field,
            san_notation=result.san_notation,
        )

    async def listen(self, fen: str) -> ChessMove | None:
        """
        Stream microphone audio until a legal chess move is detected.
        Returns a structured ChessMove, or None if interrupted.

        Args:
            fen: FEN of the current board position.
        """
        
        board = chess.Board(fen)
        legal_sans = [board.san(m) for m in board.legal_moves]
        legal_ucis = [board.uci(m) for m in board.legal_moves]
        print(f"Listening for chess move... (FEN: {fen}...)")
        print(f"Legal moves: {', '.join(legal_sans)}")
        print(f"legal ucis: {', '.join(legal_ucis)}")

        stop_event = asyncio.Event()
        detected: list[ChessMove] = []
        commit_timer: list[asyncio.Task] = []

        connection = await self._el_client.speech_to_text.realtime.connect(
            RealtimeAudioOptions(
                model_id="scribe_v2_realtime",
                audio_format=AudioFormat.PCM_16000,
                sample_rate=_RATE,
                commit_strategy=CommitStrategy.VAD,
                language_code="en",
            )
        )

        async def _delayed_stop():
            await asyncio.sleep(self._stop_delay)
            stop_event.set()

        async def _check_transcript(text: str):
            if not text:
                return
            try:
                move = await asyncio.to_thread(self._detect_move, text, board.unicode(), legal_sans, legal_ucis)
            except Exception as e:
                print(f"[Detection error] {e}")
                return
            if move is None:
                print(f"  (no legal move found in: '{text}')")
                return
            if detected:
                detected[0] = move
            else:
                detected.append(move)
                print(f"Chess move detected: '{move.san_notation}' — waiting {self._stop_delay}s...")
            if commit_timer and not commit_timer[0].done():
                commit_timer[0].cancel()
            commit_timer[:] = [asyncio.create_task(_delayed_stop())]

        def on_session_started(_data):
            print("Listening for chess move...")

        def on_partial_transcript(data):
            print(f"  {data.get('text', '')}", end="\r")

        def on_committed_transcript(data):
            text = data.get("text", "").strip()
            print(f"\nHeard: {text}")
            asyncio.create_task(_check_transcript(text))

        def on_error(error):
            print(f"Error: {error}")
            stop_event.set()

        def on_close():
            stop_event.set()

        connection.on(RealtimeEvents.SESSION_STARTED, on_session_started)
        connection.on(RealtimeEvents.PARTIAL_TRANSCRIPT, on_partial_transcript)
        connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, on_committed_transcript)
        connection.on(RealtimeEvents.ERROR, on_error)
        connection.on(RealtimeEvents.CLOSE, on_close)

        async def _stream_mic():
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=_RATE,
                input=True,
                frames_per_buffer=_CHUNK,
            )
            loop = asyncio.get_event_loop()
            try:
                while not stop_event.is_set():
                    chunk = await loop.run_in_executor(
                        None, lambda: stream.read(_CHUNK, exception_on_overflow=False)
                    )
                    await connection.send(
                        {"audio_base_64": base64.b64encode(chunk).decode("utf-8")}
                    )
            finally:
                stream.stop_stream()
                stream.close()
                p.terminate()

        try:
            await asyncio.gather(_stream_mic(), stop_event.wait())
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            await connection.close()

        if detected:
            move = detected[0]
            print(f"Parsed: {move.from_field} -> {move.to_field}  ({move.san_notation})")
        return detected[0] if detected else None

    async def listen_parsed(self, fen: str) -> ChessMove | None:
        """Alias for listen(). Kept for backwards compatibility."""
        return await self.listen(fen)
