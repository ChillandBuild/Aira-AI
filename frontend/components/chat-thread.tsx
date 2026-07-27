"use client";
import { toast } from "sonner";
import { Fragment, memo, useCallback, useEffect, useRef, useState } from "react";
import { api, Lead, Message } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { cn } from "@/lib/utils";
import { usePolling } from "@/hooks/usePolling";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import {
  Bot, User, CheckCircle2, Send, PowerOff, Power,
  AlertTriangle, Pencil, MessageCircle, Trash2,
  Plus, Mic, MicOff, FileText, Image as ImageIcon,
  Music, Video, Download, X, Eraser, MoreVertical,
  ArrowLeft,
} from "lucide-react";

const AVATAR_COLORS = [
  "bg-violet-500", "bg-blue-500", "bg-indigo-500", "bg-cyan-500",
  "bg-teal-500", "bg-pink-500", "bg-rose-500", "bg-orange-500",
  "bg-amber-500", "bg-emerald-500",
];

function getAvatarColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) & 0xffffffff;
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function getInitials(name: string | null, phone: string | null): string {
  if (name) return name.split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2);
  if (phone) return phone.slice(-2);
  return "?";
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function formatDateDivider(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  if (isSameDay(date, now)) return "Today";
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (isSameDay(date, yesterday)) return "Yesterday";
  return date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "long",
    year: date.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
}

function IgIcon({ size = 10, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

function TgIcon({ size = 10, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function FbIcon({ size = 10, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
    </svg>
  );
}

// ─── Media bubble renderer ────────────────────────────────────────────────────
function MediaBubble({ msg }: { msg: Message }) {
  const mediaType = msg.media_type;
  const filename = msg.media_filename || "file";
  const isOutbound = msg.direction === "outbound";

  if (!mediaType) return null;

  if (mediaType === "image") {
    // Images: show placeholder since we store meta:ID not public URL
    return (
      <div className={cn(
        "max-w-[240px] rounded-xl overflow-hidden border",
        isOutbound ? "border-white/20" : "border-surface-mid"
      )}>
        <div className={cn(
          "flex flex-col items-center justify-center gap-2 p-6 rounded-xl",
          isOutbound ? "bg-white/10" : "bg-surface-low"
        )}>
          <ImageIcon size={32} className={isOutbound ? "text-white/70" : "text-on-surface-muted"} />
          <span className={cn("font-label text-xs truncate max-w-[180px]", isOutbound ? "text-white/80" : "text-on-surface-muted")}>
            {filename}
          </span>
        </div>
      </div>
    );
  }

  if (mediaType === "audio") {
    return (
      <div className={cn(
        "flex items-center gap-2 px-3 py-2 rounded-xl",
        isOutbound ? "bg-white/10" : "bg-surface-low"
      )}>
        <Music size={16} className={isOutbound ? "text-white/80" : "text-secondary"} />
        <span className={cn("font-label text-xs", isOutbound ? "text-white/80" : "text-on-surface-muted")}>
          {filename}
        </span>
      </div>
    );
  }

  if (mediaType === "video") {
    return (
      <div className={cn(
        "flex items-center gap-2 px-3 py-2 rounded-xl",
        isOutbound ? "bg-white/10" : "bg-surface-low"
      )}>
        <Video size={16} className={isOutbound ? "text-white/80" : "text-secondary"} />
        <span className={cn("font-label text-xs", isOutbound ? "text-white/80" : "text-on-surface-muted")}>
          {filename}
        </span>
      </div>
    );
  }

  // Document / sticker / default
  return (
    <div className={cn(
      "flex items-center gap-2 px-3 py-2 rounded-xl border",
      isOutbound ? "bg-white/10 border-white/20" : "bg-surface-low border-surface-mid"
    )}>
      <FileText size={16} className={isOutbound ? "text-white/80" : "text-secondary"} />
      <div className="min-w-0">
        <p className={cn("font-label text-xs font-semibold truncate max-w-[160px]", isOutbound ? "text-white" : "text-on-surface")}>
          {filename}
        </p>
        <p className={cn("font-label text-[10px]", isOutbound ? "text-white/60" : "text-on-surface-muted")}>
          {mediaType}
        </p>
      </div>
      <Download size={13} className={isOutbound ? "text-white/60" : "text-on-surface-muted"} />
    </div>
  );
}

// ─── Single message bubble (memoized — only re-renders when this message changes) ─
const MessageBubble = memo(function MessageBubble({ msg }: { msg: Message }) {
  const isAiMediaRecommendation =
    msg.direction === "outbound" &&
    msg.is_ai_generated &&
    msg.media_type === "image";

  return (
    <div className={cn("flex gap-2", msg.direction === "outbound" && "flex-row-reverse")}>
      <div className={cn(
        "w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5",
        msg.direction === "outbound"
          ? (msg.is_ai_generated ? "bg-secondary/10" : "bg-primary/10")
          : "bg-surface-mid"
      )}>
        {msg.direction === "outbound" ? (
          msg.is_ai_generated ? <Bot size={14} className="text-secondary" /> : <User size={14} className="text-primary" />
        ) : (
          <User size={14} className="text-on-surface-muted" />
        )}
      </div>
      <div className={cn(
        "max-w-[82%] md:max-w-[70%] px-4 py-2.5 rounded-2xl font-body text-sm",
        msg.direction === "outbound"
          ? "bg-primary text-white rounded-tr-sm"
          : "bg-surface text-on-surface shadow-card rounded-tl-sm"
      )}>
        {msg.media_type && <MediaBubble msg={msg} />}
        {msg.content && !(msg.media_type && msg.content.startsWith("[")) && (
          <p className={cn("whitespace-pre-wrap", msg.media_type && "mt-1.5 text-xs opacity-80")}>
            {msg.content}
          </p>
        )}
        <p className="mt-1 text-[10px] opacity-60">
          {msg.direction === "outbound" && (
            <>
              {isAiMediaRecommendation
                ? "AI media recommendation"
                : msg.is_ai_generated
                ? msg.reply_source === "knowledge"
                  ? "📄 Knowledge Base"
                  : "✨ AI"
                : "Sent by you"}
              {" · "}
            </>
          )}
          {new Date(msg.created_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
    </div>
  );
});

// ─── Date divider (WhatsApp-style day separator) ──────────────────────────────
function DateDivider({ dateStr }: { dateStr: string }) {
  return (
    <div className="flex justify-center my-3 select-none">
      <span className="rounded-full bg-surface-low px-3 py-1 font-label text-[11px] font-semibold text-on-surface-muted shadow-sm">
        {formatDateDivider(dateStr)}
      </span>
    </div>
  );
}

// ─── Selected file preview ────────────────────────────────────────────────────
function FilePreview({ file, onRemove }: { file: File; onRemove: () => void }) {
  const isImage = file.type.startsWith("image/");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (isImage) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    }
  }, [file, isImage]);

  const sizeMB = (file.size / 1024 / 1024).toFixed(1);

  return (
    <div className="flex items-center gap-2 px-3 py-2 mb-2 bg-surface-low rounded-xl border border-surface-mid">
      {isImage && previewUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={previewUrl} alt={file.name} loading="lazy" decoding="async" className="w-10 h-10 object-cover rounded-lg shrink-0" />
      ) : (
        <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center shrink-0">
          <FileText size={18} className="text-primary" />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="font-label text-xs font-semibold text-on-surface truncate">{file.name}</p>
        <p className="font-label text-[10px] text-on-surface-muted">{sizeMB} MB</p>
      </div>
      <button onClick={onRemove} className="p-1 rounded-lg hover:bg-surface-mid transition-colors text-on-surface-muted hover:text-red-500">
        <X size={14} />
      </button>
    </div>
  );
}

// ─── Main ChatThread component ────────────────────────────────────────────────
export function ChatThread({
  lead,
  onDeleted,
  onLeadUpdate,
  onBack,
}: {
  lead: Lead;
  onDeleted?: (id: string) => void;
  onLeadUpdate?: (updated: Lead) => void;
  onBack?: () => void;
}) {
  const { role, permissions } = useAuthRole();
  const canReplyToConversations = role === "owner" || permissions.includes("conversations.reply");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [current, setCurrent] = useState<Lead>(lead);
  const [converting, setConverting] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Media state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileCaption, setFileCaption] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCurrent(lead);
    setDraft("");
    setSendError(null);
    setEditingName(false);
    setSelectedFile(null);
    setFileCaption("");
  }, [lead.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync fields that the right panel may update externally
  useEffect(() => {
    setCurrent((prev) => ({
      ...prev,
      ai_enabled: lead.ai_enabled,
      converted_at: lead.converted_at,
      name: lead.name,
      score: lead.score,
      segment: lead.segment,
    }));
  }, [lead.ai_enabled, lead.converted_at, lead.name, lead.score, lead.segment]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function saveName() {
    const trimmed = nameDraft.trim();
    setEditingName(false);
    if (!trimmed || trimmed === current.name) return;
    try {
      const updated = await api.leads.update(lead.id, { name: trimmed });
      setCurrent(updated);
      onLeadUpdate?.(updated);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Rename failed");
    }
  }

  async function markConverted() {
    if (!confirm(`Mark ${lead.name || lead.phone} as converted? This feeds AI Auto-Tune.`)) return;
    setConverting(true);
    try {
      const updated = await api.leads.convert(lead.id);
      setCurrent(updated);
      onLeadUpdate?.(updated);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    } finally { setConverting(false); }
  }

  async function deleteConversation() {
    if (!confirm(`Delete the conversation with ${current.name || current.phone}? This removes the lead from every page. This action cannot be undone from the dashboard.`)) return;
    setDeleting(true);
    try {
      await api.leads.delete(lead.id);
      onDeleted?.(lead.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
      setDeleting(false);
    }
  }

  async function clearChat() {
    if (!confirm(`Clear all messages with ${current.name || current.phone}? The lead profile is kept but the chat history is permanently erased and AI will be re-enabled.`)) return;
    setClearing(true);
    try {
      await api.leads.clearChat(lead.id);
      setMessages([]);
      setCurrent((prev) => ({ ...prev, ai_enabled: true }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Clear failed");
    } finally {
      setClearing(false);
    }
  }

  async function toggleAI() {
    setToggling(true);
    try {
      const updated = await api.leads.toggleAI(lead.id, !current.ai_enabled);
      setCurrent(updated);
      onLeadUpdate?.(updated);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Toggle failed");
    } finally { setToggling(false); }
  }

  async function sendReply() {
    const text = draft.trim();
    if (!canReplyToConversations || !text || sending) return;
    setSending(true);
    setSendError(null);
    try {
      const sentMsg = await api.leads.sendMessage(lead.id, text);
      setMessages((prev) => {
        const msgId = sentMsg.id || (sentMsg as unknown as Record<string, unknown>).sid || Date.now().toString();
        if (prev.some((m) => m.id === msgId)) return prev;
        return [...prev, sentMsg as Message];
      });
      setDraft("");
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "Send failed");
    } finally { setSending(false); }
  }

  async function sendMedia() {
    if (!canReplyToConversations || !selectedFile || sending) return;
    setSending(true);
    setSendError(null);
    try {
      const sentMsg = await api.leads.sendMedia(lead.id, selectedFile, fileCaption || undefined);
      setMessages((prev) => {
        if (prev.some((m) => m.id === sentMsg.id)) return prev;
        return [...prev, sentMsg as Message];
      });
      setSelectedFile(null);
      setFileCaption("");
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "Media send failed");
    } finally { setSending(false); }
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Try OGG first (WhatsApp native), fall back to webm
      const mimeType = MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")
        ? "audio/ogg;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      const chunks: Blob[] = [];

      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = () => {
        const ext = mimeType.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(chunks, { type: mimeType });
        const file = new File([blob], `voice-note.${ext}`, { type: mimeType });
        setSelectedFile(file);
        stream.getTracks().forEach(t => t.stop());
      };

      recorder.start();
      setMediaRecorder(recorder);
      setIsRecording(true);
    } catch {
      toast.error("Microphone access denied — please allow access in browser settings");
    }
  }

  function stopRecording() {
    mediaRecorder?.stop();
    setIsRecording(false);
    setMediaRecorder(null);
  }

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    const fetchMsgs = async () => {
      try {
        const msgs = await api.leads.messages(lead.id);
        if (mounted) { setMessages(msgs); setLoading(false); }
      } catch {
        if (mounted) setLoading(false);
      }
    };

    fetchMsgs();

    const channel = supabase
      .channel(`messages:${lead.id}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "messages", filter: `lead_id=eq.${lead.id}` },
        (payload) => {
          if (!mounted) return;
          setMessages((prev) => {
            if (prev.some((m) => m.id === payload.new.id)) return prev;
            return [...prev, payload.new as Message];
          });
        }
      )
      .subscribe();

    return () => {
      mounted = false;
      supabase.removeChannel(channel);
    };
  }, [lead.id]);

  const pollMessages = useCallback(() => {
    api.leads.messages(lead.id).then((newMsgs) => {
      setMessages((prev) => {
        if (
          prev.length !== newMsgs.length ||
          (prev.length > 0 && newMsgs.length > 0 && prev[prev.length - 1].id !== newMsgs[newMsgs.length - 1].id)
        ) return newMsgs;
        return prev;
      });
    }).catch(() => { /* silent — realtime is primary */ });
  }, [lead.id]);

  usePolling(pollMessages, 15000);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const aiEnabled = current.ai_enabled !== false;
  const converted = Boolean(current.converted_at);
  const isInstagram = current.source === "instagram";
  const isTelegram = current.source === "telegram";
  const isFacebook = current.source === "facebook";
  const isWhatsApp = !isInstagram && !isTelegram && !isFacebook;
  const canSendMedia = canReplyToConversations && !aiEnabled && isWhatsApp;

  const lastInbound = [...messages].reverse().find((m) => m.direction === "inbound");
  const hoursSinceInbound = lastInbound
    ? (Date.now() - new Date(lastInbound.created_at).getTime()) / 3_600_000
    : Infinity;
  const outsideWindow = hoursSinceInbound > 24;

  return (
    <div className="flex-1 flex flex-col h-full min-w-0">
      {/* Header */}
      <div className="px-3 py-3 md:px-5 border-b border-surface-mid bg-surface flex items-center gap-3">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface-low text-on-surface hover:bg-surface-mid md:hidden"
            title="Back to conversations"
          >
            <ArrowLeft size={18} />
          </button>
        )}
        {/* Avatar */}
        <div className={cn("w-9 h-9 rounded-full flex items-center justify-center text-white font-semibold text-sm shrink-0 select-none", getAvatarColor(lead.id))}>
          {getInitials(current.name, current.phone)}
        </div>

        {/* Name + subtitle */}
        <div className="flex-1 min-w-0">
          {editingName ? (
            <input
              autoFocus
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={saveName}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveName();
                if (e.key === "Escape") setEditingName(false);
              }}
              placeholder="Add a name"
              className="font-body text-sm font-semibold text-on-surface bg-surface-low px-2 py-0.5 rounded border border-primary focus:outline-none focus:ring-1 focus:ring-primary w-56"
            />
          ) : (
            <button
              onClick={() => { setNameDraft(current.name || ""); setEditingName(true); }}
              className="group flex items-center gap-1.5 text-left"
              title="Click to rename"
            >
              <span className="font-body text-[14px] font-semibold text-on-surface truncate">
                {current.name || current.phone || "Unknown"}
              </span>
              <Pencil size={11} className="opacity-0 group-hover:opacity-50 text-on-surface-muted shrink-0" />
            </button>
          )}
          <p className="font-label text-[11px] text-on-surface-muted flex items-center gap-1">
            {isInstagram ? (
              <span className="inline-flex items-center gap-0.5 text-pink-500 font-semibold"><IgIcon size={9} /> Instagram</span>
            ) : isTelegram ? (
              <span className="inline-flex items-center gap-0.5 text-sky-500 font-semibold"><TgIcon size={9} /> Telegram</span>
            ) : isFacebook ? (
              <span className="inline-flex items-center gap-0.5 text-blue-600 font-semibold"><FbIcon size={9} /> Facebook</span>
            ) : (
              <span className="inline-flex items-center gap-0.5 text-green-600 font-semibold"><MessageCircle size={9} /> WhatsApp</span>
            )}
            <span className="text-on-surface-muted/50">·</span>
            <span>Score {current.score}/10</span>
            <span className="text-on-surface-muted/50">·</span>
            <span>Seg {current.segment}</span>
            {!aiEnabled && <span className="text-amber-600 font-semibold ml-1">· Handling</span>}
          </p>
        </div>

        {/* ⋯ dropdown — AI toggle + Clear + Delete */}
        <div className="relative shrink-0" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen((v) => !v)}
            className="p-1.5 rounded-lg hover:bg-surface-low text-on-surface-muted hover:text-on-surface transition-colors"
            title="More actions"
          >
            <MoreVertical size={16} />
          </button>
          {dropdownOpen && (
            <div className="absolute right-0 top-full mt-1 w-44 bg-surface border border-surface-mid rounded-xl shadow-xl overflow-hidden z-30 py-1.5">
              <button
                onClick={() => { setDropdownOpen(false); toggleAI(); }}
                disabled={toggling}
                className={cn(
                  "w-full text-left px-4 py-2 text-[13px] font-medium transition-colors flex items-center gap-2 disabled:opacity-40",
                  aiEnabled ? "text-amber-600 hover:bg-amber-50" : "text-emerald-600 hover:bg-emerald-50"
                )}
              >
                {aiEnabled ? <PowerOff size={13} /> : <Power size={13} />}
                {toggling ? "Updating…" : aiEnabled ? "Pause AI" : "Resume AI"}
              </button>
              {!converted && (
                <button
                  onClick={() => { setDropdownOpen(false); markConverted(); }}
                  disabled={converting}
                  className="w-full text-left px-4 py-2 text-[13px] font-medium text-primary hover:bg-primary/5 transition-colors flex items-center gap-2 disabled:opacity-40"
                >
                  <CheckCircle2 size={13} /> {converting ? "Saving…" : "Mark Converted"}
                </button>
              )}
              <div className="border-t border-surface-mid my-1" />
              <button
                onClick={() => { setDropdownOpen(false); clearChat(); }}
                disabled={clearing}
                className="w-full text-left px-4 py-2 text-[13px] font-medium text-orange-600 hover:bg-orange-50 transition-colors flex items-center gap-2 disabled:opacity-40"
              >
                <Eraser size={13} /> {clearing ? "Clearing…" : "Clear Chat"}
              </button>
              <button
                onClick={() => { setDropdownOpen(false); deleteConversation(); }}
                disabled={deleting}
                className="w-full text-left px-4 py-2 text-[13px] font-medium text-red-600 hover:bg-red-50 transition-colors flex items-center gap-2 disabled:opacity-40"
              >
                <Trash2 size={13} /> {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-4 md:px-6 space-y-3 bg-background">
        {loading ? (
          <div className="flex items-center justify-center h-full text-on-surface-muted font-body text-sm">
            Loading messages…
          </div>
        ) : messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-on-surface-muted font-body text-sm">
            No messages yet
          </div>
        ) : (
          messages.map((msg, i) => {
            const prev = messages[i - 1];
            const showDivider = !prev || !isSameDay(new Date(msg.created_at), new Date(prev.created_at));
            return (
              <Fragment key={msg.id}>
                {showDivider && <DateDivider dateStr={msg.created_at} />}
                <MessageBubble msg={msg} />
              </Fragment>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-surface-mid bg-surface px-3 py-3 md:px-4">
        {outsideWindow && isWhatsApp && (
          <div className="mb-2 flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-800">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            <p className="font-label text-[11px] leading-snug">
              Outside 24-hour window{lastInbound ? ` (last inbound ${Math.round(hoursSinceInbound)}h ago)` : ""}. Only approved templates go through reliably.
            </p>
          </div>
        )}
        {!aiEnabled && (
          <p className="font-label text-[11px] text-amber-700 mb-2">
            AI is paused — your replies go directly to the lead.
          </p>
        )}

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.png,.jpg,.jpeg,.webp,.mp3,.ogg,.wav,.aac,.amr,.mp4,.3gp,audio/webm"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) setSelectedFile(f);
            e.target.value = "";
          }}
        />

        {selectedFile ? (
          /* File preview + send */
          <div className="space-y-2">
            <FilePreview file={selectedFile} onRemove={() => { setSelectedFile(null); setFileCaption(""); }} />
            <div className="flex items-center gap-2 bg-surface-low border border-surface-mid rounded-2xl px-4 py-2">
              <input
                value={fileCaption}
                onChange={(e) => setFileCaption(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") sendMedia(); }}
                placeholder="Add a caption (optional)…"
                disabled={sending}
                className="flex-1 bg-transparent font-body text-sm focus:outline-none disabled:opacity-50"
              />
              <button
                onClick={sendMedia}
                disabled={sending}
                className="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center shrink-0 hover:bg-primary/90 disabled:opacity-40 transition-colors"
              >
                <Send size={14} />
              </button>
            </div>
          </div>
        ) : (
          /* Main input bar */
          <div className="flex items-center gap-2 bg-surface-low border border-surface-mid rounded-2xl px-3 py-2 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15 transition-all">
            {canSendMedia ? (
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isRecording}
                title="Attach file"
                className="p-1 text-on-surface-muted hover:text-primary transition-colors disabled:opacity-40 shrink-0"
              >
                <Plus size={18} />
              </button>
            ) : (
              <div className="w-1" />
            )}

            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendReply(); }
              }}
              rows={1}
              disabled={!canReplyToConversations || sending || isRecording}
              placeholder={canReplyToConversations ? (isRecording ? "Recording… tap 🔴 to stop" : "Type a message…") : "Read-only conversation"}
              className="flex-1 bg-transparent font-body text-[13.5px] resize-none focus:outline-none disabled:opacity-50 max-h-28 leading-relaxed"
              style={{ minHeight: "24px" }}
              onInput={(e) => {
                const t = e.currentTarget;
                t.style.height = "auto";
                t.style.height = `${Math.min(t.scrollHeight, 112)}px`;
              }}
            />

            {canSendMedia && (
              <button
                onClick={isRecording ? stopRecording : startRecording}
                title={isRecording ? "Stop recording" : "Voice note"}
                className={cn(
                  "p-1.5 rounded-full transition-colors shrink-0",
                  isRecording ? "text-red-600 bg-red-50 animate-pulse" : "text-on-surface-muted hover:text-primary"
                )}
              >
                {isRecording ? <MicOff size={16} /> : <Mic size={16} />}
              </button>
            )}

            <button
              onClick={sendReply}
              disabled={!canReplyToConversations || sending || !draft.trim() || isRecording}
              title={canReplyToConversations ? "Send message" : "You have read-only access to conversations"}
              className="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center shrink-0 hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
            >
              <Send size={13} />
            </button>
          </div>
        )}

        {sendError && <p className="mt-2 font-label text-xs text-red-600">{sendError}</p>}
      </div>
    </div>
  );
}
