"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";

interface PitcherStart {
  date: string;
  game_id: number;
  opponent: string;
  home_away: "home" | "away";
  venue: string | null;
  is_confirmed: boolean;
}

interface RecentStat {
  date: string;
  innings_pitched: number | null;
  earned_runs: number | null;
  strikeouts: number | null;
  walks: number | null;
  hits_allowed: number | null;
  pitches: number | null;
}

interface PitcherWeek {
  player_id: number;
  full_name: string;
  team: string | null;
  throws: string | null;
  is_two_start: boolean;
  starts: PitcherStart[];
  recent_stats: RecentStat[];
}

interface WeekResponse {
  week_start: string;
  week_end: string;
  dates: string[];
  pitchers: PitcherWeek[];
}

interface StreamerEntry {
  player_id: number;
  full_name: string;
  team: string | null;
  throws: string | null;
  date: string;
  opponent: string;
  home_away: "home" | "away";
  venue: string | null;
  is_confirmed: boolean;
  stats: Record<string, unknown> | null;
}

interface StreamersResponse {
  streamers: StreamerEntry[];
}

function dayLabel(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short" });
}

function formatIP(ip: number | null): string {
  if (ip == null) return "—";
  const full = Math.floor(ip);
  const frac = ip - full;
  if (frac < 0.1) return `${full}.0`;
  if (frac < 0.4) return `${full}.1`;
  if (frac < 0.7) return `${full}.2`;
  return `${full}.0`;
}

function PitcherRow({
  pitcher,
  dates,
}: {
  pitcher: PitcherWeek;
  dates: string[];
}) {
  // Map starts by date
  const startsByDate: Record<string, PitcherStart> = {};
  for (const s of pitcher.starts) {
    startsByDate[s.date] = s;
  }

  return (
    <tr className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50">
      <td className="px-3 py-3 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <span className="font-medium">{pitcher.full_name}</span>
          {pitcher.throws && (
            <span className="text-xs text-zinc-400">({pitcher.throws})</span>
          )}
          {pitcher.is_two_start && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-700 dark:bg-amber-950 dark:text-amber-300">
              2-START
            </span>
          )}
        </div>
        <div className="text-xs text-zinc-400 dark:text-zinc-500">
          {pitcher.team}
        </div>
      </td>
      {dates.map((d) => {
        const start = startsByDate[d];
        return (
          <td key={d} className="px-2 py-3 text-center text-sm">
            {start ? (
              <div>
                <span
                  className={`font-medium ${
                    start.home_away === "home"
                      ? "text-zinc-700 dark:text-zinc-200"
                      : "text-zinc-500 dark:text-zinc-400"
                  }`}
                >
                  {start.home_away === "home" ? "vs" : "@"} {start.opponent}
                </span>
                {!start.is_confirmed && (
                  <span className="ml-1 text-[10px] text-amber-500">?</span>
                )}
              </div>
            ) : (
              <span className="text-zinc-300 dark:text-zinc-700">—</span>
            )}
          </td>
        );
      })}
      <td className="px-3 py-3">
        <div className="flex gap-3 text-xs text-zinc-500 dark:text-zinc-400">
          {pitcher.recent_stats.length > 0 ? (
            pitcher.recent_stats.map((s, i) => (
              <div key={i} className="text-center">
                <div className="font-mono">{formatIP(s.innings_pitched)} IP</div>
                <div>
                  {s.earned_runs ?? 0} ER, {s.strikeouts ?? 0} K
                </div>
              </div>
            ))
          ) : (
            <span className="italic">No recent data</span>
          )}
        </div>
      </td>
    </tr>
  );
}

function StreamerCard({ streamer }: { streamer: StreamerEntry }) {
  const prefix = streamer.home_away === "home" ? "vs" : "@";
  const era = streamer.stats?.["ERA"] ?? streamer.stats?.["era"];
  const whip = streamer.stats?.["WHIP"] ?? streamer.stats?.["whip"];
  const kPer9 = streamer.stats?.["K/9"] ?? streamer.stats?.["k_per_9"];

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between">
        <div>
          <span className="font-medium">{streamer.full_name}</span>
          {streamer.throws && (
            <span className="ml-1 text-xs text-zinc-400">
              ({streamer.throws})
            </span>
          )}
        </div>
        <span className="text-xs text-zinc-400">{streamer.team}</span>
      </div>
      <div className="mt-1 flex items-center gap-3 text-sm">
        <span className="font-medium">
          {prefix} {streamer.opponent}
        </span>
        <span className="text-xs text-zinc-400">
          {new Date(streamer.date + "T12:00:00").toLocaleDateString(undefined, {
            weekday: "short",
            month: "short",
            day: "numeric",
          })}
        </span>
        {!streamer.is_confirmed && (
          <span className="text-[10px] text-amber-500">projected</span>
        )}
      </div>
      {(era != null || whip != null || kPer9 != null) && (
        <div className="mt-2 flex gap-3 text-xs text-zinc-500 dark:text-zinc-400">
          {era != null && <span>ERA {Number(era).toFixed(2)}</span>}
          {whip != null && <span>WHIP {Number(whip).toFixed(2)}</span>}
          {kPer9 != null && <span>K/9 {Number(kPer9).toFixed(1)}</span>}
        </div>
      )}
    </div>
  );
}

export default function PitchingPage() {
  const [week, setWeek] = useState<WeekResponse | null>(null);
  const [streamers, setStreamers] = useState<StreamersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchApi<WeekResponse>("/api/pitching/week")
      .then(setWeek)
      .catch((e) => setError(e.message));
    fetchApi<StreamersResponse>("/api/pitching/streamers")
      .then(setStreamers)
      .catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-2xl font-bold tracking-tight hover:opacity-80"
            >
              Ripken
            </Link>
            <span className="text-sm text-zinc-400 dark:text-zinc-500">/</span>
            <span className="text-sm font-medium">Pitching Planner</span>
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

      <main className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}

        {/* Weekly SP Schedule */}
        <h2 className="mb-4 text-xl font-semibold">
          Weekly Schedule{" "}
          {week && (
            <span className="text-base font-normal text-zinc-500 dark:text-zinc-400">
              {week.week_start} — {week.week_end}
            </span>
          )}
        </h2>

        {!week && !error && (
          <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>
        )}

        {week && week.pitchers.length === 0 && (
          <p className="mb-8 text-zinc-500 dark:text-zinc-400">
            No starting pitchers on your roster.
          </p>
        )}

        {week && week.pitchers.length > 0 && (
          <div className="mb-10 overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">
                    Pitcher
                  </th>
                  {week.dates.map((d) => (
                    <th
                      key={d}
                      className={`px-2 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 ${
                        d === new Date().toISOString().slice(0, 10)
                          ? "bg-indigo-50 dark:bg-indigo-950/30"
                          : ""
                      }`}
                    >
                      {dayLabel(d)}
                    </th>
                  ))}
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">
                    Last 3 Starts
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-zinc-900">
                {week.pitchers.map((p) => (
                  <PitcherRow key={p.player_id} pitcher={p} dates={week.dates} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Streaming Candidates */}
        <h2 className="mb-4 text-xl font-semibold">Streaming Candidates</h2>
        {streamers && streamers.streamers.length === 0 && (
          <p className="text-zinc-500 dark:text-zinc-400">
            No streaming candidates available this week.
          </p>
        )}
        {streamers && streamers.streamers.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {streamers.streamers.map((s) => (
              <StreamerCard key={`${s.player_id}-${s.date}`} streamer={s} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
