"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchApi,
  type LeagueInfo,
  type LeaguesResponse,
  type LineupStatus,
  type RosterEntry,
  type RosterResponse,
  type StartSitScore,
} from "@/lib/api";

const IL_POSITIONS = new Set(["IL", "IL+", "IL10", "IL15", "IL60", "DL", "NA"]);
const BENCH_POSITIONS = new Set(["BN", "Bench"]);

function classifyPosition(pos: string): "starter" | "bench" | "il" {
  if (IL_POSITIONS.has(pos)) return "il";
  if (BENCH_POSITIONS.has(pos)) return "bench";
  return "starter";
}

function GameBadge({ entry }: { entry: RosterEntry }) {
  if (entry.player?.status && entry.player.status !== "active") {
    return (
      <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300">
        {entry.player.status.toUpperCase()}
      </span>
    );
  }
  if (!entry.today_game) {
    return (
      <span className="text-xs text-zinc-400 dark:text-zinc-500">Off day</span>
    );
  }
  const g = entry.today_game;
  const prefix = g.home_away === "home" ? "vs" : "@";
  const time = g.game_time
    ? new Date(g.game_time).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
      })
    : "";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className="h-2 w-2 rounded-full bg-green-500" />
      <span className="font-medium">
        {prefix} {g.opponent}
      </span>
      {time && (
        <span className="text-zinc-400 dark:text-zinc-500">{time}</span>
      )}
    </span>
  );
}

function StartSitBadge({ data }: { data: StartSitScore | null }) {
  if (!data || data.score === null) return null;

  const score = data.score;
  let bg: string;
  let text: string;

  if (score > 70) {
    bg = "bg-green-100 dark:bg-green-950";
    text = "text-green-700 dark:text-green-300";
  } else if (score > 50) {
    bg = "bg-emerald-50 dark:bg-emerald-950/50";
    text = "text-emerald-600 dark:text-emerald-400";
  } else if (score > 30) {
    bg = "bg-amber-50 dark:bg-amber-950/50";
    text = "text-amber-600 dark:text-amber-400";
  } else {
    bg = "bg-red-50 dark:bg-red-950/50";
    text = "text-red-600 dark:text-red-400";
  }

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1.5">
        <span className={`rounded px-1.5 py-0.5 text-xs font-bold ${bg} ${text}`}>
          {score}
        </span>
        <span className={`text-xs font-medium ${text}`}>
          {data.label}
        </span>
      </div>
    </div>
  );
}

function LineupBadge({ status }: { status: LineupStatus | null }) {
  if (!status) return null;

  if (status.not_starting) {
    return (
      <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
        Not Starting
      </span>
    );
  }

  if (status.is_starting_pitcher) {
    return (
      <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300">
        SP{status.is_confirmed ? "" : " (proj)"}
      </span>
    );
  }

  if (status.batting_order !== null) {
    return (
      <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
        #{status.batting_order}{status.is_confirmed ? "" : " (proj)"}
      </span>
    );
  }

  return null;
}

function RosterSection({
  title,
  entries,
  showStartSit,
}: {
  title: string;
  entries: RosterEntry[];
  showStartSit: boolean;
}) {
  if (entries.length === 0) return null;

  return (
    <div className="mb-6">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
        {title}
      </h3>
      <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
              <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">
                Pos
              </th>
              <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">
                Player
              </th>
              <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">
                Team
              </th>
              <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">
                Today
              </th>
              <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-24">
                Lineup
              </th>
              {showStartSit && (
                <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Confidence
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => {
              const isIl =
                entry.player?.status && entry.player.status !== "active";
              const hasGame = !!entry.today_game;
              const rowBg = isIl
                ? "bg-red-50/50 dark:bg-red-950/20"
                : hasGame
                  ? "bg-green-50/30 dark:bg-green-950/10"
                  : "";
              return (
                <tr
                  key={entry.yahoo_player_key ?? i}
                  className={`border-b border-zinc-100 last:border-0 dark:border-zinc-800/50 ${rowBg}`}
                >
                  <td className="px-3 py-2 font-mono text-xs text-zinc-500 dark:text-zinc-400">
                    {entry.roster_position}
                  </td>
                  <td className="px-3 py-2">
                    {entry.player ? (
                      <div>
                        <span className="font-medium">
                          {entry.player.full_name}
                        </span>
                        {entry.player.position && (
                          <span className="ml-1.5 text-xs text-zinc-400 dark:text-zinc-500">
                            {entry.player.position}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="italic text-zinc-400 dark:text-zinc-500">
                        Unmatched ({entry.yahoo_player_key})
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                    {entry.player?.team ?? "—"}
                  </td>
                  <td className="px-3 py-2">
                    <GameBadge entry={entry} />
                  </td>
                  <td className="px-3 py-2">
                    <LineupBadge status={entry.lineup_status} />
                  </td>
                  {showStartSit && (
                    <td className="px-3 py-2">
                      <StartSitBadge data={entry.start_sit} />
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function RosterPage() {
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [activeLeague, setActiveLeague] = useState<number | null>(null);
  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load leagues on mount
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

  // Load roster when active league changes
  useEffect(() => {
    if (activeLeague === null) return;
    setLoading(true);
    fetchApi<RosterResponse>(`/api/roster/${activeLeague}`)
      .then((res) => {
        setRoster(res.roster);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [activeLeague]);

  // Group roster entries
  const starters = roster.filter(
    (e) => classifyPosition(e.roster_position) === "starter"
  );
  const bench = roster.filter(
    (e) => classifyPosition(e.roster_position) === "bench"
  );
  const il = roster.filter(
    (e) => classifyPosition(e.roster_position) === "il"
  );

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
            <span className="text-sm font-medium">My Roster</span>
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
        {error && (
          <p className="mb-6 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
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

        {leagues.length === 1 && (
          <h2 className="mb-6 text-xl font-semibold">{leagues[0].name}</h2>
        )}

        {loading && (
          <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>
        )}

        {!loading && leagues.length === 0 && (
          <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center dark:border-zinc-800 dark:bg-zinc-900">
            <p className="mb-2 text-lg font-medium">No leagues connected</p>
            <p className="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
              Connect your Yahoo account to see your roster.
            </p>
            <a
              href="http://localhost:8000/auth/yahoo"
              className="inline-block rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
            >
              Connect Yahoo
            </a>
          </div>
        )}

        {!loading && roster.length > 0 && (
          <>
            <RosterSection title="Starting Lineup" entries={starters} showStartSit={true} />
            <RosterSection title="Bench" entries={bench} showStartSit={true} />
            <RosterSection title="Injured List" entries={il} showStartSit={false} />
          </>
        )}
      </main>
    </div>
  );
}
