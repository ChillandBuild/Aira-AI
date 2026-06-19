"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Upload,
  Download,
  FileText,
  Loader2,
  Plus,
  Pencil,
  Trash2,
  Eye,
  ChevronRight,
  X,
  GripVertical,
  GitBranch,
  Star,
  ToggleLeft,
  ToggleRight,
  Check,
  CloudUpload,
} from "lucide-react";
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

interface Branch {
  label: string;
  goto: number;
}

interface Step {
  order: number;
  text: string;
  note?: string;
  branches?: Branch[];
}

interface CallScript {
  id: string;
  name: string;
  segment: string | null;
  steps: Step[];
  is_default: boolean;
  active: boolean;
  created_at: string;
}

type FormStep = { text: string; note: string; branches: Branch[] };

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Kolkata",
  }).format(new Date(dateStr));
}

async function toCsvFile(file: File): Promise<File> {
  const lower = file.name.toLowerCase();
  if (!lower.endsWith(".xlsx") && !lower.endsWith(".xls")) return file;
  // @ts-expect-error xlsx types
  const XLSX = await import("xlsx");
  const wb = XLSX.read(await file.arrayBuffer(), { type: "array" });
  const ws = wb.Sheets[wb.SheetNames[0]];
  if (!ws) throw new Error("The spreadsheet has no sheets");
  const csv = XLSX.utils.sheet_to_csv(ws, { blankrows: false, rawNumbers: false });
  return new File([csv], file.name.replace(/\.(xlsx|xls)$/i, ".csv"), { type: "text/csv" });
}

function emptyFormStep(): FormStep {
  return { text: "", note: "", branches: [] };
}

function stepsToForm(steps: Step[]): FormStep[] {
  if (!steps.length) return [emptyFormStep()];
  return steps
    .sort((a, b) => a.order - b.order)
    .map((s) => ({ text: s.text, note: s.note ?? "", branches: s.branches ?? [] }));
}

function formToSteps(form: FormStep[]): Step[] {
  return form.map((f, i) => ({
    order: i + 1,
    text: f.text,
    ...(f.note ? { note: f.note } : {}),
    ...(f.branches.length ? { branches: f.branches } : {}),
  }));
}

// ─── Script API helpers ──────────────────────────────────────────────────────

async function fetchScripts(): Promise<CallScript[]> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_URL}/api/v1/call-scripts`, {
      headers: { "Content-Type": "application/json", ...headers },
    });
    if (!res.ok) return [];
    const raw = await res.json();
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

async function apiCreateScript(body: {
  name: string;
  segment?: string | null;
  steps: Step[];
  is_default: boolean;
}): Promise<CallScript> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/call-scripts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Create failed" }));
    throw new Error(err.detail || "Create failed");
  }
  return res.json();
}

async function apiUpdateScript(
  id: string,
  body: Partial<{ name: string; segment: string | null; steps: Step[]; is_default: boolean; active: boolean }>
): Promise<CallScript> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/call-scripts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Update failed" }));
    throw new Error(err.detail || "Update failed");
  }
  return res.json();
}

async function apiDeleteScript(id: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/call-scripts/${id}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", ...headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Delete failed" }));
    throw new Error(err.detail || "Delete failed");
  }
}

// ─── Step Indicator ──────────────────────────────────────────────────────────

const WIZARD_STEPS = ["Upload", "Confirm"];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-start w-full mb-10">
      {WIZARD_STEPS.map((label, i) => {
        const step = i + 1;
        const done = step < current;
        const active = step === current;
        return (
          <div key={label} className="flex-1 flex flex-col items-center relative">
            {i > 0 && (
              <div className={cn("absolute top-5 right-1/2 w-full h-0.5 -translate-y-1/2 transition-colors", done ? "bg-tertiary" : "bg-surface-mid")} />
            )}
            <div className={cn(
              "relative z-10 w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all",
              done ? "bg-tertiary text-white" : active ? "bg-tertiary text-white ring-4 ring-tertiary/20 shadow-md" : "bg-surface text-on-surface-muted border-2 border-surface-mid"
            )}>
              {done ? <Check size={16} /> : step}
            </div>
            <span className={cn(
              "mt-2 font-label text-xs text-center whitespace-nowrap",
              active ? "text-tertiary font-semibold" : done ? "text-tertiary/50" : "text-on-surface-muted"
            )}>
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function TelecallingUploadPage() {
  const [activeTab, setActiveTab] = useState<"upload" | "history" | "scripts">("upload");

  return (
    <div className="max-w-7xl">
      {/* Tab Navigation */}
      <div className="flex items-center gap-1 border-b border-surface-mid mb-6">
        {(["upload", "history", "scripts"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              "px-6 py-3 font-label font-semibold text-sm transition-all border-b-2",
              activeTab === tab
                ? "border-tertiary text-tertiary"
                : "border-transparent text-on-surface-muted hover:text-on-surface"
            )}
          >
            {tab === "upload" ? "Upload Contacts" : tab === "history" ? "Upload History" : "Scripts"}
          </button>
        ))}
      </div>

      {activeTab === "upload" && <UploadTab />}
      {activeTab === "history" && <HistoryTab />}
      {activeTab === "scripts" && <ScriptsTab />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// UPLOAD TAB — 3-step wizard
// ═══════════════════════════════════════════════════════════════════════════════

function UploadTab() {
  const [currentStep, setCurrentStep] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Count rows by reading the file
  const [rowCount, setRowCount] = useState<number | null>(null);

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setFile(null);
    setUploadResult(null);
    setUploadError(null);
    setRowCount(null);
    if (!selected) return;

    try {
      const csvFile = await toCsvFile(selected);
      setFile(csvFile);
      // Count CSV rows (excluding header)
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target?.result as string;
        if (text) {
          const lines = text.split("\n").filter((l) => l.trim().length > 0);
          setRowCount(Math.max(0, lines.length - 1)); // subtract header
        }
      };
      reader.readAsText(csvFile);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Failed to process file");
    }
  }

  async function handleDrop(e: React.DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    const dropped = e.dataTransfer.files?.[0];
    setFile(null);
    setUploadResult(null);
    setUploadError(null);
    setRowCount(null);
    if (!dropped) return;

    const lowerName = dropped.name.toLowerCase();
    if (lowerName.endsWith(".csv") || lowerName.endsWith(".xlsx") || lowerName.endsWith(".xls")) {
      try {
        const csvFile = await toCsvFile(dropped);
        setFile(csvFile);
        const reader = new FileReader();
        reader.onload = (ev) => {
          const text = ev.target?.result as string;
          if (text) {
            const lines = text.split("\n").filter((l) => l.trim().length > 0);
            setRowCount(Math.max(0, lines.length - 1));
          }
        };
        reader.readAsText(csvFile);
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : "Failed to process file");
      }
    } else {
      setUploadError("Invalid file format. Please upload a .csv, .xlsx, or .xls file.");
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLLabelElement>) {
    e.preventDefault();
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    setUploadError(null);
    try {
      const headers = await getAuthHeaders();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_URL}/api/v1/telecalling-upload/upload`, {
        method: "POST",
        body: fd,
        headers: { ...headers },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || `Upload failed (${res.status})`);
      }
      const result: UploadResult = await res.json();
      setUploadResult(result);
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function handleReset() {
    setFile(null);
    setCurrentStep(1);
    setUploadResult(null);
    setUploadError(null);
    setRowCount(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  function downloadSampleCSV() {
    const csvContent = "data:text/csv;charset=utf-8,phone,name,course,city\n919876543210,John Doe,Full Stack Development,Chennai\n919988776655,Jane Smith,Data Science,Bangalore\n";
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "aira_sample_contacts.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  return (
    <div className="animate-slide-up">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        {/* Left Column: Wizard Card */}
        <div className="lg:col-span-2 bg-surface rounded-[2rem] p-8 shadow-lg ring-1 ring-[#c4c7c7]/20 min-h-[500px] flex flex-col">
          <StepIndicator current={currentStep} />

          {/* ── Step 1: Upload CSV ─────────────────────────────────────────── */}
          {currentStep === 1 && (
            <div className="space-y-6 flex-1">
              <div>
                <h2 className="font-display text-2xl font-bold text-on-surface mb-1">Upload your contacts</h2>
                <p className="font-body text-sm text-on-surface-muted">Select a CSV or Excel file with contact data. We will detect column mappings automatically.</p>
              </div>

              {uploadError && (
                <div className="text-sm font-semibold text-red-600 bg-red-50 border border-red-200 rounded-xl p-3 flex items-center gap-2">
                  <X size={14} className="text-red-500" />
                  {uploadError}
                </div>
              )}

              <label
                className={cn(
                  "relative flex flex-col items-center justify-center gap-5 py-12 rounded-2xl border-2 border-dashed cursor-pointer transition-all group",
                  file ? "border-tertiary bg-tertiary/5" : "border-tertiary/30 hover:border-tertiary/70 hover:bg-tertiary/[0.04]"
                )}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
              >
                <div className={cn(
                  "w-16 h-16 rounded-2xl flex items-center justify-center transition-all shadow-sm",
                  file ? "bg-tertiary text-white" : "bg-tertiary/10 text-tertiary group-hover:bg-tertiary/20"
                )}>
                  {file ? <Check size={28} /> : <CloudUpload size={28} />}
                </div>
                <div className="text-center px-4">
                  <p className="font-display text-lg font-bold text-on-surface truncate max-w-md mx-auto">
                    {file ? file.name : "Drop your CSV or Excel file here"}
                  </p>
                  <p className="font-body text-xs text-on-surface-muted mt-1.5">
                    {file
                      ? `${(file.size / 1024).toFixed(1)} KB${rowCount !== null ? ` · ${rowCount.toLocaleString()} rows` : ""} · click to change file`
                      : "or click to browse — .csv, .xlsx, .xls · name and phone columns required"}
                  </p>
                </div>
                {!file && (
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[10px] text-on-surface-muted font-label border-t border-dashed border-tertiary/20 w-full justify-center pt-4 mt-1">
                    <span className="flex items-center gap-1"><Check size={10} className="text-tertiary" /> Auto-detects columns</span>
                    <span className="flex items-center gap-1"><Check size={10} className="text-tertiary" /> Deduplicates leads</span>
                    <span className="flex items-center gap-1"><Check size={10} className="text-tertiary" /> Indian numbers formatted</span>
                  </div>
                )}
                <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleFileSelect} />
              </label>

              <div className="flex justify-end">
                <button
                  disabled={!file}
                  onClick={() => setCurrentStep(2)}
                  className={cn(
                    "flex items-center gap-2 px-6 py-3 rounded-xl font-label font-semibold text-sm transition-all",
                    file
                      ? "bg-tertiary text-white hover:bg-tertiary/90 shadow-md"
                      : "bg-surface-mid text-on-surface-muted cursor-not-allowed"
                  )}
                >
                  Next <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}

          {/* ── Step 2: Confirm & Upload ───────────────────────────────────── */}
          {currentStep === 2 && (
            <div className="space-y-6 flex-1">
              <div>
                <h2 className="font-display text-2xl font-bold text-on-surface mb-1">Review & Upload</h2>
                <p className="font-body text-sm text-on-surface-muted">Double-check the details below, then start the upload.</p>
              </div>

              {/* Summary Card */}
              {!uploadResult && !uploadError && (
                <div className="rounded-2xl border border-surface-mid bg-surface-low p-6 space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-tertiary/10 flex items-center justify-center">
                      <FileText size={20} className="text-tertiary" />
                    </div>
                    <div>
                      <p className="font-label text-sm font-semibold text-on-surface">{file?.name ?? "No file"}</p>
                      <p className="font-body text-xs text-on-surface-muted">
                        {file ? `${(file.size / 1024).toFixed(1)} KB` : ""}
                        {rowCount !== null ? ` · ${rowCount.toLocaleString()} contacts` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="border-t border-surface-mid pt-4">
                    <div>
                      <p className="font-label text-xs text-on-surface-muted mb-1">File Type</p>
                      <p className="font-label text-sm font-semibold text-on-surface">CSV</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Success Banner */}
              {uploadResult && (
                <div className="rounded-2xl border-2 border-emerald-200 bg-emerald-50 p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-full bg-emerald-500 flex items-center justify-center">
                      <Check size={20} className="text-white" />
                    </div>
                    <div>
                      <p className="font-display text-lg font-bold text-emerald-800">Upload Successful</p>
                      <p className="font-body text-xs text-emerald-600">Batch ID: {uploadResult.batch_id}</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="bg-white/70 rounded-xl p-3 text-center">
                      <p className="font-display text-2xl font-bold text-emerald-700">{uploadResult.inserted}</p>
                      <p className="font-label text-xs text-emerald-600">Inserted</p>
                    </div>
                    <div className="bg-white/70 rounded-xl p-3 text-center">
                      <p className="font-display text-2xl font-bold text-amber-700">{uploadResult.duplicates}</p>
                      <p className="font-label text-xs text-amber-600">Duplicates</p>
                    </div>
                    <div className="bg-white/70 rounded-xl p-3 text-center">
                      <p className="font-display text-2xl font-bold text-blue-700">{uploadResult.assigned}</p>
                      <p className="font-label text-xs text-blue-600">Assigned</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Error Banner */}
              {uploadError && (
                <div className="rounded-2xl border-2 border-red-200 bg-red-50 p-6">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-red-500 flex items-center justify-center">
                      <X size={20} className="text-white" />
                    </div>
                    <div>
                      <p className="font-display text-lg font-bold text-red-800">Upload Failed</p>
                      <p className="font-body text-sm text-red-600">{uploadError}</p>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex justify-between">
                <button
                  onClick={() => {
                    if (uploadResult || uploadError) {
                      handleReset();
                    } else {
                      setCurrentStep(1);
                    }
                  }}
                  className="px-6 py-3 rounded-xl font-label font-semibold text-sm text-on-surface-muted hover:text-on-surface hover:bg-surface-low transition-all"
                >
                  {uploadResult || uploadError ? "Start New Upload" : "Back"}
                </button>
                {!uploadResult && !uploadError && (
                  <button
                    disabled={!file || uploading}
                    onClick={handleUpload}
                    className={cn(
                      "flex items-center gap-2 px-6 py-3 rounded-xl font-label font-semibold text-sm transition-all",
                      !file || uploading
                        ? "bg-surface-mid text-on-surface-muted cursor-not-allowed"
                        : "bg-tertiary text-white hover:bg-tertiary/90 shadow-md"
                    )}
                  >
                    {uploading ? (
                      <><Loader2 size={16} className="animate-spin" /> Uploading...</>
                    ) : (
                      <><Upload size={16} /> Upload Contacts</>
                    )}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Sidebar */}
        <div className="space-y-6">
          <div className="bg-surface rounded-[2rem] p-6 shadow-lg ring-1 ring-[#c4c7c7]/20">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600">
                <FileText size={16} />
              </div>
              <h3 className="font-display font-bold text-on-surface text-base">CSV Template</h3>
            </div>
            
            <div className="space-y-4">
              <p className="font-body text-xs text-on-surface-muted leading-relaxed">
                Make sure your CSV or Excel file includes these headers. Match additional variables with custom columns.
              </p>

              <div className="divide-y divide-surface-mid border-t border-b border-surface-mid">
                <div className="py-2 flex justify-between text-xs font-body">
                  <span className="font-mono text-on-surface font-semibold">phone</span>
                  <span className="text-red-700 font-bold bg-red-50 px-1.5 py-0.5 rounded text-[9px]">Required</span>
                </div>
                <div className="py-2 flex justify-between text-xs font-body">
                  <span className="font-mono text-on-surface font-semibold">name</span>
                  <span className="text-on-surface-muted bg-surface-low px-1.5 py-0.5 rounded text-[9px]">Optional</span>
                </div>
                <div className="py-2 flex justify-between text-xs font-body">
                  <span className="font-mono text-on-surface font-semibold">course / other</span>
                  <span className="text-on-surface-muted bg-surface-low px-1.5 py-0.5 rounded text-[9px]">Optional</span>
                </div>
              </div>

              <button
                onClick={downloadSampleCSV}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-surface-low hover:bg-surface-mid rounded-xl font-label text-xs font-bold text-on-surface transition-colors border border-surface-mid/60"
              >
                <Download size={13} />
                Download Sample CSV
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// UPLOAD HISTORY TAB
// ═══════════════════════════════════════════════════════════════════════════════

function HistoryTab() {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const LIMIT = 20;

  const fetchHistory = useCallback(async (p: number) => {
    try {
      setHistoryLoading(true);
      const headers = await getAuthHeaders();
      const res = await fetch(
        `${API_URL}/api/v1/telecalling-upload/history?page=${p}&limit=${LIMIT}`,
        { headers }
      );
      if (!res.ok) throw new Error("Failed to load history");
      const raw = await res.json();
      const data: HistoryItem[] = Array.isArray(raw) ? raw : [];
      setHistory(data);
      setHasMore(data.length === LIMIT);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory(page);
  }, [page, fetchHistory]);

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
      alert("Failed to download CSV.");
    }
  }

  return (
    <div className="animate-slide-up">
      <div className="bg-surface rounded-[2rem] p-8 shadow-lg ring-1 ring-[#c4c7c7]/20">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="font-display text-xl font-bold text-on-surface">Upload History</h2>
            <p className="font-body text-sm text-on-surface-muted mt-1">View all previous uploads and download assignment CSVs.</p>
          </div>
        </div>

        {historyLoading && history.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-on-surface-muted">
            <Loader2 size={24} className="animate-spin mr-3 text-tertiary" />
            <span className="font-body text-sm">Loading history...</span>
          </div>
        ) : history.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-surface-low flex items-center justify-center mx-auto mb-3">
              <FileText size={24} className="text-on-surface-muted" />
            </div>
            <p className="font-label text-sm text-on-surface-muted">No uploads yet. Upload your first CSV to see it here.</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-surface-mid">
                    <th className="pb-3 pr-4 text-left font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">File Name</th>
                    <th className="pb-3 pr-4 text-left font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">Date</th>
                    <th className="pb-3 pr-4 text-right font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">Total</th>
                    <th className="pb-3 pr-4 text-right font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">Inserted</th>
                    <th className="pb-3 pr-4 text-right font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">Duplicates</th>
                    <th className="pb-3 pr-4 text-right font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">Assigned</th>
                    <th className="pb-3 font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr key={item.id} className="border-b border-surface-mid/50 last:border-0 hover:bg-surface-low/50 transition-colors">
                      <td className="py-4 pr-4">
                        <div className="flex items-center gap-2">
                          <FileText size={14} className="shrink-0 text-on-surface-muted" />
                          <span className="truncate max-w-[200px] font-label text-sm font-medium text-on-surface">{item.file_name}</span>
                        </div>
                      </td>
                      <td className="py-4 pr-4 font-body text-sm text-on-surface-muted whitespace-nowrap">{formatDate(item.created_at)}</td>
                      <td className="py-4 pr-4 text-right font-label text-sm tabular-nums text-on-surface">{item.total_contacts}</td>
                      <td className="py-4 pr-4 text-right font-label text-sm tabular-nums text-emerald-600">{item.inserted}</td>
                      <td className="py-4 pr-4 text-right font-label text-sm tabular-nums text-amber-600">{item.duplicates}</td>
                      <td className="py-4 pr-4 text-right font-label text-sm tabular-nums text-blue-600">{item.assigned}</td>
                      <td className="py-4">
                        <button
                          onClick={() => handleDownloadCsv(item.id, item.file_name)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-label font-semibold text-tertiary hover:bg-tertiary/10 transition-colors"
                        >
                          <Download size={13} /> CSV
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between mt-6 pt-4 border-t border-surface-mid">
              <span className="font-label text-xs text-on-surface-muted">Page {page}</span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-4 py-2 rounded-xl font-label text-xs font-semibold border border-surface-mid text-on-surface-muted hover:bg-surface-low disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                >
                  Previous
                </button>
                <button
                  disabled={!hasMore}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-4 py-2 rounded-xl font-label text-xs font-semibold border border-surface-mid text-on-surface-muted hover:bg-surface-low disabled:opacity-40 disabled:cursor-not-allowed transition-all"
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

// ═══════════════════════════════════════════════════════════════════════════════
// SCRIPTS TAB
// ═══════════════════════════════════════════════════════════════════════════════

function ScriptsTab() {
  const [scripts, setScripts] = useState<CallScript[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [showEditor, setShowEditor] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formName, setFormName] = useState("");
  const [formIsDefault, setFormIsDefault] = useState(false);
  const [formSteps, setFormSteps] = useState<FormStep[]>([emptyFormStep()]);

  const [previewScript, setPreviewScript] = useState<CallScript | null>(null);
  const [previewStep, setPreviewStep] = useState(0);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchScripts();
      setScripts(Array.isArray(data) ? data : []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  function openCreate() {
    setEditingId(null);
    setFormName("");
    setFormIsDefault(false);
    setFormSteps([emptyFormStep()]);
    setShowEditor(true);
  }

  function openEdit(s: CallScript) {
    setEditingId(s.id);
    setFormName(s.name);
    setFormIsDefault(s.is_default);
    setFormSteps(stepsToForm(s.steps));
    setShowEditor(true);
  }

  function closeEditor() {
    setShowEditor(false);
    setEditingId(null);
  }

  async function handleSave() {
    if (!formName.trim() || formSteps.every((s) => !s.text.trim())) return;
    setSaving(true);
    try {
      const steps = formToSteps(formSteps);
      if (editingId) {
        await apiUpdateScript(editingId, { name: formName.trim(), segment: null, steps, is_default: formIsDefault });
      } else {
        await apiCreateScript({ name: formName.trim(), steps, is_default: formIsDefault });
      }
      closeEditor();
      await load();
    } catch (err) {
      console.error("Failed to save script:", err);
    }
    setSaving(false);
  }

  async function handleToggleActive(s: CallScript) {
    try {
      await apiUpdateScript(s.id, { active: !s.active });
      setScripts((prev) => prev.map((x) => (x.id === s.id ? { ...x, active: !x.active } : x)));
    } catch { /* silent */ }
  }

  async function handleDelete(id: string) {
    try {
      await apiDeleteScript(id);
      setScripts((prev) => prev.filter((x) => x.id !== id));
      setDeletingId(null);
    } catch { /* silent */ }
  }

  function updateStep(idx: number, patch: Partial<FormStep>) {
    setFormSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }

  function removeStep(idx: number) {
    setFormSteps((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));
  }

  function addBranch(stepIdx: number) {
    setFormSteps((prev) =>
      prev.map((s, i) => (i === stepIdx ? { ...s, branches: [...s.branches, { label: "", goto: 1 }] } : s))
    );
  }

  function updateBranch(stepIdx: number, branchIdx: number, patch: Partial<Branch>) {
    setFormSteps((prev) =>
      prev.map((s, i) =>
        i === stepIdx ? { ...s, branches: s.branches.map((b, bi) => (bi === branchIdx ? { ...b, ...patch } : b)) } : s
      )
    );
  }

  function removeBranch(stepIdx: number, branchIdx: number) {
    setFormSteps((prev) =>
      prev.map((s, i) => (i === stepIdx ? { ...s, branches: s.branches.filter((_, bi) => bi !== branchIdx) } : s))
    );
  }

  return (
    <div className="animate-slide-up">
      {/* Script list */}
      <div className="bg-surface rounded-[2rem] p-8 shadow-lg ring-1 ring-[#c4c7c7]/20">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="font-display text-xl font-bold text-on-surface">Call Scripts</h2>
            <p className="font-body text-sm text-on-surface-muted mt-1">Create guided talk tracks for your telecalling team.</p>
          </div>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 bg-tertiary text-white px-4 py-2.5 rounded-xl font-label text-sm font-semibold hover:bg-tertiary/90 shadow-md transition-all"
          >
            <Plus size={16} /> New Script
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="animate-spin text-tertiary" />
          </div>
        ) : scripts.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-surface-low flex items-center justify-center mx-auto mb-3">
              <FileText size={24} className="text-on-surface-muted" />
            </div>
            <p className="font-label text-sm text-on-surface-muted">No scripts yet. Create one to give telecallers guided talk tracks.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {scripts.map((s) => (
              <div
                key={s.id}
                className="bg-surface-low border border-surface-mid rounded-2xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:shadow-sm transition-all"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-display text-sm font-bold text-on-surface truncate">{s.name}</span>
                    {s.is_default && (
                      <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-purple-50 text-purple-700 border border-purple-200 flex items-center gap-0.5">
                        <Star size={9} className="fill-purple-500 text-purple-500" />Default
                      </span>
                    )}
                    {!s.active && (
                      <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-[#f0ece4] text-[#a8a29e] border border-[#e8e3db]">Inactive</span>
                    )}
                  </div>
                  <p className="font-body text-xs text-on-surface-muted mt-1">{s.steps.length} step{s.steps.length !== 1 ? "s" : ""}</p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button onClick={() => handleToggleActive(s)} className="p-2 rounded-xl hover:bg-surface transition-colors">
                    {s.active ? <ToggleRight size={18} className="text-emerald-500" /> : <ToggleLeft size={18} className="text-on-surface-muted" />}
                  </button>
                  <button onClick={() => { setPreviewScript(s); setPreviewStep(0); }} className="p-2 rounded-xl hover:bg-surface text-on-surface-muted transition-colors">
                    <Eye size={15} />
                  </button>
                  <button onClick={() => openEdit(s)} className="p-2 rounded-xl hover:bg-surface text-on-surface-muted transition-colors">
                    <Pencil size={15} />
                  </button>
                  <button onClick={() => setDeletingId(s.id)} className="p-2 rounded-xl hover:bg-red-50 text-red-500 transition-colors">
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Delete confirmation */}
      {deletingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-surface rounded-2xl p-6 shadow-2xl w-full max-w-sm ring-1 ring-[#c4c7c7]/20">
            <h3 className="font-display text-base font-bold text-on-surface mb-2">Delete Script</h3>
            <p className="font-body text-sm text-on-surface-muted mb-6">Are you sure? This cannot be undone.</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeletingId(null)} className="px-4 py-2 rounded-xl font-label text-sm font-semibold text-on-surface-muted hover:bg-surface-low transition-colors">Cancel</button>
              <button onClick={() => handleDelete(deletingId)} className="bg-red-600 text-white px-4 py-2 rounded-xl font-label text-sm font-semibold hover:bg-red-700 transition-colors">Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-2xl ring-1 ring-[#c4c7c7]/20 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-6 pb-4 border-b border-surface-mid shrink-0">
              <h2 className="font-display text-lg font-bold text-on-surface">{editingId ? "Edit Script" : "New Script"}</h2>
              <button onClick={closeEditor} className="p-2 rounded-xl hover:bg-surface-low text-on-surface-muted transition-colors"><X size={18} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              <div>
                <label className="block font-label text-xs font-semibold text-on-surface-muted mb-1.5 uppercase tracking-wider">Script Name</label>
                <input type="text" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="e.g. Segment A Hot Lead Script"
                  className="w-full border border-surface-mid rounded-xl px-4 py-3 font-body text-sm text-on-surface bg-surface-low placeholder:text-on-surface-muted focus:outline-none focus:ring-2 focus:ring-tertiary" />
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={formIsDefault} onChange={(e) => setFormIsDefault(e.target.checked)} className="w-4 h-4 rounded border-surface-mid text-tertiary focus:ring-tertiary" />
                <span className="font-label text-xs font-semibold text-on-surface-muted">Set as default script</span>
              </label>
              <div>
                <label className="block font-label text-xs font-semibold text-on-surface-muted mb-3 uppercase tracking-wider">Steps</label>
                <div className="space-y-4">
                  {formSteps.map((step, idx) => (
                    <div key={idx} className="bg-surface-low border border-surface-mid rounded-xl p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <GripVertical size={14} className="text-on-surface-muted" />
                        <span className="font-label text-[10px] font-bold text-on-surface-muted uppercase tracking-wider">Step {idx + 1}</span>
                        {formSteps.length > 1 && (
                          <button onClick={() => removeStep(idx)} className="ml-auto p-1 rounded-lg hover:bg-red-50 text-on-surface-muted hover:text-red-500 transition-colors"><X size={14} /></button>
                        )}
                      </div>
                      <textarea value={step.text} onChange={(e) => updateStep(idx, { text: e.target.value })} placeholder="Script line..." rows={2}
                        className="w-full border border-surface-mid rounded-lg px-3 py-2 font-body text-sm text-on-surface bg-surface placeholder:text-on-surface-muted focus:outline-none focus:ring-2 focus:ring-tertiary resize-none" />
                      <input type="text" value={step.note} onChange={(e) => updateStep(idx, { note: e.target.value })} placeholder="Coaching hint (optional)"
                        className="w-full mt-2 border border-surface-mid rounded-lg px-3 py-1.5 font-body text-xs text-on-surface-muted bg-surface placeholder:text-on-surface-muted focus:outline-none focus:ring-2 focus:ring-tertiary" />
                      {step.branches.length > 0 && (
                        <div className="mt-3 space-y-2">
                          <span className="font-label text-[10px] font-bold text-on-surface-muted uppercase flex items-center gap-1"><GitBranch size={10} />Branches</span>
                          {step.branches.map((br, bi) => (
                            <div key={bi} className="flex items-center gap-2">
                              <input type="text" value={br.label} onChange={(e) => updateBranch(idx, bi, { label: e.target.value })} placeholder="Label"
                                className="flex-1 border border-surface-mid rounded-lg px-2.5 py-1.5 font-body text-xs bg-surface text-on-surface" />
                              <span className="font-label text-[10px] text-on-surface-muted">Go to</span>
                              <input type="number" min={1} max={formSteps.length} value={br.goto} onChange={(e) => updateBranch(idx, bi, { goto: parseInt(e.target.value) || 1 })}
                                className="w-14 border border-surface-mid rounded-lg px-2 py-1.5 font-body text-xs text-center bg-surface text-on-surface" />
                              <button onClick={() => removeBranch(idx, bi)} className="p-1 rounded hover:bg-red-50 text-on-surface-muted hover:text-red-500 transition-colors"><X size={12} /></button>
                            </div>
                          ))}
                        </div>
                      )}
                      <button onClick={() => addBranch(idx)} className="mt-2 font-label text-[10px] font-semibold text-tertiary hover:text-tertiary/80 flex items-center gap-1 transition-colors">
                        <GitBranch size={10} />Add Branch
                      </button>
                    </div>
                  ))}
                </div>
                <button onClick={() => setFormSteps((prev) => [...prev, emptyFormStep()])}
                  className="mt-3 flex items-center gap-1.5 px-4 py-2 rounded-xl font-label text-xs font-semibold text-on-surface-muted border border-surface-mid hover:bg-surface-low transition-colors">
                  <Plus size={14} />Add Step
                </button>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 p-6 pt-4 border-t border-surface-mid shrink-0">
              <button onClick={closeEditor} className="px-4 py-2 rounded-xl font-label text-sm font-semibold text-on-surface-muted hover:bg-surface-low transition-colors">Cancel</button>
              <button onClick={handleSave} disabled={saving}
                className="flex items-center gap-2 bg-tertiary text-white px-5 py-2.5 rounded-xl font-label text-sm font-semibold hover:bg-tertiary/90 shadow-md disabled:opacity-50 transition-all">
                {saving && <Loader2 size={14} className="animate-spin" />}
                {editingId ? "Save Changes" : "Create Script"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {previewScript && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-2xl ring-1 ring-[#c4c7c7]/20 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-6 pb-4 border-b border-surface-mid shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <Eye size={18} className="text-tertiary" />
                  <h2 className="font-display text-lg font-bold text-on-surface">Script Preview</h2>
                </div>
                <p className="font-body text-xs text-on-surface-muted mt-0.5">{previewScript.name}</p>
              </div>
              <button onClick={() => { setPreviewScript(null); setPreviewStep(0); }} className="p-2 rounded-xl hover:bg-surface-low text-on-surface-muted transition-colors"><X size={18} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {previewScript.steps.sort((a, b) => a.order - b.order).map((step, idx) => {
                const isCurrent = idx === previewStep;
                return (
                  <div key={idx} className={cn(
                    "rounded-xl p-4 border-2 transition-all",
                    isCurrent ? "border-tertiary bg-tertiary/5 shadow-sm" : "border-surface-mid bg-surface"
                  )}>
                    <div className="flex items-start gap-3">
                      <span className={cn(
                        "shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold",
                        isCurrent ? "bg-tertiary text-white" : "bg-surface-low text-on-surface-muted"
                      )}>{step.order}</span>
                      <div className="min-w-0 flex-1">
                        <p className={cn("font-body text-sm", isCurrent ? "text-on-surface font-semibold" : "text-on-surface-muted")}>{step.text}</p>
                        {step.note && <p className="font-body text-xs text-on-surface-muted italic mt-1">{step.note}</p>}
                        {isCurrent && step.branches && step.branches.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-3">
                            {step.branches.map((br, bi) => (
                              <button key={bi} onClick={() => { const i = previewScript.steps.findIndex((s) => s.order === br.goto); if (i >= 0) setPreviewStep(i); }}
                                className="bg-surface-low text-on-surface px-3 py-1.5 rounded-lg font-label text-xs font-semibold hover:bg-surface-mid flex items-center gap-1 transition-colors">
                                <ChevronRight size={12} />{br.label || `Go to ${br.goto}`}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex items-center justify-between p-6 pt-4 border-t border-surface-mid shrink-0">
              <span className="font-label text-xs text-on-surface-muted">Step {previewStep + 1} of {previewScript.steps.length}</span>
              <div className="flex gap-2">
                <button onClick={() => setPreviewStep((p) => Math.max(0, p - 1))} disabled={previewStep === 0}
                  className="px-4 py-2 rounded-xl font-label text-xs font-semibold text-on-surface-muted hover:bg-surface-low disabled:opacity-40 transition-colors">Back</button>
                <button onClick={() => setPreviewStep((p) => Math.min(previewScript.steps.length - 1, p + 1))} disabled={previewStep === previewScript.steps.length - 1}
                  className="flex items-center gap-1 bg-tertiary text-white px-4 py-2 rounded-xl font-label text-sm font-semibold hover:bg-tertiary/90 disabled:opacity-40 transition-all">
                  Next<ChevronRight size={14} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
