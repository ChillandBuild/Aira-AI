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
  Tag, Shield, BookOpen, Lock, ArrowRight, Circle, Lightbulb
} from "lucide-react";
import { api, API_URL, getAuthHeaders, KnowledgeDocContent } from "@/lib/api";
import { cn } from "@/lib/utils";
import { usePolling } from "@/hooks/usePolling";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { useRouter, useSearchParams } from "next/navigation";
import { SwitchPill } from "@/components/ui/controls";

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

// ─── Description Guide ────────────────────────────────────────────────────────
// Plain-language onboarding for the Description tab. Clients writing this box are
// business owners, not prompt engineers -- the points below are the ones that
// actually change how Aira replies, in the order they matter.
//
// Deliberately NOT asked for here: opening hours and reply language. Both are
// structured settings (app_settings.business_hours, the reply-language mode) that
// ai_reply injects live, with real open/closed state -- a hand-typed line here
// only goes stale and then contradicts them mid-conversation.

const DESCRIPTION_POINTS: { title: string; body: string; example: string }[] = [
  {
    title: "Who you are",
    body: "Your business name, what line of work you are in, and the area you actually serve.",
    example: "We are Sunrise Interiors, a home interior studio running since 2015. We take up work across Coimbatore and Tiruppur.",
  },
  {
    title: "What you sell",
    body: "Your main services or products — named the way your customers name them, not your internal terms.",
    example: "We do modular kitchens, wardrobes, and full home interiors.",
  },
  {
    title: "Who your customers are",
    body: "Who usually contacts you, and what they normally want — so Aira pitches at the right level instead of guessing.",
    example: "Mostly families moving into a new apartment. They usually want a rough price and a site visit.",
  },
  {
    title: "What you want Aira to do",
    body: "The point of every conversation. Without this Aira will answer politely and let the customer go.",
    example: "Answer their question, then offer a free site visit and ask which area they live in.",
  },
  {
    title: "What Aira must never do",
    body: "The promises that would cost you if a machine made them on your behalf.",
    example: "Never quote a final price, promise a discount, or commit to a delivery date.",
  },
  {
    title: "Tone, and when to fetch a person",
    body: "How you want Aira to sound, and the topics it should hand straight to your team.",
    example: "Warm and respectful, address customers as sir or madam. Hand over complaints and anything about an ongoing order.",
  },
];

// Headed sections rather than one prose blob: the same text is re-read on every
// reply, and a labelled block is far harder for the model to lose than a
// sentence buried mid-paragraph. No hours and no language line -- see above.
const DESCRIPTION_TEMPLATE = `ABOUT US
We are [BUSINESS NAME], a [WHAT YOU DO] business running since [YEAR].
We serve [YOUR AREA, CITIES, OR "customers anywhere - we work online"].

WHAT WE OFFER
- [SERVICE OR PRODUCT 1] - [one line, in the words customers use]
- [SERVICE OR PRODUCT 2] - [one line, in the words customers use]
- [SERVICE OR PRODUCT 3] - [one line, in the words customers use]

WHO WE TALK TO
Most people who contact us are [WHO THEY ARE].
They usually want [WHAT THEY ASK FOR MOST OFTEN].

YOUR JOB IN EVERY CONVERSATION
Understand what the customer needs, answer it clearly, then [YOUR GOAL: book a
visit / collect their requirement / get them onto the app / arrange a callback].
Ask one question at a time. Never leave a customer without a next step.

WHAT YOU MUST NEVER DO
- Never [PROMISE A DISCOUNT / CONFIRM A FINAL PRICE / COMMIT TO A DATE].
- Never invent an answer. If you do not know, say you will check with the team.
- Never [ANYTHING ELSE THAT WOULD COST YOU: e.g. give medical or legal advice].

HAND OVER TO A PERSON WHEN
[A COMPLAINT / A REFUND OR CANCELLATION / ANYTHING ABOUT AN EXISTING ORDER /
THE CUSTOMER IS UPSET OR ASKS FOR A HUMAN].

HOW TO SOUND
[WARM AND RESPECTFUL / CASUAL AND FRIENDLY]. [ADDRESS CUSTOMERS AS SIR OR MADAM.]
Keep replies short — [TWO OR THREE] sentences unless they ask for detail.`;

// ─── Documents (RAG) Guide ────────────────────────────────────────────────────
// The mirror of DESCRIPTION_POINTS for the Documents tab. The split clients get
// wrong is what belongs in each place: the description is re-read on every reply
// and competes with the safety rules for attention, so everything long, detailed
// or changeable has to live here instead and be looked up only when asked.

const RAG_POINTS: { title: string; body: string; example: string }[] = [
  {
    title: "Prices and packages",
    body: "Full rate cards, what each package includes, and what costs extra.",
    example: "Modular kitchen — Basic ₹1.8L, Premium ₹3.2L. Chimney and hob are extra.",
  },
  {
    title: "What each service actually involves",
    body: "The detail behind the one-liners on your Description page — included, excluded, how long it takes.",
    example: "Full home interiors: design, material, execution. Civil work is not included. 60 to 75 days.",
  },
  {
    title: "Questions you answer every day",
    body: "Refunds, cancellations, delivery times, warranty — write them as question and answer.",
    example: "Q: Do you give a warranty? A: 10 years on modular units, 1 year on hardware.",
  },
  {
    title: "Policies and terms",
    body: "Payment terms, eligibility, cancellation rules — anything a customer might argue about later.",
    example: "50% advance on order, 40% before installation, 10% on handover.",
  },
  {
    title: "Locations and directions",
    body: "Branch list, addresses, landmarks, parking — the things people ask right before they visit.",
    example: "Showroom: 3rd floor, Brookefields Mall, Coimbatore. Parking in basement 2.",
  },
  {
    title: "Proof of your work",
    body: "Past projects, client names you are allowed to share, certifications, awards.",
    example: "Completed 400+ homes since 2015. ISO 9001 certified.",
  },
];

const RAG_TEMPLATE = `PRICING — [SERVICE NAME]

[PACKAGE 1] - [PRICE]
Includes: [WHAT IS INCLUDED]
Not included: [WHAT COSTS EXTRA]

[PACKAGE 2] - [PRICE]
Includes: [WHAT IS INCLUDED]
Not included: [WHAT COSTS EXTRA]

COMMON QUESTIONS

Q: [QUESTION A CUSTOMER ACTUALLY ASKS]
A: [YOUR ANSWER IN ONE OR TWO SENTENCES]

Q: [ANOTHER QUESTION]
A: [YOUR ANSWER]

PAYMENT AND CANCELLATION

[YOUR PAYMENT TERMS]
[YOUR CANCELLATION RULE]`;

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

  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  // Description is the default: the AI's identity and the scoring rubric are the
  // prerequisites for RAG documents to be worth anything, so that is where a
  // client lands. Only an explicit ?tab=documents opens the document library.
  const tab = (rawTab === "documents" ? "documents" : "description") as
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
  // Description + rubric drive the upload gate on the Documents tab, so they are
  // fetched on mount rather than lazily when the Description tab opens.
  const [setupLoaded, setSetupLoaded] = useState(false);

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

  // Description Guide
  const [showDescExample, setShowDescExample] = useState(false);
  // Documents Guide
  const [showRagExample, setShowRagExample] = useState(false);
  // Which template was last copied — "desc" | "rag" | null, so the two Copy
  // buttons confirm independently.
  const [copiedTemplate, setCopiedTemplate] = useState<"desc" | "rag" | null>(null);

  async function copyTemplate(which: "desc" | "rag") {
    try {
      await navigator.clipboard.writeText(
        which === "desc" ? DESCRIPTION_TEMPLATE : RAG_TEMPLATE
      );
      setCopiedTemplate(which);
      setTimeout(() => setCopiedTemplate(null), 2000);
    } catch {
      toast.error("Could not copy. Select the text and copy it manually.");
    }
  }

  // ─── Documents gate ────────────────────────────────────────────────────────
  // Retrieved excerpts arrive with no document name attached and can miss
  // entirely, so they are only useful on top of an assistant that already knows
  // who it is (description) and how to score what it hears (rubric). Uploading
  // before both exist produces a knowledge base the AI cannot actually use, so
  // the upload surface stays locked until they are saved.
  const hasDescription = savedDescription.trim().length > 0;
  const hasRubric = savedRubric.trim().length > 0;
  const setupComplete = hasDescription && hasRubric;
  const uploadLocked = setupLoaded && !setupComplete;
  const canUpload = canManageKnowledge && setupLoaded && setupComplete;

  function goToDescription() {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("tab");
    const qs = params.toString();
    router.replace(`/dashboard/knowledge${qs ? `?${qs}` : ""}`, { scroll: false });
  }

  useEffect(() => {
    loadData();
    api.knowledge
      .listCampaignTags()
      .then(setCampaignTags)
      .catch(() => {});
    // Both tabs need these: Description renders them, Documents gates uploading on them.
    Promise.all([loadDescription(), loadAppLink(), loadAiTuneSettings()]).finally(() =>
      setSetupLoaded(true)
    );
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const hasProcessing = useMemo(
    () => documents.some((d) => d.status === "processing"),
    [documents]
  );
  usePolling(loadDocuments, 5000, hasProcessing);

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
    if (!setupComplete) {
      setUploadError(
        "Save your business description and lead scoring rubric before uploading documents."
      );
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
    if (!uploading && canUpload) {
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
    if (uploading || !canUpload) return;
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

  async function toggleRubricAutoUpdate(next: boolean) {
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
          {/* ── Plain-language guide ──────────────────────────────────────── */}
          <div className="bg-gradient-to-br from-purple-50/70 via-surface to-surface border border-purple-100 rounded-2xl p-5 md:p-6 shadow-xs">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-xl bg-purple-100/80 text-primary flex items-center justify-center shrink-0 mt-0.5">
                <Lightbulb size={18} />
              </div>
              <div className="min-w-0">
                <h4 className="font-display font-bold text-sm text-on-surface">
                  Start here — what to upload on this page
                </h4>
                <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed max-w-3xl">
                  Your Description page is the note Aira reads before every reply. This
                  page is the folder it goes and looks something up in when a customer
                  actually asks. So everything long, detailed or likely to change belongs
                  here — prices, FAQs, policies — not in the description.
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              {RAG_POINTS.map((point, i) => (
                <div
                  key={point.title}
                  className={cn(
                    "p-3.5 bg-white rounded-xl border border-purple-100",
                    RAG_POINTS.length % 2 === 1 &&
                      i === RAG_POINTS.length - 1 &&
                      "md:col-span-2"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 shrink-0 rounded-full bg-primary/10 text-primary font-label text-[10px] font-bold flex items-center justify-center">
                      {i + 1}
                    </span>
                    <p className="font-label text-xs font-bold text-on-surface">
                      {point.title}
                    </p>
                  </div>
                  <p className="font-body text-xs text-on-surface-muted mt-1.5 leading-relaxed">
                    {point.body}
                  </p>
                  <p className="font-body text-xs text-on-surface/70 italic mt-2 pl-2.5 border-l-2 border-purple-200 leading-relaxed">
                    {point.example}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="flex items-start gap-2 rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
                <Check size={14} className="text-emerald-600 shrink-0 mt-0.5" strokeWidth={3} />
                <p className="font-body text-xs text-on-surface-muted leading-relaxed">
                  <span className="font-semibold text-on-surface">Plain beats pretty.</span>{" "}
                  A simple Word or PDF with clear headings and short paragraphs gets
                  searched far better than a designed brochure. One topic per file, and
                  re-upload the file when the prices change.
                </p>
              </div>
              <div className="flex items-start gap-2 rounded-xl border border-surface-mid bg-surface-low p-3">
                <X size={14} className="text-on-surface-muted shrink-0 mt-0.5" strokeWidth={3} />
                <p className="font-body text-xs text-on-surface-muted leading-relaxed">
                  <span className="font-semibold text-on-surface">Leave out</span> your
                  business intro and tone — those belong on the Description page. Scans of
                  handwriting and text inside images cannot be read at all.
                </p>
              </div>
            </div>

            <button
              onClick={() => setShowRagExample(!showRagExample)}
              className="mt-4 text-xs font-label font-bold text-primary hover:underline"
            >
              {showRagExample ? "Hide the fill-in-the-blanks example" : "Show a fill-in-the-blanks example →"}
            </button>

            {showRagExample && (
              <div className="mt-3 rounded-xl border border-purple-100 bg-white overflow-hidden">
                <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-purple-100 bg-purple-50/40">
                  <p className="font-label text-[11px] font-bold uppercase tracking-wider text-primary">
                    Paste this into a document and replace the words in brackets
                  </p>
                  <button
                    onClick={() => copyTemplate("rag")}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-purple-200 bg-white font-label text-[11px] font-bold text-primary hover:bg-purple-50 transition-colors shrink-0"
                  >
                    {copiedTemplate === "rag" ? (
                      <>
                        <Check size={12} strokeWidth={3} /> Copied
                      </>
                    ) : (
                      <>
                        <Copy size={12} /> Copy
                      </>
                    )}
                  </button>
                </div>
                <pre className="px-4 py-3.5 font-mono text-[11px] leading-relaxed text-on-surface whitespace-pre-wrap overflow-x-auto">
                  {RAG_TEMPLATE}
                </pre>
              </div>
            )}
          </div>

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

              {campaignTags.length > 0 && !uploadLocked && (
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

            {/* Drag & Drop Area — locked until description + rubric are saved */}
            <div className="p-4 sm:p-6">
              {uploadLocked ? (
                <div className="rounded-2xl border border-amber-200 bg-amber-50/40 p-8 flex flex-col items-center text-center">
                  <div className="w-14 h-14 rounded-2xl bg-amber-100 text-amber-700 flex items-center justify-center shadow-xs mb-3">
                    <Lock size={24} />
                  </div>

                  <p className="font-display text-base font-bold text-on-surface">
                    Finish your Description first
                  </p>
                  <p className="font-body text-xs text-on-surface-muted mt-1 max-w-md leading-relaxed">
                    Documents are searched per message and can come back empty. Your
                    business description and scoring rubric are read on every reply — so
                    they have to be in place before uploads add anything.
                  </p>

                  <div className="mt-5 w-full max-w-sm space-y-2">
                    {[
                      { done: hasDescription, label: "Business description saved" },
                      { done: hasRubric, label: "Lead scoring rubric saved" },
                    ].map((step) => (
                      <div
                        key={step.label}
                        className="flex items-center gap-2.5 rounded-xl border border-surface-mid bg-white px-3.5 py-2.5 text-left"
                      >
                        {step.done ? (
                          <span className="w-5 h-5 shrink-0 rounded-full bg-emerald-500 text-white flex items-center justify-center">
                            <Check size={12} strokeWidth={3} />
                          </span>
                        ) : (
                          <Circle size={20} className="shrink-0 text-on-surface-muted/50" />
                        )}
                        <span
                          className={cn(
                            "font-label text-xs font-semibold",
                            step.done ? "text-on-surface-muted line-through" : "text-on-surface"
                          )}
                        >
                          {step.label}
                        </span>
                        <span className="ml-auto font-body text-[11px] font-semibold text-on-surface-muted">
                          {step.done ? "Done" : "Pending"}
                        </span>
                      </div>
                    ))}
                  </div>

                  {canManageKnowledge ? (
                    <button
                      type="button"
                      onClick={goToDescription}
                      className="mt-5 flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 transition-colors shadow-xs"
                    >
                      Go to Description <ArrowRight size={15} />
                    </button>
                  ) : (
                    <p className="mt-5 font-body text-xs text-on-surface-muted">
                      Ask an account owner to complete these before uploading documents.
                    </p>
                  )}
                </div>
              ) : (
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
                    disabled={uploading || !canUpload}
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
              )}

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
                      {uploadLocked
                        ? "Save your business description and lead scoring rubric first — documents build on top of them."
                        : "Upload company FAQs, product catalogs, service brochures, or pricing sheets above so your AI assistant can accurately answer lead questions."}
                    </p>
                    {uploadLocked ? (
                      <button
                        type="button"
                        onClick={goToDescription}
                        disabled={!canManageKnowledge}
                        className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl font-label text-xs font-semibold hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-xs"
                      >
                        Go to Description <ArrowRight size={14} />
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={!canUpload}
                        className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl font-label text-xs font-semibold hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-xs"
                      >
                        <Upload size={14} /> Upload First Document
                      </button>
                    )}
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
          {/* ── Plain-language guide ──────────────────────────────────────── */}
          <div className="bg-gradient-to-br from-purple-50/70 via-surface to-surface border border-purple-100 rounded-2xl p-5 md:p-6 shadow-xs">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-xl bg-purple-100/80 text-primary flex items-center justify-center shrink-0 mt-0.5">
                <Lightbulb size={18} />
              </div>
              <div className="min-w-0">
                <h4 className="font-display font-bold text-sm text-on-surface">
                  Start here — what to write on this page
                </h4>
                <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed max-w-3xl">
                  Aira reads this before every single reply it sends. Think of it as the
                  note you would hand a new employee on their first day: who we are, what
                  we sell, what to get out of every conversation, and where to stop and
                  fetch a person. Write it in plain sentences — there is nothing technical
                  to get right here.
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              {DESCRIPTION_POINTS.map((point, i) => (
                <div
                  key={point.title}
                  className={cn(
                    "p-3.5 bg-white rounded-xl border border-purple-100",
                    // Odd count leaves the last card alone on its row — let it span.
                    DESCRIPTION_POINTS.length % 2 === 1 &&
                      i === DESCRIPTION_POINTS.length - 1 &&
                      "md:col-span-2"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 shrink-0 rounded-full bg-primary/10 text-primary font-label text-[10px] font-bold flex items-center justify-center">
                      {i + 1}
                    </span>
                    <p className="font-label text-xs font-bold text-on-surface">
                      {point.title}
                    </p>
                  </div>
                  <p className="font-body text-xs text-on-surface-muted mt-1.5 leading-relaxed">
                    {point.body}
                  </p>
                  <p className="font-body text-xs text-on-surface/70 italic mt-2 pl-2.5 border-l-2 border-purple-200 leading-relaxed">
                    {point.example}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="flex items-start gap-2 rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
                <Check size={14} className="text-emerald-600 shrink-0 mt-0.5" strokeWidth={3} />
                <p className="font-body text-xs text-on-surface-muted leading-relaxed">
                  <span className="font-semibold text-on-surface">Keep it short.</span>{" "}
                  Around 200 to 350 words. Every word here is re-read on every single
                  reply, so anything you add competes for attention with everything else.
                </p>
              </div>
              <div className="flex items-start gap-2 rounded-xl border border-surface-mid bg-surface-low p-3">
                <X size={14} className="text-on-surface-muted shrink-0 mt-0.5" strokeWidth={3} />
                <p className="font-body text-xs text-on-surface-muted leading-relaxed">
                  <span className="font-semibold text-on-surface">Leave out</span> your
                  opening hours, reply language and app link — Aira already gets those
                  from Settings, live. Price lists, packages and FAQs belong in Documents
                  (RAG), which Aira reads only when a customer actually asks.
                </p>
              </div>
            </div>

            <button
              onClick={() => setShowDescExample(!showDescExample)}
              className="mt-4 text-xs font-label font-bold text-primary hover:underline"
            >
              {showDescExample ? "Hide the fill-in-the-blanks example" : "Show a fill-in-the-blanks example →"}
            </button>

            {showDescExample && (
              <div className="mt-3 rounded-xl border border-purple-100 bg-white overflow-hidden">
                <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-purple-100 bg-purple-50/40">
                  <p className="font-label text-[11px] font-bold uppercase tracking-wider text-primary">
                    Copy this and replace the words in brackets
                  </p>
                  <button
                    onClick={() => copyTemplate("desc")}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-purple-200 bg-white font-label text-[11px] font-bold text-primary hover:bg-purple-50 transition-colors shrink-0"
                  >
                    {copiedTemplate === "desc" ? (
                      <>
                        <Check size={12} strokeWidth={3} /> Copied
                      </>
                    ) : (
                      <>
                        <Copy size={12} /> Copy
                      </>
                    )}
                  </button>
                </div>
                <pre className="px-4 py-3.5 font-mono text-[11px] leading-relaxed text-on-surface whitespace-pre-wrap overflow-x-auto">
                  {DESCRIPTION_TEMPLATE}
                </pre>
              </div>
            )}
          </div>

          {/* Business Description Card */}
          <div className="bg-surface rounded-2xl p-6 md:p-8 border border-surface-mid shadow-sm space-y-4">
            <div>
              <h2 className="font-display text-lg font-bold text-primary">
                Lead Segment Description
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

              <div className="mt-0.5">
                <SwitchPill
                  on={rubricAutoUpdate}
                  onChange={toggleRubricAutoUpdate}
                  loading={rubricToggleSaving}
                  disabled={!canManageKnowledge}
                  aria-label="Auto-generate rubric from business description"
                />
              </div>
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
