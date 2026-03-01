"""Supervisor agent that coordinates other agents and makes final decisions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, AsyncIterator

from backend.chess_engine import ChessBoard
from backend.llm import LLMConfig, LLMProvider

from .base import AgentConfig, BaseAgent, MoveProposal

if TYPE_CHECKING:
    from backend.chess_engine.engine_analyzer import EngineAnalyzer, PositionAnalysis

# Debug flag - set to True to see supervisor's full prompt/response
DEBUG_SUPERVISOR = True


class SupervisorAgent(BaseAgent):
    """
    Supervisor agent that coordinates piece agents and makes final decisions.

    The supervisor can:
    - Analyze the position in detail using a reasoning model
    - Propose 3 candidate moves with natural language descriptions
    - Describe the impact of each move on every piece of the team
    - Agents vote based on descriptions, not UCI notation
    """

    @staticmethod
    def _piece_type_for_move(board: ChessBoard, uci_move: str) -> str | None:
        """Derive the piece type name from a UCI move's source square."""
        try:
            from_square = uci_move[:2]
            piece_info = board.get_piece_at(from_square)
            return piece_info.name if piece_info else None
        except Exception:
            return None

    def __init__(
        self,
        llm_provider: LLMProvider,
        config: AgentConfig | None = None,
        prompt_template: str | None = None,
    ):
        super().__init__("supervisor", llm_provider, config)
        self.prompt_template = prompt_template or self._default_prompt_template()
        self._synthesis_template = self._default_synthesis_template()
        self._analysis_template = self._default_analysis_template()
        self._narration_template = self._default_narration_template()

    @property
    def agent_type(self) -> str:
        return "supervisor"

    def _default_prompt_template(self) -> str:
        return """You are a chess grandmaster and entertaining commentator supervising a team of piece agents.
Each piece agent has proposed a move. Your job is to pick the best move.

Current position (FEN): {fen}
Turn: {color}

Board visualization:
{board_visual}

Move history: {move_history}

Legal moves: {legal_moves}

Piece agent proposals:
{proposals}

Select the best move. Use vivid language, like a sports commentator calling a big play.

Respond in this format:
MOVE: <chosen move in UCI notation>
REASONING: <2-3 entertaining sentences about why this is the move — make it dramatic and fun>"""

    def _default_analysis_template(self) -> str:
        return """You are a chess grandmaster and entertaining commentator. Analyze the position and propose exactly 3 candidate moves.

CRITICAL: Describe moves strategically WITHOUT revealing exact squares or UCI notation. Keep descriptions SHORT and FUN.

Current position (FEN): {fen}
Turn: {color}

Board visualization:
{board_visual}

Move history: {move_history}

Our pieces on the board:
{our_pieces}

Legal moves available: {legal_moves}

Propose exactly 3 candidate moves, ranked from best to worst.

Respond in this EXACT format:

ANALYSIS:
<2-3 sentences about the position — keep it lively, like a sports commentator setting the scene>

MOVE A:
UCI: <move in UCI notation - this will be hidden from agents>
DESCRIPTION: <1-2 punchy, entertaining sentences. e.g., "The knight leaps into the fray like a wrecking ball, threatening to fork the king and queen!">
IMPACTS:
- King: <brief phrase, e.g., "Safe and cozy">
- Queen: <brief phrase, e.g., "Ready to pounce">
(list ALL our pieces with their current squares)

MOVE B:
UCI: <move>
DESCRIPTION: <1-2 punchy sentences>
IMPACTS:
- <piece>: <brief phrase>
...

MOVE C:
UCI: <move>
DESCRIPTION: <1-2 punchy sentences>
IMPACTS:
- <piece>: <brief phrase>
..."""

    def _default_narration_template(self) -> str:
        """Template for narrating engine-provided moves."""
        return """You are a chess grandmaster and entertaining commentator translating engine analysis into exciting descriptions for piece agents.

The engine has analyzed the position and proposes these moves:
{engine_moves}

Position evaluation: {evaluation_text} ({evaluation:+.2f} pawns)
Game phase: {game_phase}

Threats we face:
{threats_to_us}

Threats to opponent:
{threats_to_them}

Our pieces:
{our_pieces}

Your job: Describe each move like a sports commentator calling a big play. Make it vivid and fun!
- Do NOT change the move order (the engine has ranked them)
- Do NOT add or remove moves
- Keep descriptions to 1-2 punchy, entertaining sentences
- Keep impacts to a brief phrase each

Respond in this EXACT format:

MOVE A:
UCI: {move_a_uci}
DESCRIPTION: <1-2 punchy sentences — dramatic, vivid, fun to listen to>
IMPACTS:
- <piece type> (<square>): <brief phrase>
(list ALL our pieces)

MOVE B:
UCI: {move_b_uci}
DESCRIPTION: <1-2 punchy sentences>
IMPACTS:
- <piece>: <brief phrase>
...

MOVE C:
UCI: {move_c_uci}
DESCRIPTION: <1-2 punchy sentences>
IMPACTS:
- <piece>: <brief phrase>
..."""

    def _default_synthesis_template(self) -> str:
        return """You are an entertaining chess commentator wrapping up a heated debate between piece agents.

Current position (FEN): {fen}

Board:
{board_visual}

Proposals being discussed:
{proposals}

Previous deliberation context:
{context}

Give a punchy 2-3 sentence verdict, like a sports announcer wrapping up the debate. Which move wins and why? Make it dramatic and fun."""

    def _build_prompt(
        self, board: ChessBoard, proposals: list[MoveProposal]
    ) -> str:
        """Build the prompt for supervisor analysis."""
        proposals_text = "\n".join(
            f"- {p.piece_type} on {p.piece_square}: {p.description or p.move} - {p.reasoning}"
            for p in proposals
        )

        move_history = board.get_move_history()
        move_history_str = ", ".join(move_history[-10:]) if move_history else "none"
        legal_moves = ", ".join(board.get_legal_moves_uci())

        return self.prompt_template.format(
            fen=board.fen,
            color=board.turn_name,
            board_visual=board.get_board_visual(),
            move_history=move_history_str,
            legal_moves=legal_moves,
            proposals=proposals_text if proposals_text else "No proposals received",
        )

    def _build_analysis_prompt(self, board: ChessBoard) -> str:
        """Build the prompt for detailed position analysis with move candidates."""
        move_history = board.get_move_history()
        move_history_str = ", ".join(move_history[-10:]) if move_history else "none"
        legal_moves = ", ".join(board.get_legal_moves_uci())

        # Get our pieces with their positions
        color = board.turn
        our_pieces = board.get_pieces(color)
        pieces_text = "\n".join(
            f"- {p.name.capitalize()} on {p.square_name}"
            for p in our_pieces
        )

        return self._analysis_template.format(
            fen=board.fen,
            color=board.turn_name,
            board_visual=board.get_board_visual(),
            move_history=move_history_str,
            legal_moves=legal_moves,
            our_pieces=pieces_text,
        )

    def _build_narration_prompt(
        self, board: ChessBoard, engine_analysis: "PositionAnalysis"
    ) -> str:
        """Build prompt for LLM to narrate engine-provided moves."""
        # Format engine moves
        engine_moves_text = []
        choices = ["A", "B", "C"]
        for i, move in enumerate(engine_analysis.top_moves[:3]):
            eval_str = ""
            if move.mate_in is not None:
                eval_str = f"mate in {move.mate_in}"
            elif move.centipawn_score is not None:
                eval_str = f"eval {move.centipawn_score/100:+.2f}"

            details = []
            if move.is_capture:
                details.append(f"captures {move.captured_piece or 'piece'}")
            if move.is_check:
                details.append("gives check")
            details_str = ", ".join(details) if details else "quiet move"

            engine_moves_text.append(
                f"Move {choices[i]}: {move.san} ({move.uci}) - {eval_str}, {details_str}"
            )

        # Format threats
        threats_to_us = (
            "\n".join(f"- {t}" for t in engine_analysis.threats_to_us[:5])
            if engine_analysis.threats_to_us
            else "- No immediate threats"
        )
        threats_to_them = (
            "\n".join(f"- {t}" for t in engine_analysis.threats_to_them[:5])
            if engine_analysis.threats_to_them
            else "- No immediate threats to opponent"
        )

        # Format our pieces
        our_pieces_text = "\n".join(
            f"- {p.piece_type.capitalize()} on {p.square}"
            + (" (HANGING!)" if p.is_hanging else "")
            + (" (attacked)" if p.is_attacked and not p.is_hanging else "")
            for p in engine_analysis.our_pieces
        )

        # Get UCI moves for template
        move_ucis = [m.uci for m in engine_analysis.top_moves[:3]]
        while len(move_ucis) < 3:
            move_ucis.append("")

        return self._narration_template.format(
            engine_moves="\n".join(engine_moves_text),
            evaluation_text=engine_analysis.evaluation_text,
            evaluation=engine_analysis.evaluation,
            game_phase=engine_analysis.game_phase,
            threats_to_us=threats_to_us,
            threats_to_them=threats_to_them,
            our_pieces=our_pieces_text,
            move_a_uci=move_ucis[0],
            move_b_uci=move_ucis[1],
            move_c_uci=move_ucis[2],
        )

    async def propose_move(self, board: ChessBoard) -> MoveProposal | None:
        """
        Propose a move without any piece agent input.

        This is the supervisor making an independent decision.
        """
        legal_moves = board.get_legal_moves_uci()
        if not legal_moves:
            return None

        # Build a simpler prompt for independent analysis
        prompt = f"""You are a chess grandmaster and entertaining commentator analyzing the current position.

Current position (FEN): {board.fen}
Turn: {board.turn_name}

Board visualization:
{board.get_board_visual()}

Legal moves: {', '.join(legal_moves)}

Pick the best move. Keep it fun and dramatic!

Respond in this format:
MOVE: <chosen move in UCI notation>
REASONING: <2-3 punchy sentences — vivid language, like a sports commentator calling the play>"""

        response = await self.llm_provider.complete(prompt, self._llm_config)
        return self._parse_proposal(response.content, legal_moves)

    async def analyze_position(
        self,
        board: ChessBoard,
        engine_analyzer: "EngineAnalyzer | None" = None,
    ) -> list[MoveProposal]:
        """
        Perform detailed analysis and return 3 candidate moves with descriptions and per-piece impacts.

        This is the main method for the new voting flow where agents vote based on
        descriptive moves rather than UCI notation.

        Args:
            board: The chess board to analyze
            engine_analyzer: Optional Stockfish engine analyzer. If provided and available,
                           engine moves are used and LLM only narrates them.
        """
        legal_moves = board.get_legal_moves_uci()
        if not legal_moves:
            return []

        # Try engine analysis first if available
        engine_analysis = None
        if engine_analyzer and engine_analyzer.is_available:
            engine_analysis = await engine_analyzer.analyze_position(board, num_moves=3)

        if engine_analysis and engine_analysis.top_moves:
            # Engine is available - use engine moves, LLM only narrates
            return await self._analyze_position_with_engine(
                board, engine_analysis, legal_moves
            )
        else:
            # Fallback to LLM-only analysis
            return await self._analyze_position_llm(board, legal_moves)

    async def _analyze_position_with_engine(
        self,
        board: ChessBoard,
        engine_analysis: "PositionAnalysis",
        legal_moves: list[str],
    ) -> list[MoveProposal]:
        """Use engine analysis and have LLM narrate the moves."""
        prompt = self._build_narration_prompt(board, engine_analysis)

        analysis_config = LLMConfig(
            model=self._llm_config.model,
            temperature=self._llm_config.temperature,
            max_tokens=4096,
        )
        response = await self.llm_provider.complete(prompt, analysis_config)

        if DEBUG_SUPERVISOR:
            print("\n" + "=" * 100)
            print("DEBUG: SUPERVISOR POSITION ANALYSIS (ENGINE-ASSISTED)")
            print("=" * 100)
            print(f"\n--- ENGINE EVALUATION: {engine_analysis.evaluation_text} ---")
            print(f"--- GAME PHASE: {engine_analysis.game_phase} ---")
            print("\n--- ENGINE TOP MOVES ---")
            for i, m in enumerate(engine_analysis.top_moves[:3]):
                eval_str = f"mate in {m.mate_in}" if m.mate_in else f"{m.centipawn_score/100:+.2f}" if m.centipawn_score else "?"
                print(f"  {['A', 'B', 'C'][i]}: {m.san} ({m.uci}) - {eval_str}")
            print("\n--- THREATS TO US ---")
            for t in engine_analysis.threats_to_us[:5]:
                print(f"  - {t}")
            print("\n--- NARRATION PROMPT ---\n")
            print(prompt[:1500] + "..." if len(prompt) > 1500 else prompt)
            print("\n--- SUPERVISOR NARRATION ---\n")
            print(response.content)
            print("\n" + "=" * 100 + "\n")

        # Parse the narrated response - moves must match engine moves
        candidates = self._parse_analysis(response.content, legal_moves, board)

        # Verify and enforce engine move order
        engine_move_ucis = [m.uci for m in engine_analysis.top_moves[:3]]
        verified_candidates = []

        for i, engine_uci in enumerate(engine_move_ucis):
            # Find matching candidate or create fallback
            matching = next((c for c in candidates if c.move == engine_uci), None)
            if matching:
                verified_candidates.append(matching)
            else:
                # LLM didn't properly describe this move, create a basic description
                engine_move = engine_analysis.top_moves[i]
                eval_str = ""
                if engine_move.mate_in:
                    eval_str = f"Mate in {engine_move.mate_in}"
                elif engine_move.centipawn_score:
                    eval_str = f"Eval: {engine_move.centipawn_score/100:+.2f}"

                desc = f"{engine_move.san}"
                if engine_move.is_capture:
                    desc += f" captures {engine_move.captured_piece or 'piece'}"
                if engine_move.is_check:
                    desc += " with check"
                if eval_str:
                    desc += f" ({eval_str})"

                verified_candidates.append(MoveProposal(
                    agent_id=self.agent_id,
                    move=engine_uci,
                    reasoning=desc,
                    description=desc,
                    piece_impacts={},
                    piece_type=self._piece_type_for_move(board, engine_uci),
                ))

        if DEBUG_SUPERVISOR:
            print("\n--- VERIFIED CANDIDATES (ENGINE-ORDERED) ---")
            for i, c in enumerate(verified_candidates):
                print(f"\nOption {['A', 'B', 'C'][i]}:")
                print(f"  UCI Move: {c.move}")
                print(f"  Description: {c.description}")
            print("\n" + "=" * 100 + "\n")

        return verified_candidates[:3]

    async def _analyze_position_llm(
        self, board: ChessBoard, legal_moves: list[str]
    ) -> list[MoveProposal]:
        """Fallback: LLM-only analysis when engine is not available."""
        prompt = self._build_analysis_prompt(board)
        analysis_config = LLMConfig(
            model=self._llm_config.model,
            temperature=self._llm_config.temperature,
            max_tokens=4096,
        )
        response = await self.llm_provider.complete(prompt, analysis_config)

        if DEBUG_SUPERVISOR:
            print("\n" + "=" * 100)
            print("DEBUG: SUPERVISOR POSITION ANALYSIS (LLM-ONLY FALLBACK)")
            print("=" * 100)
            print("\n--- PROMPT SENT TO SUPERVISOR ---\n")
            print(prompt[:2000] + "..." if len(prompt) > 2000 else prompt)
            print("\n--- SUPERVISOR RESPONSE ---\n")
            print(response.content)
            print("\n" + "=" * 100 + "\n")

        candidates = self._parse_analysis(response.content, legal_moves, board)

        if DEBUG_SUPERVISOR:
            print("\n--- PARSED CANDIDATES ---")
            for i, c in enumerate(candidates):
                print(f"\nOption {['A', 'B', 'C'][i]}:")
                print(f"  UCI Move: {c.move}")
                print(f"  Description: {c.description}")
                print(f"  Impacts: {c.piece_impacts}")
            print("\n" + "=" * 100 + "\n")

        return candidates

    def _parse_analysis(
        self, response: str, legal_moves: list[str], board: ChessBoard
    ) -> list[MoveProposal]:
        """Parse the detailed analysis response into MoveProposals with descriptions and impacts."""
        legal_set = set(legal_moves)
        candidates = []

        # Strip markdown formatting from response for easier parsing
        clean_response = response.replace("**", "").replace("*", "")

        if DEBUG_SUPERVISOR:
            print("\n--- PARSING ANALYSIS ---")
            # Show a snippet of cleaned response to verify markdown is stripped
            print(f"  [PARSE] Clean response first 500 chars:\n{clean_response[:500]}")

        # Parse each MOVE section (A, B, C)
        for choice in ["A", "B", "C"]:
            # Match various formats: "MOVE A:", "MOVE A :", "Move A:", etc.
            pattern = rf"MOVE\s+{choice}\s*:"
            match = re.search(pattern, clean_response, re.IGNORECASE)
            if not match:
                if DEBUG_SUPERVISOR:
                    print(f"  [PARSE] Could not find MOVE {choice} section")
                continue

            start_idx = match.end()
            # Find end of this move section (next MOVE or end of string)
            next_choices = "BC" if choice == "A" else ("C" if choice == "B" else "")
            if next_choices:
                next_move = re.search(rf"MOVE\s+[{next_choices}]\s*:", clean_response[start_idx:], re.IGNORECASE)
                end_idx = start_idx + next_move.start() if next_move else len(clean_response)
            else:
                end_idx = len(clean_response)
            section = clean_response[start_idx:end_idx]

            if DEBUG_SUPERVISOR:
                print(f"  [PARSE] MOVE {choice} section (first 200 chars): {section[:200]}...")

            # Parse UCI move
            uci_match = re.search(r"UCI:\s*(\S+)", section, re.IGNORECASE)
            if not uci_match:
                if DEBUG_SUPERVISOR:
                    print(f"  [PARSE] Could not find UCI in MOVE {choice}")
                continue
            move = uci_match.group(1).lower().strip()
            if move not in legal_set:
                if DEBUG_SUPERVISOR:
                    print(f"  [PARSE] Move {move} not in legal moves, trying to find valid move")
                # Try to find a valid move
                for word in move.split():
                    if word in legal_set:
                        move = word
                        break
                else:
                    if DEBUG_SUPERVISOR:
                        print(f"  [PARSE] Skipping MOVE {choice} - no valid UCI move found")
                    continue

            # Parse description - look for DESCRIPTION: followed by text until IMPACTS: or next section
            desc_match = re.search(r"DESCRIPTION:\s*(.+?)(?=\n\s*IMPACTS:|\n\s*-\s*\w+:|\Z)", section, re.IGNORECASE | re.DOTALL)
            if desc_match:
                description = desc_match.group(1).strip()
                # Clean up the description - remove any leading dashes or markdown
                description = re.sub(r'^[-–—]\s*', '', description)
            else:
                description = f"Move option {choice}"

            if DEBUG_SUPERVISOR:
                print(f"  [PARSE] MOVE {choice} description: {description[:100]}...")

            # Parse impacts - look for lines starting with - followed by piece name and colon
            piece_impacts = {}
            impacts_match = re.search(r"IMPACTS:\s*\n((?:[-\s]*[A-Za-z\(\)].*\n?)+)", section, re.IGNORECASE)
            if impacts_match:
                impacts_text = impacts_match.group(1)
                if DEBUG_SUPERVISOR:
                    print(f"  [PARSE] Found IMPACTS section with {len(impacts_text.split(chr(10)))} lines")
                for line in impacts_text.strip().split("\n"):
                    line = line.strip()
                    # Remove leading dash and whitespace
                    if line.startswith("-"):
                        line = line[1:].strip()
                    # Skip empty lines or lines that look like section headers
                    if not line or line.upper().startswith("MOVE") or line.upper().startswith("UCI") or line.upper().startswith("DESCRIPTION"):
                        continue
                    # Parse "Piece (square):" or "Piece:" format
                    if ":" in line:
                        piece_part, impact = line.split(":", 1)
                        # Normalize piece identifier - handle "King (e8)" -> "king_e8"
                        piece_key = piece_part.strip().lower()
                        # Extract square from parentheses if present
                        square_match = re.search(r'\(([a-h][1-8])\)', piece_key)
                        if square_match:
                            square = square_match.group(1)
                            piece_name = re.sub(r'\s*\([a-h][1-8]\)', '', piece_key).strip()
                            piece_key = f"{piece_name}_{square}"
                        else:
                            piece_key = piece_key.replace(" ", "_")
                        piece_impacts[piece_key] = impact.strip()
            else:
                if DEBUG_SUPERVISOR:
                    print(f"  [PARSE] No IMPACTS section found for MOVE {choice}")

            if DEBUG_SUPERVISOR:
                print(f"  [PARSE] MOVE {choice} found {len(piece_impacts)} piece impacts")

            candidates.append(MoveProposal(
                agent_id=self.agent_id,
                move=move,
                reasoning=description,
                description=description,
                piece_impacts=piece_impacts,
                piece_type=self._piece_type_for_move(board, move),
            ))

        # Fallback: if parsing failed, use first 3 legal moves
        if not candidates:
            for i, move in enumerate(legal_moves[:3]):
                choice = ["A", "B", "C"][i]
                candidates.append(MoveProposal(
                    agent_id=self.agent_id,
                    move=move,
                    reasoning=f"Fallback candidate {choice}",
                    description=f"Option {choice}: Make a move",
                    piece_impacts={},
                    piece_type=self._piece_type_for_move(board, move),
                ))

        return candidates[:3]

    async def synthesize_proposals(
        self, board: ChessBoard, proposals: list[MoveProposal]
    ) -> MoveProposal:
        """
        Synthesize multiple piece agent proposals into a final decision.

        This is the main method for supervisor-based strategy.
        """
        legal_moves = board.get_legal_moves_uci()

        if not proposals:
            # No proposals, make independent decision
            result = await self.propose_move(board)
            if result:
                return result
            # Fallback to first legal move
            first_move = legal_moves[0] if legal_moves else ""
            return MoveProposal(
                agent_id=self.agent_id,
                move=first_move,
                reasoning="No proposals available, selecting first legal move",
                piece_type=self._piece_type_for_move(board, first_move) if first_move else None,
            )

        prompt = self._build_prompt(board, proposals)
        response = await self.llm_provider.complete(prompt, self._llm_config)
        proposal = self._parse_proposal(response.content, legal_moves, board)

        if proposal:
            return proposal

        # Fallback: pick first proposal
        best = proposals[0]
        return MoveProposal(
            agent_id=self.agent_id,
            move=best.move,
            reasoning=f"Deferring to {best.agent_id}: {best.reasoning}",
            piece_type=best.piece_type or self._piece_type_for_move(board, best.move),
        )

    async def stream_proposal(
        self, board: ChessBoard
    ) -> AsyncIterator[tuple[str, MoveProposal | None]]:
        """Stream the supervisor's independent analysis."""
        legal_moves = board.get_legal_moves_uci()
        if not legal_moves:
            yield ("No legal moves available", None)
            return

        prompt = f"""You are a chess grandmaster and entertaining commentator analyzing the current position.

Current position (FEN): {board.fen}
Turn: {board.turn_name}

Board visualization:
{board.get_board_visual()}

Legal moves: {', '.join(legal_moves)}

Pick the best move. Keep it fun and dramatic!

Respond in this format:
MOVE: <chosen move in UCI notation>
REASONING: <2-3 punchy sentences — vivid language, like a sports commentator calling the play>"""

        full_response = ""
        async for chunk in self.llm_provider.stream(prompt, self._llm_config):
            full_response += chunk
            yield (chunk, None)

        proposal = self._parse_proposal(full_response, legal_moves, board)
        yield ("", proposal)

    async def stream_synthesis(
        self, board: ChessBoard, proposals: list[MoveProposal]
    ) -> AsyncIterator[tuple[str, MoveProposal | None]]:
        """Stream the synthesis of piece agent proposals."""
        legal_moves = board.get_legal_moves_uci()

        if not proposals:
            async for chunk, proposal in self.stream_proposal(board):
                yield (chunk, proposal)
            return

        prompt = self._build_prompt(board, proposals)
        full_response = ""

        async for chunk in self.llm_provider.stream(prompt, self._llm_config):
            full_response += chunk
            yield (chunk, None)

        proposal = self._parse_proposal(full_response, legal_moves, board)

        if not proposal:
            best = proposals[0]
            proposal = MoveProposal(
                agent_id=self.agent_id,
                move=best.move,
                reasoning=f"Deferring to {best.agent_id}: {best.reasoning}",
                piece_type=best.piece_type or self._piece_type_for_move(board, best.move),
            )

        yield ("", proposal)

    def _parse_proposal(
        self, response: str, legal_moves: list[str], board: ChessBoard | None = None
    ) -> MoveProposal | None:
        """Parse the LLM response into a MoveProposal."""
        legal_set = set(legal_moves)
        lines = response.strip().split("\n")

        move = None
        reasoning = response

        for line in lines:
            line = line.strip()
            # Strip markdown formatting
            clean_line = line.replace("**", "").replace("*", "").strip()
            if clean_line.upper().startswith("MOVE:"):
                candidate = clean_line.split(":")[1].strip().lower()
                candidate = candidate.split()[0] if candidate else ""
                if candidate in legal_set:
                    move = candidate
            elif clean_line.upper().startswith("REASONING:"):
                reasoning = clean_line.split(":", 1)[1].strip()

        if move is None:
            return None

        return MoveProposal(
            agent_id=self.agent_id,
            move=move,
            reasoning=reasoning,
            piece_type=self._piece_type_for_move(board, move) if board else None,
        )
