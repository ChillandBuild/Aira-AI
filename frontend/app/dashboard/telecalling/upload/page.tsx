"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Upload, Download, FileText, Loader2 } from "lucide-react";
import { getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "https://aira-ai-5tfr.onrender.com";

// ─── Types ───────────────────────────────────────────────────────────────────

interface UploadResult {
  batch_id: string;
  total: number;
  inserted: number;
  duplicates: number;
  assigned: number;
}

interface HistoryItem {
  id: string;
  file_name: string;
  total_contacts: number;
  inserted: number;
  duplicates: number;
  assigned: number;
  segment_override: string | null;
  created_at: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Kolkata",
  }).format(d);
}

const SEGMENT_OPTIONS = [
  { value: "", label: "None (auto)" },
  { value: "A", label: "A" },
  { value: "B", label: "B" },
  { value: "C", label: "C" },
  { value: "D", label: "D" },
];

// ─── Page ────────────────────────────────────────────────────────────────────

export default function TelecallingUploadPage() {
  // Upload state
  const [file, setFile] = useState<File | null>(null);
  const [segmentOverride, setSegmentOverride] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // History state
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const LIMIT = 20;

  // ── Fetch history ──────────────────────────────────────────────────────────

  const fetchHistory = useCallback(
    async (p: number) => {
      try {
        setHistoryLoading(true);
        const headers = await getAuthHeaders();
        const res = await fetch(
          `${API_URL}/api/v1/telecalling-upload/history?page=${p}&limit=${LIMIT}`,
          { headers }
        );
        if (!res.ok) throw new Error("Failed to load history");
        const data: HistoryItem[] = await res.json();
        setHistory(data);
        setHasMore(data.length === LIMIT);
      } catch {
        setHistory([]);
      } finally {
        setHistoryLoading(false);
      }
    },
    [LIMIT]
  );

  useEffect(() => {
    fetchHistory(page);
  }, [page, fetchHistory]);

  // ── Upload handler ─────────────────────────────────────────────────────────

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    setUploadError(null);

    try {
      const headers = await getAuthHeaders();
      const fd = new FormData();
      fd.append("file", file);
      if (segmentOverride) fd.append("segment_override", segmentOverride);

      const res = await fetch(
        `${API_URL}/api/v1/telecalling-upload/upload`,
        {
          method: "POST",
          body: fd,
          headers: { ...headers },
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || `Upload failed (${res.status})`);
      }

      const result: UploadResult = await res.json();
      setUploadResult(result);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      // Refresh history
      fetchHistory(1);
      setPage(1);
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  // ── CSV download handler ───────────────────────────────────────────────────

  async function handleDownloadCsv(batchId: string, fileName: string) {
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(
        `${API_URL}/api/v1/telecalling-upload/history/${batchId}/csv`,
        { headers }
      );
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `assignments_${fileName}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      alert("Failed to download CSV. Please try again.");
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
          <Upload size={18} />
        </div>
        <div>
          <h1 className="font-display text-lg font-bold text-tertiary">
            Telecalling Upload
          </h1>
          <p className="text-xs text-ink-secondary">
            Upload CSV contacts for telecalling assignment
          </p>
        </div>
      </div>

      {/* ── Upload Card ───────────────────────────────────────────────────── */}
      <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
        <h2 className="font-display text-base font-bold text-tertiary mb-4">
          Upload Contacts
        </h2>

        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-end">
          {/* File input */}
          <div className="flex-1 min-w-0">
            <label className="block text-xs font-medium text-ink-secondary mb-1.5">
              CSV File
            </label>
            <div
              className={cn(
                "relative flex items-center gap-2 rounded-lg border border-dashed px-3 py-2.5 transition cursor-pointer",
                file
                  ? "border-indigo-300 bg-indigo-50/50"
                  : "border-slate-200 bg-surface-low hover:border-slate-300"
              )}
              onClick={() => fileRef.current?.click()}
            >
              <FileText size={16} className="shrink-0 text-ink-muted" />
              <span className="truncate text-sm text-ink-secondary">
                {file ? file.name : "Choose a .csv file..."}
              </span>
              <input
                ref={fileRef}
                type="file"
                accept=".csv"
                className="absolute inset-0 opacity-0 cursor-pointer"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setUploadResult(null);
                  setUploadError(null);
                }}
              />
            </div>
          </div>

          {/* Segment override */}
          <div className="w-full sm:w-44">
            <label className="block text-xs font-medium text-ink-secondary mb-1.5">
              Segment Override
            </label>
            <select
              value={segmentOverride}
              onChange={(e) => setSegmentOverride(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-surface-low px-3 py-2.5 text-sm text-ink outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
            >
              {SEGMENT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Upload button */}
          <button
            disabled={!file || uploading}
            onClick={handleUpload}
            className="bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 whitespace-nowrap transition"
          >
            {uploading ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload size={14} />
                Upload
              </>
            )}
          </button>
        </div>

        {/* Success banner */}
        {uploadResult && (
          <div className="mt-4 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-800 flex flex-wrap gap-x-6 gap-y-1">
            <span className="font-semibold">Upload successful</span>
            <span>
              Inserted: <strong>{uploadResult.inserted}</strong>
            </span>
            <span>
              Duplicates: <strong>{uploadResult.duplicates}</strong>
            </span>
            <span>
              Assigned: <strong>{uploadResult.assigned}</strong>
            </span>
          </div>
        )}

        {/* Error banner */}
        {uploadError && (
          <div className="mt-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {uploadError}
          </div>
        )}
      </div>

      {/* ── History Card ──────────────────────────────────────────────────── */}
      <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
        <h2 className="font-display text-base font-bold text-tertiary mb-4">
          Upload History
        </h2>

        {historyLoading && history.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-ink-muted">
            <Loader2 size={20} className="animate-spin mr-2" />
            Loading...
          </div>
        ) : history.length === 0 ? (
          <div className="text-center py-12 text-ink-muted text-sm">
            No uploads yet. Upload a CSV above to get started.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-ink-muted">
                    <th className="pb-2 pr-4 font-medium">File Name</th>
                    <th className="pb-2 pr-4 font-medium">Date</th>
                    <th className="pb-2 pr-4 font-medium text-right">Total</th>
                    <th className="pb-2 pr-4 font-medium text-right">Inserted</th>
                    <th className="pb-2 pr-4 font-medium text-right">Duplicates</th>
                    <th className="pb-2 pr-4 font-medium text-right">Assigned</th>
                    <th className="pb-2 pr-4 font-medium">Segment</th>
                    <th className="pb-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr
                      key={item.id}
                      className="border-b border-slate-100 last:border-0"
                    >
                      <td className="py-2.5 pr-4">
                        <div className="flex items-center gap-1.5">
                          <FileText
                            size={13}
                            className="shrink-0 text-ink-muted"
                          />
                          <span className="truncate max-w-[180px] font-medium text-ink">
                            {item.file_name}
                          </span>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 text-ink-secondary whitespace-nowrap">
                        {formatDate(item.created_at)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-ink">
                        {item.total_contacts}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-emerald-600">
                        {item.inserted}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-amber-600">
                        {item.duplicates}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-indigo-600">
                        {item.assigned}
                      </td>
                      <td className="py-2.5 pr-4">
                        {item.segment_override ? (
                          <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-indigo-50 text-indigo-700">
                            {item.segment_override}
                          </span>
                        ) : (
                          <span className="text-ink-muted">Auto</span>
                        )}
                      </td>
                      <td className="py-2.5">
                        <button
                          onClick={() =>
                            handleDownloadCsv(item.id, item.file_name)
                          }
                          className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 font-medium transition"
                        >
                          <Download size={12} />
                          <span>Download CSV</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
              <span className="text-xs text-ink-muted">
                Page {page}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-ink-secondary hover:bg-surface-low disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  Previous
                </button>
                <button
                  disabled={!hasMore}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-ink-secondary hover:bg-surface-low disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
