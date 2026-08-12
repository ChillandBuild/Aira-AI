"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { API_URL, IntakeSession, IntakeStatus, api, getAuthHeaders } from "@/lib/api";
import { IntakeTable } from "./IntakeTable";
import { IntakeDrawer } from "./IntakeDrawer";
import { ColumnPicker } from "./ColumnPicker";
import { deriveColumns } from "./columns";

type Filter = IntakeStatus | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "awaiting_payment", label: "Awaiting Payment" },
  { key: "paid", label: "Paid" },
  { key: "resolved", label: "Resolved" },
];

export default function IntakePage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<IntakeSession[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<IntakeSession | null>(null);
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());

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
    setSelected(null);
    loadFirstPage();
  }, [loadFirstPage]);

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
              onClick={() => setFilter(key)}
              className={`rounded-lg px-3 py-1.5 font-label text-xs font-bold transition-all ${
                filter === key ? "bg-white text-ink shadow-sm" : "text-ink-muted"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

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
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
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
            selectedId={selected?.id ?? null}
            hasMore={Boolean(cursor)}
            loadingMore={loadingMore}
            onSelect={setSelected}
            onLoadMore={loadMore}
          />
        )}
      </div>

      {selected && (
        <IntakeDrawer
          session={selected}
          onClose={() => setSelected(null)}
          onChanged={() => {
            setSelected(null);
            loadFirstPage();
          }}
        />
      )}
    </div>
  );
}
