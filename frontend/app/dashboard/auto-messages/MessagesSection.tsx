"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  type AutoMessageCustomEvent,
  type AutoMessageEvents,
  type AutoMessageRule,
  type AutoMessageTemplate,
} from "@/lib/api";
import { AddEventRow } from "./AddEventRow";
import { EventRow, rowId } from "./EventRow";
import { ghostBtn, type EventInfo } from "./shared";

const SAVED_FLASH_MS = 2000;
const NO_TEMPLATE_REASON = "You need an approved WhatsApp template first.";

interface Data {
  events: AutoMessageEvents;
  rules: AutoMessageRule[];
  templates: AutoMessageTemplate[];
}

/** What the owner tried to open while the open row had unsaved edits: a row key, or null for "collapse". */
interface Pending {
  target: string | null;
}

function toInfos(events: AutoMessageEvents): EventInfo[] {
  return [
    ...events.builtin.map((b) => ({ key: b.key, label: b.label, description: b.description, custom: false })),
    ...events.custom.map((c) => ({ key: c.key, label: c.label, description: c.description, custom: true })),
  ];
}

export function MessagesSection({ canManage }: { canManage: boolean }) {
  const [data, setData] = useState<Data | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lostNames, setLostNames] = useState<Record<string, string>>({});
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [switchingKey, setSwitchingKey] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (flashTimer.current) clearTimeout(flashTimer.current);
    },
    []
  );

  const load = useCallback(async (quiet: boolean) => {
    if (!quiet) setLoadError(false);
    try {
      const [events, rules, templates] = await Promise.all([
        api.autoMessages.events(),
        api.autoMessages.rules(),
        api.autoMessages.templates(),
      ]);
      setData({ events, rules: rules.rules, templates: templates.templates });
      if (rules.rules.some((r) => !r.template_approved)) {
        // GET /rules has no template name, so look it up for the "lost approval" line. Best effort.
        api.templates
          .list()
          .then((all) => setLostNames(Object.fromEntries(all.map((t) => [t.id, t.name]))))
          .catch(() => undefined);
      }
    } catch (err) {
      if (quiet) setActionError(err instanceof Error ? err.message : "Couldn't refresh your messages.");
      else setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const infos = useMemo(() => (data ? toInfos(data.events) : []), [data]);

  /** Moves to `target` with no questions asked. */
  function go(target: string | null) {
    const leaving = openKey;
    setPending(null);
    setDirty(false);
    setOpenKey(target);
    if (target === null && leaving) {
      requestAnimationFrame(() => document.getElementById(rowId(leaving))?.focus());
    }
  }

  /** Moves to `target`, unless the open row has unsaved edits: then it asks, inside that row. */
  function request(target: string | null) {
    if (openKey !== null && target !== openKey && dirty) {
      setPending({ target });
      return;
    }
    if (target === openKey && dirty) {
      setPending({ target: null });
      return;
    }
    go(target);
  }

  function flashSaved(key: string) {
    setSavedKey(key);
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setSavedKey(null), SAVED_FLASH_MS);
  }

  async function handleSaved(key: string) {
    await load(true);
    flashSaved(key);
    go(pending ? pending.target : null);
  }

  async function toggle(rule: AutoMessageRule, enabled: boolean) {
    setSwitchingKey(rule.event);
    setActionError(null);
    try {
      const updated = await api.autoMessages.updateRule(rule.id, { enabled });
      setData((d) =>
        d && {
          ...d,
          rules: d.rules.map((r) => (r.id === rule.id ? { ...r, ...updated } : r)),
        }
      );
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Couldn't change it. Try again.");
    } finally {
      setSwitchingKey(null);
    }
  }

  async function handleCreated(created: AutoMessageCustomEvent) {
    await load(true);
    request(created.key);
  }

  if (loadError) {
    return (
      <div role="alert" className="rounded-[24px] border border-border-subtle bg-white p-5 font-body text-sm text-ink-secondary">
        Couldn&apos;t load your messages.{" "}
        <button type="button" onClick={() => void load(false)} className={`${ghostBtn} ml-1`}>
          Try again
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="overflow-hidden rounded-[24px] border border-border-subtle bg-white" aria-busy="true" aria-label="Loading your messages">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-[68px] animate-pulse border-t border-border-subtle bg-border-subtle first:border-t-0" />
        ))}
      </div>
    );
  }

  const hasTemplates = data.templates.length > 0;
  const canAdd = hasTemplates;
  const takenKeys = infos.map((e) => e.key);

  return (
    <div className="space-y-3">
      {!hasTemplates && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 font-body text-xs text-amber-800">
          You need an approved WhatsApp template first.{" "}
          <Link href="/dashboard/templates" className="font-semibold underline">
            Create one in Templates
          </Link>{" "}
          (Meta approves in 1 to 24 hours).
        </p>
      )}
      {actionError && (
        <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 font-body text-xs font-semibold text-danger">
          {actionError}
        </p>
      )}

      <ul className="m-0 list-none overflow-hidden rounded-[24px] border border-border-subtle bg-white p-0">
        {infos.map((ev) => {
          const rule = data.rules.find((r) => r.event === ev.key) ?? null;
          const template = rule ? data.templates.find((t) => t.id === rule.template_id) ?? null : null;
          const isOpen = openKey === ev.key;
          return (
            <EventRow
              key={ev.key}
              ev={ev}
              rule={rule}
              template={template}
              lostTemplateName={rule ? lostNames[rule.template_id] ?? null : null}
              templates={data.templates}
              canManage={canManage}
              canAdd={canAdd}
              open={isOpen}
              justSaved={savedKey === ev.key}
              switching={switchingKey === ev.key}
              warnUnsaved={isOpen && pending !== null}
              onToggleOpen={() => request(isOpen ? null : ev.key)}
              onToggleEnabled={(next) => {
                if (rule) void toggle(rule, next);
              }}
              onDirtyChange={setDirty}
              onSaved={() => void handleSaved(ev.key)}
              onChanged={() => void load(true)}
              onRequestClose={() => request(null)}
              onDiscard={() => go(pending ? pending.target : null)}
              onKeepEditing={() => setPending(null)}
              onDeleted={() => {
                void load(true);
                go(null);
              }}
            />
          );
        })}
        {canManage && (
          <AddEventRow
            customCount={data.events.custom.length}
            limit={data.events.limit}
            takenKeys={takenKeys}
            disabledReason={canAdd ? null : NO_TEMPLATE_REASON}
            onCreated={(c) => void handleCreated(c)}
          />
        )}
      </ul>
    </div>
  );
}
