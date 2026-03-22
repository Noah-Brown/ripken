"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ProspectFactors {
  performance: number;
  roster_need: number;
  proximity: number;
  forty_man: number;
  service_time: number;
  buzz: number;
}

interface BuzzItem {
  source: string;
  title: string;
  url: string;
  snippet: string | null;
  published_at: string | null;
}

interface ProspectEntry {
  prospect_id: number;
  player_id: number;
  full_name: string;
  org: string;
  level: string | null;
  position: string | null;
  user_rank: number | null;
  fangraphs_rank: number | null;
  eta: string | null;
  on_40_man: boolean;
  scouting_notes: string | null;
  minor_league_stats: Record<string, unknown> | null;
  signal_score: number;
  signal: "hot" | "warm" | "cold";
  factors: ProspectFactors;
  buzz: BuzzItem[];
}

interface ProspectsResponse {
  prospects: ProspectEntry[];
}

const signalColors = {
  hot: {
    bg: "bg-red-100 dark:bg-red-950",
    text: "text-red-700 dark:text-red-300",
    dot: "bg-red-500",
    label: "HOT",
  },
  warm: {
    bg: "bg-amber-100 dark:bg-amber-950",
    text: "text-amber-700 dark:text-amber-300",
    dot: "bg-amber-500",
    label: "WARM",
  },
  cold: {
    bg: "bg-blue-100 dark:bg-blue-950",
    text: "text-blue-700 dark:text-blue-300",
    dot: "bg-blue-500",
    label: "COLD",
  },
};

function BuzzBadge({ count }: { count: number }) {
  if (count === 0) return <span className="text-xs text-zinc-400">—</span>;
  const intensity = count >= 4 ? "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300"
    : count >= 2 ? "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300"
    : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${intensity}`}>
      {count} {count === 1 ? "article" : "articles"}
    </span>
  );
}

function BuzzTooltip({ items }: { items: BuzzItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-2 space-y-2">
      {items.map((b, i) => (
        <div key={i} className="rounded-md border border-purple-200 bg-purple-50 px-3 py-2 dark:border-purple-900 dark:bg-purple-950/50">
          <a
            href={b.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-medium text-purple-700 hover:underline dark:text-purple-300"
          >
            {b.title}
          </a>
          <div className="mt-0.5 flex items-center gap-2 text-[10px] text-zinc-500 dark:text-zinc-400">
            <span>{b.source}</span>
            {b.published_at && (
              <span>{new Date(b.published_at).toLocaleDateString()}</span>
            )}
          </div>
          {b.snippet && (
            <p className="mt-1 text-[11px] leading-relaxed text-zinc-600 dark:text-zinc-400">
              {b.snippet}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function ProspectRow({ p }: { p: ProspectEntry }) {
  const signal = signalColors[p.signal];
  const [showBuzz, setShowBuzz] = useState(false);

  return (
    <>
      <tr className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50">
        <td className="px-3 py-3 text-center">
          <span className="text-sm font-mono text-zinc-400">
            {p.user_rank ?? p.fangraphs_rank ?? "—"}
          </span>
        </td>
        <td className="px-3 py-3">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${signal.dot}`} />
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${signal.bg} ${signal.text}`}>
              {p.signal_score}
            </span>
          </div>
        </td>
        <td className="px-3 py-3">
          <div>
            <span className="font-medium">{p.full_name}</span>
            {p.position && (
              <span className="ml-1.5 text-xs text-zinc-400">{p.position}</span>
            )}
          </div>
          {p.scouting_notes && (
            <div className="mt-0.5 text-xs text-zinc-400 dark:text-zinc-500 truncate max-w-xs">
              {p.scouting_notes}
            </div>
          )}
        </td>
        <td className="px-3 py-3 text-xs text-zinc-500">{p.org}</td>
        <td className="px-3 py-3 text-xs text-zinc-500">{p.level ?? "—"}</td>
        <td className="px-3 py-3 text-center">
          {p.on_40_man ? (
            <span className="text-xs font-medium text-green-600 dark:text-green-400">Yes</span>
          ) : (
            <span className="text-xs text-zinc-400">No</span>
          )}
        </td>
        <td className="px-3 py-3 text-xs text-zinc-500">{p.eta ?? "—"}</td>
        <td className="px-3 py-3">
          {p.minor_league_stats && (
            <div className="flex gap-2 text-xs text-zinc-500">
              {p.minor_league_stats.ops != null && (
                <span>OPS <span className="font-mono">{String(p.minor_league_stats.ops)}</span></span>
              )}
              {p.minor_league_stats.era != null && (
                <span>ERA <span className="font-mono">{String(p.minor_league_stats.era)}</span></span>
              )}
              {p.minor_league_stats.hr != null && (
                <span>HR <span className="font-mono">{String(p.minor_league_stats.hr)}</span></span>
              )}
              {p.minor_league_stats.sb != null && (
                <span>SB <span className="font-mono">{String(p.minor_league_stats.sb)}</span></span>
              )}
            </div>
          )}
        </td>
        <td className="px-3 py-3">
          {p.buzz.length > 0 ? (
            <button onClick={() => setShowBuzz(!showBuzz)} className="cursor-pointer">
              <BuzzBadge count={p.buzz.length} />
            </button>
          ) : (
            <BuzzBadge count={0} />
          )}
        </td>
      </tr>
      {showBuzz && p.buzz.length > 0 && (
        <tr>
          <td colSpan={9} className="px-6 pb-3 bg-zinc-50 dark:bg-zinc-900/50">
            <BuzzTooltip items={p.buzz} />
          </td>
        </tr>
      )}
    </>
  );
}

export default function ProspectsPage() {
  const [data, setData] = useState<ProspectsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadData = () => {
    setLoading(true);
    fetchApi<ProspectsResponse>("/api/prospects")
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleImport = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/api/prospects/import`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      const result = await res.json();
      alert(`Imported ${result.imported} prospects, skipped ${result.skipped}`);
      loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const prospects = data?.prospects ?? [];

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-2xl font-bold tracking-tight hover:opacity-80">Ripken</Link>
            <span className="text-sm text-zinc-400 dark:text-zinc-500">/</span>
            <span className="text-sm font-medium">Prospect Board</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/roster" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Roster</Link>
            <Link href="/waivers" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Waivers</Link>
            <Link href="/bullpen" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Bullpen</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>
        )}

        {/* Import CSV */}
        <div className="mb-6 flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="text-sm text-zinc-500 file:mr-3 file:rounded-lg file:border-0 file:bg-zinc-100 file:px-4 file:py-2 file:text-sm file:font-medium dark:file:bg-zinc-800 dark:file:text-zinc-300"
          />
          <button
            onClick={handleImport}
            disabled={uploading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {uploading ? "Importing..." : "Import CSV"}
          </button>
        </div>

        {/* Legend */}
        <div className="mb-4 flex gap-4 text-xs text-zinc-500 dark:text-zinc-400">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-red-500" /> Hot (70+)
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-amber-500" /> Warm (40-69)
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-blue-500" /> Cold (&lt;40)
          </span>
        </div>

        {loading && <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>}

        {!loading && prospects.length === 0 && (
          <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center dark:border-zinc-800 dark:bg-zinc-900">
            <p className="mb-2 text-lg font-medium">No prospects on watchlist</p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Import a FanGraphs prospect CSV to get started.
            </p>
          </div>
        )}

        {!loading && prospects.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                  <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 w-12">Rank</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Signal</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Player</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Org</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Level</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 w-16">40-Man</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-20">ETA</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">MiLB Stats</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-24">Buzz</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-zinc-900">
                {prospects.map((p) => (
                  <ProspectRow key={p.prospect_id} p={p} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
