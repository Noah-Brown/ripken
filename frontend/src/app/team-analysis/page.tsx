"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";
import type { LeagueInfo, TeamAnalysisResponse, CategoryDetail } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function RadarChart({ categories, numTeams }: { categories: CategoryDetail[]; numTeams: number }) {
  const size = 300;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size / 2 - 40;
  const n = categories.length;
  if (n < 3) return null;

  const angleStep = 360 / n;
  const myNorm = categories.map((c) => 1 - (c.rank - 1) / Math.max(numTeams - 1, 1));
  const avgNorm = categories.map(() => 0.5);

  const toPoints = (values: number[]) =>
    values
      .map((v, i) => {
        const { x, y } = polarToCartesian(cx, cy, v * maxR, i * angleStep);
        return `${x},${y}`;
      })
      .join(" ");

  const rings = [0.25, 0.5, 0.75, 1.0];
  const needColor = (need: number) => {
    if (need >= 0.7) return "#ef4444";
    if (need >= 0.4) return "#eab308";
    return "#22c55e";
  };

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="mx-auto">
      {rings.map((r) => (
        <polygon
          key={r}
          points={Array.from({ length: n }, (_, i) => {
            const { x, y } = polarToCartesian(cx, cy, r * maxR, i * angleStep);
            return `${x},${y}`;
          }).join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth="0.5"
          className="text-zinc-700"
        />
      ))}
      {categories.map((_, i) => {
        const { x, y } = polarToCartesian(cx, cy, maxR, i * angleStep);
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={x}
            y2={y}
            stroke="currentColor"
            strokeWidth="0.5"
            className="text-zinc-700"
          />
        );
      })}
      <polygon
        points={toPoints(avgNorm)}
        fill="none"
        stroke="#666"
        strokeWidth="1"
        strokeDasharray="4,3"
      />
      <polygon
        points={toPoints(myNorm)}
        fill="rgba(78,205,196,0.2)"
        stroke="#4ecdc4"
        strokeWidth="2"
      />
      {categories.map((cat, i) => {
        const { x, y } = polarToCartesian(cx, cy, maxR + 22, i * angleStep);
        return (
          <text
            key={cat.category}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="10"
            fill={needColor(cat.need)}
          >
            {cat.category} ({cat.rank})
          </text>
        );
      })}
    </svg>
  );
}

function SummaryCards({ categories }: { categories: CategoryDetail[] }) {
  const sorted = [...categories].sort((a, b) => b.need - a.need);
  const biggestNeed = sorted[0];
  const biggestStrength = sorted[sorted.length - 1];
  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4">
        <div className="text-xs text-zinc-400 uppercase">Biggest Need</div>
        <div className="text-2xl font-bold text-red-400">{biggestNeed?.category}</div>
        <div className="text-xs text-zinc-500">Rank: {biggestNeed?.rank}th</div>
      </div>
      <div className="rounded-lg bg-green-500/10 border border-green-500/20 p-4">
        <div className="text-xs text-zinc-400 uppercase">Biggest Strength</div>
        <div className="text-2xl font-bold text-green-400">{biggestStrength?.category}</div>
        <div className="text-xs text-zinc-500">Rank: {biggestStrength?.rank}th</div>
      </div>
      <div className="rounded-lg bg-zinc-800 border border-zinc-700 p-4">
        <div className="text-xs text-zinc-400 uppercase">Categories</div>
        <div className="text-2xl font-bold">{categories.length}</div>
        <div className="text-xs text-zinc-500">Scoring categories</div>
      </div>
    </div>
  );
}

function needBadgeClass(need: number): string {
  if (need >= 0.7) return "text-red-400";
  if (need >= 0.4) return "text-yellow-400";
  return "text-green-400";
}

function CategoryTable({
  categories,
  leagueFormat,
}: {
  categories: CategoryDetail[];
  leagueFormat: string;
}) {
  const isRoto = leagueFormat !== "head";
  const thClass = "px-3 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400";

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
            <th className={`${thClass} text-left`}>Category</th>
            <th className={`${thClass} text-center`}>Projected</th>
            <th className={`${thClass} text-center`}>League Avg</th>
            <th className={`${thClass} text-center`}>Rank</th>
            <th className={`${thClass} text-center`}>Need</th>
            {isRoto && (
              <>
                <th className={`${thClass} text-center`}>Gap to Next</th>
                <th className={`${thClass} text-center`}>Gap Below</th>
                <th className={`${thClass} text-center`}>Pts Available</th>
              </>
            )}
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-zinc-900">
          {categories.map((cat) => (
            <tr
              key={cat.category}
              className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50"
            >
              <td className="px-3 py-2 font-medium">{cat.category}</td>
              <td className="px-3 py-2 text-center font-mono text-xs">
                {cat.my_value != null ? cat.my_value.toFixed(2) : "\u2014"}
              </td>
              <td className="px-3 py-2 text-center font-mono text-xs">
                {cat.league_avg != null ? cat.league_avg.toFixed(2) : "\u2014"}
              </td>
              <td className="px-3 py-2 text-center font-mono text-xs">{cat.rank}</td>
              <td className={`px-3 py-2 text-center font-mono text-xs font-bold ${needBadgeClass(cat.need)}`}>
                {cat.need.toFixed(2)}
              </td>
              {isRoto && (
                <>
                  <td className="px-3 py-2 text-center font-mono text-xs">
                    {cat.gap_to_next != null ? cat.gap_to_next.toFixed(2) : "\u2014"}
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-xs">
                    {cat.gap_below != null ? cat.gap_below.toFixed(2) : "\u2014"}
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-xs">
                    {cat.points_available != null ? cat.points_available.toFixed(1) : "\u2014"}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function H2HMatchupPanel({
  matchup,
}: {
  matchup: NonNullable<TeamAnalysisResponse["current_matchup"]>;
}) {
  const edgeColor = (edge: string) => {
    if (edge === "win") return "text-green-400";
    if (edge === "loss") return "text-red-400";
    return "text-zinc-400";
  };

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold mb-4">
        Current Matchup vs <span className="text-indigo-400">{matchup.opponent}</span>
      </h2>
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
              <th className="px-3 py-2 text-xs font-medium text-zinc-500 text-left">Category</th>
              <th className="px-3 py-2 text-xs font-medium text-zinc-500 text-center">My Proj.</th>
              <th className="px-3 py-2 text-xs font-medium text-zinc-500 text-center">
                Opp Proj.
              </th>
              <th className="px-3 py-2 text-xs font-medium text-zinc-500 text-center">Edge</th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-zinc-900">
            {matchup.category_comparison.map((row) => (
              <tr
                key={row.category}
                className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50"
              >
                <td className="px-3 py-2 font-medium">{row.category}</td>
                <td className="px-3 py-2 text-center font-mono text-xs">
                  {row.my_projected.toFixed(2)}
                </td>
                <td className="px-3 py-2 text-center font-mono text-xs">
                  {row.opp_projected.toFixed(2)}
                </td>
                <td className={`px-3 py-2 text-center font-mono text-xs font-bold ${edgeColor(row.edge)}`}>
                  {row.edge.toUpperCase()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TeamAnalysisPage() {
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
  const [data, setData] = useState<TeamAnalysisResponse | null>(null);
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
    fetchApi<TeamAnalysisResponse>(`/api/leagues/${selectedLeague}/team-analysis`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [selectedLeague]);

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
            <span className="text-sm font-medium">Team Analysis</span>
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

        {/* League selector */}
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
        </div>

        {leagues.length === 0 && !loading && (
          <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center dark:border-zinc-800 dark:bg-zinc-900">
            <p className="mb-2 text-lg font-medium">No leagues connected</p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Connect your Yahoo account to view team analysis.
            </p>
          </div>
        )}

        {loading && (
          <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>
        )}

        {!loading && data && (
          <>
            {data.error && (
              <p className="mb-4 rounded-lg bg-yellow-50 p-4 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300">
                {data.error}
              </p>
            )}

            {data.categories.length > 0 && (
              <>
                <div className="mb-2">
                  <span className="text-xs text-zinc-400 uppercase tracking-wider">
                    {data.my_team.team_name}
                  </span>
                  <span className="ml-2 text-xs text-zinc-500">
                    {data.league_format === "head" ? "Head-to-Head" : "Rotisserie"} &middot;{" "}
                    {data.num_teams} teams
                  </span>
                </div>

                <SummaryCards categories={data.categories} />

                <div className="grid grid-cols-1 gap-8 lg:grid-cols-2 mb-8">
                  <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
                    <h2 className="text-sm font-semibold mb-4 text-zinc-600 dark:text-zinc-300">
                      Category Radar
                    </h2>
                    <RadarChart categories={data.categories} numTeams={data.num_teams} />
                    <p className="mt-2 text-center text-xs text-zinc-500">
                      Teal = your team &middot; Dashed = league avg
                    </p>
                  </div>

                  <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
                    <h2 className="text-sm font-semibold mb-4 text-zinc-600 dark:text-zinc-300">
                      Category Breakdown
                    </h2>
                    <CategoryTable
                      categories={data.categories}
                      leagueFormat={data.league_format}
                    />
                  </div>
                </div>

                {data.current_matchup && (
                  <H2HMatchupPanel matchup={data.current_matchup} />
                )}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
