"use client";
import { useCallback, useEffect, useState } from "react";
import { MessageSquareMore, Plus, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SettingsSection } from "./SettingsSection";
import { CheckField } from "@/components/ui/controls";

// Mirrors BUTTON_TITLE_MAX / BUTTON_COUNT_MAX in backend/app/services/meta_cloud.py
// and BODY_TEXT_MAX / MAX_BLOCKS_PER_TENANT in app/services/quick_replies.py.
const BUTTON_LABEL_MAX = 20;
const BUTTON_COUNT_MAX = 3;
const BODY_TEXT_MAX = 1024;
const MAX_BLOCKS = 10;

interface QuickReplyButton {
  id?: string;
  label: string;
}

interface QuickReplyBlock {
  id?: string;
  name: string;
  use_when: string;
  body_text: string;
  buttons: QuickReplyButton[];
  is_active: boolean;
}

const EMPTY_BLOCK: QuickReplyBlock = {
  name: "",
  use_when: "",
  body_text: "",
  buttons: [{ label: "" }],
  is_active: true,
};

export function QuickRepliesPanel({ canManage }: { canManage: boolean }) {
  const [blocks, setBlocks] = useState<QuickReplyBlock[]>([]);
  const [draft, setDraft] = useState<QuickReplyBlock | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/quick-replies`, { headers: auth });
      if (res.ok) setBlocks(await res.json());
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const isEdit = Boolean(draft.id);
      const res = await fetch(
        `${API_URL}/api/v1/quick-replies${isEdit ? `/${draft.id}` : ""}`,
        {
          method: isEdit ? "PATCH" : "POST",
          headers: { ...auth, "Content-Type": "application/json" },
          body: JSON.stringify(draft),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || "Could not save this block");
        return;
      }
      setDraft(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id?: string) {
    if (!id) return;
    const auth = await getAuthHeaders();
    await fetch(`${API_URL}/api/v1/quick-replies/${id}`, { method: "DELETE", headers: auth });
    await load();
  }

  function patchDraft(patch: Partial<QuickReplyBlock>) {
    setDraft((d) => (d ? { ...d, ...patch } : d));
  }

  function patchButton(index: number, label: string) {
    setDraft((d) => {
      if (!d) return d;
      const buttons = d.buttons.map((b, i) =>
        i === index ? { ...b, label: label.slice(0, BUTTON_LABEL_MAX) } : b,
      );
      return { ...d, buttons };
    });
  }

  return (
    <SettingsSection
      id="quick-replies"
      icon={MessageSquareMore}
      accent="violet"
      title="Quick Reply Buttons"
      description="Save a message with tappable buttons. The AI sends it when a lead asks something matching your description."
      status={{
        label: `${blocks.filter((b) => b.is_active).length} active`,
        tone: blocks.some((b) => b.is_active) ? "on" : "off",
      }}
    >
      <div className="space-y-4">
        {blocks.map((b) => (
          <div
            key={b.id}
            className="rounded-2xl border border-border bg-surface-subtle p-3 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <div className="font-label text-sm font-semibold text-ink">
                {b.name}
                {!b.is_active && (
                  <span className="ml-2 font-body text-xs text-ink-muted">(paused)</span>
                )}
              </div>
              <div className="font-body text-xs text-ink-muted mt-0.5">{b.use_when}</div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {b.buttons.map((btn, i) => (
                  <span
                    key={i}
                    className="px-2 py-0.5 rounded-md border border-border bg-white font-body text-xs text-ink"
                  >
                    {btn.label}
                  </span>
                ))}
              </div>
            </div>
            {canManage && (
              <div className="flex gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => setDraft({ ...b })}
                  className="font-label text-xs text-ink-muted hover:text-ink"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => remove(b.id)}
                  aria-label="Delete block"
                  className="text-ink-muted hover:text-red-600"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            )}
          </div>
        ))}

        {blocks.length === 0 && !draft && (
          <p className="font-body text-xs text-ink-muted italic">
            No blocks yet — add one to let the AI offer tappable choices.
          </p>
        )}

        {canManage && !draft && blocks.length < MAX_BLOCKS && (
          <button
            type="button"
            onClick={() => setDraft({ ...EMPTY_BLOCK })}
            className="inline-flex items-center gap-1.5 font-label text-xs text-ink-muted hover:text-ink"
          >
            <Plus size={14} /> New block
          </button>
        )}

        {canManage && !draft && blocks.length >= MAX_BLOCKS && (
          <p className="font-body text-xs text-ink-muted">
            You have the maximum of {MAX_BLOCKS} blocks. The list is sent to the AI on every
            reply, so a longer one makes matching slower and less accurate.
          </p>
        )}

        {draft && (
          <div className="rounded-2xl border border-border bg-white p-4 space-y-3">
            <input
              type="text"
              value={draft.name}
              onChange={(e) => patchDraft({ name: e.target.value })}
              placeholder="Block name (e.g. Menu options)"
              className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink"
            />

            <div>
              <div className="font-label text-sm font-semibold text-ink mb-1">
                When should the AI send this?
              </div>
              <div className="font-body text-xs text-ink-muted mb-2">
                Describe the kind of question this answers — this is what the AI reads to
                decide. e.g. &quot;Lead asks about food, dishes, or what we serve.&quot;
              </div>
              <textarea
                value={draft.use_when}
                onChange={(e) => patchDraft({ use_when: e.target.value })}
                rows={2}
                className="w-full px-3 py-2 rounded-xl border border-border text-sm font-body text-ink"
              />
            </div>

            <div>
              <div className="font-label text-sm font-semibold text-ink mb-1">Message</div>
              <textarea
                value={draft.body_text}
                onChange={(e) => patchDraft({ body_text: e.target.value.slice(0, BODY_TEXT_MAX) })}
                rows={2}
                placeholder="Sent to the lead exactly as written"
                className="w-full px-3 py-2 rounded-xl border border-border text-sm font-body text-ink"
              />
            </div>

            <div className="space-y-2">
              <div className="font-label text-sm font-semibold text-ink">
                Buttons ({draft.buttons.length}/{BUTTON_COUNT_MAX})
              </div>
              {draft.buttons.map((btn, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={btn.label}
                    onChange={(e) => patchButton(i, e.target.value)}
                    placeholder={`Button ${i + 1}`}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink"
                  />
                  <span
                    className={`font-label text-xs tabular-nums ${
                      btn.label.length >= BUTTON_LABEL_MAX ? "text-red-600" : "text-ink-muted"
                    }`}
                  >
                    {btn.label.length}/{BUTTON_LABEL_MAX}
                  </span>
                  {draft.buttons.length > 1 && (
                    <button
                      type="button"
                      onClick={() =>
                        patchDraft({ buttons: draft.buttons.filter((_, x) => x !== i) })
                      }
                      aria-label="Remove button"
                      className="text-ink-muted hover:text-red-600"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
              {draft.buttons.length < BUTTON_COUNT_MAX && (
                <button
                  type="button"
                  onClick={() => patchDraft({ buttons: [...draft.buttons, { label: "" }] })}
                  className="inline-flex items-center gap-1.5 font-label text-xs text-ink-muted hover:text-ink"
                >
                  <Plus size={14} /> Add button
                </button>
              )}
            </div>

            {/* The preview is the only place the client sees what the lead actually
                gets, and it is what makes the 20-character limit concrete. */}
            <div className="rounded-xl bg-[#e7f7d4] p-3 space-y-2">
              <div className="font-body text-sm text-ink whitespace-pre-wrap">
                {draft.body_text || "Your message will appear here"}
              </div>
              <div className="flex flex-col gap-1">
                {draft.buttons.map((btn, i) => (
                  <div
                    key={i}
                    className="text-center py-1.5 rounded-lg bg-white font-body text-sm text-[#1f7aec]"
                  >
                    {btn.label || `Button ${i + 1}`}
                  </div>
                ))}
              </div>
            </div>

            <CheckField
              checked={draft.is_active}
              onChange={(v) => patchDraft({ is_active: v })}
              label="Active"
              description="Paused blocks are never offered to the AI."
            />

            {error && <p className="font-body text-xs text-red-600">{error}</p>}

            <div className="flex gap-2">
              <button
                type="button"
                onClick={save}
                disabled={busy}
                className="px-3 py-1.5 rounded-lg bg-ink text-white font-label text-xs disabled:opacity-50"
              >
                {busy ? "Saving…" : "Save block"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft(null);
                  setError(null);
                }}
                className="px-3 py-1.5 rounded-lg border border-border font-label text-xs text-ink"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </SettingsSection>
  );
}
