"use client";
import { useState } from "react";
import { ChevronDown, ChevronUp, Pencil, Pin, Trash2, User } from "lucide-react";
import { formatPhone, formatDateTime } from "@/lib/utils";
import type { NoteWithLead } from "@/lib/api";
import type { Note } from "@/app/dashboard/telecalling/types";
import { cardBgFor, splitNoteContent, SEGMENT_COLORS, SEGMENT_LABELS, TagChip, TagSelector } from "./shared";

interface NoteCardProps {
  note: Note | NoteWithLead;
  view: "grid" | "list";
  showLead?: boolean;
  isEditing: boolean;
  editContent: string;
  editPinned: boolean;
  editTags: string[];
  saving: boolean;
  onStartEdit: () => void;
  onContentChange: (v: string) => void;
  onPinnedChange: (v: boolean) => void;
  onTagsChange: (tags: string[]) => void;
  onSave: () => void;
  onCancel: () => void;
  onDelete: () => void;
  onLeadClick?: () => void;
}

function LeadBadge({ note, onClick }: { note: NoteWithLead; onClick?: () => void }) {
  const lead = note.leads;
  if (!lead) return null;
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick?.(); }}
      className="flex items-center gap-1.5 min-w-0 hover:opacity-80 transition-opacity"
    >
      <div className="w-5 h-5 rounded-full bg-primary text-white flex items-center justify-center font-display text-[9px] font-bold shrink-0">
        {lead.name ? lead.name.charAt(0).toUpperCase() : <User size={9} />}
      </div>
      <span className="font-label text-xs font-bold text-[#44403c] truncate">
        {lead.name || formatPhone(lead.phone)}
      </span>
      <span className={`px-1.5 py-0.5 rounded font-label text-[8px] font-black uppercase shrink-0 ${SEGMENT_COLORS[lead.segment]}`}>
        {SEGMENT_LABELS[lead.segment] ?? lead.segment}
      </span>
    </button>
  );
}

export default function NoteCard({
  note, view, showLead, isEditing,
  editContent, editPinned, editTags, saving,
  onStartEdit, onContentChange, onPinnedChange, onTagsChange, onSave, onCancel, onDelete, onLeadClick,
}: NoteCardProps) {
  const cardBg = cardBgFor(note);
  const hasLead = showLead && "leads" in note && note.leads;
  const { title, body } = splitNoteContent(note.content);
  const [expanded, setExpanded] = useState(false);

  if (isEditing) {
    return (
      <div className={`rounded-2xl border p-4 ${view === "grid" ? "break-inside-avoid mb-4" : "mb-2"} ${cardBg}`}>
        <textarea
          value={editContent}
          onChange={(e) => onContentChange(e.target.value)}
          rows={3}
          autoFocus
          className="w-full px-3 py-2 rounded-lg bg-white border border-[#e8e3db] font-body text-sm focus:outline-none focus:ring-2 focus:ring-primary resize-none"
        />
        <div className="flex items-center justify-between gap-2 flex-wrap mt-2">
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 cursor-pointer select-none">
              <input type="checkbox" checked={editPinned} onChange={(e) => onPinnedChange(e.target.checked)} className="rounded" />
              <span className="font-label text-xs text-[#78716c]">Pinned</span>
            </label>
            <TagSelector selected={editTags} onChange={onTagsChange} />
          </div>
          <div className="flex gap-2">
            <button onClick={onSave} disabled={saving}
              className="px-3 py-1.5 bg-primary text-white rounded-lg font-label text-xs font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors">
              {saving ? "Saving…" : "Save"}
            </button>
            <button onClick={onCancel}
              className="px-3 py-1.5 bg-white border border-[#e8e3db] rounded-lg font-label text-xs font-semibold hover:bg-[#faf8f5] transition-colors">
              Cancel
            </button>
          </div>
        </div>
        {editTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {editTags.map((t) => <TagChip key={t} label={t} onRemove={() => onTagsChange(editTags.filter((x) => x !== t))} />)}
          </div>
        )}
      </div>
    );
  }

  if (view === "list") {
    return (
      <div className={`rounded-xl border p-3 transition-all hover:shadow-sm group ${cardBg}`}>
        <div className="flex items-center gap-3">
          {note.is_pinned && <Pin size={12} className="text-amber-500 fill-amber-400 shrink-0" />}
          {hasLead && (
            <div className="w-40 shrink-0">
              <LeadBadge note={note as NoteWithLead} onClick={onLeadClick} />
            </div>
          )}
          {title ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="flex-1 min-w-0 flex items-center gap-1.5 text-left"
            >
              <p className="flex-1 min-w-0 font-body text-sm font-bold text-[#292524] truncate">{title}</p>
              {expanded ? <ChevronUp size={12} className="text-[#a8a29e] shrink-0" /> : <ChevronDown size={12} className="text-[#a8a29e] shrink-0" />}
            </button>
          ) : (
            <p className="flex-1 min-w-0 font-body text-sm text-[#44403c] truncate">{note.content}</p>
          )}
          <div className="flex items-center gap-1.5 shrink-0">
            {(note.tags ?? []).slice(0, 2).map((t) => <TagChip key={t} label={t} />)}
          </div>
          <span className="font-label text-[10px] text-[#a8a29e] shrink-0">{formatDateTime(note.created_at)}</span>
          <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onClick={onStartEdit} className="p-1.5 rounded-lg hover:bg-white transition-colors text-[#a8a29e] hover:text-[#44403c]">
              <Pencil size={12} />
            </button>
            <button onClick={onDelete} className="p-1.5 rounded-lg hover:bg-red-50 transition-colors text-[#a8a29e] hover:text-red-500">
              <Trash2 size={12} />
            </button>
          </div>
        </div>
        {title && expanded && (
          <p className="mt-2 pt-2 border-t border-black/5 font-body text-xs text-[#57534e] whitespace-pre-wrap">{body || "—"}</p>
        )}
      </div>
    );
  }

  // grid card
  return (
    <div className={`rounded-2xl border p-4 break-inside-avoid mb-4 transition-all hover:shadow-md group ${cardBg}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        {hasLead ? <LeadBadge note={note as NoteWithLead} onClick={onLeadClick} /> : <span />}
        {note.is_pinned && <Pin size={12} className="text-amber-500 fill-amber-400 shrink-0" />}
      </div>
      {title ? (
        <>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5 w-full text-left"
          >
            <p className="flex-1 min-w-0 font-body text-sm font-bold text-[#292524] truncate">{title}</p>
            {expanded ? <ChevronUp size={12} className="text-[#a8a29e] shrink-0" /> : <ChevronDown size={12} className="text-[#a8a29e] shrink-0" />}
          </button>
          {expanded && (
            <p className="font-body text-sm text-[#44403c] whitespace-pre-wrap line-clamp-6 mt-1.5">{body || "—"}</p>
          )}
        </>
      ) : (
        <p className="font-body text-sm text-[#44403c] whitespace-pre-wrap line-clamp-6">{note.content}</p>
      )}
      {(note.tags ?? []).length > 0 && (
        <div className="flex items-center gap-1.5 mt-3 flex-wrap">
          {(note.tags ?? []).map((t) => <TagChip key={t} label={t} />)}
        </div>
      )}
      <div className="flex items-center justify-between mt-3 pt-2 border-t border-black/5">
        <span className="font-label text-[10px] text-[#a8a29e]">{formatDateTime(note.created_at)}</span>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={onStartEdit} className="p-1.5 rounded-lg hover:bg-white transition-colors text-[#a8a29e] hover:text-[#44403c]">
            <Pencil size={12} />
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-lg hover:bg-red-50 transition-colors text-[#a8a29e] hover:text-red-500">
            <Trash2 size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
