"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Plus,
  RefreshCw,
  Search,
  Filter,
  Grid,
  List,
  Shuffle,
  Trash2,
  Eye,
  Layers,
  ChevronRight,
  X,
  AlertCircle,
  HelpCircle,
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { LANGUAGES, STATUS_COLORS } from "./types";
import type { Template } from "./types";
import TemplateCard from "./components/template-card";
import WhatsAppPreview from "./components/whatsapp-preview";

export default function TemplatesPage() {
  const router = useRouter();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Sync / Action states
  const [syncing, setSyncing] = useState(false);
  const [syncingId, setSyncingId] = useState<string | null>(null);

  // Search & Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [viewMode, setViewMode] = useState<"GRID" | "TABLE">("GRID");

  // Selected Detail Modal
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);

  // Variations Modal
  const [variationsModalId, setVariationsModalId] = useState<string | null>(null);
  const [variationsList, setVariationsList] = useState<string[]>([]);
  const [newVariation, setNewVariation] = useState("");
  const [variationsLoading, setVariationsLoading] = useState(false);

  // Load templates from API
  async function loadTemplates() {
    setLoading(true);
    setError(null);
    try {
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/templates/`, {
        headers: authHeaders,
      });
      if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
      const data = await res.json();
      setTemplates(data.data || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load templates");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTemplates();
  }, []);

  // Sync all templates from Meta
  async function handleSyncAll() {
    setSyncing(true);
    setError(null);
    try {
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/templates/sync-from-meta`, {
        method: "POST",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Failed to sync templates from Meta");
      const result = await res.json();
      await loadTemplates();
      alert(`Sync completed: ${result.total} templates synced (${result.added} added, ${result.updated} updated).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync from Meta failed");
    } finally {
      setSyncing(false);
    }
  }

  // Single Template Actions
  async function handleSyncSingle(id: string, e?: React.MouseEvent) {
    e?.stopPropagation();
    setSyncingId(id);
    try {
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/templates/${id}/sync`, {
        method: "POST",
        headers: authHeaders,
      });
      if (res.ok) {
        const updated = await res.json();
        setTemplates((prev) => prev.map((t) => (t.id === id ? updated : t)));
      }
    } catch {
      // ignore failures
    } finally {
      setSyncingId(null);
    }
  }

  async function handleDelete(id: string, e?: React.MouseEvent) {
    e?.stopPropagation();
    if (!confirm("Are you sure you want to delete this template?")) return;
    try {
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/templates/${id}`, {
        method: "DELETE",
        headers: authHeaders,
      });
      if (res.ok) {
        setTemplates((prev) => prev.filter((t) => t.id !== id));
        if (selectedTemplate?.id === id) {
          setSelectedTemplate(null);
        }
      } else {
        throw new Error("Failed to delete template");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  // Variations Modal Logic
  async function openVariationsModal(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    setVariationsModalId(id);
    setVariationsList([]);
    setNewVariation("");
    setVariationsLoading(true);
    try {
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/templates/${id}/variations`, {
        headers: authHeaders,
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setVariationsList(data.variations ?? []);
    } catch {
      setVariationsList([]);
    } finally {
      setVariationsLoading(false);
    }
  }

  async function handleVariationAdd() {
    const nameTrimmed = newVariation.trim();
    if (!nameTrimmed || !variationsModalId) return;
    const next = [...variationsList, nameTrimmed];
    setVariationsList(next);
    setNewVariation("");
    try {
      const authHeaders = await getAuthHeaders();
      await fetch(`${API_URL}/api/v1/templates/${variationsModalId}/variations`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders },
        body: JSON.stringify({ variations: next }),
      });
    } catch {
      setVariationsList((prev) => prev.filter((v) => v !== nameTrimmed));
    }
  }

  async function handleVariationRemove(varName: string) {
    if (!variationsModalId) return;
    const next = variationsList.filter((v) => v !== varName);
    setVariationsList(next);
    try {
      const authHeaders = await getAuthHeaders();
      await fetch(`${API_URL}/api/v1/templates/${variationsModalId}/variations`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders },
        body: JSON.stringify({ variations: next }),
      });
    } catch {
      setVariationsList((prev) => [...prev, varName]);
    }
  }

  // Filter Logic
  const filteredTemplates = templates.filter((t) => {
    const matchesSearch = t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.body_text.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategory === "ALL" || t.category === selectedCategory;
    const matchesStatus = selectedStatus === "ALL" || t.status === selectedStatus;
    return matchesSearch && matchesCategory && matchesStatus;
  });

  // Calculate statistics
  const countApproved = templates.filter((t) => t.status === "APPROVED").length;
  const countPending = templates.filter((t) => t.status === "PENDING").length;
  const countRejected = templates.filter((t) => t.status === "REJECTED" || t.status === "PAUSED").length;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex justify-end gap-4 flex-wrap">
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={handleSyncAll}
            disabled={syncing}
            className="btn-ghost flex items-center gap-2 text-xs font-semibold text-ink-secondary"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            {syncing ? "Syncing..." : "Sync from Meta"}
          </button>

          <Link href="/dashboard/templates/carousel" className="btn-ghost flex items-center gap-2 text-xs font-semibold">
            <Layers size={14} />
            New Carousel
          </Link>

          <Link href="/dashboard/templates/new" className="btn-primary flex items-center gap-2 text-xs font-semibold">
            <Plus size={14} />
            Create Template
          </Link>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: "Approved Templates", count: countApproved, color: "#10b981", bg: "bg-emerald-50/50", border: "border-emerald-100" },
          { label: "Pending Review", count: countPending, color: "#f59e0b", bg: "bg-amber-50/50", border: "border-amber-100" },
          { label: "Rejected / Paused", count: countRejected, color: "#ef4444", bg: "bg-red-50/50", border: "border-red-100" },
        ].map((s) => (
          <div key={s.label} className={`card p-4 rounded-2xl border ${s.border} ${s.bg} flex items-center gap-4 shadow-sm`}>
            <div className="w-12 h-12 rounded-xl bg-white border border-border-subtle flex items-center justify-center font-bold text-lg" style={{ color: s.color }}>
              {s.count}
            </div>
            <div>
              <p className="font-body text-xs text-ink-muted uppercase tracking-wider font-bold">{s.label}</p>
              <p className="font-display font-semibold text-ink text-sm mt-0.5">templates loaded</p>
            </div>
          </div>
        ))}
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl text-sm flex items-center gap-2 animate-slide-up">
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      {/* Filter and View Controls Bar */}
      <div className="flex flex-row items-center justify-between gap-3 p-4 bg-white border border-border-subtle rounded-2xl shadow-sm overflow-x-auto whitespace-nowrap">
        {/* Search input */}
        <div className="relative shrink-0 w-64">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search templates..."
            style={{ paddingLeft: "2.25rem" }}
            className="input text-xs py-2 w-full"
          />
        </div>

        {/* Dropdowns & Toggle */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="flex items-center gap-1">
            <Filter size={13} className="text-ink-muted hidden md:inline" />
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="input text-xs py-1.5 px-3 min-w-[120px] max-w-[150px] bg-white cursor-pointer"
            >
              <option value="ALL">All Types</option>
              <option value="MARKETING">Marketing</option>
              <option value="UTILITY">Utility</option>
              <option value="AUTHENTICATION">Authentication</option>
            </select>
          </div>

          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="input text-xs py-1.5 px-3 min-w-[120px] max-w-[150px] bg-white cursor-pointer"
          >
            <option value="ALL">All Statuses</option>
            <option value="APPROVED">Approved</option>
            <option value="PENDING">Pending</option>
            <option value="REJECTED">Rejected</option>
            <option value="PAUSED">Paused</option>
          </select>

          {/* Grid/Table Toggle */}
          <div className="border border-border-subtle rounded-xl p-0.5 flex items-center bg-surface-subtle">
            <button
              onClick={() => setViewMode("GRID")}
              className={`p-1.5 rounded-lg transition-all ${
                viewMode === "GRID" ? "bg-white shadow-sm text-emerald-600" : "text-ink-muted hover:text-ink"
              }`}
            >
              <Grid size={14} />
            </button>
            <button
              onClick={() => setViewMode("TABLE")}
              className={`p-1.5 rounded-lg transition-all ${
                viewMode === "TABLE" ? "bg-white shadow-sm text-emerald-600" : "text-ink-muted hover:text-ink"
              }`}
            >
              <List size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="card h-64 border border-border-subtle rounded-2xl animate-pulse bg-surface-subtle" />
          ))}
        </div>
      ) : filteredTemplates.length === 0 ? (
        <div className="card text-center py-16 rounded-3xl border border-border-subtle bg-white">
          <HelpCircle size={36} className="mx-auto text-ink-muted mb-3" />
          <p className="font-display font-semibold text-ink text-base">No Templates Found</p>
          <p className="font-body text-xs text-ink-muted mt-1 max-w-xs mx-auto leading-relaxed">
            Create a new template to submit it to WhatsApp, or sync with Meta to load your existing structures.
          </p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <button onClick={handleSyncAll} className="btn-ghost text-xs">Sync from Meta</button>
            <Link href="/dashboard/templates/new" className="btn-primary text-xs px-5 py-2">
              New Template
            </Link>
          </div>
        </div>
      ) : viewMode === "GRID" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredTemplates.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              onEdit={(tmpl) => router.push(`/dashboard/templates/${tmpl.id}`)}
              onDelete={(tmpl) => handleDelete(tmpl.id)}
              onSync={(tmpl) => handleSyncSingle(tmpl.id)}
              onSend={(tmpl) => router.push(`/dashboard/outbound-leads?template=${encodeURIComponent(tmpl.name)}`)}
              onDuplicate={(tmpl) => {
                // Quick duplicate to builder
                router.push(`/dashboard/templates/new?duplicate=${tmpl.id}`);
              }}
            />
          ))}
        </div>
      ) : (
        /* Table View */
        <div className="bg-white border border-border-subtle rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-subtle border-b border-border-subtle text-ink-muted text-[11px] font-bold uppercase tracking-wider">
                  <th className="px-5 py-3.5">Template Name</th>
                  <th className="px-5 py-3.5">Category</th>
                  <th className="px-5 py-3.5">Language</th>
                  <th className="px-5 py-3.5">Status</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle text-xs">
                {filteredTemplates.map((t) => {
                  const statusColors = STATUS_COLORS[t.status] || { bg: "bg-gray-100", text: "text-gray-600", dot: "bg-gray-400" };
                  return (
                    <tr
                      key={t.id}
                      onClick={() => setSelectedTemplate(t)}
                      className="hover:bg-surface-subtle/40 transition-colors cursor-pointer"
                    >
                      <td className="px-5 py-4 font-mono font-medium text-ink truncate max-w-[200px]">
                        {t.name}
                      </td>
                      <td className="px-5 py-4 text-ink-secondary">
                        {t.category}
                      </td>
                      <td className="px-5 py-4 text-ink-secondary">
                        {LANGUAGES.find((l) => l.code === t.language)?.label || t.language}
                      </td>
                      <td className="px-5 py-4">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full font-semibold ${statusColors.bg} ${statusColors.text}`}>
                          <span className={`w-1 h-1 rounded-full ${statusColors.dot}`} />
                          {t.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => setSelectedTemplate(t)}
                            className="p-1.5 rounded-lg hover:bg-surface-subtle text-ink-muted hover:text-ink"
                            title="View Preview"
                          >
                            <Eye size={13} />
                          </button>
                          <button
                            onClick={(e) => handleSyncSingle(t.id, e)}
                            disabled={syncingId === t.id}
                            className="p-1.5 rounded-lg hover:bg-surface-subtle text-ink-muted hover:text-ink disabled:opacity-50"
                            title="Sync Status"
                          >
                            <RefreshCw size={13} className={syncingId === t.id ? "animate-spin" : ""} />
                          </button>
                          <button
                            onClick={(e) => openVariationsModal(t.id, e)}
                            className="p-1.5 rounded-lg hover:bg-violet-50 text-ink-muted hover:text-violet-600"
                            title="Rotate Variations"
                          >
                            <Shuffle size={13} />
                          </button>
                          <button
                            onClick={() => router.push(`/dashboard/templates/${t.id}`)}
                            className="p-1.5 rounded-lg hover:bg-emerald-50 text-ink-muted hover:text-emerald-600"
                            title="Open Detail/Editor"
                          >
                            <ChevronRight size={13} />
                          </button>
                          <button
                            onClick={(e) => handleDelete(t.id, e)}
                            className="p-1.5 rounded-lg hover:bg-red-50 text-ink-muted hover:text-red-500"
                            title="Delete"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── View Detail Drawer/Modal ─────────────────────────────────────────── */}
      {selectedTemplate && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-4xl overflow-hidden flex flex-col max-h-[85vh] animate-slide-up">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-5 border-b border-border-subtle bg-surface-subtle">
              <div className="min-w-0">
                <p className="font-body text-[10px] text-ink-muted uppercase font-bold tracking-wider">Template Detail</p>
                <h2 className="font-mono text-sm font-semibold text-ink truncate max-w-lg mt-0.5">{selectedTemplate.name}</h2>
              </div>
              <button
                onClick={() => setSelectedTemplate(null)}
                className="p-2 rounded-xl hover:bg-white/80 text-ink-muted hover:text-ink transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
              {/* Left Column: Metadata */}
              <div className="md:col-span-6 space-y-4">
                <div className="grid grid-cols-2 gap-4 bg-surface-subtle/40 p-4 rounded-2xl border border-border-subtle">
                  <div>
                    <p className="font-body text-[10px] text-ink-muted uppercase font-bold tracking-wider">Category</p>
                    <p className="font-body text-xs font-semibold text-ink mt-0.5">{selectedTemplate.category}</p>
                  </div>
                  <div>
                    <p className="font-body text-[10px] text-ink-muted uppercase font-bold tracking-wider">Language</p>
                    <p className="font-body text-xs font-semibold text-ink mt-0.5">
                      {LANGUAGES.find((l) => l.code === selectedTemplate.language)?.label || selectedTemplate.language}
                    </p>
                  </div>
                  <div>
                    <p className="font-body text-[10px] text-ink-muted uppercase font-bold tracking-wider">Meta ID</p>
                    <p className="font-mono text-[10px] font-semibold text-ink truncate mt-0.5 select-all">
                      {selectedTemplate.meta_template_id || "None"}
                    </p>
                  </div>
                  <div>
                    <p className="font-body text-[10px] text-ink-muted uppercase font-bold tracking-wider">Status</p>
                    <p className="font-body text-xs font-semibold text-ink mt-0.5">{selectedTemplate.status}</p>
                  </div>
                </div>

                {selectedTemplate.rejection_reason && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
                    <p className="font-semibold mb-0.5">WhatsApp Rejection Reason:</p>
                    <p className="leading-relaxed">{selectedTemplate.rejection_reason}</p>
                  </div>
                )}

                <div className="space-y-2">
                  <h3 className="font-body text-xs font-bold text-ink uppercase tracking-wider">Configuration</h3>
                  {selectedTemplate.header_text && (
                    <div>
                      <p className="font-body text-[10px] text-ink-muted">Header Text</p>
                      <p className="font-body text-xs text-ink">{selectedTemplate.header_text}</p>
                    </div>
                  )}
                  {selectedTemplate.footer_text && (
                    <div>
                      <p className="font-body text-[10px] text-ink-muted">Footer Text</p>
                      <p className="font-body text-xs text-ink-muted">{selectedTemplate.footer_text}</p>
                    </div>
                  )}
                  <div>
                    <p className="font-body text-[10px] text-ink-muted">Body Text</p>
                    <p className="font-body text-xs text-ink whitespace-pre-wrap leading-relaxed select-all">
                      {selectedTemplate.body_text}
                    </p>
                  </div>
                </div>
              </div>

              {/* Right Column: Live Preview */}
              <div className="md:col-span-6 space-y-3">
                <label className="font-body text-xs font-bold text-ink uppercase tracking-wider block">Live Message Preview</label>
                <WhatsAppPreview
                  headerType={selectedTemplate.header_media_type as "NONE" | "TEXT" | "IMAGE" | "VIDEO" | "DOCUMENT" | undefined}
                  headerText={selectedTemplate.header_text || undefined}
                  headerMediaUrl={selectedTemplate.header_media_url || undefined}
                  bodyText={selectedTemplate.body_text}
                  footerText={selectedTemplate.footer_text || undefined}
                  buttons={selectedTemplate.buttons?.map((b) => ({
                    type: b.type,
                    text: b.type === "ONE_TAP" ? (b.autofill_text || "Autofill") : b.text,
                    url: b.url,
                    phone: b.phone,
                  })) || []}
                />
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-border-subtle bg-white flex items-center justify-end gap-2.5">
              <button onClick={() => setSelectedTemplate(null)} className="btn-ghost text-xs">Close</button>
              {(selectedTemplate.status === "REJECTED" || selectedTemplate.status === "PAUSED") && (
                <button
                  onClick={() => {
                    setSelectedTemplate(null);
                    router.push(`/dashboard/templates/${selectedTemplate.id}`);
                  }}
                  className="btn-primary text-xs bg-emerald-600 hover:bg-emerald-700"
                >
                  Edit and Resubmit
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Template Variations Modal ─────────────────────────────────────── */}
      {variationsModalId && (() => {
        const t = templates.find((x) => x.id === variationsModalId);
        return (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md p-6 animate-slide-up">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl bg-violet-50 flex items-center justify-center">
                    <Shuffle size={16} className="text-violet-600" />
                  </div>
                  <div>
                    <h2 className="font-display font-bold text-ink text-sm">Message Variations</h2>
                    {t && <p className="font-mono text-[10px] text-ink-muted mt-0.5 truncate max-w-[200px]">{t.name}</p>}
                  </div>
                </div>
                <button
                  onClick={() => {
                    setVariationsModalId(null);
                    setVariationsList([]);
                  }}
                  className="p-1.5 rounded-lg hover:bg-surface-subtle text-ink-muted"
                >
                  <X size={16} />
                </button>
              </div>

              <p className="font-body text-xs text-ink-muted leading-relaxed mb-4">
                Add other approved templates to rotate inside broadcasts. When sending messages, Aira will select randomly among variations.
              </p>

              {variationsLoading ? (
                <div className="space-y-2 mb-4">
                  <div className="h-8 rounded-lg bg-surface-subtle animate-pulse" />
                  <div className="h-8 rounded-lg bg-surface-subtle animate-pulse" />
                </div>
              ) : (
                <div className="space-y-4">
                  {variationsList.length === 0 ? (
                    <p className="text-xs text-ink-muted italic text-center py-4 bg-surface-subtle rounded-xl">No sibling variations configured.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {variationsList.map((v) => (
                        <span key={v} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-50 text-violet-700 text-xs font-mono font-medium">
                          {v}
                          <button onClick={() => handleVariationRemove(v)} className="text-violet-400 hover:text-violet-700">
                            <X size={12} />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Add Input */}
                  <div className="flex gap-2">
                    <input
                      value={newVariation}
                      onChange={(e) => setNewVariation(e.target.value)}
                      placeholder="Template name (exact case)"
                      className="input text-xs flex-1"
                    />
                    <button
                      onClick={handleVariationAdd}
                      disabled={!newVariation.trim()}
                      className="btn-primary text-xs px-4 disabled:opacity-50"
                    >
                      Add
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
