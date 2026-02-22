const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export interface ProbablePitcherInfo {
  name: string;
  mlb_id: number;
  team: string;
  is_confirmed: boolean;
}

export interface GameInfo {
  game_id: number;
  date: string;
  game_time: string | null;
  home_team: string;
  away_team: string;
  status: string;
  home_score: number | null;
  away_score: number | null;
  venue: string | null;
  probable_pitchers: {
    home: ProbablePitcherInfo | null;
    away: ProbablePitcherInfo | null;
  };
}

export interface TodayResponse {
  date: string;
  games: GameInfo[];
}

// --- Roster / League types ---

export interface LeagueInfo {
  id: number;
  yahoo_league_key: string;
  name: string;
  format: string;
  num_teams: number | null;
  season: number | null;
}

export interface LeaguesResponse {
  leagues: LeagueInfo[];
}

export interface TodayGameInfo {
  game_id: number;
  opponent: string;
  home_away: "home" | "away";
  game_time: string | null;
  status: string;
  venue: string | null;
}

export interface RosterPlayer {
  id: number;
  full_name: string;
  team: string | null;
  position: string | null;
  status: string | null;
}

export interface RosterEntry {
  roster_position: string;
  yahoo_player_key: string | null;
  player: RosterPlayer | null;
  today_game: TodayGameInfo | null;
  stats: {
    date: string;
    stat_type: string;
    stats: string;
  } | null;
}

export interface RosterResponse {
  league_id: number;
  date: string;
  roster: RosterEntry[];
}
