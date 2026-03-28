"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { fetchApi, type GameInfo, type TodayResponse } from "@/lib/api";

interface AlertItem {
  id: number;
  player_id: number | null;
  alert_type: string;
  message: string;
  is_read: boolean;
  created_at: string | null;
}

interface AlertsResponse {
  alerts: AlertItem[];
  unread_count: number;
}

const alertTypeIcon: Record<string, string> = {
  callup: "↑",
  il_move: "🏥",
  role_change: "↔",
  lineup_posted: "✓",
  unexpected_bench: "⚠",
  dropped_in_league: "↓",
  hot_streak: "🔥",
};

function AlertFeed({ alerts, onDismiss }: { alerts: AlertItem[]; onDismiss: (id: number) => void }) {
  if (alerts.length === 0) return null;

  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
          Alerts
        </h3>
      </div>
      <div className="space-y-2">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className="flex items-start justify-between rounded-lg border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
          >
            <div className="flex items-start gap-3">
              <span className="text-sm">{alertTypeIcon[alert.alert_type] ?? "•"}</span>
              <div>
                <p className="text-sm">{alert.message}</p>
                {alert.created_at && (
                  <p className="mt-0.5 text-xs text-zinc-400 dark:text-zinc-500">
                    {new Date(alert.created_at).toLocaleString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={() => onDismiss(alert.id)}
              className="ml-2 text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

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

function HomeContent() {
  const [data, setData] = useState<TodayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [yahooConnected, setYahooConnected] = useState<boolean | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const searchParams = useSearchParams();
  const justConnected = searchParams.get("yahoo_connected") === "1";

  useEffect(() => {
    fetchApi<TodayResponse>("/api/today")
      .then(setData)
      .catch((e) => setError(e.message));

    fetchApi<{ connected: boolean }>("/auth/yahoo/status")
      .then((res) => setYahooConnected(res.connected))
      .catch(() => setYahooConnected(false));

    fetchApi<AlertsResponse>("/api/alerts?unread_only=true&limit=10")
      .then((res) => {
        setAlerts(res.alerts);
        setUnreadCount(res.unread_count);
      })
      .catch(() => {});
  }, []);

  const dismissAlert = async (id: number) => {
    try {
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/alerts/${id}/read`,
        { method: "POST" }
      );
      setAlerts((prev) => prev.filter((a) => a.id !== id));
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {}
  };

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <h1 className="text-2xl font-bold tracking-tight">Ripken</h1>
          <div className="flex items-center gap-4">
            {unreadCount > 0 && (
              <span className="relative flex items-center">
                <span className="rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-bold text-white">
                  {unreadCount}
                </span>
              </span>
            )}
            {yahooConnected && (
              <>
                <Link href="/roster" className="text-sm font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300">
                  Roster
                </Link>
                <Link href="/lineups" className="text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
                  Lineups
                </Link>
                <Link href="/pitching" className="text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
                  Pitching
                </Link>
                <Link href="/bullpen" className="text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
                  Bullpen
                </Link>
                <Link href="/prospects" className="text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
                  Prospects
                </Link>
              </>
            )}
            <span className="text-sm text-zinc-500 dark:text-zinc-400">
              Fantasy Baseball Dashboard
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        {/* Yahoo connection status */}
        {justConnected && (
          <div className="mb-6 rounded-lg bg-green-50 p-4 text-green-700 dark:bg-green-950 dark:text-green-300">
            Yahoo account connected successfully! Your leagues and rosters are syncing.
          </div>
        )}
        {yahooConnected === false && (
          <div className="mb-6 flex items-center justify-between rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
            <div>
              <p className="font-medium">Connect Yahoo Fantasy</p>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Link your Yahoo account to see your roster and league data.
              </p>
            </div>
            <a
              href="http://localhost:8000/auth/yahoo"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
            >
              Connect Yahoo
            </a>
          </div>
        )}

        {/* Alert Feed */}
        <AlertFeed alerts={alerts} onDismiss={dismissAlert} />

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

export default function Home() {
  return (
    <Suspense>
      <HomeContent />
    </Suspense>
  );
}
