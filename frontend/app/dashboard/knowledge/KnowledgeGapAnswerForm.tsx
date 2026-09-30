"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, BookOpen, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

interface KnowledgeGapAnswerFormProps {
  question: string;
  uploadedDocumentId?: string | null;
  canManage: boolean;
  onUploaded: () => Promise<void> | void;
}

export default function KnowledgeGapAnswerForm({ question, uploadedDocumentId, canManage, onUploaded }: KnowledgeGapAnswerFormProps) {
  const [answer, setAnswer] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(uploadedDocumentId ?? null);
  const [uploaded, setUploaded] = useState(Boolean(uploadedDocumentId));
  const answerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!uploaded) answerRef.current?.focus();
  }, [uploaded]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanAnswer = answer.trim();
    if (!canManage || !cleanAnswer || uploading) return;

    setUploading(true);
    setError(null);
    try {
      const body = `Question\n${question.trim()}\n\nAnswer\n${cleanAnswer}\n`;
      const file = new File([body], `answer-${Date.now()}.txt`, { type: "text/plain" });
      const uploaded = (await api.knowledge.uploadDocument(file, null, null)) as { id?: string };
      setDocumentId(uploaded.id ?? null);
      setUploaded(true);
      try {
        await onUploaded();
      } catch {
        // The upload already succeeded; a list refresh can recover on the next poll or visit.
      }
    } catch (cause) {
      setError(cause instanceof Error && cause.message ? cause.message : "Could not add this answer. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  const retestHref = `/dashboard/brain?section=test&question=${encodeURIComponent(question)}`;

  return (
    <section className="rounded-2xl border border-primary/25 bg-primary/[0.03] p-4 shadow-sm sm:p-5" aria-labelledby="knowledge-gap-title">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <BookOpen size={19} aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <h2 id="knowledge-gap-title" className="font-display text-base font-bold text-on-surface">Add the missing answer</h2>
          <p className="mt-1 font-body text-xs text-on-surface-muted">
            This creates a knowledge document. Aira will sort it, and it must be reviewed before the answer becomes active.
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-surface-mid bg-white p-3">
        <p className="font-label text-[11px] font-bold uppercase tracking-wide text-on-surface-muted">Customer question</p>
        <p className="mt-1 break-words font-body text-sm text-on-surface">{question}</p>
      </div>

      {uploaded ? (
        <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
          <p className="font-display text-sm font-bold text-emerald-800">Answer added and sent for sorting</p>
          <p className="mt-1 font-body text-xs text-emerald-800/80">Review and approve the sorted document before testing the answer.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {documentId && (
              <Link
                href={`/dashboard/knowledge?tab=documents&status=review&review=${encodeURIComponent(documentId)}&uploaded=${encodeURIComponent(documentId)}&question=${encodeURIComponent(question)}`}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-primary px-3 font-label text-xs font-bold text-white hover:bg-primary/90"
              >
                Review this answer <ArrowRight size={13} aria-hidden />
              </Link>
            )}
            <Link href="/dashboard/brain?section=approvals" className="inline-flex min-h-9 items-center rounded-lg border border-surface-mid bg-white px-3 font-label text-xs font-bold text-on-surface hover:border-primary/40">All approvals</Link>
            <Link href={retestHref} className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-surface-mid bg-white px-3 font-label text-xs font-bold text-on-surface hover:border-primary/40">
              Return to Test Aira
            </Link>
          </div>
        </div>
      ) : (
        <form className="mt-4" onSubmit={submit}>
          <label htmlFor="knowledge-gap-answer" className="font-label text-xs font-bold text-on-surface">Answer</label>
          <textarea
            ref={answerRef}
            id="knowledge-gap-answer"
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            rows={5}
            maxLength={12000}
            disabled={!canManage || uploading}
            placeholder="Write the answer Aira should learn"
            className="mt-1.5 w-full resize-y rounded-xl border border-surface-mid bg-white px-3 py-2 font-body text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:bg-surface-mid disabled:opacity-60"
          />
          {!canManage && <p className="mt-2 font-body text-xs text-on-surface-muted">You need knowledge management access to add an answer.</p>}
          {error && <p role="alert" className="mt-2 font-body text-xs text-danger">{error}</p>}
          <button
            type="submit"
            disabled={!canManage || !answer.trim() || uploading}
            className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-xl bg-primary px-4 font-label text-sm font-bold text-white hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <BookOpen size={15} aria-hidden />}
            {uploading ? "Adding answer…" : "Add answer for review"}
          </button>
        </form>
      )}
    </section>
  );
}
