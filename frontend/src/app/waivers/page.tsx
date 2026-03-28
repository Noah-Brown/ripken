"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";
import type { LeagueInfo } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WaiverPlayer {
  player_id: number;
  full_name: string;
  team: string | null;
  status: string;
  owner: string | null;
  is_mine: boolean;
  is_available: boolean;
  projection: Record<string, number> | null;
}

interface WaiversResponse {
  league_id: number;
  league_name: string;
  positions: Record<string, WaiverPlayer[]>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PITCHER_POSITIONS = new Set(["SP", "RP", "P"]);

const BATTER_COLS: { key: string; label: string; fmt: (v: number) => string }[] = [
  { key: "PA", label: "PA", fmt: (v) => Math.round(v).toString() },
  { key: "R", label: "R", fmt: (v) => Math.round(v).toString() },
  { key: "HR", label: "HR", fmt: (v) => Math.round(v).toString() },
  { key: "RBI", label: "RBI", fmt: (v) => Math.round(v).toString() },
  { key: "SB", label: "SB", fmt: (v) => Math.round(v).toString() },
  { key: "AVG", label: "AVG", fmt: (v) => v.toFixed(3).replace(/^0/, "") },
  { key: "OBP", label: "OBP", fmt: (v) => v.toFixed(3).replace(/^0/, "") },
  { key: "SLG", label: "SLG", fmt: (v) => v.toFixed(3).replace(/^0/, "") },
  { key: "OPS", label: "OPS", fmt: (v) => v.toFixed(3).replace(/^0/, "") },
  { key: "wRC+", label: "wRC+", fmt: (v) => Math.round(v).toString() },
  { key: "Off", label: "Off", fmt: (v) => v.toFixed(1) },
];

const PITCHER_COLS: { key: string; label: string; fmt: (v: number) => string }[] = [
  { key: "IP", label: "IP", fmt: (v) => v.toFixed(1) },
  { key: "W", label: "W", fmt: (v) => Math.round(v).toString() },
  { key: "QS", label: "QS", fmt: (v) => Math.round(v).toString() },
  { key: "SV", label: "SV", fmt: (v) => Math.round(v).toString() },
  { key: "ERA", label: "ERA", fmt: (v) => v.toFixed(2) },
  { key: "WHIP", label: "WHIP", fmt: (v) => v.toFixed(2) },
  { key: "K/9", label: "K/9", fmt: (v) => v.toFixed(2) },
  { key: "SO", label: "K", fmt: (v) => Math.round(v).toString() },
  { key: "WAR", label: "WAR", fmt: (v) => v.toFixed(1) },
];

const POSITIONS = ["", "C", "1B", "2B", "SS", "3B", "OF", "DH", "Util", "SP", "RP", "P", "BN", "IL"];

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function PositionTable({
  pos,
  players,
  isPitcher,
}: {
  pos: string;
  players: WaiverPlayer[];
  isPitcher: boolean;
}) {
  const cols = isPitcher ? PITCHER_COLS : BATTER_COLS;
  const thClass = "px-2 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400";

  return (
    <Fragment>
      <div className="mt-6 mb-2">
        <h2 className="text-sm font-bold text-zinc-600 dark:text-zinc-300">
          {pos}{" "}
          <span className="font-normal text-zinc-400">({players.length})</span>
        </h2>
      </div>
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800 mb-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
              <th className={`${thClass} text-left`}>Player</th>
              <th className={`${thClass} text-left`}>Owner</th>
              {cols.map((c) => (
                <th key={c.key} className={`${thClass} text-center`}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-zinc-900">
            {players.map((p) => (
              <tr
                key={p.player_id}
                className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50"
              >
                <td className="px-2 py-2">
                  <span
                    className={`text-sm font-medium ${
                      p.is_mine
                        ? "text-green-600 dark:text-green-400"
                        : ""
                    }`}
                  >
                    {p.full_name}
                  </span>
                  {p.team && (
                    <span className="ml-1 text-xs text-zinc-400 dark:text-zinc-500">
                      {p.team}
                    </span>
                  )}
                </td>
                <td className="px-2 py-2 text-xs">
                  {p.is_available ? (
                    <span className="font-medium text-green-600 dark:text-green-400">
                      FA
                    </span>
                  ) : (
                    <span className="text-zinc-500 dark:text-zinc-400">
                      {p.owner}
                    </span>
                  )}
                </td>
                {cols.map((c) => {
                  const v = p.projection?.[c.key];
                  return (
                    <td
                      key={c.key}
                      className="px-2 py-2 text-center font-mono text-xs"
                    >
                      {v != null ? c.fmt(v) : "\u2014"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Fragment>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function WaiversPage() {
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
  const [position, setPosition] = useState<string>("");
  const [data, setData] = useState<WaiversResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchApi<{ leagues: LeagueInfo[] }>("/api/leagues")
      .then((res) => {
        setLeagues(res.leagues);
        if (res.leagues.length > 0) setSelectedLeague(res.leagues[0].id);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedLeague) return;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (position) params.set("position", position);
    const qs = params.toString();

    fetchApi<WaiversResponse>(
      `/api/waivers/${selectedLeague}${qs ? `?${qs}` : ""}`
    )
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [selectedLeague, position]);

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-2xl font-bold tracking-tight hover:opacity-80"
            >
              Ripken
            </Link>
            <span className="text-sm text-zinc-400 dark:text-zinc-500">/</span>
            <span className="text-sm font-medium">Waiver Wire</span>
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

      <main className="mx-auto max-w-7xl px-6 py-8">
        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}

        {/* Filters */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          {leagues.length > 0 && (
            <select
              value={selectedLeague ?? ""}
              onChange={(e) => setSelectedLeague(Number(e.target.value))}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
            >
              {leagues.map((lg) => (
                <option key={lg.id} value={lg.id}>
                  {lg.name}
                </option>
              ))}
            </select>
          )}
          <select
            value={position}
            onChange={(e) => setPosition(e.target.value)}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
          >
            <option value="">All Positions</option>
            {POSITIONS.filter(Boolean).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
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

        {loading && (
          <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>
        )}

        {!loading &&
          data &&
          Object.keys(data.positions).length === 0 && (
            <p className="text-zinc-500 dark:text-zinc-400">
              No projection data available. Import projections first.
            </p>
          )}

        {!loading &&
          data &&
          Object.entries(data.positions).map(([pos, players]) => (
            <PositionTable
              key={pos}
              pos={pos}
              players={players}
              isPitcher={PITCHER_POSITIONS.has(pos)}
            />
          ))}
      </main>
    </div>
  );
}
