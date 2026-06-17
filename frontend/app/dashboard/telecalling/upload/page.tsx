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
} from "lucide-react";
import { getAuthHeaders } from "@/lib/api";

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

const SEGMENT_OPTIONS = [
  { value: "", label: "None (auto)" },
  { value: "A", label: "A" },
  { value: "B", label: "B" },
  { value: "C", label: "C" },
  { value: "D", label: "D" },
];

const SEGMENT_COLORS: Record<string, string> = {
  A: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  B: "bg-blue-50 text-blue-700 border border-blue-200",
  C: "bg-amber-50 text-amber-700 border border-amber-200",
  D: "bg-rose-50 text-rose-700 border border-rose-200",
};

function segmentBadge(seg: string | null) {
  if (!seg)
    return (
      <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-slate-100 text-slate-500 border border-slate-200">
        All
      </span>
    );
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase ${SEGMENT_COLORS[seg] ?? "bg-slate-100 text-slate-500 border border-slate-200"}`}
    >
      Seg {seg}
    </span>
  );
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
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/call-scripts`, {
    headers: { "Content-Type": "application/json", ...headers },
  });
  if (!res.ok) return [];
  return res.json();
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

// ─── Page ────────────────────────────────────────────────────────────────────

export default function TelecallingUploadPage() {
  const [activeTab, setActiveTab] = useState<"upload" | "scripts">("upload");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
          <Upload size={18} />
        </div>
        <div>
          <h1 className="font-display text-lg font-bold text-tertiary">
            Telecalling Management
          </h1>
          <p className="text-xs text-ink-secondary">
            Upload contacts and manage call scripts
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 p-0.5 bg-slate-100 rounded-xl w-fit">
        <button
          onClick={() => setActiveTab("upload")}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "upload" ? "bg-white text-indigo-600 shadow-sm" : "text-slate-500 hover:text-slate-700"
          }`}
        >
          <Upload size={14} /> Upload Contacts
        </button>
        <button
          onClick={() => setActiveTab("scripts")}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "scripts" ? "bg-white text-indigo-600 shadow-sm" : "text-slate-500 hover:text-slate-700"
          }`}
        >
          <FileText size={14} /> Call Scripts
        </button>
      </div>

      {activeTab === "upload" ? <UploadTab /> : <ScriptsTab />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// UPLOAD TAB
// ═══════════════════════════════════════════════════════════════════════════════

function UploadTab() {
  const [file, setFile] = useState<File | null>(null);
  const [segmentOverride, setSegmentOverride] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

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
      const data: HistoryItem[] = await res.json();
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
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      fetchHistory(1);
      setPage(1);
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

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
    <>
      {/* Upload Card */}
      <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
        <h2 className="font-display text-base font-bold text-tertiary mb-4">Upload Contacts</h2>
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-end">
          <div className="flex-1 min-w-0">
            <label className="block text-xs font-medium text-ink-secondary mb-1.5">CSV File</label>
            <div
              className={`relative flex items-center gap-2 rounded-lg border border-dashed px-3 py-2.5 transition cursor-pointer ${
                file ? "border-indigo-300 bg-indigo-50/50" : "border-slate-200 bg-surface-low hover:border-slate-300"
              }`}
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
          <div className="w-full sm:w-44">
            <label className="block text-xs font-medium text-ink-secondary mb-1.5">Segment Override</label>
            <select
              value={segmentOverride}
              onChange={(e) => setSegmentOverride(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-surface-low px-3 py-2.5 text-sm text-ink outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
            >
              {SEGMENT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <button
            disabled={!file || uploading}
            onClick={handleUpload}
            className="bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 whitespace-nowrap transition"
          >
            {uploading ? (
              <><Loader2 size={14} className="animate-spin" />Uploading...</>
            ) : (
              <><Upload size={14} />Upload</>
            )}
          </button>
        </div>
        {uploadResult && (
          <div className="mt-4 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-800 flex flex-wrap gap-x-6 gap-y-1">
            <span className="font-semibold">Upload successful</span>
            <span>Inserted: <strong>{uploadResult.inserted}</strong></span>
            <span>Duplicates: <strong>{uploadResult.duplicates}</strong></span>
            <span>Assigned: <strong>{uploadResult.assigned}</strong></span>
          </div>
        )}
        {uploadError && (
          <div className="mt-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{uploadError}</div>
        )}
      </div>

      {/* History Card */}
      <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
        <h2 className="font-display text-base font-bold text-tertiary mb-4">Upload History</h2>
        {historyLoading && history.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-ink-muted">
            <Loader2 size={20} className="animate-spin mr-2" />Loading...
          </div>
        ) : history.length === 0 ? (
          <div className="text-center py-12 text-ink-muted text-sm">No uploads yet.</div>
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
                    <tr key={item.id} className="border-b border-slate-100 last:border-0">
                      <td className="py-2.5 pr-4">
                        <div className="flex items-center gap-1.5">
                          <FileText size={13} className="shrink-0 text-ink-muted" />
                          <span className="truncate max-w-[180px] font-medium text-ink">{item.file_name}</span>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 text-ink-secondary whitespace-nowrap">{formatDate(item.created_at)}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-ink">{item.total_contacts}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-emerald-600">{item.inserted}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-amber-600">{item.duplicates}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-indigo-600">{item.assigned}</td>
                      <td className="py-2.5 pr-4">
                        {item.segment_override ? (
                          <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-indigo-50 text-indigo-700">{item.segment_override}</span>
                        ) : (
                          <span className="text-ink-muted">Auto</span>
                        )}
                      </td>
                      <td className="py-2.5">
                        <button
                          onClick={() => handleDownloadCsv(item.id, item.file_name)}
                          className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 font-medium transition"
                        >
                          <Download size={12} /><span>Download CSV</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
              <span className="text-xs text-ink-muted">Page {page}</span>
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
    </>
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
  const [formSegment, setFormSegment] = useState<string>("");
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
    setFormSegment("");
    setFormIsDefault(false);
    setFormSteps([emptyFormStep()]);
    setShowEditor(true);
  }

  function openEdit(s: CallScript) {
    setEditingId(s.id);
    setFormName(s.name);
    setFormSegment(s.segment ?? "");
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
      const segment = formSegment || null;
      if (editingId) {
        await apiUpdateScript(editingId, { name: formName.trim(), segment, steps, is_default: formIsDefault });
      } else {
        await apiCreateScript({ name: formName.trim(), segment, steps, is_default: formIsDefault });
      }
      closeEditor();
      await load();
    } catch { /* silent */ }
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
    <>
      {/* Script list */}
      <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display text-base font-bold text-tertiary">Call Scripts</h2>
          <button
            onClick={openCreate}
            className="flex items-center gap-1.5 bg-indigo-600 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-indigo-700 transition"
          >
            <Plus size={14} />New Script
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="animate-spin text-indigo-500" />
          </div>
        ) : scripts.length === 0 ? (
          <div className="text-center py-12 text-sm text-ink-muted">
            <FileText size={24} className="text-slate-300 mx-auto mb-2" />
            No scripts yet. Create one to give telecallers guided talk tracks.
          </div>
        ) : (
          <div className="space-y-3">
            {scripts.map((s) => (
              <div
                key={s.id}
                className="bg-slate-50 border border-slate-100 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-display text-sm font-bold text-slate-800 truncate">{s.name}</span>
                    {segmentBadge(s.segment)}
                    {s.is_default && (
                      <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-purple-50 text-purple-700 border border-purple-200 flex items-center gap-0.5">
                        <Star size={9} className="fill-purple-500 text-purple-500" />Default
                      </span>
                    )}
                    {!s.active && (
                      <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-slate-100 text-slate-400 border border-slate-200">Inactive</span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">{s.steps.length} step{s.steps.length !== 1 ? "s" : ""}</p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button onClick={() => handleToggleActive(s)} className="p-1.5 rounded-lg hover:bg-slate-200 transition">
                    {s.active ? <ToggleRight size={18} className="text-emerald-500" /> : <ToggleLeft size={18} className="text-slate-400" />}
                  </button>
                  <button onClick={() => { setPreviewScript(s); setPreviewStep(0); }} className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-500 transition">
                    <Eye size={15} />
                  </button>
                  <button onClick={() => openEdit(s)} className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-500 transition">
                    <Pencil size={15} />
                  </button>
                  <button onClick={() => setDeletingId(s.id)} className="p-1.5 rounded-lg hover:bg-rose-50 text-rose-500 transition">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl p-6 shadow-2xl w-full max-w-sm border border-slate-100">
            <h3 className="font-display text-base font-bold text-slate-800 mb-2">Delete Script</h3>
            <p className="text-sm text-slate-500 mb-6">Are you sure? This cannot be undone.</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeletingId(null)} className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200">Cancel</button>
              <button onClick={() => handleDelete(deletingId)} className="bg-rose-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-rose-700">Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl border border-slate-100 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-6 pb-4 border-b border-slate-100 shrink-0">
              <h2 className="font-display text-lg font-bold text-slate-800">{editingId ? "Edit Script" : "New Script"}</h2>
              <button onClick={closeEditor} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400"><X size={18} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              <div>
                <label className="block text-xs font-bold text-slate-600 mb-1.5">Script Name</label>
                <input type="text" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="e.g. Segment A Hot Lead Script"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400" />
              </div>
              <div className="flex gap-4 items-end">
                <div className="flex-1">
                  <label className="block text-xs font-bold text-slate-600 mb-1.5">Segment</label>
                  <select value={formSegment} onChange={(e) => setFormSegment(e.target.value)}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 bg-white">
                    <option value="">None (All)</option>
                    <option value="A">A</option><option value="B">B</option><option value="C">C</option><option value="D">D</option>
                  </select>
                </div>
                <label className="flex items-center gap-2 pb-2 cursor-pointer">
                  <input type="checkbox" checked={formIsDefault} onChange={(e) => setFormIsDefault(e.target.checked)} className="w-4 h-4 rounded border-slate-300 text-indigo-600" />
                  <span className="text-xs font-medium text-slate-600">Default</span>
                </label>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-600 mb-3">Steps</label>
                <div className="space-y-4">
                  {formSteps.map((step, idx) => (
                    <div key={idx} className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <GripVertical size={14} className="text-slate-300" />
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Step {idx + 1}</span>
                        {formSteps.length > 1 && (
                          <button onClick={() => removeStep(idx)} className="ml-auto p-1 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-500"><X size={14} /></button>
                        )}
                      </div>
                      <textarea value={step.text} onChange={(e) => updateStep(idx, { text: e.target.value })} placeholder="Script line..." rows={2}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 resize-none" />
                      <input type="text" value={step.note} onChange={(e) => updateStep(idx, { note: e.target.value })} placeholder="Coaching hint (optional)"
                        className="w-full mt-2 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-600 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30" />
                      {step.branches.length > 0 && (
                        <div className="mt-3 space-y-2">
                          <span className="text-[10px] font-bold text-slate-400 uppercase flex items-center gap-1"><GitBranch size={10} />Branches</span>
                          {step.branches.map((br, bi) => (
                            <div key={bi} className="flex items-center gap-2">
                              <input type="text" value={br.label} onChange={(e) => updateBranch(idx, bi, { label: e.target.value })} placeholder="Label"
                                className="flex-1 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs" />
                              <span className="text-[10px] text-slate-400">Go to</span>
                              <input type="number" min={1} max={formSteps.length} value={br.goto} onChange={(e) => updateBranch(idx, bi, { goto: parseInt(e.target.value) || 1 })}
                                className="w-14 border border-slate-200 rounded-lg px-2 py-1.5 text-xs text-center" />
                              <button onClick={() => removeBranch(idx, bi)} className="p-1 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-500"><X size={12} /></button>
                            </div>
                          ))}
                        </div>
                      )}
                      <button onClick={() => addBranch(idx)} className="mt-2 text-[10px] font-medium text-indigo-600 hover:text-indigo-700 flex items-center gap-1">
                        <GitBranch size={10} />Add Branch
                      </button>
                    </div>
                  ))}
                </div>
                <button onClick={() => setFormSteps((prev) => [...prev, emptyFormStep()])}
                  className="mt-3 flex items-center gap-1.5 bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200">
                  <Plus size={14} />Add Step
                </button>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 p-6 pt-4 border-t border-slate-100 shrink-0">
              <button onClick={closeEditor} className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200">Cancel</button>
              <button onClick={handleSave} disabled={saving}
                className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
                {saving && <Loader2 size={14} className="animate-spin" />}
                {editingId ? "Save Changes" : "Create Script"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {previewScript && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl border border-slate-100 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-6 pb-4 border-b border-slate-100 shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <Eye size={18} className="text-indigo-500" />
                  <h2 className="font-display text-lg font-bold text-slate-800">Script Preview</h2>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">{previewScript.name}{previewScript.segment ? ` · Segment ${previewScript.segment}` : ""}</p>
              </div>
              <button onClick={() => { setPreviewScript(null); setPreviewStep(0); }} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400"><X size={18} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {previewScript.steps.sort((a, b) => a.order - b.order).map((step, idx) => {
                const isCurrent = idx === previewStep;
                return (
                  <div key={idx} className={`rounded-xl p-4 border-2 transition-all ${isCurrent ? "border-indigo-400 bg-indigo-50/50 shadow-sm" : "border-slate-100 bg-white"}`}>
                    <div className="flex items-start gap-3">
                      <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${isCurrent ? "bg-indigo-600 text-white" : "bg-slate-200 text-slate-500"}`}>{step.order}</span>
                      <div className="min-w-0 flex-1">
                        <p className={`text-sm ${isCurrent ? "text-slate-900 font-semibold" : "text-slate-600"}`}>{step.text}</p>
                        {step.note && <p className="text-xs text-slate-400 italic mt-1">{step.note}</p>}
                        {isCurrent && step.branches && step.branches.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-3">
                            {step.branches.map((br, bi) => (
                              <button key={bi} onClick={() => { const i = previewScript.steps.findIndex((s) => s.order === br.goto); if (i >= 0) setPreviewStep(i); }}
                                className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 flex items-center gap-1">
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
            <div className="flex items-center justify-between p-6 pt-4 border-t border-slate-100 shrink-0">
              <span className="text-xs text-slate-400 font-medium">Step {previewStep + 1} of {previewScript.steps.length}</span>
              <div className="flex gap-2">
                <button onClick={() => setPreviewStep((p) => Math.max(0, p - 1))} disabled={previewStep === 0}
                  className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 disabled:opacity-40">Back</button>
                <button onClick={() => setPreviewStep((p) => Math.min(previewScript.steps.length - 1, p + 1))} disabled={previewStep === previewScript.steps.length - 1}
                  className="flex items-center gap-1 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-40">
                  Next<ChevronRight size={14} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
