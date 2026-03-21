"""Paper sports betting models — bets, bankroll tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class PaperBet(TenantScoped, table=True):
    """A paper sports bet linked to a portfolio."""

    __tablename__ = "paper_bets"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    portfolio_id: UUID = Field(foreign_key="paper_portfolios.id", index=True)

    # Game info
    sport: str = "nhl"  # nhl, nba, nfl, mlb, soccer
    game: str = ""  # e.g. "COL @ CHI"
    game_date: datetime = Field(default_factory=utcnow)

    # Bet details
    bet_type: str = "moneyline"  # moneyline, spread, total, player_prop
    selection: str = ""  # e.g. "COL ML", "Over 6.5", "Makar O2.5 SOG"
    player: Optional[str] = None  # Player name for props
    prop_type: Optional[str] = None  # points, goals, assists, shots_on_goal, saves
    line: Optional[float] = None  # The line/spread/total value (e.g. 2.5, 6.5, -1.5)
    odds: int = 0  # American odds (e.g. -135, +265)

    # Sizing
    stake: float = 0.0  # Dollar amount wagered
    kelly_pct: Optional[float] = None  # Kelly % used for sizing
    confidence: Optional[float] = None  # Agent confidence 0-100

    # Result
    status: str = "pending"  # pending, won, lost, push, void
    payout: float = 0.0  # Amount returned (0 if lost, stake+profit if won)
    pnl: float = 0.0  # Profit/loss (payout - stake)
    settled_at: Optional[datetime] = None

    # Metadata
    proposed_by: str = ""  # Agent name
    reasoning: str = ""  # Why the bet was placed
    book: str = ""  # Best book where odds were found
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
