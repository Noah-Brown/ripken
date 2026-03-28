"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchApi,
  type LeagueInfo,
  type LeaguesResponse,
} from "@/lib/api";

interface ScoreBreakdown {
  projection: number;
  recent: number;
  scarcity: number;
}

interface WaiverPlayer {
  player_id: number;
  full_name: string;
  team: string | null;
  position: string | null;
  status: string | null;
  score: number;
  breakdown: ScoreBreakdown;
  projection: Record<string, unknown> | null;
  recent: Record<string, unknown> | null;
}

interface WaiversResponse {
  league_id: number;
  league_name: string;
  format: string;
  players: WaiverPlayer[];
}

const POSITIONS = ["", "C", "1B", "2B", "3B", "SS", "OF", "DH", "SP", "RP"];

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-600 dark:text-green-400";
  if (score >= 50) return "text-amber-600 dark:text-amber-400";
  if (score >= 30) return "text-zinc-600 dark:text-zinc-400";
  return "text-zinc-400 dark:text-zinc-500";
}

function StatBadge({ label, value }: { label: string; value: unknown }) {
  if (value == null) return null;
  const num = Number(value);
  const display = Number.isInteger(num) ? num.toString() : num.toFixed(num < 10 ? 2 : 1);
  return (
    <span className="text-xs text-zinc-500 dark:text-zinc-400">
      {label} <span className="font-mono">{display}</span>
    </span>
  );
}

function WaiverRow({ player }: { player: WaiverPlayer }) {
  const proj = player.projection ?? {};
  const isPitcher = player.position === "SP" || player.position === "RP" || player.position === "P";

  return (
    <tr className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50">
      <td className="px-3 py-3 text-center">
        <span className={`text-lg font-bold ${scoreColor(player.score)}`}>
          {player.score}
        </span>
      </td>
      <td className="px-3 py-3">
        <div>
          <span className="font-medium">{player.full_name}</span>
          {player.position && (
            <span className="ml-1.5 text-xs text-zinc-400 dark:text-zinc-500">
              {player.position}
            </span>
          )}
        </div>
        <span className="text-xs text-zinc-400 dark:text-zinc-500">
          {player.team}
        </span>
      </td>
      <td className="px-3 py-3">
        <div className="flex gap-3">
          {isPitcher ? (
            <>
              <StatBadge label="ERA" value={proj["ERA"] ?? proj["era"]} />
              <StatBadge label="WHIP" value={proj["WHIP"] ?? proj["whip"]} />
              <StatBadge label="K/9" value={proj["K/9"] ?? proj["k_per_9"] ?? proj["SO9"]} />
            </>
          ) : (
            <>
              <StatBadge label="HR" value={proj["HR"] ?? proj["hr"]} />
              <StatBadge label="SB" value={proj["SB"] ?? proj["sb"]} />
              <StatBadge label="OPS" value={proj["OPS"] ?? proj["ops"]} />
              <StatBadge label="wRC+" value={proj["wRC+"] ?? proj["wrc_plus"]} />
            </>
          )}
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="flex gap-2">
          <ScorePill label="Proj" score={player.breakdown.projection} />
          <ScorePill label="Hot" score={player.breakdown.recent} />
          <ScorePill label="Pos" score={player.breakdown.scarcity} />
        </div>
      </td>
    </tr>
  );
}

function ScorePill({ label, score }: { label: string; score: number }) {
  const bg =
    score >= 50
      ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
      : score >= 25
        ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
        : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${bg}`}>
      {label} {score}
    </span>
  );
}

export default function WaiversPage() {
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [activeLeague, setActiveLeague] = useState<number | null>(null);
  const [position, setPosition] = useState<string>("");
  const [data, setData] = useState<WaiversResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load leagues
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

  // Load waivers when league or position changes
  useEffect(() => {
    if (activeLeague === null) return;
    setLoading(true);
    const params = new URLSearchParams();
    if (position) params.set("position", position);
    const qs = params.toString();

    fetchApi<WaiversResponse>(`/api/waivers/${activeLeague}${qs ? `?${qs}` : ""}`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [activeLeague, position]);

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-2xl font-bold tracking-tight hover:opacity-80">Ripken</Link>
            <span className="text-sm text-zinc-400 dark:text-zinc-500">/</span>
            <span className="text-sm font-medium">Waiver Wire</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/roster" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Roster</Link>
            <Link href="/league" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">League</Link>
            <Link href="/lineups" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Lineups</Link>
            <Link href="/bullpen" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Bullpen</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>
        )}

        {/* League tabs + filters */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          {leagues.length > 1 &&
            leagues.map((lg) => (
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

          <select
            value={position}
            onChange={(e) => setPosition(e.target.value)}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
          >
            <option value="">All Positions</option>
            {POSITIONS.filter(Boolean).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>

        {leagues.length === 0 && !loading && (
          <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center dark:border-zinc-800 dark:bg-zinc-900">
            <p className="mb-2 text-lg font-medium">No leagues connected</p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Connect your Yahoo account to browse the waiver wire.
            </p>
          </div>
        )}

        {loading && <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>}

        {!loading && data && data.players.length === 0 && (
          <p className="text-zinc-500 dark:text-zinc-400">
            No free agents found{position ? ` at ${position}` : ""}.
          </p>
        )}

        {!loading && data && data.players.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                  <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 w-16">Score</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Player</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Key Stats</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Breakdown</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-zinc-900">
                {data.players.map((p) => (
                  <WaiverRow key={p.player_id} player={p} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
