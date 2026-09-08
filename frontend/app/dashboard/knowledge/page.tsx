"use client";

import { toast } from "sonner";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Search, Plus, Trash2, XCircle,
  Upload, FileText, Loader2, AlertCircle,
  Save, Eye, Download, X, Link as LinkIcon,
  HardDrive, Check, Copy,
  Sparkles, LayoutGrid, List,
  FileSpreadsheet, FileCode, Image as ImageIcon,
  Tag, Shield, BookOpen
} from "lucide-react";
import { api, API_URL, getAuthHeaders, KnowledgeDocContent } from "@/lib/api";
import { cn } from "@/lib/utils";
import { usePolling } from "@/hooks/usePolling";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { useSearchParams } from "next/navigation";

// ─── Interfaces & Types ───────────────────────────────────────────────────────

interface KnowledgeDoc {
  id: string;
  name: string;
  size_bytes: number;
  file_type: string;
  status: string;
  created_at: string;
  chunk_count?: number;
  error_message?: string;
  campaign_tag_id?: string | null;
}

interface CampaignTag {
  id: string;
  name: string;
  color?: string;
}

interface FileTypeMeta {
  label: string;
  ext: string;
  badgeBg: string;
  badgeText: string;
  badgeBorder: string;
  iconBg: string;
  iconColor: string;
  category: "pdf" | "word" | "spreadsheet" | "presentation" | "text" | "image" | "other";
}

// ─── File Formatting Helpers ──────────────────────────────────────────────────

function getFileTypeMeta(fileType: string, fileName: string): FileTypeMeta {
  const lowerName = fileName.toLowerCase();
  const lowerType = (fileType || "").toLowerCase();

  if (lowerName.endsWith(".pdf") || lowerType.includes("pdf")) {
    return {
      label: "PDF",
      ext: ".pdf",
      badgeBg: "bg-red-50",
      badgeText: "text-red-700",
      badgeBorder: "border-red-200",
      iconBg: "bg-red-500/10",
      iconColor: "text-red-600",
      category: "pdf",
    };
  }
  if (
    lowerName.endsWith(".docx") ||
    lowerName.endsWith(".doc") ||
    lowerType.includes("word") ||
    lowerType.includes("wordprocessingml")
  ) {
    return {
      label: "Word",
      ext: lowerName.endsWith(".doc") ? ".doc" : ".docx",
      badgeBg: "bg-blue-50",
      badgeText: "text-blue-700",
      badgeBorder: "border-blue-200",
      iconBg: "bg-blue-500/10",
      iconColor: "text-blue-600",
      category: "word",
    };
  }
  if (
    lowerName.endsWith(".xlsx") ||
    lowerName.endsWith(".xls") ||
    lowerType.includes("spreadsheet") ||
    lowerType.includes("excel")
  ) {
    return {
      label: "Excel",
      ext: lowerName.endsWith(".xls") ? ".xls" : ".xlsx",
      badgeBg: "bg-emerald-50",
      badgeText: "text-emerald-700",
      badgeBorder: "border-emerald-200",
      iconBg: "bg-emerald-500/10",
      iconColor: "text-emerald-600",
      category: "spreadsheet",
    };
  }
  if (lowerName.endsWith(".csv") || lowerType.includes("csv")) {
    return {
      label: "CSV",
      ext: ".csv",
      badgeBg: "bg-teal-50",
      badgeText: "text-teal-700",
      badgeBorder: "border-teal-200",
      iconBg: "bg-teal-500/10",
      iconColor: "text-teal-600",
      category: "spreadsheet",
    };
  }
  if (
    lowerName.endsWith(".pptx") ||
    lowerName.endsWith(".ppt") ||
    lowerType.includes("presentation") ||
    lowerType.includes("powerpoint")
  ) {
    return {
      label: "PowerPoint",
      ext: lowerName.endsWith(".ppt") ? ".ppt" : ".pptx",
      badgeBg: "bg-amber-50",
      badgeText: "text-amber-700",
      badgeBorder: "border-amber-200",
      iconBg: "bg-amber-500/10",
      iconColor: "text-amber-600",
      category: "presentation",
    };
  }
  if (
    lowerName.endsWith(".txt") ||
    lowerName.endsWith(".md") ||
    lowerName.endsWith(".markdown") ||
    lowerType.includes("text/")
  ) {
    return {
      label: lowerName.endsWith(".md") || lowerName.endsWith(".markdown") ? "Markdown" : "Text",
      ext: lowerName.endsWith(".md") ? ".md" : ".txt",
      badgeBg: "bg-stone-100",
      badgeText: "text-stone-700",
      badgeBorder: "border-stone-200",
      iconBg: "bg-stone-500/10",
      iconColor: "text-stone-600",
      category: "text",
    };
  }
  if (lowerType.startsWith("image/") || /\.(png|jpe?g|webp|gif|svg)$/i.test(lowerName)) {
    return {
      label: "Image",
      ext: lowerName.match(/\.[0-9a-z]+$/i)?.[0] || ".img",
      badgeBg: "bg-purple-50",
      badgeText: "text-purple-700",
      badgeBorder: "border-purple-200",
      iconBg: "bg-purple-500/10",
      iconColor: "text-purple-600",
      category: "image",
    };
  }
  return {
    label: "Document",
    ext: lowerName.match(/\.[0-9a-z]+$/i)?.[0] || ".doc",
    badgeBg: "bg-surface-mid",
    badgeText: "text-on-surface-muted",
    badgeBorder: "border-surface-mid",
    iconBg: "bg-primary/10",
    iconColor: "text-primary",
    category: "other",
  };
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function KnowledgePage() {
  const { role, permissions, loading: roleLoading } = useAuthRole();
  const canViewKnowledge =
    role === "owner" ||
    permissions.includes("knowledge.view") ||
    permissions.includes("knowledge.manage");
  const canManageKnowledge =
    role === "owner" || permissions.includes("knowledge.manage");

  const [documents, setDocuments] = useState<KnowledgeDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [campaignFilter, setCampaignFilter] = useState<string>("all");
  const [viewMode, setViewMode] = useState<"table" | "grid">("table");

  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab = (rawTab === "description" || rawTab === "ai-tune" ? "description" : "documents") as
    | "documents"
    | "description";

  // Document Upload
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [campaignTags, setCampaignTags] = useState<CampaignTag[]>([]);
  const [selectedCampaignTag, setSelectedCampaignTag] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Business Description & AI Tuning
  const [description, setDescription] = useState<string>("");
  const [savedDescription, setSavedDescription] = useState<string>("");
  const [descSaving, setDescSaving] = useState(false);

  const [appLink, setAppLink] = useState<string>("");
  const [savedAppLink, setSavedAppLink] = useState<string>("");
  const [appLinkSaving, setAppLinkSaving] = useState(false);

  const [scoringRubric, setScoringRubric] = useState<string>("");
  const [savedRubric, setSavedRubric] = useState<string>("");
  const [rubricSaving, setRubricSaving] = useState(false);
  const [rubricAutoUpdate, setRubricAutoUpdate] = useState(false);
  const [rubricToggleSaving, setRubricToggleSaving] = useState(false);

  // Document Viewer Modal
  const [viewingDoc, setViewingDoc] = useState<KnowledgeDocContent | null>(null);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [viewerSearch, setViewerSearch] = useState("");
  const [copiedText, setCopiedText] = useState(false);

  // Delete Confirmation Modal
  const [deletingDoc, setDeletingDoc] = useState<KnowledgeDoc | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // RAG Guide Expandable
  const [showRagGuide, setShowRagGuide] = useState(false);

  useEffect(() => {
    loadData();
    api.knowledge
      .listCampaignTags()
      .then(setCampaignTags)
      .catch(() => {});
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

  // Map campaign tags for fast lookup
  const tagMap = useMemo(() => {
    const map = new Map<string, CampaignTag>();
    campaignTags.forEach((t) => map.set(t.id, t));
    return map;
  }, [campaignTags]);

  // Document statistics
  const stats = useMemo(() => {
    const total = documents.length;
    const indexed = documents.filter((d) => d.status === "indexed").length;
    const processing = documents.filter((d) => d.status === "processing").length;
    const failed = documents.filter((d) => d.status === "failed").length;
    const totalBytes = documents.reduce((sum, d) => sum + (d.size_bytes || 0), 0);
    const scopedCount = documents.filter((d) => Boolean(d.campaign_tag_id)).length;
    return { total, indexed, processing, failed, totalBytes, scopedCount };
  }, [documents]);

  // Filtered documents
  const filteredDocs = useMemo(() => {
    return documents.filter((doc) => {
      // Text search
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesName = doc.name.toLowerCase().includes(q);
        const tag = doc.campaign_tag_id ? tagMap.get(doc.campaign_tag_id)?.name.toLowerCase() : "";
        if (!matchesName && !tag?.includes(q)) return false;
      }

      // Status filter
      if (statusFilter !== "all" && doc.status !== statusFilter) {
        return false;
      }

      // Campaign filter
      if (campaignFilter === "global" && doc.campaign_tag_id) {
        return false;
      }
      if (campaignFilter !== "all" && campaignFilter !== "global" && doc.campaign_tag_id !== campaignFilter) {
        return false;
      }

      // Category filter
      if (categoryFilter !== "all") {
        const meta = getFileTypeMeta(doc.file_type, doc.name);
        if (meta.category !== categoryFilter) return false;
      }

      return true;
    });
  }, [documents, search, statusFilter, campaignFilter, categoryFilter, tagMap]);

  if (roleLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (!canViewKnowledge) {
    return (
      <div className="text-center py-20 bg-surface rounded-2xl border border-surface-mid p-8">
        <Shield size={32} className="mx-auto mb-3 text-on-surface-muted" />
        <h3 className="font-display font-bold text-on-surface text-base">Access Restricted</h3>
        <p className="text-on-surface-muted font-body text-sm mt-1">
          You do not have permission to view or manage the knowledge base.
        </p>
      </div>
    );
  }

  // ─── Data Loaders ─────────────────────────────────────────────────────────

  async function loadData() {
    setLoading(true);
    try {
      const docData = await api.knowledge.listDocuments();
      setDocuments(docData);
    } catch {
      // silent fail open
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
      const auto = settings.find((s) => s.key === "rubric_auto_update");
      setRubricAutoUpdate(auto?.display_value === "true");
    } catch {}
  }

  // ─── Upload Handlers ───────────────────────────────────────────────────────

  async function processUpload(file: File) {
    if (!canManageKnowledge) {
      setUploadError("Read-only role: document upload is disabled.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      await api.knowledge.uploadDocument(file, selectedCampaignTag || null);
      toast.success(`"${file.name}" uploaded. Extracting and indexing content...`);
      await loadDocuments();
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch {
      setUploadError("Upload failed. Please check file format and try again.");
      toast.error("Upload failed. Please check file format and try again.");
    } finally {
      setUploading(false);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      processUpload(file);
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    if (!uploading && canManageKnowledge) {
      setIsDragging(true);
    }
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (uploading || !canManageKnowledge) return;
    const file = e.dataTransfer.files?.[0];
    if (file) {
      processUpload(file);
    }
  }

  // ─── Delete Handlers ───────────────────────────────────────────────────────

  async function confirmDeleteDocument() {
    if (!deletingDoc) return;
    setDeleteLoading(true);
    try {
      await api.knowledge.deleteDocument(deletingDoc.id);
      toast.success(`"${deletingDoc.name}" and all indexed chunks removed.`);
      setDeletingDoc(null);
      await loadDocuments();
    } catch {
      toast.error("Failed to delete document. Please try again.");
    } finally {
      setDeleteLoading(false);
    }
  }

  // ─── Viewer & Downloader ───────────────────────────────────────────────────

  async function openDocument(docId: string) {
    setViewerLoading(true);
    setViewerSearch("");
    try {
      const content = await api.knowledge.documentContent(docId);
      setViewingDoc(content);
    } catch {
      toast.error("Could not load document text.");
    } finally {
      setViewerLoading(false);
    }
  }

  async function downloadDocument(docId: string) {
    setDownloading(true);
    try {
      const { url } = await api.knowledge.documentDownloadUrl(docId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      toast.error("The original file is not available for this document.");
    } finally {
      setDownloading(false);
    }
  }

  function copyExtractedText() {
    if (!viewingDoc?.full_text) return;
    navigator.clipboard.writeText(viewingDoc.full_text);
    setCopiedText(true);
    toast.success("Document text copied to clipboard.");
    setTimeout(() => setCopiedText(false), 2000);
  }

  // ─── AI Tuning Handlers ───────────────────────────────────────────────────

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

  async function toggleRubricAutoUpdate() {
    const next = !rubricAutoUpdate;
    setRubricToggleSaving(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ updates: { rubric_auto_update: next ? "true" : "false" } }),
      });
      if (!res.ok) throw new Error("Save failed");
      setRubricAutoUpdate(next);
      toast.success(
        next
          ? "Rubric will update automatically when you save your description."
          : "Rubric will no longer change when you save your description."
      );
    } catch {
      toast.error("Could not change setting. Please try again.");
    } finally {
      setRubricToggleSaving(false);
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {tab === "documents" ? (
        <div className="space-y-6">
          {/* ── Top Overview Stats ────────────────────────────────────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-surface rounded-2xl p-4 border border-surface-mid shadow-sm flex items-center justify-between">
              <div>
                <p className="font-label text-xs font-bold text-on-surface-muted uppercase tracking-wider">
                  Total Documents
                </p>
                <p className="font-display text-2xl font-black text-on-surface mt-1">
                  {stats.total.toLocaleString()}
                </p>
                <p className="font-body text-[11px] text-on-surface-muted mt-0.5">
                  Across all formats
                </p>
              </div>
              <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center text-primary shrink-0">
                <BookOpen size={20} />
              </div>
            </div>

            <div className="bg-surface rounded-2xl p-4 border border-surface-mid shadow-sm flex items-center justify-between">
              <div>
                <p className="font-label text-xs font-bold text-on-surface-muted uppercase tracking-wider">
                  Active & Indexed
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <p className="font-display text-2xl font-black text-emerald-700">
                    {stats.indexed.toLocaleString()}
                  </p>
                  {stats.processing > 0 && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold">
                      <Loader2 size={10} className="animate-spin" />
                      {stats.processing} indexing
                    </span>
                  )}
                </div>
                <p className="font-body text-[11px] text-emerald-700 font-semibold mt-0.5">
                  Ready for AI RAG retrieval
                </p>
              </div>
              <div className="w-11 h-11 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600 shrink-0">
                <Sparkles size={20} />
              </div>
            </div>

            <div className="bg-surface rounded-2xl p-4 border border-surface-mid shadow-sm flex items-center justify-between">
              <div>
                <p className="font-label text-xs font-bold text-on-surface-muted uppercase tracking-wider">
                  Storage Footprint
                </p>
                <p className="font-display text-2xl font-black text-on-surface mt-1">
                  {formatBytes(stats.totalBytes)}
                </p>
                <p className="font-body text-[11px] text-on-surface-muted mt-0.5">
                  Indexed vector data
                </p>
              </div>
              <div className="w-11 h-11 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600 shrink-0">
                <HardDrive size={20} />
              </div>
            </div>

            <div className="bg-surface rounded-2xl p-4 border border-surface-mid shadow-sm flex items-center justify-between">
              <div>
                <p className="font-label text-xs font-bold text-on-surface-muted uppercase tracking-wider">
                  Campaign Scopes
                </p>
                <p className="font-display text-2xl font-black text-on-surface mt-1">
                  {stats.scopedCount > 0 ? `${stats.scopedCount} Scoped` : "All Shared"}
                </p>
                <p className="font-body text-[11px] text-on-surface-muted mt-0.5">
                  {campaignTags.length} campaigns available
                </p>
              </div>
              <div className="w-11 h-11 rounded-xl bg-purple-50 flex items-center justify-center text-purple-600 shrink-0">
                <Tag size={20} />
              </div>
            </div>
          </div>

          {/* ── Modern Upload Zone Card ───────────────────────────────────── */}
          <div className="bg-surface rounded-2xl border border-surface-mid shadow-sm overflow-hidden">
            {/* Header / Scope selector bar */}
            <div className="p-4 sm:p-5 border-b border-surface-mid/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface-low/50">
              <div>
                <h2 className="font-display font-bold text-base text-on-surface flex items-center gap-2">
                  <Upload size={18} className="text-primary" />
                  Add Knowledge Document
                </h2>
                <p className="font-body text-xs text-on-surface-muted mt-0.5">
                  Upload PDFs, Word docs, spreadsheets, or notes. Content is extracted and embedded for instant AI retrieval.
                </p>
              </div>

              {campaignTags.length > 0 && (
                <div className="flex items-center gap-2 shrink-0">
                  <span className="font-label text-xs font-semibold text-on-surface-muted">
                    Campaign Scope:
                  </span>
                  <select
                    value={selectedCampaignTag}
                    onChange={(e) => setSelectedCampaignTag(e.target.value)}
                    disabled={uploading}
                    className="px-3 py-1.5 rounded-xl border border-surface-mid bg-white font-body text-xs text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 shadow-xs"
                  >
                    <option value="">🌐 All campaigns (shared)</option>
                    {campaignTags.map((t) => (
                      <option key={t.id} value={t.id}>
                        🎯 {t.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Drag & Drop Area */}
            <div className="p-4 sm:p-6">
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={cn(
                  "relative rounded-2xl border-2 border-dashed p-8 transition-colors flex flex-col items-center justify-center text-center group",
                  isDragging
                    ? "border-primary bg-primary/[0.08] shadow-inner"
                    : "border-primary/30 bg-primary/[0.02] hover:border-primary/60 hover:bg-primary/[0.04]",
                  uploading && "pointer-events-none opacity-60"
                )}
              >
                <div
                  className={cn(
                    "w-14 h-14 rounded-2xl flex items-center justify-center transition-colors shadow-xs mb-3",
                    isDragging || uploading
                      ? "bg-primary text-white"
                      : "bg-primary/10 text-primary group-hover:bg-primary/20"
                  )}
                >
                  {uploading ? (
                    <Loader2 size={26} className="animate-spin" />
                  ) : (
                    <Upload size={26} />
                  )}
                </div>

                <p className="font-display text-base font-bold text-on-surface">
                  {uploading
                    ? "Processing and indexing document…"
                    : isDragging
                    ? "Drop your file here to upload"
                    : "Drop your file here or browse from computer"}
                </p>

                <p className="font-body text-xs text-on-surface-muted mt-1 max-w-md">
                  Supports PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, and Images up to 25 MB.
                </p>

                {/* Formats badge row */}
                <div className="flex flex-wrap items-center justify-center gap-1.5 mt-3">
                  {["PDF", "DOCX", "EXCEL", "CSV", "PPTX", "TXT", "MD", "IMAGES"].map((fmt) => (
                    <span
                      key={fmt}
                      className="px-2 py-0.5 rounded-md bg-white border border-surface-mid/80 text-[10px] font-mono font-bold text-on-surface-muted"
                    >
                      {fmt}
                    </span>
                  ))}
                </div>

                {/* Scope pill reminder */}
                {selectedCampaignTag && (
                  <div className="mt-3 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-purple-50 text-purple-700 text-xs font-semibold border border-purple-100">
                    <Tag size={12} />
                    Will be scoped exclusively to &quot;{tagMap.get(selectedCampaignTag)?.name}&quot;
                  </div>
                )}

                {/* Choose file button */}
                <div className="mt-5">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading || !canManageKnowledge}
                    className="flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-xs"
                  >
                    <Plus size={16} />
                    Choose File to Upload
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.csv,.txt,.md,.markdown,image/*"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                </div>
              </div>

              {uploadError && (
                <div className="mt-3 flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-xl text-xs font-semibold border border-red-200">
                  <AlertCircle size={16} className="shrink-0" />
                  <span>{uploadError}</span>
                  <button
                    onClick={() => setUploadError(null)}
                    className="ml-auto text-red-500 hover:text-red-700 font-bold"
                  >
                    Dismiss
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* ── Filter & Search Toolbar ───────────────────────────────────── */}
          <div className="bg-surface rounded-2xl p-4 border border-surface-mid shadow-sm space-y-3">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              {/* Search Bar */}
              <div className="relative flex-1 min-w-0 max-w-md">
                <Search
                  size={16}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-on-surface-muted"
                />
                <input
                  type="text"
                  placeholder="Search documents by name or campaign tag..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-9 pr-8 py-2 rounded-xl bg-surface-low border border-surface-mid font-body text-xs text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-colors"
                />
                {search && (
                  <button
                    onClick={() => setSearch("")}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-muted hover:text-on-surface p-0.5"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>

              {/* Filters & View Switcher */}
              <div className="flex flex-wrap items-center gap-2">
                {/* Format Filter */}
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="px-3 py-2 rounded-xl border border-surface-mid bg-white font-body text-xs text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 shadow-xs"
                >
                  <option value="all">All File Types</option>
                  <option value="pdf">PDF Documents</option>
                  <option value="word">Word (.docx, .doc)</option>
                  <option value="spreadsheet">Excel & CSV</option>
                  <option value="presentation">PowerPoint (.pptx)</option>
                  <option value="text">Text & Markdown</option>
                  <option value="image">Images</option>
                </select>

                {/* Status Filter */}
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-3 py-2 rounded-xl border border-surface-mid bg-white font-body text-xs text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 shadow-xs"
                >
                  <option value="all">All Statuses</option>
                  <option value="indexed">Indexed ({stats.indexed})</option>
                  <option value="processing">Processing ({stats.processing})</option>
                  <option value="failed">Failed ({stats.failed})</option>
                </select>

                {/* Campaign Scope Filter */}
                {campaignTags.length > 0 && (
                  <select
                    value={campaignFilter}
                    onChange={(e) => setCampaignFilter(e.target.value)}
                    className="px-3 py-2 rounded-xl border border-surface-mid bg-white font-body text-xs text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 shadow-xs"
                  >
                    <option value="all">All Scopes</option>
                    <option value="global">🌐 Shared / Global only</option>
                    {campaignTags.map((t) => (
                      <option key={t.id} value={t.id}>
                        🎯 {t.name}
                      </option>
                    ))}
                  </select>
                )}

                {/* View Mode Switcher */}
                <div className="flex items-center rounded-xl bg-surface-low border border-surface-mid p-0.5">
                  <button
                    onClick={() => setViewMode("table")}
                    title="List View"
                    className={cn(
                      "p-1.5 rounded-lg transition-colors",
                      viewMode === "table"
                        ? "bg-white text-primary shadow-xs"
                        : "text-on-surface-muted hover:text-on-surface"
                    )}
                  >
                    <List size={16} />
                  </button>
                  <button
                    onClick={() => setViewMode("grid")}
                    title="Grid View"
                    className={cn(
                      "p-1.5 rounded-lg transition-colors",
                      viewMode === "grid"
                        ? "bg-white text-primary shadow-xs"
                        : "text-on-surface-muted hover:text-on-surface"
                    )}
                  >
                    <LayoutGrid size={16} />
                  </button>
                </div>
              </div>
            </div>

            {/* Active filters pill list */}
            {(search || categoryFilter !== "all" || statusFilter !== "all" || campaignFilter !== "all") && (
              <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-surface-mid/50 text-xs">
                <span className="font-label text-on-surface-muted font-bold text-[10px] uppercase">
                  Active Filters:
                </span>
                {search && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-mid text-on-surface font-medium text-xs">
                    Search: &quot;{search}&quot;
                    <button onClick={() => setSearch("")} className="hover:text-red-500">
                      <X size={12} />
                    </button>
                  </span>
                )}
                {categoryFilter !== "all" && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-mid text-on-surface font-medium text-xs capitalize">
                    Type: {categoryFilter}
                    <button onClick={() => setCategoryFilter("all")} className="hover:text-red-500">
                      <X size={12} />
                    </button>
                  </span>
                )}
                {statusFilter !== "all" && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-mid text-on-surface font-medium text-xs capitalize">
                    Status: {statusFilter}
                    <button onClick={() => setStatusFilter("all")} className="hover:text-red-500">
                      <X size={12} />
                    </button>
                  </span>
                )}
                {campaignFilter !== "all" && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-mid text-on-surface font-medium text-xs">
                    Scope: {campaignFilter === "global" ? "Global" : tagMap.get(campaignFilter)?.name}
                    <button onClick={() => setCampaignFilter("all")} className="hover:text-red-500">
                      <X size={12} />
                    </button>
                  </span>
                )}
                <button
                  onClick={() => {
                    setSearch("");
                    setCategoryFilter("all");
                    setStatusFilter("all");
                    setCampaignFilter("all");
                  }}
                  className="font-label text-xs font-bold text-primary hover:underline ml-1"
                >
                  Reset all
                </button>
              </div>
            )}
          </div>

          {/* ── Document List / Grid Section ──────────────────────────────── */}
          <div className="bg-surface rounded-2xl border border-surface-mid shadow-sm overflow-hidden">
            {loading ? (
              <div className="py-20 text-center text-on-surface-muted">
                <Loader2 size={28} className="mx-auto mb-2.5 animate-spin text-primary" />
                <p className="font-body text-sm font-semibold">Loading knowledge documents…</p>
              </div>
            ) : filteredDocs.length === 0 ? (
              <div className="py-16 px-4 text-center">
                <div className="w-14 h-14 rounded-2xl bg-surface-low border border-surface-mid flex items-center justify-center mx-auto mb-3 text-on-surface-muted">
                  <FileText size={26} />
                </div>
                {documents.length === 0 ? (
                  <>
                    <h3 className="font-display text-base font-bold text-on-surface">
                      No documents in your knowledge base yet
                    </h3>
                    <p className="font-body text-xs text-on-surface-muted mt-1 max-w-sm mx-auto">
                      Upload company FAQs, product catalogs, service brochures, or pricing sheets above so your AI assistant can accurately answer lead questions.
                    </p>
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl font-label text-xs font-semibold hover:bg-primary/90 transition-colors shadow-xs"
                    >
                      <Upload size={14} /> Upload First Document
                    </button>
                  </>
                ) : (
                  <>
                    <h3 className="font-display text-base font-bold text-on-surface">
                      No documents match your filters
                    </h3>
                    <p className="font-body text-xs text-on-surface-muted mt-1">
                      Try clearing search terms or selecting &quot;All File Types&quot;.
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setSearch("");
                        setCategoryFilter("all");
                        setStatusFilter("all");
                        setCampaignFilter("all");
                      }}
                      className="mt-4 px-4 py-2 bg-surface-low hover:bg-surface-mid rounded-xl font-label text-xs font-bold text-on-surface border border-surface-mid transition-colors"
                    >
                      Clear Filters
                    </button>
                  </>
                )}
              </div>
            ) : viewMode === "grid" ? (
              /* ── Grid Cards View ── */
              <div className="p-4 sm:p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredDocs.map((doc) => {
                  const meta = getFileTypeMeta(doc.file_type, doc.name);
                  const campaignTag = doc.campaign_tag_id ? tagMap.get(doc.campaign_tag_id) : null;

                  return (
                    <div
                      key={doc.id}
                      className="bg-white rounded-2xl border border-surface-mid p-5 shadow-xs hover:shadow-card hover:border-primary/30 transition-all flex flex-col justify-between group"
                    >
                      <div>
                        {/* Top card bar: icon + type badge + status */}
                        <div className="flex items-start justify-between gap-2 mb-3">
                          <div className="flex items-center gap-2">
                            <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center shrink-0", meta.iconBg, meta.iconColor)}>
                              {meta.category === "spreadsheet" ? (
                                <FileSpreadsheet size={20} />
                              ) : meta.category === "image" ? (
                                <ImageIcon size={20} />
                              ) : meta.category === "text" ? (
                                <FileCode size={20} />
                              ) : (
                                <FileText size={20} />
                              )}
                            </div>
                            <div>
                              <span
                                className={cn(
                                  "inline-block px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide border",
                                  meta.badgeBg,
                                  meta.badgeText,
                                  meta.badgeBorder
                                )}
                              >
                                {meta.label}
                              </span>
                              <p className="font-mono text-[10px] text-on-surface-muted mt-0.5">
                                {formatBytes(doc.size_bytes)}
                              </p>
                            </div>
                          </div>

                          {/* Status Badge */}
                          <div
                            className={cn(
                              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-label font-bold uppercase shrink-0 border",
                              doc.status === "indexed"
                                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                : doc.status === "processing"
                                ? "bg-amber-50 text-amber-700 border-amber-200"
                                : "bg-red-50 text-red-700 border-red-200"
                            )}
                          >
                            {doc.status === "indexed" ? (
                              <>
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                <span>Indexed</span>
                              </>
                            ) : doc.status === "processing" ? (
                              <>
                                <Loader2 size={11} className="animate-spin text-amber-600" />
                                <span>Indexing</span>
                              </>
                            ) : (
                              <>
                                <XCircle size={11} className="text-red-500" />
                                <span>Failed</span>
                              </>
                            )}
                          </div>
                        </div>

                        {/* Title */}
                        <h4
                          className="font-display font-bold text-sm text-on-surface line-clamp-2 leading-snug group-hover:text-primary transition-colors"
                          title={doc.name}
                        >
                          {doc.name}
                        </h4>

                        {/* Campaign Scope Pill */}
                        <div className="mt-3">
                          {campaignTag ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-purple-50 text-purple-700 text-[11px] font-semibold border border-purple-100">
                              <Tag size={11} /> {campaignTag.name}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-low text-on-surface-muted text-[11px] font-medium border border-surface-mid">
                              🌐 All campaigns (shared)
                            </span>
                          )}
                        </div>

                        {/* Error message if failed */}
                        {doc.status === "failed" && (
                          <p className="text-xs text-red-600 mt-2 bg-red-50 p-2 rounded-lg border border-red-100">
                            {doc.error_message || "Extraction failed. Try re-uploading file."}
                          </p>
                        )}
                      </div>

                      {/* Footer: Date & Actions */}
                      <div className="pt-4 mt-4 border-t border-surface-mid/60 flex items-center justify-between">
                        <span className="font-body text-[11px] text-on-surface-muted">
                          {formatDate(doc.created_at)}
                        </span>

                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => openDocument(doc.id)}
                            title="View extracted text"
                            className="p-1.5 text-on-surface-muted hover:text-primary hover:bg-primary/5 rounded-lg transition-colors"
                          >
                            <Eye size={16} />
                          </button>
                          <button
                            onClick={() => downloadDocument(doc.id)}
                            title="Download original file"
                            className="p-1.5 text-on-surface-muted hover:text-primary hover:bg-primary/5 rounded-lg transition-colors"
                          >
                            <Download size={16} />
                          </button>
                          {canManageKnowledge && (
                            <button
                              onClick={() => setDeletingDoc(doc)}
                              title="Delete document"
                              className="p-1.5 text-on-surface-muted hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                            >
                              <Trash2 size={16} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              /* ── Modern Table View ── */
              <div className="overflow-x-auto">
                <table className="w-full text-left font-body text-sm">
                  <thead>
                    <tr className="bg-surface-low/80 border-b border-surface-mid text-[11px] font-label font-bold text-on-surface-muted uppercase tracking-wider">
                      <th className="px-5 py-3.5">Document</th>
                      <th className="px-4 py-3.5">Format</th>
                      <th className="px-4 py-3.5">Scope</th>
                      <th className="px-4 py-3.5">Status</th>
                      <th className="px-4 py-3.5">Uploaded</th>
                      <th className="px-5 py-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-mid/60">
                    {filteredDocs.map((doc) => {
                      const meta = getFileTypeMeta(doc.file_type, doc.name);
                      const campaignTag = doc.campaign_tag_id ? tagMap.get(doc.campaign_tag_id) : null;

                      return (
                        <tr
                          key={doc.id}
                          className="hover:bg-surface-low/60 transition-colors group"
                        >
                          {/* Document Name & Size */}
                          <td className="px-5 py-3.5 max-w-sm">
                            <div className="flex items-center gap-3">
                              <div
                                className={cn(
                                  "w-9 h-9 rounded-xl flex items-center justify-center shrink-0",
                                  meta.iconBg,
                                  meta.iconColor
                                )}
                              >
                                {meta.category === "spreadsheet" ? (
                                  <FileSpreadsheet size={18} />
                                ) : meta.category === "image" ? (
                                  <ImageIcon size={18} />
                                ) : meta.category === "text" ? (
                                  <FileCode size={18} />
                                ) : (
                                  <FileText size={18} />
                                )}
                              </div>
                              <div className="min-w-0">
                                <p
                                  className="font-semibold text-on-surface text-sm truncate group-hover:text-primary transition-colors"
                                  title={doc.name}
                                >
                                  {doc.name}
                                </p>
                                <p className="font-mono text-[11px] text-on-surface-muted mt-0.5">
                                  {formatBytes(doc.size_bytes)}
                                </p>
                                {doc.status === "failed" && (
                                  <p className="text-[11px] text-red-600 truncate mt-0.5 max-w-xs">
                                    {doc.error_message || "Extraction error — delete & re-upload"}
                                  </p>
                                )}
                              </div>
                            </div>
                          </td>

                          {/* Clean Format Badge */}
                          <td className="px-4 py-3.5 whitespace-nowrap">
                            <span
                              className={cn(
                                "inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider border",
                                meta.badgeBg,
                                meta.badgeText,
                                meta.badgeBorder
                              )}
                            >
                              {meta.label}
                            </span>
                          </td>

                          {/* Campaign Scope */}
                          <td className="px-4 py-3.5 whitespace-nowrap">
                            {campaignTag ? (
                              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-purple-50 text-purple-700 text-xs font-semibold border border-purple-100">
                                <Tag size={11} /> {campaignTag.name}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-surface-low text-on-surface-muted text-xs font-medium border border-surface-mid">
                                🌐 Shared
                              </span>
                            )}
                          </td>

                          {/* Status */}
                          <td className="px-4 py-3.5 whitespace-nowrap">
                            <div
                              className={cn(
                                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-label font-bold uppercase border",
                                doc.status === "indexed"
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                  : doc.status === "processing"
                                  ? "bg-amber-50 text-amber-700 border-amber-200"
                                  : "bg-red-50 text-red-700 border-red-200"
                              )}
                            >
                              {doc.status === "indexed" ? (
                                <>
                                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                  <span>Indexed</span>
                                </>
                              ) : doc.status === "processing" ? (
                                <>
                                  <Loader2 size={11} className="animate-spin text-amber-600" />
                                  <span>Indexing</span>
                                </>
                              ) : (
                                <>
                                  <XCircle size={11} className="text-red-500" />
                                  <span>Failed</span>
                                </>
                              )}
                            </div>
                          </td>

                          {/* Created Date */}
                          <td className="px-4 py-3.5 whitespace-nowrap text-on-surface-muted text-xs">
                            {formatDate(doc.created_at)}
                          </td>

                          {/* Actions */}
                          <td className="px-5 py-3.5 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => openDocument(doc.id)}
                                title="View extracted text"
                                className="p-2 text-on-surface-muted hover:text-primary hover:bg-primary/5 rounded-lg transition-colors"
                              >
                                <Eye size={16} />
                              </button>
                              <button
                                onClick={() => downloadDocument(doc.id)}
                                title="Download original file"
                                className="p-2 text-on-surface-muted hover:text-primary hover:bg-primary/5 rounded-lg transition-colors"
                              >
                                <Download size={16} />
                              </button>
                              {canManageKnowledge && (
                                <button
                                  onClick={() => setDeletingDoc(doc)}
                                  title="Delete document"
                                  className="p-2 text-on-surface-muted hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                >
                                  <Trash2 size={16} />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ── Modern RAG Explainer Card ─────────────────────────────────── */}
          <div className="bg-gradient-to-br from-purple-50/70 via-surface to-surface border border-purple-100 rounded-2xl p-5 shadow-xs">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-xl bg-purple-100/80 text-primary flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles size={18} />
                </div>
                <div>
                  <h4 className="font-display font-bold text-sm text-on-surface">
                    How AI Retrieval-Augmented Generation (RAG) Operates
                  </h4>
                  <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed max-w-2xl">
                    When leads ask questions via WhatsApp or during telecalling, Aira converts their question into an embedding and performs a semantic vector search across your indexed documents. Only verified, factual snippets are provided to the LLM to construct completely hallucination-free replies.
                  </p>
                </div>
              </div>

              <button
                onClick={() => setShowRagGuide(!showRagGuide)}
                className="text-xs font-label font-bold text-primary hover:underline shrink-0 pt-1"
              >
                {showRagGuide ? "Hide Details" : "Read Architecture →"}
              </button>
            </div>

            {showRagGuide && (
              <div className="mt-4 pt-4 border-t border-purple-100/80 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-body">
                <div className="p-3 bg-white rounded-xl border border-purple-100">
                  <p className="font-bold text-primary font-label uppercase tracking-wider text-[10px]">
                    1. Text Extraction & Chunking
                  </p>
                  <p className="text-on-surface-muted mt-1">
                    Uploaded documents are parsed (Docx, PDF, Excel) and split into semantic chunks with 10% overlap to preserve context.
                  </p>
                </div>
                <div className="p-3 bg-white rounded-xl border border-purple-100">
                  <p className="font-bold text-primary font-label uppercase tracking-wider text-[10px]">
                    2. Vector Embeddings
                  </p>
                  <p className="text-on-surface-muted mt-1">
                    Each chunk is encoded into 512-dimensional vector space using high-precision embedding models and indexed with HNSW.
                  </p>
                </div>
                <div className="p-3 bg-white rounded-xl border border-purple-100">
                  <p className="font-bold text-primary font-label uppercase tracking-wider text-[10px]">
                    3. Campaign Scoping
                  </p>
                  <p className="text-on-surface-muted mt-1">
                    Documents scoped to a campaign tag only surface for leads belonging to that campaign, preventing cross-product confusion.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* ── Description Tab ─────────────────────────────────────────────── */
        <div className="space-y-6">
          {/* Business Description Card */}
          <div className="bg-surface rounded-2xl p-6 md:p-8 border border-surface-mid shadow-sm space-y-4">
            <div>
              <h2 className="font-display text-lg font-bold text-primary">
                Business Description & Identity
              </h2>
              <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed">
                Describe your business, products, services, and the role your AI assistant plays. Write it in clear, natural language — as you would brief a new team member. Your assistant uses this core context to formulate responses and understand brand tone.
              </p>
            </div>

            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={!canManageKnowledge}
              rows={12}
              placeholder="Example: We are a real estate consultancy based in Bangalore specializing in residential villas and apartments in North Bangalore. We help prospective homebuyers with site visits, loan pre-approvals, and booking assistance. Most customers contact us asking about project amenities, pricing per sq.ft, handover timelines, and visit schedules."
              className="w-full px-4 py-3.5 rounded-xl bg-surface-low border border-surface-mid font-body text-sm leading-relaxed text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-colors"
            />

            <div className="flex items-center justify-between pt-2">
              <span className="font-mono text-xs text-on-surface-muted">
                {description.length.toLocaleString()} characters
              </span>
              <button
                onClick={saveDescription}
                disabled={descSaving || description === savedDescription || !canManageKnowledge}
                className="flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-xs"
              >
                <Save size={14} /> {descSaving ? "Saving…" : "Save Description"}
              </button>
            </div>
          </div>

          {/* App / Download Link */}
          <div className="bg-surface rounded-2xl p-6 md:p-8 border border-surface-mid shadow-sm space-y-4">
            <div>
              <h2 className="font-display text-lg font-bold text-primary flex items-center gap-2">
                <LinkIcon size={18} /> Canonical App or Booking Link
              </h2>
              <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed">
                Provide your official app download URL, booking page, or website link. When leads ask for your app or booking page, the AI will provide this exact link without hallucinating alternatives.
              </p>
            </div>

            <input
              type="url"
              value={appLink}
              onChange={(e) => setAppLink(e.target.value)}
              disabled={!canManageKnowledge}
              placeholder="https://yourapp.com/download or https://cal.com/yourbusiness"
              className="w-full px-4 py-3 rounded-xl bg-surface-low border border-surface-mid font-body text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-colors"
            />

            <div className="flex justify-end pt-2">
              <button
                onClick={saveAppLink}
                disabled={appLinkSaving || appLink === savedAppLink || !canManageKnowledge}
                className="flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-xs"
              >
                <Save size={14} /> {appLinkSaving ? "Saving…" : "Save Link"}
              </button>
            </div>
          </div>

          {/* Scoring Rubric */}
          <div className="bg-surface rounded-2xl p-6 md:p-8 border border-surface-mid shadow-sm space-y-4">
            <div>
              <h2 className="font-display text-lg font-bold text-primary">
                Lead Scoring Rubric (1–10)
              </h2>
              <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed">
                The criteria used by Aira to evaluate conversation transcripts and assign 1–10 intent scores to leads. You can edit this rubric manually or toggle auto-update to sync with your business description.
              </p>
            </div>

            <div className="flex items-start justify-between gap-4 rounded-xl border border-surface-mid bg-surface-low p-4">
              <div>
                <p className="font-label text-sm font-semibold text-on-surface">
                  Auto-generate rubric from business description
                </p>
                <p className="font-body text-xs text-on-surface-muted mt-0.5 leading-relaxed">
                  {rubricAutoUpdate
                    ? "Active: saving your description will automatically update this rubric based on your updated products/services."
                    : "Disabled: manual rubric changes below will be preserved and won't be modified when editing your business description."}
                </p>
              </div>

              <button
                type="button"
                role="switch"
                aria-checked={rubricAutoUpdate}
                onClick={toggleRubricAutoUpdate}
                disabled={rubricToggleSaving || !canManageKnowledge}
                className={cn(
                  "relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50",
                  rubricAutoUpdate ? "bg-primary" : "bg-surface-mid"
                )}
              >
                <span
                  className={cn(
                    "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform",
                    rubricAutoUpdate ? "translate-x-[22px]" : "translate-x-0.5"
                  )}
                />
              </button>
            </div>

            <textarea
              value={scoringRubric}
              onChange={(e) => setScoringRubric(e.target.value)}
              rows={7}
              spellCheck={false}
              placeholder={
                "9-10: High intent — asked about pricing, booking slot, or requested human advisor callback\n" +
                "7-8: Warm — showed clear interest, asked specific product or qualification questions\n" +
                "5-6: Neutral — general inquiry, no immediate buying signal\n" +
                "3-4: Lukewarm — vague interest, brief replies\n" +
                "1-2: Low — unresponsive, spam, or out-of-scope"
              }
              className="w-full px-4 py-3.5 rounded-xl bg-surface-low border border-surface-mid font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-colors"
            />

            <div className="flex justify-end pt-2">
              <button
                onClick={saveRubric}
                disabled={rubricSaving || scoringRubric === savedRubric || !canManageKnowledge}
                className="flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-xs"
              >
                <Save size={14} /> {rubricSaving ? "Saving…" : "Save Rubric"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Extracted Document Viewer Loading Overlay ───────────────────────── */}
      {viewerLoading && !viewingDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl p-5 shadow-2xl border border-surface-mid flex items-center gap-3">
            <Loader2 size={24} className="animate-spin text-primary" />
            <span className="font-body text-sm font-semibold text-on-surface">Loading document content…</span>
          </div>
        </div>
      )}

      {/* ── Extracted Document Viewer Modal ─────────────────────────────────── */}
      {viewingDoc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs"
          onClick={() => setViewingDoc(null)}
        >
          <div
            className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-surface shadow-2xl border border-surface-mid"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-start justify-between gap-4 border-b border-surface-mid px-6 py-4 bg-surface-low/50">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider border",
                      getFileTypeMeta(viewingDoc.file_type, viewingDoc.name).badgeBg,
                      getFileTypeMeta(viewingDoc.file_type, viewingDoc.name).badgeText,
                      getFileTypeMeta(viewingDoc.file_type, viewingDoc.name).badgeBorder
                    )}
                  >
                    {getFileTypeMeta(viewingDoc.file_type, viewingDoc.name).label}
                  </span>
                  <h3 className="truncate font-display text-base font-bold text-on-surface">
                    {viewingDoc.name}
                  </h3>
                </div>
                <p className="mt-1 font-body text-xs text-on-surface-muted">
                  {formatBytes(viewingDoc.size_bytes)} ·{" "}
                  {viewingDoc.full_text?.length.toLocaleString() || 0} characters extracted ·{" "}
                  Uploaded {formatDate(viewingDoc.created_at)}
                </p>
              </div>

              <button
                onClick={() => setViewingDoc(null)}
                className="rounded-lg p-1.5 text-on-surface-muted hover:bg-surface-mid hover:text-on-surface transition-colors"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* In-Modal Search Bar */}
            <div className="px-6 py-2.5 border-b border-surface-mid/60 bg-white flex items-center gap-2">
              <Search size={14} className="text-on-surface-muted" />
              <input
                type="text"
                placeholder="Find in document text..."
                value={viewerSearch}
                onChange={(e) => setViewerSearch(e.target.value)}
                className="flex-1 min-w-0 bg-transparent text-xs font-body focus:outline-none text-on-surface"
              />
              {viewerSearch && (
                <button
                  onClick={() => setViewerSearch("")}
                  className="text-on-surface-muted hover:text-on-surface p-0.5"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Content Body */}
            <div className="flex-1 overflow-y-auto px-6 py-4 bg-surface-low/30">
              {viewingDoc.full_text ? (
                <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-on-surface bg-white p-4 rounded-xl border border-surface-mid/80 shadow-xs">
                  {viewerSearch
                    ? viewingDoc.full_text
                        .split(new RegExp(`(${viewerSearch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"))
                        .map((part, i) =>
                          part.toLowerCase() === viewerSearch.toLowerCase() ? (
                            <mark key={i} className="bg-amber-200 text-amber-900 rounded-xs px-0.5">
                              {part}
                            </mark>
                          ) : (
                            part
                          )
                        )
                    : viewingDoc.full_text}
                </pre>
              ) : (
                <div className="py-12 text-center font-body text-xs text-on-surface-muted">
                  <FileText size={24} className="mx-auto mb-2 opacity-40" />
                  No text content was extracted from this file.
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between gap-4 border-t border-surface-mid px-6 py-3.5 bg-surface-low/50">
              <button
                onClick={copyExtractedText}
                disabled={!viewingDoc.full_text}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-surface hover:bg-surface-mid text-on-surface rounded-xl font-label text-xs font-semibold border border-surface-mid transition-colors shadow-xs"
              >
                {copiedText ? (
                  <>
                    <Check size={14} className="text-emerald-600" />
                    <span>Copied to Clipboard</span>
                  </>
                ) : (
                  <>
                    <Copy size={14} />
                    <span>Copy Text</span>
                  </>
                )}
              </button>

              <div className="flex items-center gap-2">
                {viewingDoc.downloadable && (
                  <button
                    onClick={() => downloadDocument(viewingDoc.id)}
                    disabled={downloading}
                    className="flex items-center gap-1.5 px-4 py-2 bg-primary text-white rounded-xl font-label text-xs font-semibold hover:bg-primary/90 disabled:opacity-40 transition-colors shadow-xs"
                  >
                    <Download size={14} />
                    {downloading ? "Preparing…" : "Download Original File"}
                  </button>
                )}
                <button
                  onClick={() => setViewingDoc(null)}
                  className="px-4 py-2 bg-surface hover:bg-surface-mid text-on-surface rounded-xl font-label text-xs font-semibold border border-surface-mid transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete Confirmation Dialog ────────────────────────────────────── */}
      {deletingDoc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs"
          onClick={() => setDeletingDoc(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-2xl border border-surface-mid space-y-4 animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-12 h-12 rounded-2xl bg-red-50 text-red-600 flex items-center justify-center">
              <Trash2 size={24} />
            </div>

            <div>
              <h3 className="font-display font-bold text-lg text-on-surface">
                Delete Knowledge Document?
              </h3>
              <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed">
                Are you sure you want to permanently delete{" "}
                <strong className="text-on-surface font-semibold">{deletingDoc.name}</strong>?
              </p>
              <div className="mt-2.5 p-3 rounded-xl bg-amber-50 border border-amber-100 text-amber-800 text-xs font-body">
                All extracted text and pgvector embeddings for this document will be immediately purged from AI memory.
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-surface-mid/60">
              <button
                type="button"
                onClick={() => setDeletingDoc(null)}
                disabled={deleteLoading}
                className="px-4 py-2 rounded-xl border border-surface-mid bg-surface font-label text-xs font-semibold text-on-surface hover:bg-surface-low transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDeleteDocument}
                disabled={deleteLoading}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-red-600 text-white font-label text-xs font-semibold hover:bg-red-700 disabled:opacity-50 transition-colors shadow-xs"
              >
                {deleteLoading && <Loader2 size={13} className="animate-spin" />}
                {deleteLoading ? "Deleting…" : "Yes, Delete Document"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
