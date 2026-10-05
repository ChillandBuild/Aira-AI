"use client";
import { useCallback, useEffect, useState } from "react";
import { Clock, Pencil, Plus, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type AutoMessageEvent,
  type AutoMessageRule,
  type AutoMessageTemplate,
} from "@/lib/api";
import { SwitchPill } from "@/components/ui/controls";
import { EVENTS, delayLabel, ghostBtn } from "./shared";
import { RuleEditor } from "./RuleEditor";

type Editing = { event: AutoMessageEvent; rule: AutoMessageRule | null } | null;

export function MessagesTab({ canManage }: { canManage: boolean }) {
  const [rules, setRules] = useState<AutoMessageRule[] | null>(null);
  const [templates, setTemplates] = useState<AutoMessageTemplate[]>([]);
  const [editing, setEditing] = useState<Editing>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, t] = await Promise.all([api.autoMessages.rules(), api.autoMessages.templates()]);
      setRules(r.rules);
      setTemplates(t.templates);
    } catch (err) {
      setRules([]);
      toast.error(err instanceof Error ? err.message : "Couldn't load your messages");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(rule: AutoMessageRule, enabled: boolean) {
    setBusy(rule.id);
    try {
      const updated = await api.autoMessages.updateRule(rule.id, { enabled });
      setRules((rs) => (rs ?? []).map((r) => (r.id === rule.id ? updated : r)));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't change it");
    } finally {
      setBusy(null);
    }
  }

  async function remove(rule: AutoMessageRule) {
    if (!window.confirm("Delete this message? People will stop getting it right away.")) return;
    setBusy(rule.id);
    try {
      await api.autoMessages.deleteRule(rule.id);
      setRules((rs) => (rs ?? []).filter((r) => r.id !== rule.id));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't delete it");
    } finally {
      setBusy(null);
    }
  }

  if (rules === null) {
    return (
      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-36 animate-pulse rounded-[24px] bg-border-subtle" />
        ))}
      </div>
    );
  }

  const templateName = (id: string) => templates.find((t) => t.id === id)?.name ?? "Template no longer approved";

  return (
    <div className="space-y-5">
      {EVENTS.map((ev) => {
        const r = rules.find((x) => x.event === ev.id);
        return (
          <section key={ev.id} className="rounded-[24px] border border-border-subtle bg-white p-5 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-display text-base font-bold text-ink">{ev.label}</h3>
                <p className="mt-0.5 font-body text-xs text-ink-secondary">{ev.when}</p>
              </div>
              {canManage && !r && (
                <button type="button" onClick={() => setEditing({ event: ev.id, rule: null })} className={ghostBtn}>
                  <Plus size={13} /> Add message
                </button>
              )}
            </div>

            {!r ? (
              <div className="mt-4 rounded-2xl border border-dashed border-border bg-surface-subtle px-4 py-5 text-center">
                <p className="font-body text-sm text-ink-secondary">No message yet. {ev.nobody}</p>
                <p className="mt-1 font-body text-xs text-ink-muted">{ev.hint}</p>
              </div>
            ) : (
              <div
                className={`mt-4 flex flex-wrap items-center gap-3 overflow-hidden rounded-2xl border border-border-subtle px-4 py-3 ${
                  r.enabled ? "bg-white" : "bg-surface-subtle"
                }`}
              >
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                      r.enabled ? "bg-primary/10 text-primary" : "bg-surface-mid text-ink-secondary"
                    }`}
                  >
                    <Zap size={16} />
                  </span>
                  <div className="min-w-0">
                    <p className={`truncate font-mono text-[13px] font-semibold ${r.enabled ? "text-ink" : "text-ink-muted"}`}>
                      {templateName(r.template_id)}
                    </p>
                    <p className="inline-flex items-center gap-1 font-body text-xs text-ink-muted">
                      <Clock size={11} /> {delayLabel(r.delay_minutes)}
                      {!r.enabled && " · off"}
                    </p>
                  </div>
                </div>
                {canManage && (
                  <div className="flex items-center gap-1">
                    <SwitchPill
                      size="sm"
                      on={r.enabled}
                      loading={busy === r.id}
                      onChange={(next) => toggle(r, next)}
                      aria-label={r.enabled ? "Turn off" : "Turn on"}
                    />
                    <button
                      type="button"
                      onClick={() => setEditing({ event: ev.id, rule: r })}
                      aria-label="Edit"
                      className="ml-1 rounded-lg p-2 text-ink-muted hover:bg-surface-subtle hover:text-ink"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(r)}
                      disabled={busy === r.id}
                      aria-label="Delete"
                      className="rounded-lg p-2 text-ink-muted hover:bg-rose-50 hover:text-rose-600 disabled:opacity-40"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </div>
            )}
          </section>
        );
      })}

      {editing && (
        <RuleEditor
          event={editing.event}
          rule={editing.rule}
          templates={templates}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}
