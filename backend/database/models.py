from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Core Entities
# ---------------------------------------------------------------------------


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(Text, nullable=False)
    mlb_id = Column(Integer, unique=True)
    yahoo_id_1 = Column(Integer)
    yahoo_id_2 = Column(Integer)
    fangraphs_id = Column(Integer)
    savant_id = Column(Integer)
    bref_id = Column(Text)
    team = Column(Text)
    position = Column(Text)
    bats = Column(Text)
    throws = Column(Text)
    status = Column(Text, default="active")
    is_prospect = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlayerStats(Base):
    __tablename__ = "player_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "date", "source", "stat_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    date = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    stat_type = Column(Text, nullable=False)
    stats = Column(Text, nullable=False)  # JSON blob
    created_at = Column(DateTime, default=datetime.utcnow)


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True)  # MLB game PK
    date = Column(Text, nullable=False)
    home_team = Column(Text, nullable=False)
    away_team = Column(Text, nullable=False)
    status = Column(Text, default="scheduled")
    home_score = Column(Integer)
    away_score = Column(Integer)
    venue = Column(Text)
    park_factor_r = Column(Float)
    game_time = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Lineup(Base):
    __tablename__ = "lineups"
    __table_args__ = (
        UniqueConstraint("game_id", "team", "player_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    team = Column(Text, nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    batting_order = Column(Integer)
    is_confirmed = Column(Integer, default=0)
    source = Column(Text, default="mlb")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProbablePitcher(Base):
    __tablename__ = "probable_pitchers"
    __table_args__ = (
        UniqueConstraint("game_id", "team"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    team = Column(Text, nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    is_confirmed = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PitcherAppearance(Base):
    __tablename__ = "pitcher_appearances"
    __table_args__ = (
        UniqueConstraint("player_id", "game_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    date = Column(Text, nullable=False)
    innings_pitched = Column(Float)
    pitches = Column(Integer)
    earned_runs = Column(Integer)
    strikeouts = Column(Integer)
    walks = Column(Integer)
    hits_allowed = Column(Integer)
    save = Column(Integer, default=0)
    hold = Column(Integer, default=0)
    blown_save = Column(Integer, default=0)
    entered_inning = Column(Integer)
    leverage_index_avg = Column(Float)
    inherited_runners = Column(Integer, default=0)
    inherited_scored = Column(Integer, default=0)


class RelieverRole(Base):
    __tablename__ = "reliever_roles"
    __table_args__ = (
        UniqueConstraint("player_id", "date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    date = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    confidence = Column(Text, nullable=False)
    role_evidence = Column(Text)
    saves_last_14d = Column(Integer, default=0)
    holds_last_14d = Column(Integer, default=0)
    appearances_last_7d = Column(Integer, default=0)
    avg_leverage_last_14d = Column(Float)
    days_since_last_appearance = Column(Integer)
    pitches_last_3d = Column(Integer, default=0)
    pitches_last_7d = Column(Integer, default=0)
    available_tonight = Column(Integer, default=1)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mlb_transaction_id = Column(Integer)
    date = Column(Text, nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"))
    player_name = Column(Text)
    type = Column(Text, nullable=False)
    from_team = Column(Text)
    to_team = Column(Text)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Prospect(Base):
    __tablename__ = "prospects"
    __table_args__ = (
        UniqueConstraint("player_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    org = Column(Text, nullable=False)
    user_rank = Column(Integer)
    fangraphs_rank = Column(Integer)
    eta = Column(Text)
    level = Column(Text)
    scouting_notes = Column(Text)
    on_40_man = Column(Integer, default=0)
    minor_league_stats = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# User-Scoped Entities
# ---------------------------------------------------------------------------


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    yahoo_access_token = Column(Text, nullable=False)
    yahoo_refresh_token = Column(Text, nullable=False)
    yahoo_token_expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserLeague(Base):
    __tablename__ = "user_leagues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_account_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False)
    yahoo_league_key = Column(Text, nullable=False, unique=True)
    league_name = Column(Text)
    format = Column(Text, nullable=False)
    scoring_categories = Column(Text)
    roster_slots = Column(Text)
    num_teams = Column(Integer)
    season = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserRoster(Base):
    __tablename__ = "user_rosters"
    __table_args__ = (
        UniqueConstraint("league_id", "player_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("user_leagues.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"))
    yahoo_player_key = Column(Text)
    roster_position = Column(Text)
    is_editable = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserWatchlist(Base):
    __tablename__ = "user_watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    league_id = Column(Integer, ForeignKey("user_leagues.id"))
    notes = Column(Text)
    alert_on_lineup = Column(Integer, default=0)
    alert_on_callup = Column(Integer, default=0)
    alert_on_role_change = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    alert_type = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
