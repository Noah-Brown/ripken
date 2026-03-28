"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";
import type { LeagueInfo, CategoryNeedSummary } from "@/lib/api";

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
  value_score: number | null;
  category_impact: Record<string, { projected: number; impact: number; need: number }> | null;
}

interface WaiversResponse {
  league_id: number;
  league_name: string;
  positions: Record<string, WaiverPlayer[]>;
  category_needs: CategoryNeedSummary[];
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
// Helpers
// ---------------------------------------------------------------------------

function valueColor(score: number | null): string {
  if (score == null) return "text-zinc-400";
  if (score >= 70) return "text-green-400 font-bold";
  if (score >= 40) return "text-yellow-400";
  return "text-zinc-400";
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function CategoryNeedsPanel({
  needs,
  collapsed,
  onToggle,
}: {
  needs: CategoryNeedSummary[];
  collapsed: boolean;
  onToggle: () => void;
}) {
  const sorted = [...needs].sort((a, b) => b.need - a.need);

  const chipClass = (need: number): string => {
    if (need >= 0.7) return "bg-red-500/20 text-red-400 border border-red-500/30";
    if (need >= 0.4) return "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30";
    return "bg-green-500/20 text-green-400 border border-green-500/30";
  };

  return (
    <div className="mb-6 rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold text-zinc-600 dark:text-zinc-300"
      >
        <span>Category Needs</span>
        <span className="text-xs text-zinc-400">{collapsed ? "Show" : "Hide"}</span>
      </button>
      {!collapsed && (
        <div className="flex flex-wrap gap-2 px-4 pb-4">
          {sorted.map((n) => (
            <span
              key={n.category}
              className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${chipClass(n.need)}`}
            >
              {n.category}
              {n.rank != null && (
                <span className="opacity-70">#{n.rank}</span>
              )}
              <span className="opacity-60">{(n.need * 100).toFixed(0)}%</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ImpactBreakdown({
  impact,
}: {
  impact: Record<string, { projected: number; impact: number; need: number }>;
}) {
  const entries = Object.entries(impact).sort(([, a], [, b]) => Math.abs(b.impact) - Math.abs(a.impact));

  const impactColor = (v: number): string => {
    if (v > 0.05) return "text-green-400";
    if (v < -0.05) return "text-red-400";
    return "text-zinc-400";
  };

  return (
    <div className="px-2 py-3 bg-zinc-50 dark:bg-zinc-800/50">
      <p className="text-xs font-semibold text-zinc-500 uppercase mb-2 px-2">Category Impact</p>
      <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 md:grid-cols-4">
        {entries.map(([cat, data]) => (
          <div
            key={cat}
            className="rounded px-2 py-1.5 bg-white dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800"
          >
            <div className="text-xs font-medium text-zinc-600 dark:text-zinc-300">{cat}</div>
            <div className="font-mono text-xs">
              <span className="text-zinc-400">{data.projected.toFixed(2)}</span>
              <span className={`ml-1 ${impactColor(data.impact)}`}>
                {data.impact > 0 ? "+" : ""}{data.impact.toFixed(2)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

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
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const toggleRow = (playerId: number) => {
    setExpandedRow((prev) => (prev === playerId ? null : playerId));
  };

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
              <th className={`${thClass} text-center`}>Score</th>
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
              <Fragment key={p.player_id}>
                <tr
                  className={`border-b border-zinc-100 last:border-0 dark:border-zinc-800/50 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/30 ${
                    expandedRow === p.player_id ? "bg-zinc-50 dark:bg-zinc-800/30" : ""
                  }`}
                  onClick={() => toggleRow(p.player_id)}
                >
                  <td className="px-2 py-2 text-center font-mono text-xs">
                    <span className={valueColor(p.value_score)}>
                      {p.value_score != null ? Math.round(p.value_score) : "\u2014"}
                    </span>
                  </td>
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
                {expandedRow === p.player_id && p.category_impact && (
                  <tr className="border-b border-zinc-100 dark:border-zinc-800/50">
                    <td colSpan={3 + cols.length} className="p-0">
                      <ImpactBreakdown impact={p.category_impact} />
                    </td>
                  </tr>
                )}
              </Fragment>
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
  const [needsCollapsed, setNeedsCollapsed] = useState(false);

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
            <Link href="/team-analysis" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Analysis</Link>
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

        {/* Category Needs Panel */}
        {!loading && data && data.category_needs && data.category_needs.length > 0 && (
          <CategoryNeedsPanel
            needs={data.category_needs}
            collapsed={needsCollapsed}
            onToggle={() => setNeedsCollapsed((c) => !c)}
          />
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
