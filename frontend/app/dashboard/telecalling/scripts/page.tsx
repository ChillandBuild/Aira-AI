"use client";

import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Plus,
  Pencil,
  Trash2,
  Eye,
  FileText,
  ChevronRight,
  Loader2,
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

/* ────────────────────────────── Types ────────────────────────────── */

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

type FormStep = {
  text: string;
  note: string;
  branches: Branch[];
};

/* ────────────────────────────── Helpers ───────────────────────────── */

const SEGMENT_COLORS: Record<string, string> = {
  A: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  B: "bg-blue-50 text-blue-700 border border-blue-200",
  C: "bg-amber-50 text-amber-700 border border-amber-200",
  D: "bg-rose-50 text-rose-700 border border-rose-200",
};

function segmentBadge(seg: string | null) {
  if (!seg) {
    return (
      <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-slate-100 text-slate-500 border border-slate-200">
        All
      </span>
    );
  }
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
    .map((s) => ({
      text: s.text,
      note: s.note ?? "",
      branches: s.branches ?? [],
    }));
}

function formToSteps(form: FormStep[]): Step[] {
  return form.map((f, i) => ({
    order: i + 1,
    text: f.text,
    ...(f.note ? { note: f.note } : {}),
    ...(f.branches.length ? { branches: f.branches } : {}),
  }));
}

/* ────────────────────────────── API ──────────────────────────────── */

async function fetchScripts(): Promise<CallScript[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/call-scripts`, {
    headers: { "Content-Type": "application/json", ...headers },
  });
  if (!res.ok) throw new Error("Failed to load scripts");
  return res.json();
}

async function createScript(body: {
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

async function updateScript(
  id: string,
  body: Partial<{
    name: string;
    segment: string | null;
    steps: Step[];
    is_default: boolean;
    active: boolean;
  }>
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

async function deleteScript(id: string): Promise<void> {
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

/* ────────────────────────────── Page ─────────────────────────────── */

export default function CallScriptsPage() {
  const [scripts, setScripts] = useState<CallScript[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // modal state
  const [showEditor, setShowEditor] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formName, setFormName] = useState("");
  const [formSegment, setFormSegment] = useState<string>("");
  const [formIsDefault, setFormIsDefault] = useState(false);
  const [formSteps, setFormSteps] = useState<FormStep[]>([emptyFormStep()]);

  // preview state
  const [previewScript, setPreviewScript] = useState<CallScript | null>(null);
  const [previewStep, setPreviewStep] = useState(0);

  // confirm delete
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchScripts();
      setScripts(Array.isArray(data) ? data : []);
    } catch {
      toast.error("Failed to load call scripts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /* ── Editor open/close ── */

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

  /* ── Save ── */

  async function handleSave() {
    if (!formName.trim()) {
      toast.error("Script name is required");
      return;
    }
    if (formSteps.every((s) => !s.text.trim())) {
      toast.error("Add at least one step with text");
      return;
    }

    setSaving(true);
    try {
      const steps = formToSteps(formSteps);
      const segment = formSegment || null;

      if (editingId) {
        await updateScript(editingId, {
          name: formName.trim(),
          segment,
          steps,
          is_default: formIsDefault,
        });
        toast.success("Script updated");
      } else {
        await createScript({
          name: formName.trim(),
          segment,
          steps,
          is_default: formIsDefault,
        });
        toast.success("Script created");
      }
      closeEditor();
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  /* ── Toggle active ── */

  async function handleToggleActive(s: CallScript) {
    try {
      await updateScript(s.id, { active: !s.active });
      setScripts((prev) =>
        prev.map((x) => (x.id === s.id ? { ...x, active: !x.active } : x))
      );
      toast.success(s.active ? "Script deactivated" : "Script activated");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Toggle failed");
    }
  }

  /* ── Delete ── */

  async function handleDelete(id: string) {
    try {
      await deleteScript(id);
      setScripts((prev) => prev.filter((x) => x.id !== id));
      setDeletingId(null);
      toast.success("Script deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }

  /* ── Step editor helpers ── */

  function updateStep(idx: number, patch: Partial<FormStep>) {
    setFormSteps((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, ...patch } : s))
    );
  }

  function removeStep(idx: number) {
    setFormSteps((prev) => {
      if (prev.length <= 1) return prev;
      return prev.filter((_, i) => i !== idx);
    });
  }

  function addStep() {
    setFormSteps((prev) => [...prev, emptyFormStep()]);
  }

  function addBranch(stepIdx: number) {
    setFormSteps((prev) =>
      prev.map((s, i) =>
        i === stepIdx
          ? { ...s, branches: [...s.branches, { label: "", goto: 1 }] }
          : s
      )
    );
  }

  function updateBranch(
    stepIdx: number,
    branchIdx: number,
    patch: Partial<Branch>
  ) {
    setFormSteps((prev) =>
      prev.map((s, i) =>
        i === stepIdx
          ? {
              ...s,
              branches: s.branches.map((b, bi) =>
                bi === branchIdx ? { ...b, ...patch } : b
              ),
            }
          : s
      )
    );
  }

  function removeBranch(stepIdx: number, branchIdx: number) {
    setFormSteps((prev) =>
      prev.map((s, i) =>
        i === stepIdx
          ? { ...s, branches: s.branches.filter((_, bi) => bi !== branchIdx) }
          : s
      )
    );
  }

  /* ── Preview helpers ── */

  function openPreview(s: CallScript) {
    setPreviewScript(s);
    setPreviewStep(0);
  }

  function closePreview() {
    setPreviewScript(null);
    setPreviewStep(0);
  }

  function handlePreviewGoto(stepOrder: number) {
    if (!previewScript) return;
    const idx = previewScript.steps.findIndex((s) => s.order === stepOrder);
    if (idx >= 0) setPreviewStep(idx);
  }

  /* ────────────────────────────── Render ─────────────────────────── */

  return (
    <div className="max-w-5xl mx-auto px-4 pb-12">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-3">
            <div className="p-2.5 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl shadow-md">
              <FileText size={22} className="text-white" />
            </div>
            Call Scripts
          </h1>
          <p className="font-body text-sm text-slate-500 mt-1.5">
            Manage guided scripts for telecallers. Assign scripts to segments
            and define step-by-step talk tracks.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
        >
          <Plus size={16} />
          New Script
        </button>
      </div>

      {/* ─── Script list ─── */}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <Loader2 size={32} className="animate-spin text-indigo-500" />
        </div>
      ) : scripts.length === 0 ? (
        <div className="bg-surface rounded-card p-12 shadow-card ring-1 ring-[#c4c7c7]/15 text-center">
          <div className="w-14 h-14 bg-slate-50 rounded-full flex items-center justify-center text-slate-400 border border-slate-100 mx-auto mb-4">
            <FileText size={22} />
          </div>
          <h3 className="font-display text-lg font-bold text-slate-700">
            No scripts yet
          </h3>
          <p className="font-body text-sm text-slate-400 mt-1 max-w-sm mx-auto">
            Create your first call script to give telecallers guided talk
            tracks.
          </p>
          <button
            onClick={openCreate}
            className="mt-6 inline-flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            <Plus size={16} />
            Create Script
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {scripts.map((s) => (
            <div
              key={s.id}
              className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-shadow hover:shadow-card-hover"
            >
              {/* Info */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-display text-base font-bold text-tertiary truncate">
                    {s.name}
                  </h3>
                  {segmentBadge(s.segment)}
                  {s.is_default && (
                    <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-purple-50 text-purple-700 border border-purple-200 flex items-center gap-0.5">
                      <Star size={9} className="fill-purple-500 text-purple-500" />
                      Default
                    </span>
                  )}
                  {!s.active && (
                    <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase bg-slate-100 text-slate-400 border border-slate-200">
                      Inactive
                    </span>
                  )}
                </div>
                <p className="font-body text-xs text-slate-400 mt-1">
                  {s.steps.length} step{s.steps.length !== 1 ? "s" : ""} &middot;
                  Created{" "}
                  {new Date(s.created_at).toLocaleDateString("en-US", {
                    dateStyle: "medium",
                  })}
                </p>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => handleToggleActive(s)}
                  title={s.active ? "Deactivate" : "Activate"}
                  className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-slate-500"
                >
                  {s.active ? (
                    <ToggleRight size={20} className="text-emerald-500" />
                  ) : (
                    <ToggleLeft size={20} className="text-slate-400" />
                  )}
                </button>
                <button
                  onClick={() => openPreview(s)}
                  title="Preview"
                  className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors flex items-center gap-1"
                >
                  <Eye size={14} />
                  Preview
                </button>
                <button
                  onClick={() => openEdit(s)}
                  title="Edit"
                  className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors flex items-center gap-1"
                >
                  <Pencil size={14} />
                  Edit
                </button>
                <button
                  onClick={() => setDeletingId(s.id)}
                  title="Delete"
                  className="bg-slate-100 text-rose-600 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-rose-50 transition-colors flex items-center gap-1"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ─── Delete confirmation modal ─── */}

      {deletingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl p-6 shadow-2xl w-full max-w-sm border border-slate-100">
            <h3 className="font-display text-base font-bold text-slate-800 mb-2">
              Delete Script
            </h3>
            <p className="font-body text-sm text-slate-500 mb-6">
              Are you sure you want to delete this script? This action cannot be
              undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeletingId(null)}
                className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deletingId)}
                className="bg-rose-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-rose-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Create / Edit Modal ─── */}

      {showEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl border border-slate-100 max-h-[90vh] flex flex-col">
            {/* Modal header */}
            <div className="flex items-center justify-between p-6 pb-4 border-b border-slate-100 shrink-0">
              <h2 className="font-display text-lg font-bold text-slate-800">
                {editingId ? "Edit Script" : "New Script"}
              </h2>
              <button
                onClick={closeEditor}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {/* Name */}
              <div>
                <label className="block text-xs font-bold text-slate-600 mb-1.5">
                  Script Name
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Segment A Hot Lead Script"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors"
                />
              </div>

              {/* Segment + Default row */}
              <div className="flex gap-4 items-end">
                <div className="flex-1">
                  <label className="block text-xs font-bold text-slate-600 mb-1.5">
                    Segment
                  </label>
                  <select
                    value={formSegment}
                    onChange={(e) => setFormSegment(e.target.value)}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors bg-white"
                  >
                    <option value="">None (All segments)</option>
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                    <option value="D">D</option>
                  </select>
                </div>
                <label className="flex items-center gap-2 pb-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={formIsDefault}
                    onChange={(e) => setFormIsDefault(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-xs font-medium text-slate-600">
                    Default script
                  </span>
                </label>
              </div>

              {/* Steps */}
              <div>
                <label className="block text-xs font-bold text-slate-600 mb-3">
                  Steps
                </label>
                <div className="space-y-4">
                  {formSteps.map((step, idx) => (
                    <div
                      key={idx}
                      className="bg-slate-50 border border-slate-200 rounded-xl p-4 relative group"
                    >
                      <div className="flex items-center gap-2 mb-3">
                        <GripVertical
                          size={14}
                          className="text-slate-300 shrink-0"
                        />
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          Step {idx + 1}
                        </span>
                        {formSteps.length > 1 && (
                          <button
                            onClick={() => removeStep(idx)}
                            className="ml-auto p-1 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-500 transition-colors"
                            title="Remove step"
                          >
                            <X size={14} />
                          </button>
                        )}
                      </div>

                      {/* Text */}
                      <textarea
                        value={step.text}
                        onChange={(e) =>
                          updateStep(idx, { text: e.target.value })
                        }
                        placeholder="Script line the telecaller reads..."
                        rows={2}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors resize-none"
                      />

                      {/* Note */}
                      <input
                        type="text"
                        value={step.note}
                        onChange={(e) =>
                          updateStep(idx, { note: e.target.value })
                        }
                        placeholder="Coaching hint (optional)"
                        className="w-full mt-2 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-600 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors"
                      />

                      {/* Branches */}
                      {step.branches.length > 0 && (
                        <div className="mt-3 space-y-2">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                            <GitBranch size={10} />
                            Branches
                          </span>
                          {step.branches.map((br, bi) => (
                            <div
                              key={bi}
                              className="flex items-center gap-2"
                            >
                              <input
                                type="text"
                                value={br.label}
                                onChange={(e) =>
                                  updateBranch(idx, bi, {
                                    label: e.target.value,
                                  })
                                }
                                placeholder="Label (e.g. Interested)"
                                className="flex-1 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors"
                              />
                              <div className="flex items-center gap-1">
                                <span className="text-[10px] text-slate-400">
                                  Go to
                                </span>
                                <input
                                  type="number"
                                  min={1}
                                  max={formSteps.length}
                                  value={br.goto}
                                  onChange={(e) =>
                                    updateBranch(idx, bi, {
                                      goto: parseInt(e.target.value) || 1,
                                    })
                                  }
                                  className="w-14 border border-slate-200 rounded-lg px-2 py-1.5 text-xs text-slate-700 text-center focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors"
                                />
                              </div>
                              <button
                                onClick={() => removeBranch(idx, bi)}
                                className="p-1 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-500 transition-colors"
                              >
                                <X size={12} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      <button
                        onClick={() => addBranch(idx)}
                        className="mt-2 text-[10px] font-medium text-indigo-600 hover:text-indigo-700 flex items-center gap-1 transition-colors"
                      >
                        <GitBranch size={10} />
                        Add Branch
                      </button>
                    </div>
                  ))}
                </div>

                <button
                  onClick={addStep}
                  className="mt-3 flex items-center gap-1.5 bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors"
                >
                  <Plus size={14} />
                  Add Step
                </button>
              </div>
            </div>

            {/* Modal footer */}
            <div className="flex items-center justify-end gap-3 p-6 pt-4 border-t border-slate-100 shrink-0">
              <button
                onClick={closeEditor}
                className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50"
              >
                {saving && <Loader2 size={14} className="animate-spin" />}
                {editingId ? "Save Changes" : "Create Script"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Preview Modal ─── */}

      {previewScript && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl border border-slate-100 max-h-[90vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-6 pb-4 border-b border-slate-100 shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <Eye size={18} className="text-indigo-500" />
                  <h2 className="font-display text-lg font-bold text-slate-800">
                    Script Preview
                  </h2>
                </div>
                <p className="font-body text-xs text-slate-400 mt-0.5">
                  {previewScript.name}
                  {previewScript.segment
                    ? ` · Segment ${previewScript.segment}`
                    : ""}
                </p>
              </div>
              <button
                onClick={closePreview}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Steps list */}
            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {previewScript.steps
                .sort((a, b) => a.order - b.order)
                .map((step, idx) => {
                  const isCurrent = idx === previewStep;
                  return (
                    <div
                      key={idx}
                      className={`rounded-xl p-4 border-2 transition-all ${
                        isCurrent
                          ? "border-indigo-400 bg-indigo-50/50 shadow-sm"
                          : "border-slate-100 bg-white"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <span
                          className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                            isCurrent
                              ? "bg-indigo-600 text-white"
                              : "bg-slate-200 text-slate-500"
                          }`}
                        >
                          {step.order}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p
                            className={`text-sm ${isCurrent ? "text-slate-900 font-semibold" : "text-slate-600"}`}
                          >
                            {step.text}
                          </p>
                          {step.note && (
                            <p className="text-xs text-slate-400 italic mt-1">
                              {step.note}
                            </p>
                          )}

                          {/* Branch buttons (only on current step) */}
                          {isCurrent && step.branches && step.branches.length > 0 && (
                            <div className="flex flex-wrap gap-2 mt-3">
                              {step.branches.map((br, bi) => (
                                <button
                                  key={bi}
                                  onClick={() => handlePreviewGoto(br.goto)}
                                  className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors flex items-center gap-1"
                                >
                                  <ChevronRight size={12} />
                                  {br.label || `Go to ${br.goto}`}
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

            {/* Footer with navigation */}
            <div className="flex items-center justify-between p-6 pt-4 border-t border-slate-100 shrink-0">
              <span className="text-xs text-slate-400 font-medium">
                Step {previewStep + 1} of {previewScript.steps.length}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() =>
                    setPreviewStep((p) => Math.max(0, p - 1))
                  }
                  disabled={previewStep === 0}
                  className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Back
                </button>
                <button
                  onClick={() =>
                    setPreviewStep((p) =>
                      Math.min(previewScript.steps.length - 1, p + 1)
                    )
                  }
                  disabled={previewStep === previewScript.steps.length - 1}
                  className="flex items-center gap-1 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
