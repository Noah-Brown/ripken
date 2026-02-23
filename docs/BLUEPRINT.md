# Fantasy Baseball In-Season Dashboard — Project Blueprint

## Overview

A personal, real-time fantasy baseball dashboard that merges MLB operational data (lineups, bullpen usage, prospect call-ups, advanced stats) with Yahoo Fantasy league context. Think FanGraphs Roster Resource, but filtered through "how does this affect **my** teams?"

The tool acts as a **lens** over existing data sources — it fetches, caches briefly, and layers analytics on top. It never becomes a data warehouse or redistributor of third-party content.

---

## Tech Stack (Locked)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+ / FastAPI | Strong baseball data ecosystem (pybaseball, pandas) |
| Database | SQLite (via SQLAlchemy + aiosqlite) | Single-user, zero-ops; migrate to Postgres if multi-user |
| Frontend | Next.js 14 (App Router) | Rich dashboard UI, same repo as backend |
| Scheduler | APScheduler (in-process) | Migrate to Celery if multi-user later |
| Cache | In-memory dict + SQLite | No Redis needed for single-user |
| Repo structure | Monorepo | `/backend`, `/frontend`, `/shared` at root |

---

## Repository Structure

```
fantasy-dashboard/
├── backend/
│   ├── main.py                    # FastAPI app + APScheduler setup
│   ├── config.py                  # Environment vars, API keys, constants
│   ├── database/
│   │   ├── models.py              # SQLAlchemy ORM models
│   │   ├── connection.py          # DB engine + session factory
│   │   └── migrations/            # Alembic migrations (optional)
│   ├── ingestion/
│   │   ├── mlb_stats.py           # MLB Stats API client
│   │   ├── savant.py              # Baseball Savant CSV fetcher
│   │   ├── fangraphs.py           # FanGraphs CSV fetcher
│   │   ├── player_id_crosswalk.py # Chadwick Bureau + ID mapping
│   │   └── scheduler.py           # APScheduler job definitions
│   ├── yahoo/
│   │   ├── auth.py                # OAuth2 flow
│   │   ├── client.py              # Yahoo Fantasy API wrapper
│   │   └── sync.py                # Roster/league sync logic
│   ├── analytics/
│   │   ├── reliever_roles.py      # Bullpen role inference engine
│   │   ├── matchup.py             # H2H + roto matchup projections
│   │   ├── start_sit.py           # Start/sit confidence scoring
│   │   ├── prospect_signals.py    # Call-up likelihood estimation
│   │   └── waiver_wire.py         # Free agent scoring + ranking
│   ├── api/
│   │   ├── routes/
│   │   │   ├── dashboard.py       # Dashboard home endpoints
│   │   │   ├── roster.py          # User roster endpoints
│   │   │   ├── lineups.py         # Lineup tracker endpoints
│   │   │   ├── pitching.py        # SP planner + reliever endpoints
│   │   │   ├── prospects.py       # Prospect watchlist endpoints
│   │   │   ├── matchup.py         # Matchup analyzer endpoints
│   │   │   └── waivers.py         # Waiver wire endpoints
│   │   └── dependencies.py        # Auth, DB session injection
│   └── tests/
├── frontend/
│   ├── app/                       # Next.js App Router pages
│   │   ├── page.tsx               # Dashboard home
│   │   ├── roster/page.tsx
│   │   ├── lineups/page.tsx
│   │   ├── pitching/page.tsx
│   │   ├── bullpen/page.tsx
│   │   ├── prospects/page.tsx
│   │   ├── matchup/page.tsx
│   │   └── waivers/page.tsx
│   ├── components/
│   │   ├── ui/                    # Base components (tables, cards, badges)
│   │   ├── charts/                # Sparklines, usage charts
│   │   └── modules/               # Dashboard-specific composite components
│   ├── lib/
│   │   ├── api.ts                 # Backend API client
│   │   └── types.ts               # Shared TypeScript types
│   └── public/
├── shared/
│   └── constants.py               # Team abbreviations, position enums, etc.
├── data/
│   ├── chadwick/                  # Player ID crosswalk CSVs
│   ├── park_factors.json          # Static park factor data
│   └── prospect_rankings.csv      # User-imported FanGraphs prospect list
├── docs/
│   └── BLUEPRINT.md               # This file
├── .env.example
├── docker-compose.yml             # Optional: unified dev environment
├── Makefile                       # Common commands
└── README.md
```

---

## Data Sources

### 1. MLB Stats API (Primary — Free, No Auth)

**Base URL:** `https://statsapi.mlb.com/api/v1`

| Endpoint | Use | Example |
|---|---|---|
| `/schedule` | Daily schedule, game status | `/schedule?date=2025-06-15&sportId=1` |
| `/game/{id}/feed/live` | Live game data, box scores | Full play-by-play + box score |
| `/teams/{id}/roster` | Active 26-man + 40-man rosters | Include `rosterType=active` or `fullRoster` |
| `/people/{id}/stats` | Player stats (career, season, splits) | Supports many stat groups and types |
| `/transactions` | Call-ups, options, IL, DFA, trades | Filter by date range |
| `/schedule?sportId=1&startDate=X&endDate=Y` | Probable pitchers in schedule data | Look for `probablePitcher` in game objects |

**Rate limits:** None documented, but be respectful. 1 req/sec is safe.

**Key gotcha:** Lineups (batting order) only appear in the `/game/{id}/feed/live` endpoint once they're officially submitted, typically 1-2 hours before game time. For earlier projected lineups, you need a secondary source.

### 2. Yahoo Fantasy API (User-Scoped — Free, OAuth2 Required)

**Base URL:** `https://fantasysports.yahooapis.com/fantasy/v2`

**Auth:** OAuth2 with refresh tokens. Register app at https://developer.yahoo.com/apps/.

| Resource | Use |
|---|---|
| `/users;use_login=1/games;game_keys=mlb/leagues` | List user's leagues |
| `/league/{league_key}/settings` | Scoring categories, roster slots, trade deadline |
| `/league/{league_key}/standings` | League standings |
| `/team/{team_key}/roster` | User's roster with player details |
| `/league/{league_key}/players;status=FA` | Free agents (waiver wire) |
| `/league/{league_key}/transactions` | Recent adds/drops/trades in league |
| `/team/{team_key}/matchups` | H2H matchup details |

**Rate limits:** ~20,000 requests/day. Cache aggressively — roster data doesn't change often intra-day.

**Key gotcha:** Yahoo player IDs are unique to Yahoo. You must map them to MLB IDs using name + team matching or the Chadwick crosswalk.

### 3. Baseball Savant / Statcast (Free, No Auth)

**Approach:** CSV export endpoints via URL parameters. No official API.

| Data | URL Pattern |
|---|---|
| Batter leaderboard | `https://baseballsavant.mlb.com/leaderboard/custom?...&csv=true` |
| Pitcher leaderboard | Same pattern, different player type param |
| Expected stats | `xwoba`, `xba`, `xslg` in leaderboard columns |
| Sprint speed | Leaderboard with `sprint_speed` metric |

**Frequency:** Nightly refresh is sufficient. Data updates overnight.

**Key gotcha:** URL parameters change occasionally. Build the fetcher to be configurable so you can update params without code changes.

### 4. FanGraphs (Free Tier + Subscription)

**Approach:** CSV export from leaderboard pages.

| Data | URL Pattern | Auth? |
|---|---|---|
| Batting leaderboard | `https://www.fangraphs.com/leaders.aspx?...&type=8&page=1_10000` with export | No |
| Pitching leaderboard | Same pattern | No |
| ROS Projections (Steamer/ZiPS) | Leaderboard with projection system selected | No |
| Prospect rankings | Export from prospect board | FG+ subscription |

**Frequency:** Projections weekly. Leaderboards nightly. Prospect rankings on-demand / user-imported.

**For distribution safety:** Fetch on behalf of user, cache per-user with short TTL, always attribute "Data from FanGraphs."

### 5. Chadwick Bureau — Player ID Crosswalk

**Repo:** https://github.com/chadwickbureau/register

**File:** `people.csv` — maps across MLB ID, Retrosheet, FanGraphs, Baseball Reference, and more.

**Missing:** Yahoo Fantasy IDs are NOT in Chadwick. You'll need to build a Yahoo → MLB ID mapping using name + team + position fuzzy matching, then cache the results.

---

## Data Model

### Core Entities (Shared Data)

```sql
-- The glue for everything. Every external ID maps to one internal player.
CREATE TABLE players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    mlb_id INTEGER UNIQUE,
    yahoo_id_1 INTEGER,          -- Yahoo ID in league 1 (can differ by league)
    yahoo_id_2 INTEGER,          -- Yahoo ID in league 2
    fangraphs_id INTEGER,
    savant_id INTEGER,            -- Usually same as mlb_id
    bref_id TEXT,
    team TEXT,                    -- Current MLB team abbreviation
    position TEXT,                -- Primary position
    bats TEXT,                    -- L/R/S
    throws TEXT,                  -- L/R
    status TEXT DEFAULT 'active', -- active, IL10, IL60, minors, suspended, DFA
    is_prospect INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily stat snapshots (flexible JSONB-style blob)
CREATE TABLE player_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    date TEXT NOT NULL,           -- YYYY-MM-DD
    source TEXT NOT NULL,         -- 'mlb', 'savant', 'fangraphs'
    stat_type TEXT NOT NULL,      -- 'batting', 'pitching', 'fielding', 'savant', 'projections'
    stats TEXT NOT NULL,          -- JSON blob
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, date, source, stat_type)
);

-- MLB schedule
CREATE TABLE games (
    id INTEGER PRIMARY KEY,       -- MLB game PK
    date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    status TEXT DEFAULT 'scheduled', -- scheduled, live, final, postponed
    home_score INTEGER,
    away_score INTEGER,
    venue TEXT,
    park_factor_r REAL,           -- Run-scoring park factor
    game_time TEXT,               -- Scheduled start time (UTC)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Confirmed + projected lineups
CREATE TABLE lineups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    team TEXT NOT NULL,
    player_id INTEGER NOT NULL REFERENCES players(id),
    batting_order INTEGER,        -- 1-9, NULL if bench/unavailable
    is_confirmed INTEGER DEFAULT 0,
    source TEXT DEFAULT 'mlb',    -- 'mlb' for confirmed, 'projected' for early
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, team, player_id)
);

-- Probable starting pitchers
CREATE TABLE probable_pitchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    team TEXT NOT NULL,
    player_id INTEGER NOT NULL REFERENCES players(id),
    is_confirmed INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, team)
);

-- Pitcher appearance log (drives reliever analytics)
CREATE TABLE pitcher_appearances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    game_id INTEGER NOT NULL REFERENCES games(id),
    date TEXT NOT NULL,
    innings_pitched REAL,
    pitches INTEGER,
    earned_runs INTEGER,
    strikeouts INTEGER,
    walks INTEGER,
    hits_allowed INTEGER,
    save INTEGER DEFAULT 0,
    hold INTEGER DEFAULT 0,
    blown_save INTEGER DEFAULT 0,
    entered_inning INTEGER,       -- What inning they entered
    leverage_index_avg REAL,      -- gmLI from MLB API
    inherited_runners INTEGER DEFAULT 0,
    inherited_scored INTEGER DEFAULT 0,
    UNIQUE(player_id, game_id)
);

-- Derived reliever role classifications
CREATE TABLE reliever_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    date TEXT NOT NULL,           -- Date of classification
    role TEXT NOT NULL,           -- 'closer', 'setup', 'middle', 'long', 'mop_up'
    confidence TEXT NOT NULL,     -- 'high', 'medium', 'low'
    role_evidence TEXT,           -- JSON: what data points support this classification
    saves_last_14d INTEGER DEFAULT 0,
    holds_last_14d INTEGER DEFAULT 0,
    appearances_last_7d INTEGER DEFAULT 0,
    avg_leverage_last_14d REAL,
    days_since_last_appearance INTEGER,
    pitches_last_3d INTEGER DEFAULT 0,
    pitches_last_7d INTEGER DEFAULT 0,
    available_tonight INTEGER DEFAULT 1, -- Estimated availability
    UNIQUE(player_id, date)
);

-- MLB transactions (call-ups, IL, trades, DFA)
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mlb_transaction_id INTEGER,
    date TEXT NOT NULL,
    player_id INTEGER REFERENCES players(id),
    player_name TEXT,             -- Fallback if player not yet in players table
    type TEXT NOT NULL,           -- 'call_up', 'option', 'IL', 'IL_return', 'DFA', 'trade', 'release'
    from_team TEXT,
    to_team TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prospect tracking
CREATE TABLE prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    org TEXT NOT NULL,            -- Organization (team abbreviation)
    user_rank INTEGER,            -- User's personal ranking
    fangraphs_rank INTEGER,       -- Imported from FG
    eta TEXT,                     -- Estimated arrival (e.g., '2025', 'Mid 2025')
    level TEXT,                   -- Current level: 'A', 'A+', 'AA', 'AAA'
    scouting_notes TEXT,          -- User-entered notes
    on_40_man INTEGER DEFAULT 0,
    minor_league_stats TEXT,      -- JSON blob from MLB Stats API
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id)
);
```

### User-Scoped Entities

```sql
-- Yahoo account link
CREATE TABLE user_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yahoo_access_token TEXT NOT NULL,
    yahoo_refresh_token TEXT NOT NULL,
    yahoo_token_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User's Yahoo leagues
CREATE TABLE user_leagues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_account_id INTEGER NOT NULL REFERENCES user_accounts(id),
    yahoo_league_key TEXT NOT NULL UNIQUE,
    league_name TEXT,
    format TEXT NOT NULL,         -- 'roto', 'h2h_categories', 'h2h_points'
    scoring_categories TEXT,      -- JSON: list of scoring categories
    roster_slots TEXT,            -- JSON: roster position config
    num_teams INTEGER,
    season INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cached roster (refreshed every 15 min)
CREATE TABLE user_rosters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL REFERENCES user_leagues(id),
    player_id INTEGER REFERENCES players(id),
    yahoo_player_key TEXT,
    roster_position TEXT,         -- The slot they're in (C, 1B, OF, BN, IL, etc.)
    is_editable INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(league_id, player_id)
);

-- Personal watchlist
CREATE TABLE user_watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    league_id INTEGER REFERENCES user_leagues(id), -- NULL = all leagues
    notes TEXT,
    alert_on_lineup INTEGER DEFAULT 0,
    alert_on_callup INTEGER DEFAULT 0,
    alert_on_role_change INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alert log
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER REFERENCES players(id),
    alert_type TEXT NOT NULL,     -- 'lineup', 'callup', 'role_change', 'IL', 'dropped'
    message TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Ingestion Schedule

| Job | Source | Cron / Interval | Details |
|---|---|---|---|
| `sync_schedule` | MLB Stats API | Every 6 hours | Today + next 7 days of games |
| `sync_rosters` | MLB Stats API | Every 30 min | 26-man + 40-man for all 30 teams |
| `sync_transactions` | MLB Stats API | Every 30 min | Call-ups, IL, DFA, trades |
| `sync_probable_pitchers` | MLB Stats API | Every 2 hours | 5-day lookahead |
| `sync_lineups` | MLB Stats API | Every 10 min (starting 3hr before first game) | Batting order from live feed |
| `sync_game_results` | MLB Stats API | Nightly at 2 AM ET | Final box scores, pitcher appearances |
| `sync_savant_stats` | Baseball Savant CSV | Nightly at 3 AM ET | xwOBA, barrel%, sprint speed, etc. |
| `sync_fangraphs_stats` | FanGraphs CSV | Nightly at 3:30 AM ET | Leaderboards, basic/advanced stats |
| `sync_fangraphs_projections` | FanGraphs CSV | Weekly (Sunday night) | Steamer/ZiPS ROS projections |
| `sync_yahoo_rosters` | Yahoo Fantasy API | Every 15 min | User's rosters in both leagues |
| `sync_yahoo_free_agents` | Yahoo Fantasy API | Every 30 min | Waiver wire for both leagues |
| `compute_reliever_roles` | Internal (derived) | Nightly after game results | Role classification algorithm |
| `compute_prospect_signals` | Internal (derived) | Daily | Call-up likelihood scoring |
| `sync_player_crosswalk` | Chadwick Bureau | On deploy + weekly | Player ID mapping refresh |

---

## Key Algorithms

### 1. Reliever Role Inference

**Goal:** Classify every reliever as closer / setup / middle / long / mop_up with a confidence level, and estimate nightly availability.

**Inputs (trailing 14-day window):**
- `pitcher_appearances` table: saves, holds, blown saves, innings, pitches, leverage index, inning entered
- Current team's closer situation (are saves being distributed or concentrated?)

**Classification logic:**
```
FOR each reliever with >= 3 appearances in last 14 days:

  save_rate = saves / save_opportunities (entering 9th with lead of 1-3)
  avg_leverage = mean(leverage_index) over appearances
  avg_inning_entered = mean(entered_inning)
  hold_rate = holds / appearances

  IF save_rate >= 0.60 AND saves >= 2:
      role = 'closer', confidence = 'high'
  ELIF save_rate >= 0.30 AND saves >= 1 AND avg_leverage >= 1.5:
      role = 'closer', confidence = 'medium'  -- committee situation
  ELIF avg_leverage >= 1.3 AND hold_rate >= 0.25:
      role = 'setup', confidence based on consistency
  ELIF avg_leverage >= 0.8 AND avg_inning_entered <= 7:
      role = 'middle'
  ELIF avg_inning_entered <= 6 AND avg IP per appearance >= 1.5:
      role = 'long'
  ELSE:
      role = 'mop_up'
```

**Availability estimation:**
```
available = True
IF days_since_last_appearance == 0:
    available = False (already pitched today)
IF appearances_last_3_days >= 3:
    available = False (likely needs rest)
IF pitches_last_3_days >= 75:
    available = False (high recent workload)
IF pitched_2_consecutive_days AND pitches_last_2_days >= 50:
    available = 'unlikely'
```

**Role change detection:**
Compare today's classification to 7-day-ago classification. If role changed, generate an alert.

### 2. Start/Sit Confidence Scoring

**Goal:** Give each hitter on the user's roster a confidence score for today's game.

**Inputs:**
- Opposing starting pitcher's stats (ERA, FIP, WHIP, K%, handedness)
- Batter's platoon splits (vs LHP / vs RHP)
- Park factor for today's venue
- Batter's recent performance (last 14 days: wRC+, xwOBA)
- Batter's season stats (wRC+, xwOBA)

**Formula (simplified):**
```
matchup_score = (
    0.30 * platoon_advantage_factor     # How much better/worse vs this handedness
  + 0.25 * opposing_pitcher_weakness     # Inverse of pitcher quality (bad pitcher = high score)
  + 0.20 * park_factor_boost             # Coors = boost, Oracle = penalty
  + 0.15 * recent_hot_cold               # Last 14 day wRC+ vs season wRC+
  + 0.10 * season_baseline               # Overall quality (season wRC+)
)

confidence = normalize(matchup_score, 0, 100)
label = 'Strong Start' (>70), 'Start' (50-70), 'Sit if possible' (30-50), 'Bench' (<30)
```

### 3. H2H Matchup Projections

**Goal:** For the user's H2H categories league, project each scoring category for the week and identify which categories are close (targetable or at risk).

**Inputs:**
- User's roster + opponent's roster for the week
- Probable pitcher schedule for both sides
- Player projection data (Steamer/ZiPS ROS rates)
- Number of games each player has this week

**Approach:**
```
FOR each scoring category (R, HR, RBI, SB, AVG, W, K, ERA, WHIP, SV):
  FOR each player on roster:
    projected_games = count of team games this week (minus rest day probability)
    projected_stat = player's per-game rate * projected_games
  
  team_total = sum(projected_stat for all active roster players)

Compare user_total vs opponent_total for each category.

Flag categories where margin < 10% as "swing categories"
Suggest roster moves that could tip swing categories
```

### 4. Prospect Call-Up Likelihood

**Goal:** Score watched prospects on how likely they are to be called up soon.

**Inputs:**
- Prospect's current level and minor league stats
- Parent club roster situation (is there a need at their position? injuries?)
- Service time considerations (Super 2 deadline, option years)
- 40-man roster status
- Recent promotion history (did they just get promoted to AAA?)

**Scoring:**
```
signal_score = (
    0.30 * performance_score      # MiLB stats relative to level (OPS+ or FIP at level)
  + 0.25 * roster_need_score      # Parent club weakness at this position
  + 0.20 * proximity_score        # AAA = high, AA = medium, A = low
  + 0.15 * forty_man_status       # On 40-man = easier to call up
  + 0.10 * service_time_factor    # Past Super 2? More likely.
)
```

### 5. Waiver Wire Scoring

**Goal:** Rank available free agents by pickup value for each of the user's leagues.

**Inputs:**
- Free agent list from Yahoo API
- Player's ROS projections
- Player's recent performance (hot streak detection)
- League scoring format (roto vs H2H categories)
- User's roster needs (which categories need help?)

**For roto:**
```
value = projected_standings_gain_per_category
     (i.e., how much does adding this player move the needle in each roto category?)
```

**For H2H:**
```
value = weekly_impact_score
     (i.e., given this week's matchup, how much does this player help win categories?)
```

---

## Player ID Mapping Strategy

This is the single hardest infrastructure problem. Here's the approach:

### Step 1: Load Chadwick Bureau as Base
Download `people.csv` from the Chadwick repo. This gives you MLB ID ↔ FanGraphs ID ↔ BRef ID ↔ Retrosheet ID for most historical and current players.

### Step 2: Map Savant IDs
Savant uses MLB IDs (`player_id` in their CSV exports = `mlb_id` in Chadwick). This is a freebie.

### Step 3: Map Yahoo IDs (The Hard Part)
Yahoo IDs are proprietary. Strategy:
1. Fetch all players from the Yahoo Fantasy API for the current MLB season
2. Match to internal players table using: `full_name + team + position`
3. Use fuzzy matching (Levenshtein distance) for name discrepancies (e.g., "Giancarlo Stanton" vs "Mike Stanton" historical)
4. Store confirmed mappings in the `players` table
5. Flag unmatched players for manual resolution
6. Re-run mapping weekly to catch new players, call-ups, trades

### Step 4: Ongoing Maintenance
- New players (call-ups, international signings): auto-create on first encounter from any source, then backfill IDs
- Traded players: update team field on transaction sync
- Edge cases: two players with same name on same team — rare but handle with position disambiguation

---

## Frontend Dashboard Modules

### Module 1: Dashboard Home
**URL:** `/`
**Purpose:** Today's snapshot — what do I need to know right now?
**Content:**
- Alert feed (top of page): new call-ups, role changes, lineup surprises
- "My Players Today" panel: every rostered player with game status, opponent, start time
- Quick lineup check: confirmed starters highlighted, bench/day-off flagged
- Pitching matchups for today: my SPs with opponent quality indicator

### Module 2: Roster Manager
**URL:** `/roster`
**Purpose:** Full roster view with context layered in
**Content:**
- All players across both leagues (tabbed by league)
- For each player: season stats, last 14 days, ROS projection, today's matchup
- Start/sit confidence for today
- "Roster holes" indicator: positions where you're below league average
- Quick comparison: click two players to see side-by-side stats

### Module 3: Lineup Tracker
**URL:** `/lineups`
**Purpose:** All 30 team lineups with fantasy relevance
**Content:**
- Grid of all games today, each showing confirmed/projected lineup
- Color coding: green = my player, blue = watchlist, yellow = waiver wire target
- Click any player for popup with stats, ownership %, recent performance
- Filter: "Show only games with my players"

### Module 4: Pitching Planner
**URL:** `/pitching`
**Purpose:** Weekly SP schedule + streaming targets
**Content:**
- Calendar grid (Mon-Sun) showing my SPs and their matchups
- Each cell: opponent, park, opponent wRC+ vs handedness, pitcher's recent starts
- Two-start pitchers highlighted
- Streaming candidates panel: best available free agent SPs by matchup quality
- Season IP tracker for leagues with innings limits

### Module 5: Bullpen Monitor
**URL:** `/bullpen`
**Purpose:** Reliever usage tracking and role classification
**Content:**
- All closers/setup men with role, confidence tier, availability status
- Usage heatmap: last 14 days showing when each reliever pitched
- Workload bars: pitches last 3/7 days
- Role change log: recent changes with evidence
- "Available tonight" list filtered to my rostered relievers + watchlist
- Filter by team, role, availability

### Module 6: Prospect Board
**URL:** `/prospects`
**Purpose:** Track watched prospects with call-up signals
**Content:**
- Ranked list (user-configurable order, default = imported FanGraphs ranking)
- For each: current level, minor league stats, 40-man status, ETA
- Call-up likelihood signal (red/yellow/green)
- Parent club context: "Org has need at SS" or "Blocked by established starter"
- Transactions feed filtered to prospect-relevant moves
- Quick add to watchlist / waiver claim queue

### Module 7: Matchup Analyzer (H2H League)
**URL:** `/matchup`
**Purpose:** Weekly H2H category projections
**Content:**
- Side-by-side: my team vs opponent for the week
- Per-category projection bars showing expected outcome
- "Swing categories" highlighted with suggested moves to tip them
- Opponent's probable pitchers for the week
- Historical matchup record vs this opponent

### Module 8: Waiver Wire
**URL:** `/waivers`
**Purpose:** Smart free agent discovery
**Content:**
- Tabbed by league (roto and H2H have different optimal pickups)
- Sortable by: ROS projection, last 14 day performance, ownership trend, pickup value score
- Filters: position, team, stat thresholds
- "Hot adds" feed: players with surging add rates across Yahoo
- Prospect stash candidates (minor leaguers worth IL stashing)
- Drop candidates: my worst players ranked by replaceability

---

## Alerts System

**Types:**
- `lineup_posted` — A player on my roster or watchlist has their lineup confirmed
- `unexpected_bench` — A regular starter is not in today's lineup
- `callup` — A watched prospect has been called up
- `role_change` — A reliever's role classification changed
- `il_move` — A player moved to/from the IL
- `dropped_in_league` — A player on my watchlist was dropped by another team
- `hot_streak` — A waiver wire player has exceeded a stat threshold over the last 7 days

**Delivery (start simple):**
- In-app notification feed on the dashboard home page
- Optional: webhook to Discord/Slack for push notifications (future enhancement)

**Configuration:**
- Per-player alert preferences on the watchlist
- Global toggles for each alert type
- Quiet hours setting

---

## Configuration & Environment Variables

```env
# Yahoo OAuth2
YAHOO_CLIENT_ID=your_client_id
YAHOO_CLIENT_SECRET=your_client_secret
YAHOO_REDIRECT_URI=http://localhost:3000/auth/yahoo/callback

# Database
DATABASE_URL=sqlite:///./data/fantasy_dashboard.db

# Scheduling
LINEUP_CHECK_START_HOUR=14        # Start checking lineups at 2 PM ET
LINEUP_CHECK_END_HOUR=23          # Stop at 11 PM ET
LINEUP_CHECK_INTERVAL_MINUTES=10
STATS_SYNC_HOUR=3                 # Nightly stats sync at 3 AM ET
TIMEZONE=America/New_York

# External Data
MLB_STATS_API_BASE=https://statsapi.mlb.com/api/v1
SAVANT_BASE_URL=https://baseballsavant.mlb.com
FANGRAPHS_BASE_URL=https://www.fangraphs.com

# Feature Flags
ENABLE_ALERTS=true
ENABLE_PROSPECT_TRACKING=true
```

---

## Distribution Safety Checklist

If this tool is ever shared publicly:

1. **MLB Stats API data** (stats, rosters, schedules, transactions) — Factual data, safe to display. MLB tolerates community API usage.
2. **Yahoo Fantasy API** — Each user authenticates with their own account. You're a client, not a data intermediary. Follow Yahoo developer ToS.
3. **Baseball Savant data** — Fetch per-user session, cache briefly (<24 hours), attribute "Data from Baseball Savant / Statcast."
4. **FanGraphs data** — Fetch per-user session, cache briefly, attribute "Data from FanGraphs." Do not store and serve their content as your own. Prospect rankings should be user-imported CSV, not auto-scraped.
5. **Derived analytics** (reliever roles, start/sit scores, matchup projections, prospect signals) — This is YOUR intellectual property. Built on your logic, using factual inputs. Fully safe.
6. **Never charge** for a version that relies on scraped data without licensing agreements.
7. **Attribution** — Display data source attribution on every page that shows third-party data.

---

## Known Gotchas & Edge Cases

- **Player name collisions:** Two "Will Smith"s have existed simultaneously in MLB. Always match on name + team + position, never name alone.
- **Mid-season trades:** A player's team changes. The crosswalk and roster sync must handle this gracefully. Watch the transactions feed.
- **Doubleheaders:** Two games in one day for the same team. Lineup and pitching data must handle game 1 vs game 2.
- **Postponements / Suspensions:** Games can be postponed or suspended and resumed later. Game status tracking must be robust.
- **Yahoo API quirks:** Player keys can change across seasons. League keys change every year. Build abstractions that handle this.
- **Two-way players (Ohtani rule):** Players who hit and pitch appear in both batting and pitching contexts. Your data model needs to handle dual-position players cleanly.
- **Opener games:** A "starting pitcher" may only pitch 1-2 innings before a "bulk reliever" takes over. The SP planner should flag known opener situations.
- **Service time manipulation:** Teams may delay call-ups for service time reasons. This is an important factor for prospect signal scoring but is hard to quantify algorithmically.

---

# Implementation Roadmap

> **Progress Summary (last updated: 2026-02-22)**
>
> | Phase | Status | Tasks Done |
> |---|---|---|
> | Phase 1 — Foundation | ✅ Complete | 6/6 |
> | Phase 2 — Yahoo Integration | ✅ Complete | 5/5 |
> | Phase 3 — Core Modules | ✅ Complete | 4/4 |
> | Phase 4 — Smart Features | ✅ Complete | 4/4 |
> | Phase 5 — Polish | 🔲 Not started | 0/4 |
>
> **Key files created in Phase 1:**
> - `backend/main.py` — FastAPI app + APScheduler integration
> - `backend/config.py` — Pydantic settings from `.env`
> - `backend/database/models.py` — All 14 SQLAlchemy ORM models
> - `backend/database/connection.py` — Async engine + session factory
> - `backend/ingestion/mlb_stats.py` — MLB Stats API client (5 methods)
> - `backend/ingestion/player_id_crosswalk.py` — Chadwick Bureau CSV → players table
> - `backend/ingestion/savant.py` — Baseball Savant CSV fetcher
> - `backend/ingestion/fangraphs.py` — FanGraphs CSV fetcher + projections
> - `backend/ingestion/scheduler.py` — APScheduler job definitions
> - `backend/api/routes/dashboard.py` — `GET /api/today` endpoint
> - `frontend/src/app/page.tsx` — Dashboard home with game cards
> - `frontend/src/lib/api.ts` — Backend API client + TypeScript types
> - `shared/constants.py` — Team abbreviations, positions, enums
>
> **Key files created in Phase 2:**
> - `backend/yahoo/auth.py` — OAuth2 flow (authorization + token refresh)
> - `backend/yahoo/client.py` — Yahoo Fantasy API wrapper (leagues, rosters, free agents, matchups)
> - `backend/yahoo/sync.py` — Roster/league sync logic with player ID mapping
> - `backend/api/routes/auth.py` — OAuth endpoints (`/auth/yahoo`, `/auth/yahoo/callback`, `/auth/yahoo/status`)
> - `backend/api/routes/roster.py` — League + roster endpoints (`/api/leagues`, `/api/roster/{league_id}`)
> - `frontend/src/app/roster/page.tsx` — Roster view with league tabs, stats, game info
>
> **Key files created in Phase 3:**
> - `backend/api/routes/lineups.py` — Lineup tracker endpoint (`/api/lineups/today`)
> - `backend/api/routes/pitching.py` — Pitching planner endpoints (`/api/pitching/week`, `/api/pitching/streamers`)
> - `backend/api/routes/bullpen.py` — Bullpen monitor endpoint (`/api/bullpen`)
> - `backend/api/routes/waivers.py` — Waiver wire endpoint (`/api/waivers/{league_id}`)
> - `backend/analytics/reliever_roles.py` — Reliever role inference engine
> - `frontend/src/app/lineups/page.tsx` — Lineup tracker with fantasy relevance annotations
> - `frontend/src/app/pitching/page.tsx` — SP calendar + streaming candidates
> - `frontend/src/app/bullpen/page.tsx` — Reliever roles, usage heatmap, availability
> - `frontend/src/app/waivers/page.tsx` — Scored free agents with position filters
>
> **Key files created in Phase 4:**
> - `backend/analytics/start_sit.py` — Start/sit confidence scoring (platoon, pitcher, park, form, baseline)
> - `backend/analytics/matchup.py` — H2H matchup projection engine (batting + pitching categories)
> - `backend/analytics/prospect_signals.py` — Call-up likelihood scoring (Hot/Warm/Cold)
> - `backend/analytics/alerts.py` — Alert generation (call-ups, IL moves, role changes)
> - `backend/api/routes/matchup.py` — Matchup projection endpoint (`/api/matchup/{league_id}`)
> - `backend/api/routes/prospects.py` — Prospect CRUD + CSV import endpoints
> - `backend/api/routes/alerts.py` — Alert feed + read/mark-all endpoints
> - `frontend/src/app/matchup/page.tsx` — Side-by-side category projections
> - `frontend/src/app/prospects/page.tsx` — Prospect watchlist with signal indicators
>
> **Next up:** Phase 5, Task 5.1 — Dashboard home refinement

## Phase 1 — Foundation (Get Data Flowing) ✅ COMPLETE

### Task 1.1: Project Scaffolding ✅
- ~~Initialize monorepo with `backend/` (FastAPI) and `frontend/` (Next.js)~~
- ~~Set up Python virtualenv, `pyproject.toml` or `requirements.txt`~~
- ~~Set up Next.js with TypeScript, Tailwind CSS~~
- ~~Create SQLite database with SQLAlchemy models from the schema above~~
- ~~Create Makefile with common commands: `make backend`, `make frontend`, `make db-init`~~
- ~~`.env.example` with all required environment variables~~
- **Status:** FastAPI starts on :8000, Next.js on :3000, all 14 database tables created on startup. Python deps managed via `uv` (venv at `.venv/`).

### Task 1.2: Player ID Crosswalk ✅
- ~~Download Chadwick Bureau `people.csv` and store in `data/chadwick/`~~
- ~~Write `player_id_crosswalk.py` that parses Chadwick CSV and populates the `players` table~~
- ~~Map: mlb_id, fangraphs_id, bref_id, full_name, position, bats, throws~~
- ~~Filter to active MLB players + top prospects (filter by last year played >= 2023)~~
- ~~Create a CLI command: `python -m backend.ingestion.player_id_crosswalk`~~
- **Status:** Script downloads Chadwick CSV, filters to active players, upserts in batches of 500 with ON CONFLICT logic.

### Task 1.3: MLB Stats API Integration ✅
- ~~Create `mlb_stats.py` client with methods for:~~
  - ~~`fetch_schedule(start_date, end_date)` → populates `games` table~~
  - ~~`fetch_rosters()` → updates player status (active/IL/minors) in `players` table~~
  - ~~`fetch_probable_pitchers(start_date, end_date)` → populates `probable_pitchers` table~~
  - ~~`fetch_transactions(start_date, end_date)` → populates `transactions` table~~
  - ~~`fetch_game_results(game_id)` → populates pitcher_appearances from box score data~~
- ~~Each method should be idempotent (safe to re-run, uses upsert logic)~~
- ~~Create CLI commands for each: `python -m backend.ingestion.mlb_stats --action=schedule`~~
- **Status:** All five methods work with SQLite upserts. Verified live: fetched 125 spring training games and 90 probable pitchers on first run. CLI supports `--action`, `--start-date`, `--end-date`, `--game-id`.

### Task 1.4: Nightly Stats Ingestion ✅
- ~~Create `savant.py` that fetches Statcast leaderboards (batting + pitching) via CSV export URL~~
- ~~Create `fangraphs.py` that fetches leaderboards via CSV export URL~~
- ~~Both store results in `player_stats` table as JSON blobs, keyed by player_id + date + source~~
- ~~Map external IDs to internal player_id using the crosswalk~~
- ~~Log unmatched players for review~~
- **Status:** Both fetchers store JSON blobs in `player_stats`. FanGraphs also supports ROS projection fetching. Configurable CSV URLs for when Savant/FG change params.

### Task 1.5: APScheduler Setup ✅
- ~~Integrate APScheduler into `main.py` (BackgroundScheduler)~~
- ~~Define all jobs from the Ingestion Schedule table above~~
- ~~Jobs should log start/end/duration and handle exceptions gracefully (one failed job shouldn't kill others)~~
- ~~Startup trigger: run critical jobs on app start (schedule, rosters, probable pitchers) so the dashboard isn't empty on first launch~~
- **Status:** AsyncIOScheduler integrated into FastAPI lifespan. 7 jobs defined (schedule/rosters/pitchers/transactions/savant/fangraphs/projections). Startup runs schedule + probable pitchers + rosters as background task.

### Task 1.6: Basic Frontend Shell ✅
- ~~Create a minimal dashboard page at `/` that calls the backend API~~
- ~~Backend endpoint: `GET /api/today` — returns today's games with probable pitchers~~
- ~~Display as a simple table/list: game time, teams, probable pitchers, game status~~
- ~~Prove the full pipeline works: scheduler → SQLite → FastAPI → Next.js → browser~~
- **Status:** Dashboard home renders game cards with team names, probable pitchers, game times, and venue. Full pipeline verified: scheduler → SQLite → FastAPI → Next.js → browser.

---

## Phase 2 — Yahoo Integration (Make It Personal) ✅ COMPLETE

### Task 2.1: Yahoo OAuth2 Flow ✅
- ~~Register an app at Yahoo Developer portal~~
- ~~Implement OAuth2 authorization code flow in `yahoo/auth.py`~~
- ~~Endpoints: `GET /auth/yahoo` (redirect to Yahoo), `GET /auth/yahoo/callback` (exchange code for token)~~
- ~~Store access token + refresh token in `user_accounts` table (encrypted)~~
- ~~Implement token refresh logic (Yahoo tokens expire in 1 hour)~~
- **Status:** OAuth2 flow implemented with authorization redirect, callback token exchange, and status check endpoint. Tokens stored in `user_accounts` table.

### Task 2.2: Yahoo Fantasy API Client ✅
- ~~Create `yahoo/client.py` with methods:~~
  - ~~`get_leagues()` → list user's MLB leagues~~
  - ~~`get_league_settings(league_key)` → scoring categories, roster config~~
  - ~~`get_roster(team_key)` → current roster~~
  - ~~`get_free_agents(league_key, position=None)` → waiver wire~~
  - ~~`get_matchup(team_key)` → current H2H matchup (if applicable)~~
- ~~All methods use the stored OAuth token and handle refresh automatically~~
- **Status:** Full Yahoo Fantasy API client with automatic token refresh. All methods operational.

### Task 2.3: Yahoo → Internal Player ID Mapping ✅
- ~~When syncing a Yahoo roster, map each Yahoo player to internal `players` table~~
- ~~Strategy: match on name (fuzzy) + team + position~~
- ~~Store yahoo_id in `players` table (separate fields for each league if IDs differ)~~
- ~~Log unmatched players for manual resolution~~
- ~~Create a small admin endpoint to manually link unmatched players~~
- **Status:** Player ID mapping via name + team + position matching integrated into roster sync.

### Task 2.4: League Setup + Roster Sync ✅
- ~~On first connection, populate `user_leagues` for both leagues with settings~~
- ~~Create recurring job (every 15 min) to sync rosters to `user_rosters` table~~
- ~~Store scoring categories so analytics engine knows what matters per league~~
- **Status:** League settings and rosters sync on OAuth callback and on recurring schedule.

### Task 2.5: "My Roster" Dashboard View ✅
- ~~Frontend page at `/roster` with tabs for each league~~
- ~~For each player: name, team, position, today's game status, opponent, key stats~~
- ~~Pull from backend: `GET /api/roster/{league_id}` — joins user_rosters with players, games, lineups, player_stats~~
- **Status:** Roster page with league tabs, player stats, game info, and opponent details.

---

## Phase 3 — Core Modules ✅ COMPLETE

### Task 3.1: Lineup Tracker ✅
- ~~Backend: `GET /api/lineups/today` — all games with lineup data, annotated with "my player" / "watchlist" / "free agent" flags~~
- ~~Frontend page at `/lineups`: grid of today's games, each expandable to show batting order~~
- ~~Color-coded player names by fantasy relevance~~
- ~~Auto-refresh every 2 minutes when lineups are being posted (typically 2-5 PM ET)~~
- **Status:** Lineup tracker with fantasy relevance annotations (roster/watchlist markers) and batting order display.

### Task 3.2: Pitching Planner ✅
- ~~Backend: `GET /api/pitching/week` — my SPs mapped to their starts this week with matchup context~~
- ~~Include: opponent, park factor, opponent team wRC+, pitcher's last 3 starts~~
- ~~Identify two-start pitchers~~
- ~~Backend: `GET /api/pitching/streamers` — best available SP free agents this week by matchup quality~~
- ~~Frontend page at `/pitching`: calendar grid view~~
- **Status:** SP calendar with two-start pitcher detection, matchup context, and streaming candidate recommendations.

### Task 3.3: Reliever Usage Tracking ✅
- ~~Ensure `pitcher_appearances` table is populated nightly from box score data (task 1.3)~~
- ~~Implement `reliever_roles.py` using the algorithm described in Key Algorithms section~~
- ~~Backend: `GET /api/bullpen` — all classified relievers with usage data and availability~~
- ~~Frontend page at `/bullpen`: filterable table with role badges, usage heatmap, availability indicator~~
- **Status:** Reliever role inference engine classifies closer/setup/middle/long/mop_up with confidence. Bullpen page shows 14-day usage heatmap, availability, and filters by team/role.

### Task 3.4: Waiver Wire Intelligence ✅
- ~~Backend: `GET /api/waivers/{league_id}` — scored and ranked free agents~~
- ~~Score using the waiver wire algorithm (different for roto vs H2H)~~
- ~~Include: ROS projection, last 14 day stats, ownership %, add/drop trend~~
- ~~Frontend page at `/waivers`: sortable/filterable table with league tabs~~
- **Status:** Free agents scored and ranked per league with position filtering.

---

## Phase 4 — Smart Features ✅ COMPLETE

### Task 4.1: Start/Sit Recommendations ✅
- ~~Implement `start_sit.py` using the algorithm described above~~
- ~~Add confidence scores to the roster view for each hitter~~
- ~~Backend: extend `GET /api/roster/{league_id}` to include start_sit_score~~
- ~~Frontend: add confidence badge/bar to each player row on roster page~~
- **Status:** Multi-factor confidence scoring (platoon advantage 30%, pitcher weakness 25%, park factor 20%, recent form 15%, season baseline 10%). Labels: Strong Start (>70), Start (50-70), Sit if possible (30-50), Bench (<30). Integrated into roster view.

### Task 4.2: Matchup Projections (H2H League) ✅
- ~~Implement `matchup.py` projection engine~~
- ~~Backend: `GET /api/matchup/{league_id}` — projected category outcomes vs opponent~~
- ~~Frontend page at `/matchup`: side-by-side visualization, swing categories highlighted~~
- **Status:** Projects batting (R, HR, RBI, SB, AVG, OBP, OPS) and pitching (W, K, ERA, WHIP, SV) categories using per-game rates and weekly game counts. Frontend shows side-by-side projections with player contribution breakdown.

### Task 4.3: Prospect Watchlist ✅
- ~~Allow user to import FanGraphs prospect rankings via CSV upload~~
- ~~Backend: CRUD endpoints for prospect watchlist~~
- ~~Implement `prospect_signals.py` for call-up likelihood scoring~~
- ~~Pull minor league stats from MLB Stats API (it has MiLB data)~~
- ~~Frontend page at `/prospects`: ranked list with signal indicators~~
- **Status:** Full CRUD + CSV import for prospect watchlist. Call-up likelihood scored as Hot (70+), Warm (40-69), Cold (<40) based on performance (30%), roster need (25%), proximity (20%), 40-man status (15%), service time (10%). Signal factor breakdown displayed in UI.

### Task 4.4: Alerts System ✅
- ~~Create alert generation logic that runs after each data sync~~
- ~~Store alerts in `alerts` table~~
- ~~Backend: `GET /api/alerts` — unread alerts, `POST /api/alerts/{id}/read`~~
- ~~Frontend: alert feed on dashboard home, notification badge in nav~~
- **Status:** Alert generation for call-ups, IL moves, and reliever role changes. Endpoints for fetching alerts (with unread filter), marking individual alerts read, and mark-all-read. Alert feed integrated into dashboard home page.

---

## Phase 5 — Polish 🔲 TODO

### Task 5.1: Dashboard Home Refinement 🔲
- Aggregate the most important info from all modules into the home view
- Today's alerts, my players' game times, key pitching matchups, bullpen availability
- Design for "glance and go" — the user should know what matters in 10 seconds

### Task 5.2: Mobile Responsive Views 🔲
- Ensure all pages render well on mobile
- Priority: dashboard home, roster, lineups (these are checked on-the-go)
- Lower priority for mobile: pitching planner, matchup analyzer (desktop workflows)

### Task 5.3: Error Handling & Resilience 🔲
- Graceful handling of API failures (MLB API down, Yahoo token expired, Savant CSV format changed)
- Retry logic with exponential backoff for transient failures
- Clear UI indicators when data is stale ("Last updated: 2 hours ago — MLB API unreachable")
- Dead letter queue for failed sync jobs (log and move on, don't block other jobs)

### Task 5.4: Multi-User Prep (Optional) 🔲
- If distributing: add user_id scoping to all user tables
- Swap SQLite → Postgres
- Add proper session management, CORS config, rate limiting
- Document deployment steps for others
