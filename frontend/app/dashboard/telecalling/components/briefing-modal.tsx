"use client";
import { Phone, X, Pin, FileText, BookOpen } from "lucide-react";
import { formatPhone, timeAgo } from "@/lib/utils";
import type { Lead } from "@/lib/api";
import type { NotesResponse, Note } from "../types";

const BRIEFING_TAGS = [
  "Schedule callback",
  "Send pricing",
  "Send proposal",
  "Follow up",
];

function StructuredFields({ data }: { data: Note["structured"] }) {
  const entries = Object.entries(data).filter(([, v]) => v);
  if (!entries.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
      {entries.map(([k, v]) => (
        <span key={k} className="font-label text-[10px] text-on-surface-muted">
          <span className="font-semibold capitalize">{k.replace("_", " ")}:</span> {v}
        </span>
      ))}
    </div>
  );
}

type Props = {
  lead: Lead;
  notes: NotesResponse | null;
  loading: boolean;
  dialing: boolean;
  viewOnly?: boolean;
  onStartCall: () => void;
  onClose: () => void;
  onViewAllNotes: () => void;
};

export default function BriefingModal({
  lead,
  notes,
  loading,
  dialing,
  viewOnly = false,
  onStartCall,
  onClose,
  onViewAllNotes,
}: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-surface rounded-card p-8 shadow-card w-full max-w-md ring-1 ring-[#c4c7c7]/20 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-display text-lg font-bold text-primary">
            {viewOnly ? "Lead Notes" : "Pre-Call Briefing"}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-surface-low transition-colors text-on-surface-muted"
          >
            <X size={16} />
          </button>
        </div>

        <div className="mb-5">
          <p className="font-body text-base font-semibold text-on-surface">
            {lead.name || "Unnamed lead"}
          </p>
          <p className="font-label text-sm text-on-surface-muted mt-0.5">
            {formatPhone(lead.phone)} · Score {lead.score} · Segment {lead.segment}
          </p>
        </div>

        {loading ? (
          <p className="font-body text-sm text-on-surface-muted mb-5">Loading notes…</p>
        ) : notes ? (
          <>
            {notes.pinned.length > 0 && (
              <div className="mb-5">
                <h3 className="font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wide mb-2 flex items-center gap-1.5">
                  <Pin size={11} />
                  Pinned Facts
                </h3>
                <div className="space-y-2">
                  {notes.pinned.map((note) => (
                    <div key={note.id} className="p-3 bg-surface-low rounded-xl">
                      <p className="font-body text-sm text-on-surface">{note.content}</p>
                      <StructuredFields data={note.structured} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {notes.notes.length > 0 && (
              <div className="mb-5">
                <h3 className="font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wide mb-2 flex items-center gap-1.5">
                  <FileText size={11} />
                  Last 3 Interactions
                </h3>
                <div className="space-y-2">
                  {notes.notes.slice(0, 3).map((note) => (
                    <div key={note.id} className="p-3 bg-surface-low rounded-xl">
                      <p className="font-label text-[10px] text-on-surface-muted mb-1">
                        {timeAgo(note.created_at)}
                      </p>
                      <p className="font-body text-sm text-on-surface line-clamp-2">{note.content}</p>
                    </div>
                  ))}
                </div>

                <button
                  onClick={onViewAllNotes}
                  className="mt-2 flex items-center gap-1 font-label text-xs text-primary hover:underline"
                >
                  <BookOpen size={11} />
                  See all notes
                </button>
              </div>
            )}

            {notes.pinned.length === 0 && notes.notes.length === 0 && (
              <p className="font-body text-sm text-on-surface-muted mb-5">No previous notes for this lead.</p>
            )}
          </>
        ) : null}

        {!viewOnly && (
          <div className="mb-6">
            <h3 className="font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wide mb-2">
              Suggested Next Steps
            </h3>
            <div className="flex flex-wrap gap-2">
              {BRIEFING_TAGS.map((tag) => (
                <span
                  key={tag}
                  className="px-2.5 py-1 bg-tertiary-bg text-primary rounded-full font-label text-xs font-semibold"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-3">
          {!viewOnly && (
            <button
              onClick={onStartCall}
              disabled={dialing}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-primary text-white rounded-lg font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Phone size={14} />
              {dialing ? "Dialing…" : "Start Call"}
            </button>
          )}
          <button
            onClick={onClose}
            className="flex-1 py-2.5 bg-surface border border-surface-mid rounded-lg font-label text-sm font-semibold hover:bg-surface-low transition-colors text-on-surface"
          >
            {viewOnly ? "Close" : "Cancel"}
          </button>
        </div>
      </div>
    </div>
  );
}
