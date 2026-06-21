"use client";
import { toast } from "sonner";
import { useEffect, useMemo, useState } from "react";
import {
  Search, Plus, Trash2, CheckCircle2, XCircle,
  Upload, FileText, Loader2, Info, AlertCircle,
  Database, Sparkles, Save, MessageCircle
} from "lucide-react";
import { api, AIPrompt, API_URL, getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/utils";
import { usePolling } from "@/hooks/usePolling";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { useSearchParams, useRouter } from "next/navigation";

function IgIcon({ size = 14, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

function TgIcon({ size = 14, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function FbIcon({ size = 14, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
    </svg>
  );
}

interface KnowledgeDoc {
  id: string;
  name: string;
  size_bytes: number;
  file_type: string;
  status: string;
  created_at: string;
  chunk_count?: number;
  error_message?: string;
}

type RetrievalMode = "semantic" | "keyword" | "hybrid";

const RETRIEVAL_MODES: { id: RetrievalMode; label: string; desc: string }[] = [
  { id: "semantic", label: "Smart", desc: "Understands meaning & language (Tamil/English), even when a lead rephrases. Recommended." },
  { id: "keyword", label: "Exact words", desc: "Matches the exact words in your documents. Fastest, no AI cost — weaker on reworded questions." },
  { id: "hybrid", label: "Best of both", desc: "Blends meaning + exact words for the highest accuracy." },
];

export default function KnowledgePage() {
  const { role, loading: roleLoading } = useAuthRole();
  const [documents, setDocuments] = useState<KnowledgeDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab = (rawTab === "ai-tune" ? "ai-tune" : "documents") as "documents" | "ai-tune";

  const setTab = (val: "documents" | "ai-tune") => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", val);
    router.replace(`/dashboard/knowledge?${params.toString()}`, { scroll: false });
  };

  // Knowledge search (retrieval) mode
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("semantic");
  const [retrievalSaving, setRetrievalSaving] = useState(false);

  // Document Upload
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [campaignTags, setCampaignTags] = useState<Array<{ id: string; name: string; color?: string }>>([]);
  const [selectedCampaignTag, setSelectedCampaignTag] = useState<string>("");

  // AI Tune
  const [prompts, setPrompts] = useState<AIPrompt[]>([]);
  const [activeName, setActiveName] = useState<string>("whatsapp_reply");
  const [draft, setDraft] = useState<string>("");
  const [tuneMsg, setTuneMsg] = useState<string | null>(null);
  const [tuneSaving, setTuneSaving] = useState(false);

  // Scoring Rubric
  const [scoringRubric, setScoringRubric] = useState<string>("");
  const [rubricSaving, setRubricSaving] = useState(false);

  // Post-Collection Action
  const [postAction, setPostAction] = useState<string>("");
  const [postActionSaving, setPostActionSaving] = useState(false);

  useEffect(() => {
    loadData();
    loadRetrievalMode();
    api.knowledge.listCampaignTags().then(setCampaignTags).catch(() => {});
  }, []);

  const hasProcessing = useMemo(
    () => documents.some((d) => d.status === "processing"),
    [documents]
  );
  usePolling(loadDocuments, 5000, hasProcessing);

  useEffect(() => {
    if (tab === "ai-tune") {
      if (prompts.length === 0) loadPrompts();
      loadAiTuneSettings();
    }
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const cur = prompts.find((x) => x.name === activeName);
    if (cur) setDraft(cur.content);
  }, [activeName, prompts]);

  if (roleLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (role !== "owner") {
    return (
      <div className="text-center py-20">
        <p className="text-on-surface-muted font-body">
          This section is only available for owners/admins.
        </p>
      </div>
    );
  }

  async function loadData() {
    setLoading(true);
    try {
      const docData = await api.knowledge.listDocuments();
      setDocuments(docData);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }

  async function loadDocuments() {
    try {
      const docData = await api.knowledge.listDocuments();
      setDocuments(docData);
    } catch {}
  }

  async function loadRetrievalMode() {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings`, { headers: auth });
      if (!res.ok) return;
      const data = await res.json();
      const settings: { key: string; display_value?: string }[] = data.settings ?? [];
      const v = settings.find((s) => s.key === "kb_retrieval_mode")?.display_value;
      if (v === "semantic" || v === "keyword" || v === "hybrid") setRetrievalMode(v);
    } catch {}
  }

  async function saveRetrievalMode(mode: RetrievalMode) {
    const prev = retrievalMode;
    setRetrievalMode(mode);
    setRetrievalSaving(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ updates: { kb_retrieval_mode: mode } }),
      });
      if (!res.ok) throw new Error("Save failed");
      toast.success(`Search mode set to "${RETRIEVAL_MODES.find((m) => m.id === mode)?.label}".`);
    } catch {
      setRetrievalMode(prev);
      toast.error("Failed to update search mode. Please try again.");
    } finally {
      setRetrievalSaving(false);
    }
  }

  async function loadPrompts() {
    try {
      const p = await api.aiTune.prompts();
      setPrompts(p);
      const cur = p.find((x: AIPrompt) => x.name === activeName) ?? p[0];
      if (cur) {
        setActiveName(cur.name);
        setDraft(cur.content);
      }
    } catch {}
  }

  async function loadAiTuneSettings() {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings`, { headers: auth });
      if (!res.ok) return;
      const data = await res.json();
      const settings: { key: string; display_value: string }[] = data.settings ?? [];
      const rubric = settings.find((s) => s.key === "scoring_rubric");
      const action = settings.find((s) => s.key === "collect_post_action");
      if (rubric) {
        setScoringRubric(rubric.display_value === "Not set" ? "" : rubric.display_value);
      }
      if (action) {
        setPostAction(action.display_value === "Not set" ? "" : action.display_value);
      }
    } catch {}
  }

  async function saveRubric() {
    setRubricSaving(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ updates: { scoring_rubric: scoringRubric } }),
      });
      if (!res.ok) throw new Error("Save failed");
      toast.success("Scoring rubric saved.");
    } catch {
      toast.error("Failed to save rubric. Please try again.");
    } finally {
      setRubricSaving(false);
    }
  }

  async function savePostAction() {
    setPostActionSaving(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ updates: { collect_post_action: postAction } }),
      });
      if (!res.ok) throw new Error("Save failed");
      toast.success("Post-collection action saved.");
    } catch {
      toast.error("Failed to save. Please try again.");
    } finally {
      setPostActionSaving(false);
    }
  }

  const filteredDocs = documents.filter(d =>
    d.name.toLowerCase().includes(search.toLowerCase())
  );

  // Document Handlers
  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    try {
      await api.knowledge.uploadDocument(file, selectedCampaignTag || null);
      loadDocuments();
    } catch {
      setUploadError("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  async function deleteDocument(id: string) {
    if (!confirm("Delete this document and all its indexed knowledge?")) return;
    try {
      await api.knowledge.deleteDocument(id);
      loadDocuments();
    } catch {
      toast.error("Delete failed");
    }
  }

  // AI Tune Handlers
  function handleChannelSwitch(channelId: string) {
    if (draft !== activePrompt?.content) {
      if (!confirm("You have unsaved changes. Switch channel anyway?")) {
        return;
      }
    }
    setActiveName(channelId);
  }

  async function savePrompt() {
    setTuneSaving(true);
    try {
      await api.aiTune.updatePrompt(activeName, draft);
      setTuneMsg("Prompt saved. Generating scoring rubric…");
      await loadPrompts();
      setTimeout(async () => {
        await loadAiTuneSettings();
        setTuneMsg("Prompt saved.");
      }, 4000);
    } catch (err) {
      setTuneMsg(err instanceof Error ? err.message : "Save failed");
    } finally {
      setTuneSaving(false);
    }
  }

  const activePrompt = prompts.find((p) => p.name === activeName);

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="p-1 bg-[#e8e3db]/60 rounded-2xl flex gap-1 self-start w-fit">
        <button
          onClick={() => setTab("documents")}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            tab === "documents"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          <div className="flex items-center gap-2">
            <Database size={16} /> Documents (RAG)
          </div>
        </button>
        <button
          onClick={() => setTab("ai-tune")}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            tab === "ai-tune"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          <div className="flex items-center gap-2">
            <Sparkles size={16} /> AI Tune
          </div>
        </button>
      </div>

      {tab !== "ai-tune" && (
        <div className="relative">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-muted" />
          <input
            type="text"
            placeholder="Search documents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-3 rounded-xl bg-surface border border-surface-mid focus:outline-none focus:ring-2 focus:ring-primary font-body text-sm"
          />
        </div>
      )}

      {tab === "documents" ? (
        <div className="space-y-6">
          {/* Knowledge Search Mode */}
          <div className="bg-surface rounded-card p-5 border border-surface-mid">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-primary" />
              <h3 className="font-display font-bold text-sm text-primary">Knowledge Search Mode</h3>
            </div>
            <p className="font-body text-xs text-on-surface-muted mt-1 mb-4">
              How the AI finds answers in your documents when a lead asks a question.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {RETRIEVAL_MODES.map((m) => {
                const active = retrievalMode === m.id;
                return (
                  <button
                    key={m.id}
                    onClick={() => saveRetrievalMode(m.id)}
                    disabled={retrievalSaving || active}
                    className={cn(
                      "text-left p-4 rounded-xl border-2 transition-all disabled:cursor-default",
                      active ? "border-primary bg-primary/5" : "border-surface-mid hover:border-primary/40"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-label font-bold text-sm text-on-surface">{m.label}</span>
                      {active && <CheckCircle2 size={16} className="text-primary shrink-0" />}
                    </div>
                    <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed">{m.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Upload Section */}
          <div className="bg-surface rounded-card p-6 border border-dashed border-primary/30 bg-primary/5 text-center space-y-4">
            <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center mx-auto">
              <Upload size={24} className="text-primary" />
            </div>
            <div>
              <h3 className="font-display font-bold text-lg text-primary">Upload Knowledge Documents</h3>
              <p className="font-body text-sm text-on-surface-muted">
                Supports PDF, DOCX, PPTX, XLSX, CSV, TXT, and Images. AI will extract and index the content.
              </p>
            </div>
            {campaignTags.length > 0 && (
              <div className="max-w-xs mx-auto text-left">
                <label className="block font-label text-xs font-semibold text-on-surface-muted mb-1">
                  Applies to campaign
                </label>
                <select
                  value={selectedCampaignTag}
                  onChange={(e) => setSelectedCampaignTag(e.target.value)}
                  disabled={uploading}
                  className="w-full px-3 py-2 rounded-xl border border-primary/20 bg-surface font-body text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                >
                  <option value="">All campaigns (shared)</option>
                  {campaignTags.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
                <p className="font-body text-[11px] text-on-surface-muted mt-1">
                  Scopes this document so the AI only uses it for leads from that campaign.
                </p>
              </div>
            )}
            <label className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl font-label font-semibold shadow-card hover:bg-primary/90 transition-all cursor-pointer disabled:opacity-50">
              {uploading ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
              {uploading ? "Uploading & Indexing..." : "Choose File"}
              <input type="file" className="hidden" accept=".pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,image/*" onChange={handleFileUpload} disabled={uploading} />
            </label>
            {uploadError && (
              <p className="text-red-500 text-sm flex items-center justify-center gap-1">
                <AlertCircle size={14} /> {uploadError}
              </p>
            )}
          </div>

          {/* Document List */}
          <div className="bg-surface rounded-card border border-surface-mid overflow-hidden">
            <table className="w-full text-left font-body text-sm">
              <thead className="bg-surface-low border-b border-surface-mid">
                <tr>
                  <th className="px-6 py-4 font-label font-semibold text-xs text-on-surface-muted uppercase">Document</th>
                  <th className="px-6 py-4 font-label font-semibold text-xs text-on-surface-muted uppercase">Type</th>
                  <th className="px-6 py-4 font-label font-semibold text-xs text-on-surface-muted uppercase">Status</th>
                  <th className="px-6 py-4 font-label font-semibold text-xs text-on-surface-muted uppercase">Created</th>
                  <th className="px-6 py-4 font-label font-semibold text-xs text-on-surface-muted uppercase text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-mid">
                {loading ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-on-surface-muted">
                      <Loader2 size={24} className="animate-spin mx-auto mb-2" />
                      Loading documents...
                    </td>
                  </tr>
                ) : filteredDocs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-on-surface-muted">
                      No documents uploaded yet.
                    </td>
                  </tr>
                ) : (
                  filteredDocs.map(doc => (
                    <tr key={doc.id} className="hover:bg-surface-low transition-all group">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-primary/5 rounded-lg">
                            <FileText size={18} className="text-primary" />
                          </div>
                          <div>
                            <p className="font-semibold text-on-surface">{doc.name}</p>
                            <p className="text-xs text-on-surface-muted">{(doc.size_bytes / 1024).toFixed(1)} KB</p>
                            {doc.status === "failed" && (
                              <p className="text-xs text-red-500 mt-0.5 max-w-xs" title={doc.error_message || undefined}>
                                {doc.error_message ? doc.error_message.slice(0, 80) + (doc.error_message.length > 80 ? "…" : "") : "Indexing failed — delete and re-upload"}
                              </p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-on-surface-muted">
                        {doc.file_type.split("/")[1]?.toUpperCase() || "FILE"}
                      </td>
                      <td className="px-6 py-4">
                        <div className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-label font-bold uppercase",
                          doc.status === "indexed" ? "bg-green-100 text-green-700" :
                          doc.status === "processing" ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                        )}>
                          {doc.status === "indexed" ? <CheckCircle2 size={12} /> :
                           doc.status === "processing" ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
                          {doc.status}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-on-surface-muted text-xs">
                        {new Date(doc.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => deleteDocument(doc.id)}
                          className="p-2 text-on-surface-muted hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-start gap-2 p-4 bg-amber-50 border border-amber-100 rounded-xl text-amber-800">
            <Info size={16} className="shrink-0 mt-0.5" />
            <p className="text-xs leading-relaxed">
              <strong>How RAG works:</strong> When a user asks a question, the system searches these documents for the most relevant information.
              The AI then uses those specific snippets to form an accurate, non-hallucinated answer.
            </p>
          </div>
        </div>
      ) : (
        /* AI Tune Tab */
        <div className="space-y-4 animate-in fade-in duration-200">
          {tuneMsg && (
            <div className="p-3 rounded-xl bg-surface-low text-primary font-label text-sm">
              {tuneMsg}
            </div>
          )}

          {/* Channel Selector Pills */}
          <div className="flex flex-wrap gap-2 p-1.5 bg-surface-low rounded-2xl border border-surface-mid/60 w-fit">
            {[
              { id: "whatsapp_reply", label: "WhatsApp", icon: <MessageCircle size={14} className="shrink-0" />, colorClass: "hover:bg-surface-mid text-on-surface-muted hover:text-on-surface", activeClass: "bg-green-600 text-white shadow-sm" },
              { id: "telegram_reply", label: "Telegram", icon: <TgIcon size={14} className="shrink-0" />, colorClass: "hover:bg-surface-mid text-on-surface-muted hover:text-on-surface", activeClass: "bg-sky-600 text-white shadow-sm" },
              { id: "instagram_reply", label: "Instagram", icon: <IgIcon size={14} className="shrink-0" />, colorClass: "hover:bg-surface-mid text-on-surface-muted hover:text-on-surface", activeClass: "bg-pink-600 text-white shadow-sm" },
              { id: "facebook_reply", label: "Facebook Messenger", icon: <FbIcon size={14} className="shrink-0" />, colorClass: "hover:bg-surface-mid text-on-surface-muted hover:text-on-surface", activeClass: "bg-blue-600 text-white shadow-sm" },
            ].map((chan) => {
              const isActive = activeName === chan.id;
              return (
                <button
                  key={chan.id}
                  onClick={() => handleChannelSwitch(chan.id)}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold font-label transition-all duration-200",
                    isActive ? chan.activeClass : chan.colorClass
                  )}
                >
                  {chan.icon}
                  <span>{chan.label}</span>
                </button>
              );
            })}
          </div>

          <div className="bg-surface rounded-card p-8 shadow-card ring-1 ring-[#c4c7c7]/15">
            <div className="mb-4">
              <h2 className="font-display text-lg font-bold text-primary">
                Active Prompt: {activeName === "whatsapp_reply" ? "WhatsApp" : activeName === "telegram_reply" ? "Telegram" : activeName === "instagram_reply" ? "Instagram" : "Facebook Messenger"}
              </h2>
              <p className="font-body text-sm text-on-surface-muted mt-0.5">
                {activeName === "whatsapp_reply" && "Edit the system prompt used by the WhatsApp AI auto-reply."}
                {activeName === "telegram_reply" && "Edit the system prompt used by the Telegram AI auto-reply."}
                {activeName === "instagram_reply" && "Edit the system prompt used by the Instagram AI auto-reply."}
                {activeName === "facebook_reply" && "Edit the system prompt used by the Facebook Messenger AI auto-reply."}
              </p>
            </div>
            {activePrompt && (
              <p className="font-label text-sm text-on-surface-muted mb-3">
                Updated {timeAgo(activePrompt.updated_at)} — {activePrompt.content.length} chars
              </p>
            )}
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={18}
              spellCheck={false}
              className="w-full px-5 py-4 rounded-xl bg-surface-low border border-surface-mid font-mono text-base leading-7 focus:outline-none focus:ring-2 focus:ring-primary"
              style={{ fontSize: "15px", lineHeight: "1.7" }}
            />
            <div className="mt-4 flex gap-3">
              <button
                onClick={savePrompt}
                disabled={tuneSaving || draft === activePrompt?.content}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40"
              >
                <Save size={14} /> {tuneSaving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>

          {/* Section A: Scoring Rubric */}
          <div className="bg-surface rounded-card p-8 shadow-card ring-1 ring-[#c4c7c7]/15">
            <div className="mb-4">
              <h2 className="font-display text-lg font-bold text-primary">Scoring Rubric</h2>
              <p className="font-body text-sm text-on-surface-muted mt-0.5">
                Used to score leads 1–10. Auto-generated from your system prompt — edit to customize.
              </p>
            </div>
            <textarea
              value={scoringRubric}
              onChange={(e) => setScoringRubric(e.target.value)}
              rows={8}
              spellCheck={false}
              placeholder={
                "9-10: High intent — asked about pricing, booking, or next steps\n" +
                "7-8: Warm — showed clear interest, asked product questions\n" +
                "5-6: Neutral — general inquiry, no strong buying signal\n" +
                "3-4: Lukewarm — vague interest, one-word replies\n" +
                "1-2: Low — unresponsive, spam, or out-of-scope"
              }
              className="w-full px-5 py-4 rounded-xl bg-surface-low border border-surface-mid font-mono text-sm leading-6 focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <div className="mt-4 flex gap-3">
              <button
                onClick={saveRubric}
                disabled={rubricSaving}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40"
              >
                <Save size={14} /> {rubricSaving ? "Saving…" : "Save Rubric"}
              </button>
            </div>
          </div>

          {/* Section B: Post-Collection Action */}
          <div className="bg-surface rounded-card p-8 shadow-card ring-1 ring-[#c4c7c7]/15">
            <div className="mb-4">
              <h2 className="font-display text-lg font-bold text-primary">After Data Collection</h2>
              <p className="font-body text-sm text-on-surface-muted mt-0.5">
                What should Aira do when the AI finishes collecting all required fields?
              </p>
            </div>
            <select
              value={postAction}
              onChange={(e) => setPostAction(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-surface-low border border-surface-mid font-body text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">Do nothing (just save the data)</option>
              <option value="send_payment_link">Send payment link (Razorpay)</option>
              <option value="notify_telecaller">Alert assigned telecaller</option>
            </select>
            <div className="mt-4 flex gap-3">
              <button
                onClick={savePostAction}
                disabled={postActionSaving}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40"
              >
                <Save size={14} /> {postActionSaving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
