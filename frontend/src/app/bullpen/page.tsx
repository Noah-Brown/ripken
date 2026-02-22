"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";

interface UsageDay {
  date: string;
  innings_pitched: number | null;
  pitches: number | null;
  earned_runs: number | null;
  strikeouts: number | null;
  save: number;
  hold: number;
  blown_save: number;
}

interface Reliever {
  player_id: number;
  full_name: string;
  team: string | null;
  throws: string | null;
  is_rostered: boolean;
  role: string;
  confidence: string;
  available_tonight: boolean;
  saves_last_14d: number;
  holds_last_14d: number;
  appearances_last_7d: number;
  avg_leverage_last_14d: number | null;
  days_since_last_appearance: number | null;
  pitches_last_3d: number;
  pitches_last_7d: number;
  evidence: Record<string, unknown>;
  usage_heatmap: UsageDay[];
}

interface BullpenResponse {
  date: string;
  relievers: Reliever[];
}

const ROLE_ORDER = ["closer", "setup", "middle", "long", "mop_up"];

const roleBadge: Record<string, { bg: string; text: string }> = {
  closer: { bg: "bg-red-100 dark:bg-red-950", text: "text-red-700 dark:text-red-300" },
  setup: { bg: "bg-amber-100 dark:bg-amber-950", text: "text-amber-700 dark:text-amber-300" },
  middle: { bg: "bg-blue-100 dark:bg-blue-950", text: "text-blue-700 dark:text-blue-300" },
  long: { bg: "bg-zinc-100 dark:bg-zinc-800", text: "text-zinc-600 dark:text-zinc-400" },
  mop_up: { bg: "bg-zinc-100 dark:bg-zinc-800", text: "text-zinc-500 dark:text-zinc-500" },
};

const confidenceDot: Record<string, string> = {
  high: "bg-green-500",
  medium: "bg-amber-500",
  low: "bg-zinc-400",
};

function UsageHeatmap({ days }: { days: UsageDay[] }) {
  // Build a 14-day grid
  const today = new Date();
  const cells: { date: string; pitched: boolean; pitches: number }[] = [];
  const dayMap = new Map(days.map((d) => [d.date, d]));

  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    const usage = dayMap.get(dateStr);
    cells.push({
      date: dateStr,
      pitched: !!usage,
      pitches: usage?.pitches ?? 0,
    });
  }

  return (
    <div className="flex gap-0.5">
      {cells.map((c) => (
        <div
          key={c.date}
          className={`h-4 w-3 rounded-sm ${
            c.pitched
              ? c.pitches > 25
                ? "bg-red-400 dark:bg-red-600"
                : "bg-green-400 dark:bg-green-600"
              : "bg-zinc-100 dark:bg-zinc-800"
          }`}
          title={`${c.date}${c.pitched ? ` — ${c.pitches}P` : ""}`}
        />
      ))}
    </div>
  );
}

function RelieverRow({ r }: { r: Reliever }) {
  const badge = roleBadge[r.role] ?? roleBadge.mop_up;
  const confDot = confidenceDot[r.confidence] ?? confidenceDot.low;

  return (
    <tr className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50">
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <span className={`font-medium ${r.is_rostered ? "text-green-600 dark:text-green-400" : ""}`}>
            {r.full_name}
          </span>
          {r.throws && (
            <span className="text-xs text-zinc-400">({r.throws})</span>
          )}
          {r.is_rostered && (
            <span className="h-1.5 w-1.5 rounded-full bg-green-500" title="On your roster" />
          )}
        </div>
        <span className="text-xs text-zinc-400 dark:text-zinc-500">{r.team}</span>
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-1.5">
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${badge.bg} ${badge.text}`}>
            {r.role}
          </span>
          <span className={`h-2 w-2 rounded-full ${confDot}`} title={r.confidence} />
        </div>
      </td>
      <td className="px-3 py-3 text-center">
        {r.available_tonight ? (
          <span className="text-xs font-medium text-green-600 dark:text-green-400">Yes</span>
        ) : (
          <span className="text-xs text-red-500">No</span>
        )}
      </td>
      <td className="px-3 py-3 text-center font-mono text-sm">
        {r.saves_last_14d}
      </td>
      <td className="px-3 py-3 text-center font-mono text-sm">
        {r.holds_last_14d}
      </td>
      <td className="px-3 py-3 text-center font-mono text-sm">
        {r.appearances_last_7d}
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <div className="h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div
                className={`h-2 rounded-full ${
                  r.pitches_last_3d > 60 ? "bg-red-400" : r.pitches_last_3d > 30 ? "bg-amber-400" : "bg-green-400"
                }`}
                style={{ width: `${Math.min((r.pitches_last_3d / 75) * 100, 100)}%` }}
              />
            </div>
          </div>
          <span className="text-xs text-zinc-400 w-8 text-right">{r.pitches_last_3d}P</span>
        </div>
        <div className="flex items-center gap-2 mt-1">
          <div className="flex-1">
            <div className="h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div
                className={`h-2 rounded-full ${
                  r.pitches_last_7d > 120 ? "bg-red-400" : r.pitches_last_7d > 60 ? "bg-amber-400" : "bg-green-400"
                }`}
                style={{ width: `${Math.min((r.pitches_last_7d / 150) * 100, 100)}%` }}
              />
            </div>
          </div>
          <span className="text-xs text-zinc-400 w-8 text-right">{r.pitches_last_7d}P</span>
        </div>
      </td>
      <td className="px-3 py-3">
        <UsageHeatmap days={r.usage_heatmap} />
      </td>
    </tr>
  );
}

export default function BullpenPage() {
  const [data, setData] = useState<BullpenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filterRole, setFilterRole] = useState<string>("");
  const [filterTeam, setFilterTeam] = useState<string>("");
  const [rosterOnly, setRosterOnly] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams();
    if (filterRole) params.set("role", filterRole);
    if (filterTeam) params.set("team", filterTeam);
    if (rosterOnly) params.set("roster_only", "true");
    const qs = params.toString();

    fetchApi<BullpenResponse>(`/api/bullpen${qs ? `?${qs}` : ""}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [filterRole, filterTeam, rosterOnly]);

  const teams = data
    ? [...new Set(data.relievers.map((r) => r.team).filter(Boolean))].sort()
    : [];

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-2xl font-bold tracking-tight hover:opacity-80">Ripken</Link>
            <span className="text-sm text-zinc-400 dark:text-zinc-500">/</span>
            <span className="text-sm font-medium">Bullpen Monitor</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/roster" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Roster</Link>
            <Link href="/lineups" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Lineups</Link>
            <Link href="/pitching" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Pitching</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>
        )}

        {/* Filters */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <select
            value={filterRole}
            onChange={(e) => setFilterRole(e.target.value)}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
          >
            <option value="">All Roles</option>
            {ROLE_ORDER.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <select
            value={filterTeam}
            onChange={(e) => setFilterTeam(e.target.value)}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
          >
            <option value="">All Teams</option>
            {teams.map((t) => (
              <option key={t} value={t!}>{t}</option>
            ))}
          </select>
          <button
            onClick={() => setRosterOnly(!rosterOnly)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              rosterOnly
                ? "bg-green-600 text-white"
                : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
            }`}
          >
            {rosterOnly ? "My Relievers" : "All Relievers"}
          </button>
        </div>

        {!data && !error && <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>}

        {data && data.relievers.length === 0 && (
          <p className="text-zinc-500 dark:text-zinc-400">No reliever classifications available yet.</p>
        )}

        {data && data.relievers.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Pitcher</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Role</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400">Avail</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400">SV</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400">HLD</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400">App/7d</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-36">Workload</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">14d Usage</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-zinc-900">
                {data.relievers.map((r) => (
                  <RelieverRow key={r.player_id} r={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && (
          <p className="mt-4 text-xs text-zinc-400 dark:text-zinc-500">
            Classifications as of {data.date}. Heatmap: green = pitched, red = high pitch count (&gt;25P).
          </p>
        )}
      </main>
    </div>
  );
}
