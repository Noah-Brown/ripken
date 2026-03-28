"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchApi,
  type LeagueInfo,
  type LeaguesResponse,
} from "@/lib/api";

interface CategoryProjection {
  category: string;
  my_projected: number;
  is_counting: boolean;
  lower_is_better: boolean;
}

interface PlayerProjection {
  player_id: number;
  full_name: string;
  team: string | null;
  position: string | null;
  roster_position: string;
  games_this_week: number;
  is_pitcher: boolean;
  projected_stats: Record<string, number>;
}

interface MatchupResponse {
  league_id: number;
  league_name: string;
  week_start: string;
  week_end: string;
  categories: CategoryProjection[];
  players: PlayerProjection[];
  team_games_this_week: Record<string, number>;
  error?: string;
}

function CategoryBar({ cat }: { cat: CategoryProjection }) {
  const val = cat.my_projected;
  const display = cat.is_counting ? val.toFixed(1) : val.toFixed(3);

  return (
    <div className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
      <div>
        <span className="text-sm font-semibold">{cat.category}</span>
        {cat.lower_is_better && (
          <span className="ml-1 text-[10px] text-zinc-400">(lower = better)</span>
        )}
      </div>
      <span className="text-lg font-bold font-mono">{display}</span>
    </div>
  );
}

function PlayerContributionRow({ player }: { player: PlayerProjection }) {
  const stats = player.projected_stats;
  const statEntries = Object.entries(stats);

  return (
    <tr className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50">
      <td className="px-3 py-2 font-mono text-xs text-zinc-400">
        {player.roster_position}
      </td>
      <td className="px-3 py-2">
        <span className="font-medium">{player.full_name}</span>
        {player.position && (
          <span className="ml-1.5 text-xs text-zinc-400">{player.position}</span>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-500">{player.team}</td>
      <td className="px-3 py-2 text-center text-xs">{player.games_this_week}</td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-2">
          {statEntries.map(([key, val]) => (
            <span key={key} className="text-xs text-zinc-500 dark:text-zinc-400">
              {key}{" "}
              <span className="font-mono font-medium text-zinc-700 dark:text-zinc-300">
                {typeof val === "number" && val < 1 && val > 0
                  ? val.toFixed(3)
                  : typeof val === "number"
                    ? val.toFixed(1)
                    : val}
              </span>
            </span>
          ))}
        </div>
      </td>
    </tr>
  );
}

export default function MatchupPage() {
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [activeLeague, setActiveLeague] = useState<number | null>(null);
  const [data, setData] = useState<MatchupResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchApi<LeaguesResponse>("/api/leagues")
      .then((res) => {
        setLeagues(res.leagues);
        if (res.leagues.length > 0) {
          setActiveLeague(res.leagues[0].id);
        }
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (activeLeague === null) return;
    setLoading(true);
    fetchApi<MatchupResponse>(`/api/matchup/${activeLeague}`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [activeLeague]);

  const battingCats = data?.categories.filter((c) =>
    ["R", "HR", "RBI", "SB", "AVG", "OBP", "OPS"].includes(c.category)
  ) ?? [];
  const pitchingCats = data?.categories.filter((c) =>
    ["W", "K", "ERA", "WHIP", "SV"].includes(c.category)
  ) ?? [];

  const hitters = data?.players.filter((p) => !p.is_pitcher) ?? [];
  const pitchers = data?.players.filter((p) => p.is_pitcher) ?? [];

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-2xl font-bold tracking-tight hover:opacity-80">Ripken</Link>
            <span className="text-sm text-zinc-400 dark:text-zinc-500">/</span>
            <span className="text-sm font-medium">Matchup Analyzer</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/roster" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Roster</Link>
            <Link href="/league" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">League</Link>
            <Link href="/waivers" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Waivers</Link>
            <Link href="/bullpen" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Bullpen</Link>
            <Link href="/lineups" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Lineups</Link>
            <Link href="/pitching" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Pitching</Link>
            <Link href="/matchup" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Matchup</Link>
            <Link href="/prospects" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Prospects</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>
        )}

        {/* League tabs */}
        {leagues.length > 1 && (
          <div className="mb-6 flex gap-2">
            {leagues.map((lg) => (
              <button
                key={lg.id}
                onClick={() => setActiveLeague(lg.id)}
                className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                  activeLeague === lg.id
                    ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                }`}
              >
                {lg.name}
              </button>
            ))}
          </div>
        )}

        {loading && <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>}

        {!loading && data && (
          <>
            <div className="mb-2 text-sm text-zinc-500 dark:text-zinc-400">
              Week: {data.week_start} — {data.week_end}
            </div>

            {/* Category Projections */}
            <h2 className="mb-4 text-xl font-semibold">Projected Categories</h2>
            <div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="sm:col-span-2 lg:col-span-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  Batting
                </h3>
              </div>
              {battingCats.map((c) => (
                <CategoryBar key={c.category} cat={c} />
              ))}
            </div>
            <div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="sm:col-span-2 lg:col-span-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  Pitching
                </h3>
              </div>
              {pitchingCats.map((c) => (
                <CategoryBar key={c.category} cat={c} />
              ))}
            </div>

            {/* Player Contributions */}
            <h2 className="mb-4 text-xl font-semibold">Player Contributions</h2>

            {hitters.length > 0 && (
              <div className="mb-6">
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  Hitters
                </h3>
                <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                        <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-12">Pos</th>
                        <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Player</th>
                        <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-12">Team</th>
                        <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 w-12">GP</th>
                        <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Projected</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-zinc-900">
                      {hitters.map((p) => (
                        <PlayerContributionRow key={p.player_id} player={p} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {pitchers.length > 0 && (
              <div className="mb-6">
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  Pitchers
                </h3>
                <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                        <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-12">Pos</th>
                        <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Player</th>
                        <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-12">Team</th>
                        <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 w-12">GP</th>
                        <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Projected</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-zinc-900">
                      {pitchers.map((p) => (
                        <PlayerContributionRow key={p.player_id} player={p} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}

        {!loading && leagues.length === 0 && (
          <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center dark:border-zinc-800 dark:bg-zinc-900">
            <p className="mb-2 text-lg font-medium">No leagues connected</p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Connect your Yahoo account to see matchup projections.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
