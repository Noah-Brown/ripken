"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";
import type { LeagueInfo } from "@/lib/api";

interface RosterPlayer {
  player_id: number | null;
  player_name: string;
  team: string | null;
  owner: string;
  is_current_user: boolean;
}

interface LeagueRostersResponse {
  league_name: string;
  teams: {
    yahoo_team_key: string;
    team_name: string;
    is_current_user: boolean;
  }[];
  positions: Record<string, RosterPlayer[]>;
}

export default function LeaguePage() {
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
  const [data, setData] = useState<LeagueRostersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<"player" | "owner">("player");
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    fetchApi<{ leagues: LeagueInfo[] }>("/api/leagues")
      .then((res) => {
        setLeagues(res.leagues);
        if (res.leagues.length > 0) setSelectedLeague(res.leagues[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedLeague) return;
    setError(null);
    fetchApi<LeagueRostersResponse>(
      `/api/league/${selectedLeague}/rosters`
    )
      .then(setData)
      .catch((e) => setError(e.message));
  }, [selectedLeague]);

  function handleSort(col: "player" | "owner") {
    if (sortCol === col) setSortAsc(!sortAsc);
    else {
      setSortCol(col);
      setSortAsc(true);
    }
  }

  function sortPlayers(players: RosterPlayer[]): RosterPlayer[] {
    return [...players].sort((a, b) => {
      const va = sortCol === "player" ? a.player_name : a.owner;
      const vb = sortCol === "player" ? b.player_name : b.owner;
      const cmp = va.localeCompare(vb);
      return sortAsc ? cmp : -cmp;
    });
  }

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
            <span className="text-sm font-medium">League Rosters</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/roster" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Roster</Link>
            <Link href="/bullpen" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Bullpen</Link>
            <Link href="/lineups" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Lineups</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {/* League selector */}
        <div className="mb-6 flex items-center gap-3">
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

        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}

        {!data && !error && (
          <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>
        )}

        {data &&
          Object.entries(data.positions).map(([pos, players]) => (
            <Fragment key={pos}>
              <div className="mt-6 mb-2">
                <h2 className="text-sm font-bold text-zinc-600 dark:text-zinc-300">
                  {pos}{" "}
                  <span className="font-normal text-zinc-400">
                    ({players.length})
                  </span>
                </h2>
              </div>
              <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800 mb-4">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                      <th
                        className="px-3 py-2 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 cursor-pointer select-none"
                        onClick={() => handleSort("player")}
                      >
                        Player
                        {sortCol === "player" && (
                          <span className="ml-0.5">
                            {sortAsc ? "\u25B2" : "\u25BC"}
                          </span>
                        )}
                      </th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        Team
                      </th>
                      <th
                        className="px-3 py-2 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 cursor-pointer select-none"
                        onClick={() => handleSort("owner")}
                      >
                        Owner
                        {sortCol === "owner" && (
                          <span className="ml-0.5">
                            {sortAsc ? "\u25B2" : "\u25BC"}
                          </span>
                        )}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-zinc-900">
                    {sortPlayers(players).map((p, i) => (
                      <tr
                        key={`${p.player_name}-${i}`}
                        className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50"
                      >
                        <td
                          className={`px-3 py-2 text-sm font-medium ${
                            p.is_current_user
                              ? "text-green-600 dark:text-green-400"
                              : ""
                          }`}
                        >
                          {p.player_name}
                        </td>
                        <td className="px-3 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                          {p.team || "\u2014"}
                        </td>
                        <td className="px-3 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                          {p.owner}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Fragment>
          ))}

        {data && Object.keys(data.positions).length === 0 && (
          <p className="text-zinc-500 dark:text-zinc-400">
            No roster data available. League rosters sync hourly.
          </p>
        )}
      </main>
    </div>
  );
}
