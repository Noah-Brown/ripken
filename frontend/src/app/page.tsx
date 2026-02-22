"use client";

import { useEffect, useState } from "react";
import { fetchApi, type GameInfo, type TodayResponse } from "@/lib/api";

function GameCard({ game }: { game: GameInfo }) {
  const away = game.probable_pitchers.away;
  const home = game.probable_pitchers.home;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-2 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
        <span>{game.venue}</span>
        <span className="rounded bg-zinc-100 px-2 py-0.5 font-medium dark:bg-zinc-800">
          {game.status}
        </span>
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
        <div className="text-right">
          <div className="text-lg font-bold">{game.away_team}</div>
          <div className="text-sm text-zinc-500 dark:text-zinc-400">
            {away?.name ?? "TBD"}
          </div>
        </div>
        <div className="px-3 text-center text-xs font-medium text-zinc-400">
          {game.game_time
            ? new Date(game.game_time).toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit",
              })
            : "@"}
        </div>
        <div className="text-left">
          <div className="text-lg font-bold">{game.home_team}</div>
          <div className="text-sm text-zinc-500 dark:text-zinc-400">
            {home?.name ?? "TBD"}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [data, setData] = useState<TodayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchApi<TodayResponse>("/api/today")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <h1 className="text-2xl font-bold tracking-tight">Ripken</h1>
          <span className="text-sm text-zinc-500 dark:text-zinc-400">
            Fantasy Baseball Dashboard
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <h2 className="mb-6 text-xl font-semibold">
          Today&apos;s Games{" "}
          {data && (
            <span className="text-base font-normal text-zinc-500 dark:text-zinc-400">
              {data.date}
            </span>
          )}
        </h2>
        {error && (
          <p className="rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}
        {!data && !error && (
          <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>
        )}
        {data && data.games.length === 0 && (
          <p className="text-zinc-500 dark:text-zinc-400">
            No games scheduled today.
          </p>
        )}
        {data && data.games.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.games.map((game) => (
              <GameCard key={game.game_id} game={game} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
