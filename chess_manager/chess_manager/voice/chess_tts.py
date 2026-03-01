import asyncio

import pyaudio
from elevenlabs import ElevenLabs

_PCM_RATE = 22050  # matches output_format="pcm_22050"

# Premade ElevenLabs voices mapped to chess pieces by character fit:
#   King   — Adam:    deep, commanding narrator
#   Queen  — Domi:    strong, assertive female
#   Rook   — Arnold:  powerful, solid, no-nonsense
#   Bishop — Antoni:  smooth, eloquent, measured
#   Knight — Josh:    energetic, younger male
#   Pawn   — Elli:    light, neutral, unassuming
CHESS_VOICES: dict[str, str] = {
    "king":   "pNInz6obpgDQGcFmaJgB",  # Adam
    "queen":  "AZnzlk1XvdvUeBnXmlld",  # Domi
    "rook":   "VR6AewLTigWG4xSOukaG",  # Arnold
    "bishop": "ErXwobaYiN019PkySvjV",  # Antoni
    "knight": "TxGEqnHWrfWFTfGW9XjX",  # Josh
    "pawn":   "MF3mGyEYCl7XYWbV9V6O",  # Elli
}


class ChessTTS:
    """
    Streaming TTS that plays audio immediately as chunks arrive from the API.

    A single instance should be shared across the application to avoid
    concurrent PyAudio streams fighting over the audio device.  The
    asyncio lock in ``speak()`` ensures only one utterance plays at a time.

    Usage:
        tts = ChessTTS(api_key="...")
        await tts.speak("Bishop e4", CHESS_VOICES["bishop"])
        tts.speak_sync("Rook h5", CHESS_VOICES["rook"])
    """

    def __init__(self, api_key: str, model_id: str = "eleven_flash_v2_5"):
        self._client = ElevenLabs(api_key=api_key)
        self._model_id = model_id
        self._lock = asyncio.Lock()

    def speak_sync(self, text: str, voice_id: str = CHESS_VOICES["king"]) -> None:
        """Stream TTS and play audio in real time. Blocks until playback is done."""
        audio_iter = self._client.text_to_speech.stream(
            voice_id=voice_id,
            text=text,
            model_id=self._model_id,
            output_format="pcm_22050",  # raw PCM — no decoding overhead
        )

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=_PCM_RATE,
            output=True,
        )
        try:
            for chunk in audio_iter:
                if chunk:
                    stream.write(chunk)
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    async def speak(self, text: str, voice_id: str = CHESS_VOICES["king"]) -> None:
        """Async wrapper — serializes playback so only one voice speaks at a time."""
        async with self._lock:
            await asyncio.to_thread(self.speak_sync, text, voice_id)


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY not found in environment variables")
    
    tts = ChessTTS(api_key=api_key)
    tts.speak_sync("Hello, I am the chess teacher. Let's learn some chess together!", CHESS_VOICES["king"])