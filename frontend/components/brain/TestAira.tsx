"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Loader2, RotateCcw, Send } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SectionCard } from "./SectionCard";
import {
  INITIAL_SANDBOX_STATE,
  MAX_MESSAGE_CHARS,
  canSend,
  isWindowed,
  messageForStatus,
  parseSandboxReply,
  resetState,
  toRequestMessages,
  withReply,
  withUserTurn,
  withoutFailedTurn,
  type SandboxReply,
  type SandboxState,
} from "./testAiraLogic";

interface TestAiraProps {
  /** Server path of the sandbox route: the client route, or the operator route for one client. */
  endpoint: string;
  /** False for a user without knowledge.manage. The box stays visible but disabled. */
  canUse: boolean;
  /** Shown as the inline reason when canUse is false. */
  disabledReason?: string;
  /** Pre-fills the composer when opening Test Aira from another surface. */
  initialQuestion?: string;
  /** Offers the latest unmatched customer question to a knowledge editor. */
  onAddAnswer?: (question: string) => void;
  /** Adds the card title and border when this is not already inside a titled panel. */
  standalone?: boolean;
}

class SandboxRequestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SandboxRequestError";
  }
}

async function askAira(endpoint: string, state: SandboxState): Promise<SandboxReply> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(await getAuthHeaders()) },
      body: JSON.stringify({ messages: toRequestMessages(state.turns) }),
    });
  } catch {
    throw new SandboxRequestError(messageForStatus(null));
  }
  if (!res.ok) throw new SandboxRequestError(messageForStatus(res.status));
  const reply = parseSandboxReply(await res.json().catch(() => null));
  if (!reply) throw new SandboxRequestError(messageForStatus(500));
  return reply;
}

const BUBBLE_BASE = "max-w-[85%] min-w-0 break-words whitespace-pre-wrap rounded-2xl px-3 py-2 font-body text-sm";
const ICON_BUTTON_CLASS =
  "inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl px-4 font-label text-sm font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-50";
const SUGGESTED_QUESTIONS = [
  "What are your business hours?",
  "How much does it cost?",
  "How can I buy it?",
  "Can I speak to a person?",
] as const;

export function TestAira({
  endpoint,
  canUse,
  disabledReason,
  initialQuestion = "",
  onAddAnswer,
  standalone = false,
}: TestAiraProps) {
  const [chat, setChat] = useState<SandboxState>(INITIAL_SANDBOX_STATE);
  const [draft, setDraft] = useState(initialQuestion);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(chat);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const lastInitialQuestion = useRef(initialQuestion);
  const reasonId = useId();
  const noteId = useId();
  const isPending = pendingId !== null;

  useEffect(() => {
    if (lastInitialQuestion.current !== initialQuestion) {
      lastInitialQuestion.current = initialQuestion;
      setDraft(initialQuestion);
    }
  }, [initialQuestion]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript) transcript.scrollTop = transcript.scrollHeight;
  }, [chat.turns, isPending]);

  function update(next: SandboxState): void {
    latest.current = next;
    setChat(next);
  }

  async function send(message = draft): Promise<void> {
    if (!canSend(message, isPending, canUse)) return;
    const text = message.trim();
    const sent = withUserTurn(latest.current, text);
    update(sent);
    setDraft("");
    setError(null);
    setPendingId(sent.requestId);
    try {
      const reply = await askAira(endpoint, sent);
      update(withReply(latest.current, sent.requestId, reply));
    } catch (e) {
      if (latest.current.requestId !== sent.requestId) return;
      update(withoutFailedTurn(latest.current, sent.requestId));
      setDraft(text);
      setError(e instanceof Error ? e.message : messageForStatus(500));
    } finally {
      setPendingId((current) => (current === sent.requestId ? null : current));
    }
  }

  function reset(): void {
    update(resetState(latest.current));
    setDraft("");
    setError(null);
    setPendingId(null);
  }

  const content = (
    <>
      <p id={noteId} className="rounded-xl bg-surface-low px-3 py-2 font-body text-xs text-ink-secondary">
        Answers only. This test cannot take payments, make bookings, contact a person, or send messages. Nothing is saved.
        {isWindowed(chat.turns) && " Aira only remembers the latest 20 messages of this test."}
      </p>

      <div className="mt-3 flex flex-wrap gap-2" aria-label="Suggested questions">
        {SUGGESTED_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            disabled={!canUse}
            onClick={() => setDraft(question)}
            className="min-h-10 rounded-full border border-border bg-white px-3 py-1.5 font-label text-xs font-semibold text-ink-secondary transition hover:border-primary/40 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {question}
          </button>
        ))}
      </div>

      <div
        ref={transcriptRef}
        className="mt-3 flex min-h-24 max-h-[clamp(6rem,calc(65dvh-20rem),18rem)] flex-col gap-2 overflow-y-auto overscroll-contain rounded-xl border border-border-subtle bg-white p-3"
        aria-live="polite"
      >
        {chat.turns.length === 0 && (
          <p className="font-body text-sm text-ink-muted">No messages yet. Try &ldquo;What are your timings?&rdquo;</p>
        )}
        {chat.turns.map((turn, index) => {
          const unmatchedQuestion =
            index === chat.turns.length - 1 && turn.role === "assistant"
              ? [...chat.turns.slice(0, index)].reverse().find((candidate) => candidate.role === "user")?.content
              : undefined;
          return (
            <div key={index} className={cn("flex flex-col gap-1", turn.role === "user" ? "items-end" : "items-start")}>
              <div className={cn(BUBBLE_BASE, turn.role === "user" ? "bg-primary text-white" : "border border-border bg-surface-low text-ink")}>
                {turn.content}
              </div>
              {turn.role === "assistant" && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-label text-[10px] text-ink-muted">
                    {turn.knowledgeUsed ? "Matched uploaded knowledge" : "No uploaded knowledge matched; business settings may still inform this answer"}
                  </span>
                  {unmatchedQuestion && onAddAnswer && (
                    <button
                      type="button"
                      onClick={() => onAddAnswer(unmatchedQuestion)}
                      className="font-label text-[10px] font-bold text-primary hover:underline"
                    >
                      Improve this answer
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {isPending && (
          <p className="flex items-center gap-1.5 font-body text-xs text-ink-secondary" role="status">
            <Loader2 size={12} className="animate-spin" aria-hidden /> Aira is typing
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-3 rounded-xl border border-rose-200 bg-rose-50/60 px-3 py-2 font-body text-sm text-ink">
          {error}
        </p>
      )}

      <form
        className="mt-3 flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <label htmlFor={`${reasonId}-input`} className="sr-only">
          Message to Aira
        </label>
        <textarea
          id={`${reasonId}-input`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          rows={2}
          maxLength={MAX_MESSAGE_CHARS}
          disabled={!canUse}
          aria-describedby={canUse ? noteId : reasonId}
          placeholder="Type a customer message"
          className="w-full resize-none rounded-xl border border-border bg-white px-3 py-2 font-body text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:bg-surface-mid disabled:opacity-60"
        />
        {draft.length > MAX_MESSAGE_CHARS && <p role="status" className="font-body text-xs text-warning">Shorten this question to {MAX_MESSAGE_CHARS} characters before sending ({draft.length} entered).</p>}
        {!canUse && (
          <p id={reasonId} className="font-body text-xs text-ink-secondary">
            {disabledReason}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={!canSend(draft, isPending, canUse)}
            aria-describedby={canUse ? undefined : reasonId}
            className={cn(ICON_BUTTON_CLASS, "bg-primary text-white hover:bg-primary-dark")}
          >
            <Send size={14} aria-hidden /> Send
          </button>
          <button
            type="button"
            onClick={reset}
            disabled={chat.turns.length === 0 && !isPending && draft === "" && error === null}
            className={cn(ICON_BUTTON_CLASS, "border border-border bg-white text-ink hover:border-primary/40")}
          >
            <RotateCcw size={14} aria-hidden /> Reset
          </button>
        </div>
      </form>
    </>
  );

  if (!standalone) return <div className="min-w-0">{content}</div>;

  return (
    <SectionCard title="Customer conversation" subtitle="Ask a question the way a customer would and see how Aira answers from what you've told it.">
      {content}
    </SectionCard>
  );
}
