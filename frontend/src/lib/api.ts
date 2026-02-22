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
