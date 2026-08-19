"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { API_URL, IntakeSession, api, getAuthHeaders } from "@/lib/api";
import { IntakeTable } from "./IntakeTable";
import { IntakeDashboard } from "./IntakeDashboard";
import { ColumnPicker } from "./ColumnPicker";
import { deriveColumns } from "./columns";

type Filter = "all" | "awaiting_payment" | "paid";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "awaiting_payment", label: "Awaiting Payment" },
  { key: "paid", label: "Paid" },
];

interface PackageOption {
  key: string;
  name: string;
  amount_paise: number;
}

export default function IntakePage() {
  const [filter, setFilter] = useState<Filter>("all");
  // The dashboard is a view over the same tenant's sessions, not a fourth
  // status filter — keeping it out of `filter` means switching to it and back
  // doesn't refetch the table or lose the staff member's place.
  const [view, setView] = useState<"table" | "dashboard">("table");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<IntakeSession[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());
  const [packages, setPackages] = useState<PackageOption[]>([]);

  const columns = useMemo(() => deriveColumns(rows), [rows]);
  const visibleKeys = useMemo(
    () => new Set(columns.filter((c) => !hiddenKeys.has(c.key)).map((c) => c.key)),
    [columns, hiddenKeys]
  );

  const loadFirstPage = useCallback(async () => {
    setLoading(true);
    try {
      const page = await api.intake.listSessions({ status: filter, q: query || undefined });
      setRows(page.data);
      setCursor(page.next_cursor);
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

  async function handleResolve(sessionId: string) {
    await api.intake.resolveSession(sessionId);
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
      <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
        <h1 className="font-display text-lg font-bold text-ink">Intake</h1>

        <div className="flex gap-1 rounded-xl border border-border bg-surface-subtle p-1">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                setFilter(key);
                setView("table");
              }}
              className={`rounded-lg px-3 py-1.5 font-label text-xs font-bold transition-all ${
                view === "table" && filter === key ? "bg-white text-ink shadow-sm" : "text-ink-muted"
              }`}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setView("dashboard")}
            className={`rounded-lg px-3 py-1.5 font-label text-xs font-bold transition-all ${
              view === "dashboard" ? "bg-white text-ink shadow-sm" : "text-ink-muted"
            }`}
          >
            Dashboard
          </button>
        </div>

        {view === "table" && (
          <>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name or phone"
              className="rounded-xl border border-border px-3 py-2 font-body text-sm"
            />

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
          </>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {view === "dashboard" ? (
          <IntakeDashboard />
        ) : loading ? (
          <div className="space-y-3 p-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded-xl bg-border-subtle" />
            ))}
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
            onResolve={handleResolve}
          />
        )}
      </div>
    </div>
  );
}
