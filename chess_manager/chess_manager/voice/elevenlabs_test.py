import asyncio
import os

import chess
from chess_stt import ChessSTT
from chess_tts import CHESS_VOICES, ChessTTS
from dotenv import load_dotenv

load_dotenv()


async def main():
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    stt = ChessSTT(
        elevenlabs_api_key=api_key,
        mistral_api_key=os.getenv("MISTRAL_API_KEY", ""),
        stop_delay=1.0,
    )
    tts = ChessTTS(api_key=api_key)

    board = chess.Board()

    while True:
        move = await stt.listen_parsed(fen=board.fen())
        if move:
            print(f"\n-> {move.from_field}{move.to_field}  ({move.notation})")
            await tts.speak(move.notation, CHESS_VOICES["king"])
        else:
            break


if __name__ == "__main__":
    asyncio.run(main())
