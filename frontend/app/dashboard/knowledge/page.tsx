"use client";
import { toast } from "sonner";
import { useEffect, useMemo, useState } from "react";
import {
  Search, Plus, Trash2, CheckCircle2, XCircle,
  Upload, FileText, Loader2, Info, AlertCircle,
  Database, Sparkles, Save, Link as LinkIcon
} from "lucide-react";
import { api, API_URL, getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";
import { usePolling } from "@/hooks/usePolling";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { useSearchParams, useRouter } from "next/navigation";

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


export default function KnowledgePage() {
  const { role, permissions, loading: roleLoading } = useAuthRole();
  const canViewKnowledge = role === "owner" || permissions.includes("knowledge.view") || permissions.includes("knowledge.manage");
  const canManageKnowledge = role === "owner" || permissions.includes("knowledge.manage");
  const [documents, setDocuments] = useState<KnowledgeDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  // "ai-tune" is still accepted so existing bookmarks and links keep working.
  const tab = (rawTab === "description" || rawTab === "ai-tune" ? "description" : "documents") as
    | "documents"
    | "description";

  const setTab = (val: "documents" | "description") => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", val);
    router.replace(`/dashboard/knowledge?${params.toString()}`, { scroll: false });
  };

  // Document Upload
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [campaignTags, setCampaignTags] = useState<Array<{ id: string; name: string; color?: string }>>([]);
  const [selectedCampaignTag, setSelectedCampaignTag] = useState<string>("");

  // Business Description
  const [description, setDescription] = useState<string>("");
  const [savedDescription, setSavedDescription] = useState<string>("");
  const [descSaving, setDescSaving] = useState(false);

  // App / Download Link
  const [appLink, setAppLink] = useState<string>("");
  const [savedAppLink, setSavedAppLink] = useState<string>("");
  const [appLinkSaving, setAppLinkSaving] = useState(false);

  // Scoring Rubric
  const [scoringRubric, setScoringRubric] = useState<string>("");
  const [savedRubric, setSavedRubric] = useState<string>("");
  const [rubricSaving, setRubricSaving] = useState(false);



  useEffect(() => {
    loadData();
    api.knowledge.listCampaignTags().then(setCampaignTags).catch(() => {});
  }, []);

  const hasProcessing = useMemo(
    () => documents.some((d) => d.status === "processing"),
    [documents]
  );
  usePolling(loadDocuments, 5000, hasProcessing);

  useEffect(() => {
    if (tab === "description") {
      loadDescription();
      loadAppLink();
      loadAiTuneSettings();
    }
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  if (roleLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (!canViewKnowledge) {
    return (
      <div className="text-center py-20">
        <p className="text-on-surface-muted font-body">
          You do not have access to the knowledge base.
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


  async function loadDescription() {
    try {
      const d = await api.aiTune.description();
      setDescription(d);
      setSavedDescription(d);
    } catch {}
  }

  async function loadAppLink() {
    try {
      const l = await api.aiTune.appLink();
      setAppLink(l);
      setSavedAppLink(l);
    } catch {}
  }

  async function loadAiTuneSettings() {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/`, { headers: auth });
      if (!res.ok) return;
      const data = await res.json();
      const settings: { key: string; display_value: string }[] = data.settings ?? [];
      const rubric = settings.find((s) => s.key === "scoring_rubric");
      if (rubric) {
        const val = rubric.display_value === "Not set" ? "" : rubric.display_value;
        setScoringRubric(val);
        setSavedRubric(val);
      }
    } catch {}
  }

  async function saveRubric() {
    setRubricSaving(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ updates: { scoring_rubric: scoringRubric } }),
      });
      if (!res.ok) throw new Error("Save failed");
      setSavedRubric(scoringRubric);
      toast.success("Scoring rubric saved.");
    } catch {
      toast.error("Failed to save rubric. Please try again.");
    } finally {
      setRubricSaving(false);
    }
  }



  const filteredDocs = documents.filter(d =>
    d.name.toLowerCase().includes(search.toLowerCase())
  );

  // Document Handlers
  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    if (!canManageKnowledge) {
      setUploadError("Read-only role: document upload is disabled.");
      return;
    }
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

  // Business Description Handler
  async function saveDescription() {
    setDescSaving(true);
    try {
      await api.aiTune.updateDescription(description);
      setSavedDescription(description);
      toast.success("Description saved. Updating scoring rubric…");
      setTimeout(loadAiTuneSettings, 4000);
    } catch {
      toast.error("Failed to save description. Please try again.");
    } finally {
      setDescSaving(false);
    }
  }

  // App Link Handler
  async function saveAppLink() {
    setAppLinkSaving(true);
    try {
      await api.aiTune.updateAppLink(appLink);
      setSavedAppLink(appLink);
      toast.success("App link saved.");
    } catch {
      toast.error("Failed to save app link. Please try again.");
    } finally {
      setAppLinkSaving(false);
    }
  }

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
          onClick={() => setTab("description")}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            tab === "description"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          <div className="flex items-center gap-2">
            <Sparkles size={16} /> Description
          </div>
        </button>
      </div>

      {tab !== "description" && (
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
            <label className={cn("inline-flex items-center gap-2 px-6 py-3 rounded-xl font-label font-semibold shadow-card transition-all", canManageKnowledge ? "bg-primary text-white hover:bg-primary/90 cursor-pointer" : "bg-primary text-white opacity-45 blur-[0.5px] cursor-not-allowed")}>
              {uploading ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
              {uploading ? "Uploading & Indexing..." : "Choose File"}
              <input type="file" className="hidden" accept=".pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,image/*" onChange={handleFileUpload} disabled={uploading || !canManageKnowledge} />
            </label>
            {uploadError && (
              <p className="text-red-500 text-sm flex items-center justify-center gap-1">
                <AlertCircle size={14} /> {uploadError}
              </p>
            )}
          </div>

          {/* Document List */}
          <div className="bg-surface rounded-card border border-surface-mid overflow-hidden">
            <div className="space-y-3 p-3 md:hidden">
              {loading ? (
                <div className="py-10 text-center text-on-surface-muted">
                  <Loader2 size={24} className="mx-auto mb-2 animate-spin" />
                  Loading documents...
                </div>
              ) : filteredDocs.length === 0 ? (
                <div className="py-10 text-center text-on-surface-muted">No documents uploaded yet.</div>
              ) : (
                filteredDocs.map((doc) => (
                  <div key={doc.id} className="rounded-2xl border border-surface-mid bg-white p-4 shadow-sm">
                    <div className="flex items-start gap-3">
                      <div className="rounded-xl bg-primary/5 p-2">
                        <FileText size={18} className="text-primary" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-semibold text-on-surface">{doc.name}</p>
                        <p className="mt-1 text-xs text-on-surface-muted">
                          {doc.file_type.split("/")[1]?.toUpperCase() || "FILE"} · {(doc.size_bytes / 1024).toFixed(1)} KB · {new Date(doc.created_at).toLocaleDateString()}
                        </p>
                        {doc.status === "failed" && (
                          <p className="mt-2 line-clamp-2 text-xs text-red-500">
                            {doc.error_message || "Indexing failed — delete and re-upload"}
                          </p>
                        )}
                      </div>
                      {canManageKnowledge && (
                        <button
                          onClick={() => deleteDocument(doc.id)}
                          className="rounded-lg p-2 text-on-surface-muted transition-all hover:bg-red-50 hover:text-red-500"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                    <div className={cn(
                      "mt-3 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-label text-[10px] font-bold uppercase",
                      doc.status === "indexed" ? "bg-green-100 text-green-700" :
                      doc.status === "processing" ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                    )}>
                      {doc.status === "indexed" ? <CheckCircle2 size={12} /> :
                       doc.status === "processing" ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
                      {doc.status}
                    </div>
                  </div>
                ))
              )}
            </div>
            <table className="hidden w-full text-left font-body text-sm md:table">
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
                        {canManageKnowledge && (
                          <button
                            onClick={() => deleteDocument(doc.id)}
                            className="p-2 text-on-surface-muted hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
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
        /* Description Tab */
        <div className="space-y-4 animate-in fade-in duration-200">
          <div className="bg-surface rounded-card p-8 shadow-card ring-1 ring-[#c4c7c7]/15">
            <div className="mb-4">
              <h2 className="font-display text-lg font-bold text-primary">Business Description</h2>
              <p className="font-body text-sm text-on-surface-muted mt-0.5">
                Describe your business, your products or services, and the role your
                assistant plays for customers. Write it in plain language — how you would
                explain it to a new employee on their first day. Your assistant uses this
                to understand who it is and what it is talking about.
              </p>
            </div>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={!canManageKnowledge}
              rows={14}
              placeholder="Example: We are a Vedic astrology consultancy based in Chennai. We offer birth-chart readings, marriage compatibility matching, and gemstone guidance. Consultations happen online over video call or in person at our office. Most customers come to us with questions about marriage timing, career direction, or family matters."
              className="w-full px-5 py-4 rounded-xl bg-surface-low border border-surface-mid font-body leading-7 focus:outline-none focus:ring-2 focus:ring-primary"
              style={{ fontSize: "15px", lineHeight: "1.7" }}
            />
            <div className="mt-4 flex gap-3">
              <button
                onClick={saveDescription}
                disabled={descSaving || description === savedDescription || !canManageKnowledge}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40"
              >
                <Save size={14} /> {descSaving ? "Saving…" : "Save Description"}
              </button>
            </div>
          </div>

          {/* App / Download Link */}
          <div className="bg-surface rounded-card p-8 shadow-card ring-1 ring-[#c4c7c7]/15">
            <div className="mb-4">
              <h2 className="font-display text-lg font-bold text-primary flex items-center gap-2">
                <LinkIcon size={18} /> App / Download Link
              </h2>
              <p className="font-body text-sm text-on-surface-muted mt-0.5">
                Your app, booking page, or consultation link. Your assistant shares this exact
                link whenever it needs to point a customer to your app — it never has to guess
                or make one up.
              </p>
            </div>
            <input
              type="url"
              value={appLink}
              onChange={(e) => setAppLink(e.target.value)}
              disabled={!canManageKnowledge}
              placeholder="https://yourapp.com/download"
              className="w-full px-5 py-4 rounded-xl bg-surface-low border border-surface-mid font-body focus:outline-none focus:ring-2 focus:ring-primary"
              style={{ fontSize: "15px" }}
            />
            <div className="mt-4 flex gap-3">
              <button
                onClick={saveAppLink}
                disabled={appLinkSaving || appLink === savedAppLink || !canManageKnowledge}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40"
              >
                <Save size={14} /> {appLinkSaving ? "Saving…" : "Save Link"}
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
                "9-10: High intent — asked about pricing or next steps\n" +
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
                disabled={rubricSaving || scoringRubric === savedRubric || !canManageKnowledge}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40"
              >
                <Save size={14} /> {rubricSaving ? "Saving…" : "Save Rubric"}
              </button>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
