"""Personality system for piece agents."""

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class PersonalityWeights:
    """
    Personality weights that influence how a piece agent evaluates moves.

    Each weight is 0.0-1.0, representing how much the agent values that aspect.
    The weights are normalized during evaluation, so relative values matter.
    """

    # Self-preservation: Avoid getting captured, stay safe
    self_preservation: float = 0.5

    # Personal glory: Make impactful moves, be the hero, get captures
    personal_glory: float = 0.5

    # Team victory: Prioritize moves that help the team win
    team_victory: float = 0.7

    # Aggression: Attack opponent pieces, create threats
    aggression: float = 0.5

    # Positional dominance: Control key squares, maximize mobility
    positional_dominance: float = 0.5

    # Cooperation: Support other pieces, enable team plays
    cooperation: float = 0.5

    def to_prompt_description(self) -> str:
        """Convert weights to a natural language personality description."""
        traits = []

        if self.self_preservation >= 0.7:
            traits.append("are a survivor above all — you do NOT want to get taken off this board")
        elif self.self_preservation <= 0.3:
            traits.append("would gladly throw yourself into the fire if it helps the team")

        if self.personal_glory >= 0.7:
            traits.append("live for the spotlight — you want to be the hero of this game")
        elif self.personal_glory <= 0.3:
            traits.append("are humble and happy to let others shine")

        if self.team_victory >= 0.8:
            traits.append("care about winning more than anything — the team comes first, period")
        elif self.team_victory <= 0.4:
            traits.append("sometimes care more about your own drama than actually winning")

        if self.aggression >= 0.7:
            traits.append("are a born attacker — you see an enemy piece and you want it OFF the board")
        elif self.aggression <= 0.3:
            traits.append("prefer to play it safe and let the enemy come to you")

        if self.positional_dominance >= 0.7:
            traits.append("are obsessed with owning the best squares — territory is everything")
        elif self.positional_dominance <= 0.3:
            traits.append("don't care much about fancy positioning — just get the job done")

        if self.cooperation >= 0.7:
            traits.append("are a ride-or-die teammate who always has your allies' backs")
        elif self.cooperation <= 0.3:
            traits.append("are a lone wolf who works best solo")

        if not traits:
            return "You have a balanced, adaptable personality — a jack of all trades on the board."

        return "You " + ", ".join(traits) + "."

    def to_evaluation_criteria(self) -> str:
        """Generate weighted evaluation criteria for the prompt."""
        criteria = []

        # Normalize weights for display
        total = (
            self.self_preservation + self.personal_glory + self.team_victory +
            self.aggression + self.positional_dominance + self.cooperation
        )
        if total == 0:
            total = 1

        def pct(val: float) -> int:
            return int((val / total) * 100)

        criteria.append(f"- Self-preservation ({pct(self.self_preservation)}%): Does this move keep you safe from capture?")
        criteria.append(f"- Personal glory ({pct(self.personal_glory)}%): Does this move let you make an impact, capture pieces, or be decisive?")
        criteria.append(f"- Team victory ({pct(self.team_victory)}%): Does this move help your side win the game?")
        criteria.append(f"- Aggression ({pct(self.aggression)}%): Does this move attack or threaten opponent pieces?")
        criteria.append(f"- Positional dominance ({pct(self.positional_dominance)}%): Does this move give you or your team better square control?")
        criteria.append(f"- Cooperation ({pct(self.cooperation)}%): Does this move support your teammates or enable their plans?")

        return "\n".join(criteria)


# Default personality presets for different piece types
PIECE_PERSONALITIES: dict[str, PersonalityWeights] = {
    "pawn": PersonalityWeights(
        self_preservation=0.4,  # Pawns know they're expendable but still want to live
        personal_glory=0.6,     # Dream of promotion!
        team_victory=0.7,
        aggression=0.5,
        positional_dominance=0.6,  # Pawn structure matters
        cooperation=0.6,           # Pawns work together
    ),
    "knight": PersonalityWeights(
        self_preservation=0.5,
        personal_glory=0.7,     # Knights love flashy forks
        team_victory=0.6,
        aggression=0.7,         # Aggressive jumpers
        positional_dominance=0.5,
        cooperation=0.5,
    ),
    "bishop": PersonalityWeights(
        self_preservation=0.5,
        personal_glory=0.5,
        team_victory=0.7,
        aggression=0.5,
        positional_dominance=0.8,  # Bishops love long diagonals
        cooperation=0.6,
    ),
    "rook": PersonalityWeights(
        self_preservation=0.6,  # Rooks are valuable
        personal_glory=0.5,
        team_victory=0.7,
        aggression=0.6,
        positional_dominance=0.7,  # Open files!
        cooperation=0.7,           # Rooks work great in pairs
    ),
    "queen": PersonalityWeights(
        self_preservation=0.7,  # Queen is precious
        personal_glory=0.8,     # Queen loves being the star
        team_victory=0.6,
        aggression=0.7,
        positional_dominance=0.6,
        cooperation=0.4,        # Queen often works alone
    ),
    "king": PersonalityWeights(
        self_preservation=0.9,  # King MUST survive
        personal_glory=0.3,     # King stays humble in middlegame
        team_victory=0.9,       # King's survival IS team victory
        aggression=0.2,         # King avoids fights
        positional_dominance=0.4,
        cooperation=0.7,        # King needs protection
    ),
}


def get_personality_for_piece(piece_type: str, overrides: dict[str, float] | None = None) -> PersonalityWeights:
    """Get personality weights for a piece type, with optional overrides."""
    base = PIECE_PERSONALITIES.get(piece_type, PersonalityWeights())

    if overrides:
        return PersonalityWeights(
            self_preservation=overrides.get("self_preservation", base.self_preservation),
            personal_glory=overrides.get("personal_glory", base.personal_glory),
            team_victory=overrides.get("team_victory", base.team_victory),
            aggression=overrides.get("aggression", base.aggression),
            positional_dominance=overrides.get("positional_dominance", base.positional_dominance),
            cooperation=overrides.get("cooperation", base.cooperation),
        )

    return base


def load_personality_preset(preset_name: str, config_path: str | None = None) -> dict[str, dict[str, float]]:
    """
    Load a personality preset from YAML config.

    Args:
        preset_name: Name of the preset (e.g., "default", "aggressive", "defensive")
        config_path: Path to the YAML file (defaults to configs/personalities.yaml)

    Returns:
        Dict mapping piece types to their personality weight overrides
    """
    import yaml
    from pathlib import Path

    if config_path is None:
        # Default path relative to project root
        config_path = Path(__file__).parent.parent.parent / "configs" / "personalities.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        return {}

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if preset_name not in data:
        return {}

    return data[preset_name]


# Available personality presets
PERSONALITY_PRESETS = ["default", "aggressive", "defensive", "selfish", "teamfirst"]
