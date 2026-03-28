"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";

interface LineupPlayer {
  player_id: number;
  full_name: string;
  position: string | null;
  batting_order: number | null;
  is_confirmed: boolean;
  relevance: "roster" | "watchlist" | "other";
}

interface PitcherInfo {
  name: string;
  mlb_id: number;
  player_id: number;
  team: string;
  is_confirmed: boolean;
  relevance: "roster" | "watchlist" | "other";
}

interface TeamLineup {
  lineup: LineupPlayer[];
  has_my_player: boolean;
}

interface LineupGame {
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
    home: PitcherInfo | null;
    away: PitcherInfo | null;
  };
  teams: Record<string, TeamLineup>;
  has_my_player: boolean;
}

interface LineupsResponse {
  date: string;
  games: LineupGame[];
}

const relevanceColor: Record<string, string> = {
  roster: "text-green-600 dark:text-green-400 font-semibold",
  watchlist: "text-blue-600 dark:text-blue-400",
  other: "text-zinc-700 dark:text-zinc-300",
};

const relevanceBg: Record<string, string> = {
  roster: "bg-green-500",
  watchlist: "bg-blue-500",
  other: "bg-zinc-400 dark:bg-zinc-600",
};

function LineupList({ team, data }: { team: string; data: TeamLineup }) {
  if (data.lineup.length === 0) {
    return (
      <div className="text-xs text-zinc-400 dark:text-zinc-500 italic py-1">
        Lineup not posted
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {data.lineup.map((p, i) => (
        <div key={p.player_id} className="flex items-center gap-2 text-sm">
          <span className="w-4 text-right text-xs text-zinc-400 font-mono">
            {p.batting_order ?? "—"}
          </span>
          <span
            className={`h-1.5 w-1.5 rounded-full ${relevanceBg[p.relevance]}`}
          />
          <span className={relevanceColor[p.relevance]}>
            {p.full_name}
          </span>
          {p.position && (
            <span className="text-xs text-zinc-400 dark:text-zinc-500">
              {p.position}
            </span>
          )}
          {!p.is_confirmed && (
            <span className="text-[10px] text-amber-500">proj</span>
          )}
        </div>
      ))}
    </div>
  );
}

function GameLineupCard({ game }: { game: LineupGame }) {
  const [expanded, setExpanded] = useState(game.has_my_player);
  const awayPP = game.probable_pitchers.away;
  const homePP = game.probable_pitchers.home;

  const borderColor = game.has_my_player
    ? "border-green-300 dark:border-green-800"
    : "border-zinc-200 dark:border-zinc-800";

  return (
    <div
      className={`rounded-lg border ${borderColor} bg-white shadow-sm dark:bg-zinc-900`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 text-left"
      >
        <div className="mb-2 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
          <span>{game.venue}</span>
          <div className="flex items-center gap-2">
            {game.has_my_player && (
              <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-950 dark:text-green-300">
                MY PLAYER
              </span>
            )}
            <span className="rounded bg-zinc-100 px-2 py-0.5 font-medium dark:bg-zinc-800">
              {game.status}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
          <div className="text-right">
            <div className="text-lg font-bold">{game.away_team}</div>
            <div className="text-sm text-zinc-500 dark:text-zinc-400">
              <span className={awayPP ? relevanceColor[awayPP.relevance] : ""}>
                {awayPP?.name ?? "TBD"}
              </span>
            </div>
          </div>
          <div className="px-3 text-center text-xs font-medium text-zinc-400">
            {game.game_time
              ? new Date(game.game_time).toLocaleTimeString([], {
                  hour: "numeric",
                  minute: "2-digit",
                })
              : "@"}
          </div>
          <div className="text-left">
            <div className="text-lg font-bold">{game.home_team}</div>
            <div className="text-sm text-zinc-500 dark:text-zinc-400">
              <span className={homePP ? relevanceColor[homePP.relevance] : ""}>
                {homePP?.name ?? "TBD"}
              </span>
            </div>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-zinc-100 px-4 pb-4 pt-3 dark:border-zinc-800">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="mb-2 text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">
                {game.away_team}
              </h4>
              <LineupList
                team={game.away_team}
                data={game.teams[game.away_team] ?? { lineup: [], has_my_player: false }}
              />
            </div>
            <div>
              <h4 className="mb-2 text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">
                {game.home_team}
              </h4>
              <LineupList
                team={game.home_team}
                data={game.teams[game.home_team] ?? { lineup: [], has_my_player: false }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function LineupsPage() {
  const [data, setData] = useState<LineupsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filterMine, setFilterMine] = useState(false);

  useEffect(() => {
    fetchApi<LineupsResponse>("/api/lineups/today")
      .then(setData)
      .catch((e) => setError(e.message));

    // Auto-refresh every 2 minutes
    const interval = setInterval(() => {
      fetchApi<LineupsResponse>("/api/lineups/today")
        .then(setData)
        .catch(() => {});
    }, 120_000);
    return () => clearInterval(interval);
  }, []);

  const games = data?.games ?? [];
  const filtered = filterMine ? games.filter((g) => g.has_my_player) : games;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-2xl font-bold tracking-tight hover:opacity-80"
            >
              Ripken
            </Link>
            <span className="text-sm text-zinc-400 dark:text-zinc-500">/</span>
            <span className="text-sm font-medium">Lineups</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/roster" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Roster</Link>
            <Link href="/league" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">League</Link>
            <Link href="/waivers" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Waivers</Link>
            <Link href="/team-analysis" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Analysis</Link>
            <Link href="/bullpen" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Bullpen</Link>
            <Link href="/lineups" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Lineups</Link>
            <Link href="/pitching" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Pitching</Link>
            <Link href="/matchup" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Matchup</Link>
            <Link href="/prospects" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Prospects</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-xl font-semibold">
            Today&apos;s Lineups{" "}
            {data && (
              <span className="text-base font-normal text-zinc-500 dark:text-zinc-400">
                {data.date}
              </span>
            )}
          </h2>
          <button
            onClick={() => setFilterMine(!filterMine)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              filterMine
                ? "bg-green-600 text-white"
                : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
            }`}
          >
            {filterMine ? "Showing My Games" : "Show All Games"}
          </button>
        </div>

        {/* Legend */}
        <div className="mb-4 flex gap-4 text-xs text-zinc-500 dark:text-zinc-400">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-green-500" /> My Player
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-blue-500" /> Watchlist
          </span>
        </div>

        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}
        {!data && !error && (
          <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>
        )}
        {data && filtered.length === 0 && (
          <p className="text-zinc-500 dark:text-zinc-400">
            {filterMine ? "None of your players have games today." : "No games scheduled today."}
          </p>
        )}
        {filtered.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            {filtered.map((game) => (
              <GameLineupCard key={game.game_id} game={game} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
