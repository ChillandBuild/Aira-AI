"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Search } from "lucide-react";
import { API_URL, IntakeSession, api, getAuthHeaders } from "@/lib/api";
import { IntakeTable } from "@/app/dashboard/intake/IntakeTable";
import { ColumnPicker } from "@/app/dashboard/intake/ColumnPicker";
import { deriveColumns } from "@/app/dashboard/intake/columns";

type Filter = "all" | "awaiting_payment" | "paid" | "resolved";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "awaiting_payment", label: "Awaiting Payment" },
  { key: "paid", label: "Paid" },
];
// Resolved means the astrologer's answer was delivered, so only AstroTamil clients have the tab.
const RESOLVED_FILTER: { key: Filter; label: string } = { key: "resolved", label: "Resolved" };

interface PackageOption {
  key: string;
  name: string;
  amount_paise: number;
}

/** The intake form's answer table, moved here from the old standalone Intake
 * page — Form answers is now one tab of Deals. Board/Insights views over the
 * same payment sessions are superseded by the Deals Board/Insights tabs,
 * which read from `deals` (kept in sync via sync_intake_session). */
export function FormAnswersTab() {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<IntakeSession[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());
  const [packages, setPackages] = useState<PackageOption[]>([]);
  const [astroConnected, setAstroConnected] = useState(false);
  const filters = astroConnected ? [...FILTERS, RESOLVED_FILTER] : FILTERS;

  const columns = useMemo(() => deriveColumns(rows), [rows]);
  const visibleKeys = useMemo(
    () => new Set(columns.filter((c) => !hiddenKeys.has(c.key)).map((c) => c.key)),
    [columns, hiddenKeys]
  );

  const loadFirstPage = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const page = await api.intake.listSessions({ status: filter, q: query || undefined });
      setRows(page.data);
      setCursor(page.next_cursor);
      setAstroConnected(Boolean(page.astro_connected));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [filter, query]);

  useEffect(() => {
    loadFirstPage();
  }, [loadFirstPage]);

  useEffect(() => {
    (async () => {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, { headers: auth });
      if (res.ok) {
        const config = await res.json();
        setPackages(config.packages ?? []);
      }
    })();
  }, []);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.intake.listSessions({
        status: filter,
        q: query || undefined,
        cursor,
      });
      setRows((prev) => [...prev, ...page.data]);
      setCursor(page.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, filter, loadingMore, query]);

  async function handleChangePackage(sessionId: string, packageKey: string) {
    await api.intake.changePackage(sessionId, packageKey);
    loadFirstPage();
  }

  async function downloadCsv() {
    const auth = await getAuthHeaders();
    const res = await fetch(`${API_URL}${api.intake.csvPath({ status: filter, q: query || undefined })}`, {
      headers: auth,
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `intake-${filter}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
        <div className="flex gap-1">
          {filters.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`rounded-lg px-3 py-1.5 font-label text-xs font-bold transition-all ${
                filter === key
                  ? "bg-primary/10 text-primary"
                  : "text-ink-secondary hover:bg-surface-mid"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 rounded-xl border border-border px-3 py-2">
          <Search size={14} className="text-ink-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name or phone"
            className="min-w-[240px] border-0 bg-transparent font-body text-sm outline-none placeholder:text-ink-muted"
          />
        </div>

        <div className="ml-auto flex items-center gap-2">
          <ColumnPicker columns={columns} hiddenKeys={hiddenKeys} onChange={setHiddenKeys} />
          <button
            type="button"
            onClick={downloadCsv}
            className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 font-label text-xs font-bold text-white hover:bg-primary/90"
          >
            <Download size={12} /> Download CSV
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="space-y-3 p-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded-xl bg-border-subtle" />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="font-body text-sm text-ink-muted">Could not load form answers.</p>
            <button
              type="button"
              onClick={loadFirstPage}
              className="rounded-xl bg-primary px-4 py-2 font-label text-xs font-bold text-white hover:bg-primary/90"
            >
              Retry
            </button>
          </div>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center font-body text-sm text-ink-muted">
            {query ? "No leads match that search." : "No intake leads yet."}
          </p>
        ) : (
          <IntakeTable
            rows={rows}
            columns={columns}
            visibleKeys={visibleKeys}
            packages={packages}
            hasMore={Boolean(cursor)}
            loadingMore={loadingMore}
            onLoadMore={loadMore}
            onChangePackage={handleChangePackage}
          />
        )}
      </div>
    </div>
  );
}
