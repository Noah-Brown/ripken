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
  fv: number | null;
  scouting_report: string | null;
  video_url: string | null;
  trend: string | null;
  redraft_rank: number | null;
  age: string | null;
  height: string | null;
  weight: string | null;
  bats: string | null;
  throws: string | null;
}

interface ProspectsResponse {
  prospects: ProspectEntry[];
}

interface MilbStatsLevel {
  level: string;
  sport_id: number;
  hitting: {
    avg: string; ops: string; hr: number; sb: number;
    k_pct: string; bb_pct: string; pa: number; games: number;
  } | null;
  pitching: {
    era: string; whip: string; k_per_9: string; bb_per_9: string;
    ip: string; games: number;
  } | null;
}

interface MilbStatsResponse {
  player_id: number;
  mlb_id: number | null;
  season: number;
  stats: MilbStatsLevel[];
  cached?: boolean;
  error?: string;
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

function FvBadge({ fv }: { fv: number | null }) {
  if (fv == null) return <span className="text-xs text-zinc-400">—</span>;
  const intensity =
    fv >= 70
      ? "bg-indigo-600 text-white"
      : fv >= 55
        ? "bg-indigo-500 text-white"
        : fv >= 45
          ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300"
          : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${intensity}`}>
      FV {fv}
    </span>
  );
}

function ProspectRow({ p, onClick }: { p: ProspectEntry; onClick: () => void }) {
  const signal = signalColors[p.signal];

  return (
    <tr
      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
      onClick={onClick}
    >
      <td className="px-3 py-3 text-center">
        <span className="text-sm font-mono text-zinc-400">
          {p.user_rank ?? p.fangraphs_rank ?? "—"}
        </span>
      </td>
      <td className="px-3 py-3">
        <FvBadge fv={p.fv} />
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
        <BuzzBadge count={p.buzz.length} />
      </td>
    </tr>
  );
}

function ProspectDetailPanel({
  prospect,
  onClose,
}: {
  prospect: ProspectEntry;
  onClose: () => void;
}) {
  const [stats, setStats] = useState<MilbStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const signal = signalColors[prospect.signal];

  useEffect(() => {
    setStatsLoading(true);
    fetchApi<MilbStatsResponse>(`/api/prospects/${prospect.prospect_id}/stats`)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, [prospect.prospect_id]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEsc);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleEsc);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const factorLabels: Record<string, string> = {
    performance: "Performance",
    roster_need: "Roster Need",
    proximity: "Proximity",
    forty_man: "40-Man",
    service_time: "Service Time",
    buzz: "Buzz",
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30 dark:bg-black/50"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative w-full max-w-2xl overflow-y-auto bg-white shadow-xl dark:bg-zinc-900 animate-slide-in">
        {/* Header */}
        <div className="sticky top-0 z-10 border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900">
          <button
            onClick={onClose}
            className="absolute right-4 top-4 rounded-lg p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>

          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold">{prospect.full_name}</h2>
            <FvBadge fv={prospect.fv} />
          </div>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            {[prospect.position, prospect.org, prospect.level, prospect.eta ? `ETA ${prospect.eta}` : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>

        <div className="space-y-6 px-6 py-5">
          {/* Physical Profile */}
          {(prospect.age || prospect.height || prospect.weight || prospect.bats) && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-lg bg-zinc-50 px-4 py-2.5 text-sm text-zinc-600 dark:bg-zinc-800/50 dark:text-zinc-400">
              {prospect.age && <span>Age: <span className="font-medium text-zinc-800 dark:text-zinc-200">{prospect.age}</span></span>}
              {prospect.height && <span>Ht: <span className="font-medium text-zinc-800 dark:text-zinc-200">{prospect.height}</span></span>}
              {prospect.weight && <span>Wt: <span className="font-medium text-zinc-800 dark:text-zinc-200">{prospect.weight} lbs</span></span>}
              {(prospect.bats || prospect.throws) && (
                <span>B/T: <span className="font-medium text-zinc-800 dark:text-zinc-200">{prospect.bats ?? "?"}/{prospect.throws ?? "?"}</span></span>
              )}
            </div>
          )}

          {/* Signal Score */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${signal.dot}`} />
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${signal.bg} ${signal.text}`}>
                {signal.label} {prospect.signal_score}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(prospect.factors).map(([key, value]) => (
                <div key={key} className="rounded-md bg-zinc-50 px-3 py-2 dark:bg-zinc-800/50">
                  <div className="text-[10px] text-zinc-500 dark:text-zinc-400">{factorLabels[key] ?? key}</div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-zinc-200 dark:bg-zinc-700">
                      <div
                        className="h-1.5 rounded-full bg-indigo-500"
                        style={{ width: `${value}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-zinc-500">{value}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* MiLB Stats */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              MiLB Stats ({new Date().getFullYear()} Season)
            </h3>
            {statsLoading ? (
              <p className="text-sm text-zinc-400">Loading stats...</p>
            ) : stats?.error ? (
              <p className="text-sm text-zinc-400">{stats.error}</p>
            ) : stats && stats.stats.length > 0 ? (
              <div className="space-y-3">
                {stats.stats.map((level) => (
                  <div key={level.sport_id}>
                    <div className="mb-1 text-[10px] font-semibold text-zinc-500 dark:text-zinc-400">{level.level}</div>
                    {level.hitting && (
                      <div className="grid grid-cols-4 gap-2">
                        {([
                          ["AVG", level.hitting.avg],
                          ["OPS", level.hitting.ops],
                          ["HR", level.hitting.hr],
                          ["SB", level.hitting.sb],
                          ["K%", level.hitting.k_pct],
                          ["BB%", level.hitting.bb_pct],
                          ["PA", level.hitting.pa],
                          ["G", level.hitting.games],
                        ] as [string, string | number][]).map(([label, val]) => (
                          <div key={label} className="rounded-md bg-zinc-50 px-2 py-1.5 text-center dark:bg-zinc-800/50">
                            <div className="text-sm font-bold">{val}</div>
                            <div className="text-[9px] text-zinc-400">{label}</div>
                          </div>
                        ))}
                      </div>
                    )}
                    {level.pitching && (
                      <div className="grid grid-cols-3 gap-2">
                        {([
                          ["ERA", level.pitching.era],
                          ["WHIP", level.pitching.whip],
                          ["K/9", level.pitching.k_per_9],
                          ["BB/9", level.pitching.bb_per_9],
                          ["IP", level.pitching.ip],
                          ["G", level.pitching.games],
                        ] as [string, string | number][]).map(([label, val]) => (
                          <div key={label} className="rounded-md bg-zinc-50 px-2 py-1.5 text-center dark:bg-zinc-800/50">
                            <div className="text-sm font-bold">{val}</div>
                            <div className="text-[9px] text-zinc-400">{label}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-400">No minor league stats available</p>
            )}
          </div>

          {/* Scouting Report */}
          {prospect.scouting_report && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Scouting Report
              </h3>
              <div className="max-h-96 overflow-y-auto rounded-lg bg-zinc-50 px-4 py-3 text-sm leading-relaxed text-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-300">
                {prospect.scouting_report.split("\n").map((paragraph, i) => (
                  <p key={i} className={i > 0 ? "mt-3" : ""}>
                    {paragraph}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Buzz */}
          {prospect.buzz.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Recent Buzz
              </h3>
              <BuzzTooltip items={prospect.buzz} />
            </div>
          )}

          {/* Video */}
          {prospect.video_url && (
            <div>
              <a
                href={prospect.video_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Watch Video
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ProspectsPage() {
  const [data, setData] = useState<ProspectsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selectedProspect, setSelectedProspect] = useState<ProspectEntry | null>(null);
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
      alert(`Imported ${result.imported}, updated ${result.updated ?? 0}, skipped ${result.skipped}`);
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
      <style jsx global>{`
        @keyframes slide-in {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in {
          animation: slide-in 0.2s ease-out;
        }
      `}</style>
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
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">FV</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Signal</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Player</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Org</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Level</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 w-16">40-Man</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-20">ETA</th>
                  <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-24">Buzz</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-zinc-900">
                {prospects.map((p) => (
                  <ProspectRow
                    key={p.prospect_id}
                    p={p}
                    onClick={() => setSelectedProspect(p)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedProspect && (
          <ProspectDetailPanel
            prospect={selectedProspect}
            onClose={() => setSelectedProspect(null)}
          />
        )}
      </main>
    </div>
  );
}
