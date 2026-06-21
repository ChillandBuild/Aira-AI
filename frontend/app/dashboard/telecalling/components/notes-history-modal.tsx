"use client";
import { useEffect, useState } from "react";
import { X, Pin, FileText } from "lucide-react";
import { timeAgo } from "@/lib/utils";
import type { Lead } from "@/lib/api";
import type { Note } from "../types";
import { fetchAllNotes } from "../lib/notes-api";

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
  onClose: () => void;
};

export default function NotesHistoryModal({ lead, onClose }: Props) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAllNotes(lead.id)
      .then(setNotes)
      .catch(() => setNotes([]))
      .finally(() => setLoading(false));
  }, [lead.id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-surface rounded-card p-8 shadow-card w-full max-w-lg ring-1 ring-[#c4c7c7]/20 max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between mb-4 shrink-0">
          <div>
            <h2 className="font-display text-lg font-bold text-primary">All Notes</h2>
            <p className="font-label text-xs text-on-surface-muted mt-0.5">
              {lead.name || "Unnamed"} · {notes.length} note{notes.length !== 1 ? "s" : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-surface-low transition-colors text-on-surface-muted"
          >
            <X size={16} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 space-y-3 pr-1">
          {loading && (
            <p className="font-body text-sm text-on-surface-muted">Loading…</p>
          )}
          {!loading && notes.length === 0 && (
            <p className="font-body text-sm text-on-surface-muted">No notes yet for this lead.</p>
          )}
          {notes.map((note) => (
            <div key={note.id} className="p-4 bg-surface-low rounded-xl">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="font-label text-[10px] text-on-surface-muted">
                  {timeAgo(note.created_at)}
                </span>
                {note.is_pinned && (
                  <span className="flex items-center gap-0.5 font-label text-[10px] text-secondary font-semibold">
                    <Pin size={9} />
                    Pinned
                  </span>
                )}
                {note.call_log_id && (
                  <span className="flex items-center gap-0.5 font-label text-[10px] text-on-surface-muted">
                    <FileText size={9} />
                    Post-call
                  </span>
                )}
              </div>
              <p className="font-body text-sm text-on-surface">{note.content}</p>
              <StructuredFields data={note.structured} />
            </div>
          ))}
        </div>

        <div className="mt-4 shrink-0">
          <button
            onClick={onClose}
            className="w-full py-2.5 bg-surface border border-surface-mid rounded-lg font-label text-sm font-semibold hover:bg-surface-low transition-colors text-on-surface"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
