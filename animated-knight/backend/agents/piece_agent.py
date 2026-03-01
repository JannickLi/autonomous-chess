"""Piece agent that represents a single chess piece with personality."""

from typing import AsyncIterator

import yaml

from backend.chess_engine import ChessBoard
from backend.chess_engine.board import PieceInfo
from backend.llm import LLMProvider
from backend.core import get_logger

from .base import AgentConfig, BaseAgent, MoveProposal, Vote
from .personality import PersonalityWeights, get_personality_for_piece

logger = get_logger(__name__)

# Debug flag - set to True to see one agent's full prompt/response
DEBUG_FIRST_AGENT = True
_debug_shown = False


def reset_debug_flag():
    """Reset debug flag to show next agent interaction."""
    global _debug_shown
    _debug_shown = False


class PieceAgent(BaseAgent):
    """Agent representing a single chess piece on the board with personality traits."""

    # Piece value weights for voting power
    PIECE_VALUES = {
        "pawn": 1,
        "knight": 3,
        "bishop": 3,
        "rook": 5,
        "queen": 9,
        "king": 10,
    }

    def __init__(
        self,
        piece: PieceInfo,
        llm_provider: LLMProvider,
        config: AgentConfig | None = None,
        prompt_template: str | None = None,
        personality: PersonalityWeights | None = None,
    ):
        agent_id = f"{piece.name}_{piece.square_name}"
        super().__init__(agent_id, llm_provider, config)
        self.piece = piece
        self.prompt_template = prompt_template or self._default_prompt_template()
        self.personality = personality or get_personality_for_piece(piece.name)

    @property
    def agent_type(self) -> str:
        return "piece"

    def _default_prompt_template(self) -> str:
        return """You are the {piece_name} on {square}. You are playing as {color}.

{personality_description}

Current position (FEN): {fen}
Your legal moves: {legal_moves}

Board visualization:
{board_visual}

Move history: {move_history}

As this {piece_name}, propose your best move from your legal moves.
Consider your personality traits and weigh these factors:
{evaluation_criteria}

Respond in this format:
MOVE: <your chosen move in UCI notation, e.g., e2e4>
REASONING: <1-2 sentences IN CHARACTER as this chess piece — be dramatic, funny, or opinionated based on your personality>"""

    def _build_prompt(self, board: ChessBoard) -> str:
        """Build the prompt for this piece."""
        moves = board.get_legal_moves_for_piece(self.piece.square)
        legal_moves_str = ", ".join(m.uci for m in moves) if moves else "none"
        move_history = board.get_move_history()
        move_history_str = ", ".join(move_history[-10:]) if move_history else "none"

        return self.prompt_template.format(
            piece_name=self.piece.name,
            square=self.piece.square_name,
            color=self.piece.color_name,
            fen=board.fen,
            legal_moves=legal_moves_str,
            board_visual=board.get_board_visual(),
            move_history=move_history_str,
            personality_description=self.personality.to_prompt_description(),
            evaluation_criteria=self.personality.to_evaluation_criteria(),
        )

    def _build_vote_prompt(self, board: ChessBoard, proposals: list[MoveProposal]) -> str:
        """Build the prompt for voting on proposals with descriptive moves and personal impacts."""
        choices = ["A", "B", "C"]

        # Build the options text with descriptions and personal impact
        options_text = []
        for i, p in enumerate(proposals[:3]):
            choice = choices[i]
            description = p.description or p.reasoning

            # Find the impact for this specific piece
            personal_impact = "No specific impact mentioned"
            if p.piece_impacts:
                # Try to find matching impact for this piece
                # Normalize our piece identifier
                piece_key = f"{self.piece.name}_{self.piece.square_name}".lower()
                piece_name_only = self.piece.name.lower()
                square = self.piece.square_name.lower()

                for key, impact in p.piece_impacts.items():
                    key_lower = key.lower()
                    # Exact match: "bishop_f8"
                    if piece_key == key_lower:
                        personal_impact = impact
                        break
                    # Match with parentheses: "bishop_(f8)" or contains both piece and square
                    if piece_name_only in key_lower and square in key_lower:
                        personal_impact = impact
                        break
                    # Match by piece name only (e.g., "king" for the only king)
                    if key_lower.startswith(piece_name_only) and (
                        piece_name_only in ["king", "queen"] or  # Unique pieces
                        square in key_lower  # Or square is mentioned
                    ):
                        personal_impact = impact
                        break

            options_text.append(f"""
Option {choice}:
  Strategic plan: {description}
  Impact on YOU ({self.piece.name} on {self.piece.square_name}): {personal_impact}""")

        proposals_display = "\n".join(options_text)

        return f"""You are the {self.piece.name} on {self.piece.square_name}, playing as {self.piece.color_name}.

{self.personality.to_prompt_description()}

The team strategist has analyzed the position and proposes these 3 options:
{proposals_display}

Based on YOUR personality and values, evaluate each option:
{self.personality.to_evaluation_criteria()}

You must vote for exactly ONE option (A, B, or C).
Consider both the strategic plan AND how it affects you personally.

Respond in this format:
VOTE: <A, B, or C>
REASONING: <1-2 sentences IN CHARACTER — be opinionated, dramatic, or funny about why you're voting this way>"""

    async def propose_move(self, board: ChessBoard) -> MoveProposal | None:
        """Propose a move from this piece's perspective."""
        moves = board.get_legal_moves_for_piece(self.piece.square)
        if not moves:
            return None

        prompt = self._build_prompt(board)
        response = await self.llm_provider.complete(prompt, self._llm_config)
        return self._parse_proposal(response.content, moves)

    async def stream_proposal(
        self, board: ChessBoard
    ) -> AsyncIterator[tuple[str, MoveProposal | None]]:
        """Stream the thought process while generating a proposal."""
        moves = board.get_legal_moves_for_piece(self.piece.square)
        if not moves:
            yield ("No legal moves available", None)
            return

        prompt = self._build_prompt(board)
        full_response = ""

        async for chunk in self.llm_provider.stream(prompt, self._llm_config):
            full_response += chunk
            yield (chunk, None)

        # Parse final proposal
        proposal = self._parse_proposal(full_response, moves)
        yield ("", proposal)

    async def vote(
        self, board: ChessBoard, proposals: list[MoveProposal]
    ) -> Vote:
        """Vote on proposed moves based on personality (A/B/C choice)."""
        global _debug_shown

        if not proposals:
            raise ValueError("No proposals to vote on")

        prompt = self._build_vote_prompt(board, proposals)
        response = await self.llm_provider.complete(prompt, self._llm_config)
        parsed_vote = self._parse_vote(response.content, proposals)

        # Debug: Show one agent's full interaction
        if DEBUG_FIRST_AGENT and not _debug_shown:
            _debug_shown = True
            print("\n" + "=" * 100)
            print(f"DEBUG: PIECE AGENT VOTE - {self.agent_id} ({self.piece.name} on {self.piece.square_name})")
            print("=" * 100)
            print("\n--- AGENT PERSONALITY ---")
            print(f"  self_preservation: {self.personality.self_preservation}")
            print(f"  personal_glory: {self.personality.personal_glory}")
            print(f"  team_victory: {self.personality.team_victory}")
            print(f"  aggression: {self.personality.aggression}")
            print(f"  positional_dominance: {self.personality.positional_dominance}")
            print(f"  cooperation: {self.personality.cooperation}")
            print("\n--- PROMPT SENT TO AGENT ---\n")
            print(prompt)
            print("\n--- AGENT RESPONSE ---\n")
            print(response.content)
            print("\n--- PARSED VOTE ---")
            print(f"  voted_for: {parsed_vote.voted_for}")
            print(f"  reasoning: {parsed_vote.reasoning}")
            print("\n--- PROPOSAL OPTIONS AVAILABLE ---")
            choices = ["A", "B", "C"]
            for i, p in enumerate(proposals[:3]):
                print(f"\n  Option {choices[i]}:")
                print(f"    Description: {p.description or p.move}")
                if p.piece_impacts:
                    print(f"    All Piece Impacts: {p.piece_impacts}")
            print("\n" + "=" * 100 + "\n")

        return parsed_vote

    def _parse_proposal(
        self, response: str, legal_moves: list
    ) -> MoveProposal | None:
        """Parse the LLM response into a MoveProposal."""
        legal_uci = {m.uci for m in legal_moves}
        lines = response.strip().split("\n")

        move = None
        reasoning = response

        for line in lines:
            line = line.strip()
            # Strip markdown formatting (**, *, etc.) before checking
            clean_line = line.replace("**", "").replace("*", "").strip()
            if clean_line.upper().startswith("MOVE:"):
                candidate = clean_line.split(":", 1)[1].strip().lower()
                # Clean up any extra characters
                candidate = candidate.split()[0] if candidate else ""
                if candidate in legal_uci:
                    move = candidate
            elif clean_line.upper().startswith("REASONING:"):
                reasoning = clean_line.split(":", 1)[1].strip()

        # If no valid move found, pick the first legal move
        if move is None and legal_moves:
            move = legal_moves[0].uci

        if move is None:
            return None

        return MoveProposal(
            agent_id=self.agent_id,
            move=move,
            reasoning=reasoning,
            piece_type=self.piece.name,
            piece_square=self.piece.square_name,
        )

    def _parse_vote(
        self, response: str, proposals: list[MoveProposal]
    ) -> Vote:
        """Parse the LLM response into a Vote (A, B, or C)."""
        valid_choices = {"a", "b", "c"}
        lines = response.strip().split("\n")

        voted_for = "A"  # Default fallback
        vote_found = False
        reasoning = response

        # Debug: Always log parsing info for first agent
        global _debug_shown
        show_parse_debug = DEBUG_FIRST_AGENT and not _debug_shown

        if show_parse_debug:
            print(f"\n  [PARSE DEBUG] Starting vote parse")
            print(f"  [PARSE DEBUG] Valid choices: {valid_choices}")
            print(f"  [PARSE DEBUG] Number of lines in response: {len(lines)}")

        for line in lines:
            line = line.strip()
            # Strip markdown formatting (**, *, etc.) before checking
            clean_line = line.replace("**", "").replace("*", "").strip()
            if clean_line.upper().startswith("VOTE:"):
                candidate = clean_line.split(":", 1)[1].strip().upper()
                # Extract just the letter (A, B, or C)
                candidate = candidate.split()[0] if candidate else "A"
                candidate = candidate.strip(".,;:!?")  # Remove punctuation
                if show_parse_debug:
                    print(f"  [PARSE DEBUG] Found VOTE line: '{line}' -> cleaned: '{clean_line}'")
                    print(f"  [PARSE DEBUG] Extracted candidate: '{candidate}'")
                if candidate.lower() in valid_choices:
                    voted_for = candidate.upper()
                    vote_found = True
                    if show_parse_debug:
                        print(f"  [PARSE DEBUG] Vote accepted: {voted_for}")
                else:
                    if show_parse_debug:
                        print(f"  [PARSE DEBUG] WARNING: '{candidate}' not in valid choices, using fallback: {voted_for}")
            elif clean_line.upper().startswith("REASONING:"):
                reasoning = clean_line.split(":", 1)[1].strip()

        if show_parse_debug:
            print(f"  [PARSE DEBUG] Final vote result: voted_for='{voted_for}', vote_found={vote_found}")

        return Vote(
            agent_id=self.agent_id,
            voted_for=voted_for,
            reasoning=reasoning,
        )

    @classmethod
    def create_for_movable_pieces(
        cls,
        board: ChessBoard,
        llm_provider: LLMProvider,
        config: AgentConfig | None = None,
        prompt_template: str | None = None,
        personality_overrides: dict[str, dict[str, float]] | None = None,
    ) -> list["PieceAgent"]:
        """Create piece agents for all pieces that have legal moves."""
        movable_pieces = board.get_movable_pieces()
        agents = []

        for piece in movable_pieces:
            # Get personality with any overrides for this piece type
            overrides = None
            if personality_overrides and piece.name in personality_overrides:
                overrides = personality_overrides[piece.name]

            personality = get_personality_for_piece(piece.name, overrides)

            agents.append(cls(
                piece, llm_provider, config, prompt_template, personality
            ))

        return agents

    @classmethod
    def create_for_all_pieces(
        cls,
        board: ChessBoard,
        llm_provider: LLMProvider,
        config: AgentConfig | None = None,
        prompt_template: str | None = None,
        personality_overrides: dict[str, dict[str, float]] | None = None,
    ) -> list["PieceAgent"]:
        """Create piece agents for ALL pieces of the current player (for voting)."""
        color = board.turn
        all_pieces = board.get_pieces(color)
        agents = []

        for piece in all_pieces:
            overrides = None
            if personality_overrides and piece.name in personality_overrides:
                overrides = personality_overrides[piece.name]

            personality = get_personality_for_piece(piece.name, overrides)

            agents.append(cls(
                piece, llm_provider, config, prompt_template, personality
            ))

        return agents


def load_piece_prompt_template(path: str) -> str:
    """Load a piece prompt template from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("template", "")
