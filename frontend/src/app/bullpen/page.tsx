"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";
import type { LeagueInfo } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Ownership {
  team_name: string;
  is_mine: boolean;
}

interface Reliever {
  player_id: number;
  full_name: string;
  team: string | null;
  throws: string | null;
  status: string;
  is_rostered: boolean;
  ownership: Ownership | null;
  role: string;
  confidence: string;
  available_tonight: boolean;
  season_g: number;
  season_ip: number;
  season_era: number;
  season_sv: number;
  season_hld: number;
  season_k9: number;
  season_k_pct: number;
  daily_pitches: (number | null)[];
  pitches_last_3d: number;
  pitches_last_7d: number;
  days_since_last_appearance: number | null;
}

interface BullpenResponse {
  date: string;
  day_columns: string[];
  relievers: Reliever[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ROLE_ORDER = ["closer", "setup", "middle", "long", "mop_up"];

const ROLE_PRIORITY: Record<string, number> = {
  closer: 0,
  setup: 1,
  middle: 2,
  long: 3,
  mop_up: 4,
};

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

type SortKey =
  | "pitcher"
  | "team"
  | "role"
  | "g"
  | "ip"
  | "era"
  | "sv"
  | "hld"
  | "k9"
  | "k_pct";

function sortValue(r: Reliever, key: SortKey): number | string {
  switch (key) {
    case "pitcher": return r.full_name;
    case "team": return r.team || "";
    case "role": return ROLE_PRIORITY[r.role] ?? 99;
    case "g": return r.season_g;
    case "ip": return r.season_ip;
    case "era": return r.season_era;
    case "sv": return r.season_sv;
    case "hld": return r.season_hld;
    case "k9": return r.season_k9;
    case "k_pct": return r.season_k_pct;
  }
}

function formatDate(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${parseInt(m)}/${parseInt(d)}`;
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function SortHeader({
  label,
  sortKey,
  currentSort,
  sortAsc,
  onSort,
  className = "",
}: {
  label: string;
  sortKey: SortKey;
  currentSort: SortKey;
  sortAsc: boolean;
  onSort: (key: SortKey) => void;
  className?: string;
}) {
  const active = currentSort === sortKey;
  return (
    <th
      className={`px-2 py-2 font-medium text-zinc-500 dark:text-zinc-400 cursor-pointer select-none hover:text-zinc-700 dark:hover:text-zinc-200 ${className}`}
      onClick={() => onSort(sortKey)}
    >
      {label}
      {active && (
        <span className="ml-0.5 text-xs">{sortAsc ? "\u25B2" : "\u25BC"}</span>
      )}
    </th>
  );
}

function RelieverRow({
  r,
  dayColumns,
  showTeam,
}: {
  r: Reliever;
  dayColumns: string[];
  showTeam: boolean;
}) {
  const badge = roleBadge[r.role] ?? roleBadge.mop_up;
  const confDot = confidenceDot[r.confidence] ?? confidenceDot.low;

  return (
    <tr className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50 hover:bg-zinc-50 dark:hover:bg-zinc-800/30">
      {/* Pitcher */}
      <td className="px-2 py-2">
        <div className="flex items-center gap-1.5">
          <span
            className={`font-medium text-sm ${
              r.ownership?.is_mine || (!r.ownership && r.is_rostered)
                ? "text-green-600 dark:text-green-400"
                : ""
            }`}
          >
            {r.full_name}
          </span>
          {r.ownership?.is_mine && (
            <span
              className="h-1.5 w-1.5 rounded-full bg-green-500 flex-shrink-0"
              title="On your roster"
            />
          )}
          {r.ownership && !r.ownership.is_mine && (
            <span
              className="h-1.5 w-1.5 rounded-full bg-amber-500 flex-shrink-0"
              title={r.ownership.team_name}
            />
          )}
          {!r.ownership && r.is_rostered && (
            <span
              className="h-1.5 w-1.5 rounded-full bg-green-500 flex-shrink-0"
              title="On your roster"
            />
          )}
          {r.status === "inactive" && (
            <span className="rounded px-1 py-0.5 text-[10px] font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
              MINORS
            </span>
          )}
        </div>
        {showTeam && r.team && (
          <span className="text-xs text-zinc-400 dark:text-zinc-500">
            {r.team}
          </span>
        )}
      </td>

      {/* THR */}
      <td className="px-2 py-2 text-center text-xs text-zinc-500 dark:text-zinc-400">
        {r.throws || "—"}
      </td>

      {/* Role */}
      <td className="px-2 py-2">
        <div className="flex items-center gap-1">
          <span
            className={`rounded px-1.5 py-0.5 text-xs font-medium ${badge.bg} ${badge.text}`}
          >
            {r.role}
          </span>
          <span
            className={`h-1.5 w-1.5 rounded-full ${confDot}`}
            title={r.confidence}
          />
        </div>
      </td>

      {/* Season stats */}
      <td className="px-2 py-2 text-center font-mono text-xs">{r.season_g}</td>
      <td className="px-2 py-2 text-center font-mono text-xs">
        {r.season_ip.toFixed(1)}
      </td>
      <td className="px-2 py-2 text-center font-mono text-xs">
        {r.season_era.toFixed(2)}
      </td>
      <td className="px-2 py-2 text-center font-mono text-xs">{r.season_sv}</td>
      <td className="px-2 py-2 text-center font-mono text-xs">{r.season_hld}</td>
      <td className="px-2 py-2 text-center font-mono text-xs">
        {r.season_k9.toFixed(2)}
      </td>
      <td className="px-2 py-2 text-center font-mono text-xs">
        {r.season_k_pct > 0 ? r.season_k_pct.toFixed(3).replace(/^0/, "") : ".000"}
      </td>

      {/* Daily pitch counts */}
      {dayColumns.map((d, i) => {
        const p = r.daily_pitches[i];
        return (
          <td
            key={d}
            className={`px-1.5 py-2 text-center font-mono text-xs ${
              p !== null && p > 25
                ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
                : ""
            }`}
          >
            {p !== null ? p : ""}
          </td>
        );
      })}
    </tr>
  );
}

function TableHead({
  dayColumns,
  viewMode,
  sortCol,
  sortAsc,
  onSort,
}: {
  dayColumns: string[];
  viewMode: "team" | "flat";
  sortCol: SortKey;
  sortAsc: boolean;
  onSort: (key: SortKey) => void;
}) {
  const thClass =
    "px-2 py-2 font-medium text-zinc-500 dark:text-zinc-400 text-xs";

  if (viewMode === "team") {
    return (
      <thead>
        <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
          <th className={`${thClass} text-left`}>Pitcher</th>
          <th className={`${thClass} text-center`}>THR</th>
          <th className={`${thClass} text-left`}>Role</th>
          <th className={`${thClass} text-center`}>G</th>
          <th className={`${thClass} text-center`}>IP</th>
          <th className={`${thClass} text-center`}>ERA</th>
          <th className={`${thClass} text-center`}>SV</th>
          <th className={`${thClass} text-center`}>HLD</th>
          <th className={`${thClass} text-center`}>K/9</th>
          <th className={`${thClass} text-center`}>K%</th>
          {dayColumns.map((d) => (
            <th key={d} className={`${thClass} text-center`}>
              {formatDate(d)}
            </th>
          ))}
        </tr>
      </thead>
    );
  }

  // Flat mode — sortable headers
  return (
    <thead>
      <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
        <SortHeader label="Pitcher" sortKey="pitcher" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-left text-xs" />
        <th className={`${thClass} text-center`}>THR</th>
        <SortHeader label="Role" sortKey="role" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-left text-xs" />
        <SortHeader label="G" sortKey="g" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-center text-xs" />
        <SortHeader label="IP" sortKey="ip" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-center text-xs" />
        <SortHeader label="ERA" sortKey="era" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-center text-xs" />
        <SortHeader label="SV" sortKey="sv" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-center text-xs" />
        <SortHeader label="HLD" sortKey="hld" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-center text-xs" />
        <SortHeader label="K/9" sortKey="k9" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-center text-xs" />
        <SortHeader label="K%" sortKey="k_pct" currentSort={sortCol} sortAsc={sortAsc} onSort={onSort} className="text-center text-xs" />
        {dayColumns.map((d) => (
          <th key={d} className={`${thClass} text-center`}>
            {formatDate(d)}
          </th>
        ))}
      </tr>
    </thead>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BullpenPage() {
  const [data, setData] = useState<BullpenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filterRole, setFilterRole] = useState<string>("");
  const [filterTeam, setFilterTeam] = useState<string>("");
  const [rosterOnly, setRosterOnly] = useState(false);
  const [viewMode, setViewMode] = useState<"team" | "flat">("team");
  const [sortCol, setSortCol] = useState<SortKey>("role");
  const [sortAsc, setSortAsc] = useState(true);
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [selectedLeague, setSelectedLeague] = useState<number | null>(null);

  useEffect(() => {
    fetchApi<{ leagues: LeagueInfo[] }>("/api/leagues")
      .then((res) => setLeagues(res.leagues))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (filterRole) params.set("role", filterRole);
    if (filterTeam) params.set("team", filterTeam);
    if (rosterOnly) params.set("roster_only", "true");
    if (selectedLeague) params.set("league_id", String(selectedLeague));
    const qs = params.toString();

    fetchApi<BullpenResponse>(`/api/bullpen${qs ? `?${qs}` : ""}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [filterRole, filterTeam, rosterOnly, selectedLeague]);

  const teams = data
    ? [...new Set(data.relievers.map((r) => r.team).filter(Boolean))].sort()
    : [];

  const filteredRelievers = data?.relievers ?? [];

  // Team-grouped view
  const teamGroups = useMemo(() => {
    const groups: Record<string, Reliever[]> = {};
    for (const r of filteredRelievers) {
      const team = r.team || "???";
      if (!groups[team]) groups[team] = [];
      groups[team].push(r);
    }
    for (const t of Object.keys(groups)) {
      groups[t].sort(
        (a, b) => (ROLE_PRIORITY[a.role] ?? 99) - (ROLE_PRIORITY[b.role] ?? 99)
      );
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredRelievers]);

  // Flat sorted view
  const sortedRelievers = useMemo(() => {
    const arr = [...filteredRelievers];
    arr.sort((a, b) => {
      const va = sortValue(a, sortCol);
      const vb = sortValue(b, sortCol);
      let cmp: number;
      if (typeof va === "number" && typeof vb === "number") {
        cmp = va - vb;
      } else {
        cmp = String(va).localeCompare(String(vb));
      }
      // Secondary sort by team then name for stability
      if (cmp === 0) {
        cmp = (a.team || "").localeCompare(b.team || "");
      }
      if (cmp === 0) {
        cmp = a.full_name.localeCompare(b.full_name);
      }
      return sortAsc ? cmp : -cmp;
    });
    return arr;
  }, [filteredRelievers, sortCol, sortAsc]);

  function handleSort(key: SortKey) {
    if (sortCol === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(key);
      setSortAsc(true);
    }
  }

  const dayColumns = data?.day_columns ?? [];

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
            <span className="text-sm font-medium">Bullpen Monitor</span>
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
              onChange={(e) =>
                setSelectedLeague(e.target.value ? Number(e.target.value) : null)
              }
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
            >
              <option value="">No League</option>
              {leagues.map((lg) => (
                <option key={lg.id} value={lg.id}>
                  {lg.name}
                </option>
              ))}
            </select>
          )}
          <select
            value={filterRole}
            onChange={(e) => setFilterRole(e.target.value)}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
          >
            <option value="">All Roles</option>
            {ROLE_ORDER.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <select
            value={filterTeam}
            onChange={(e) => setFilterTeam(e.target.value)}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
          >
            <option value="">All Teams</option>
            {teams.map((t) => (
              <option key={t} value={t!}>
                {t}
              </option>
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
          <button
            onClick={() => setViewMode(viewMode === "team" ? "flat" : "team")}
            className="rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
          >
            {viewMode === "team" ? "By Team" : "All Players"}
          </button>
        </div>

        {!data && !error && (
          <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>
        )}

        {data && filteredRelievers.length === 0 && (
          <p className="text-zinc-500 dark:text-zinc-400">
            No reliever classifications available yet.
          </p>
        )}

        {data && filteredRelievers.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <TableHead
                dayColumns={dayColumns}
                viewMode={viewMode}
                sortCol={sortCol}
                sortAsc={sortAsc}
                onSort={handleSort}
              />
              <tbody className="bg-white dark:bg-zinc-900">
                {viewMode === "team"
                  ? teamGroups.map(([team, relievers]) => (
                      <Fragment key={team}>
                        <tr className="bg-zinc-100 dark:bg-zinc-800/60">
                          <td
                            colSpan={10 + dayColumns.length}
                            className="px-2 py-1.5 text-xs font-bold tracking-wide text-zinc-600 dark:text-zinc-300"
                          >
                            {team}
                          </td>
                        </tr>
                        {relievers.map((r) => (
                          <RelieverRow
                            key={r.player_id}
                            r={r}
                            dayColumns={dayColumns}
                            showTeam={false}
                          />
                        ))}
                      </Fragment>
                    ))
                  : sortedRelievers.map((r) => (
                      <RelieverRow
                        key={r.player_id}
                        r={r}
                        dayColumns={dayColumns}
                        showTeam={true}
                      />
                    ))}
              </tbody>
            </table>
          </div>
        )}

        {data && (
          <p className="mt-4 text-xs text-zinc-400 dark:text-zinc-500">
            Classifications as of {data.date}. Red cells indicate high pitch
            count (&gt;25P).
          </p>
        )}
      </main>
    </div>
  );
}
