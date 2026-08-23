"use client";
import { useEffect, useState } from "react";
import { Bell, Trash2, Plus } from "lucide-react";
import { api, NotificationConfig, Caller, WabaTemplate } from "@/lib/api";
import { SaveButton, SaveStatus, SectionFooter, SettingsSection } from "./SettingsSection";

const EVENT_LABELS: Record<string, string> = {
  callback_due: "Callback due reminder",
  callback_claimable: "Callback open to claim",
  callback_taken_over: "Your callback was claimed",
  lead_assigned: "New lead assigned",
  lead_replied: "Lead replied",
  handover_new: "Chat handover needed",
};

const AUDIENCE_OPTIONS: { value: NotificationConfig["claimable_audience"]; label: string }[] = [
  { value: "telecallers_and_admin", label: "Telecallers + Admin" },
  { value: "telecallers_only", label: "Telecallers only" },
  { value: "admin_only", label: "Admin only" },
  { value: "specific", label: "Specific telecallers" },
];

const SEGMENTS = ["A", "B", "C", "D"] as const;
const SEGMENT_LABELS: Record<(typeof SEGMENTS)[number], string> = { A: "Hot", B: "Warm", C: "Cold", D: "Not Interested" };
const SEGMENT_STYLES: Record<(typeof SEGMENTS)[number], string> = {
  A: "bg-segment-a-bg text-segment-a-text border-segment-a-border",
  B: "bg-segment-b-bg text-segment-b-text border-segment-b-border",
  C: "bg-segment-c-bg text-segment-c-text border-segment-c-border",
  D: "bg-segment-d-bg text-segment-d-text border-segment-d-border",
};
const E164_REGEX = /^\+[1-9]\d{6,14}$/;

/** The two WhatsApp alert blocks share this shape. */
type WhatsAppBlock = NotificationConfig["whatsapp_notifications"];

export function NotificationConfigPanel({ canManage = true }: { canManage?: boolean }) {
  const [cfg, setCfg] = useState<NotificationConfig | null>(null);
  const [callers, setCallers] = useState<Caller[]>([]);
  const [templates, setTemplates] = useState<WabaTemplate[]>([]);
  const [state, setState] = useState<"idle" | "dirty" | "saving" | "saved">("idle");

  useEffect(() => {
    api.notifications.getConfig().then(setCfg).catch(() => {});
    api.callers.list().then((res) => setCallers((res.data || []).filter((c) => c.active))).catch(() => {});
    api.templates.list().then(setTemplates).catch(() => {});
  }, []);

  function patch(next: Partial<NotificationConfig>) {
    if (!canManage) return;
    setCfg((c) => (c ? { ...c, ...next } : c));
    setState("dirty");
  }

  async function save() {
    if (!cfg || !canManage) return;
    setState("saving");
    try {
      const saved = await api.notifications.saveConfig(cfg);
      setCfg(saved);
      setState("saved");
      setTimeout(() => setState("idle"), 2500);
    } catch {
      setState("dirty");
    }
  }

  if (!cfg) {
    return <div className="card rounded-3xl h-56 animate-pulse bg-border-subtle" />;
  }

  const approvedTemplates = templates.filter((t) => t.status === "APPROVED");

  const activeEvents = Object.keys(EVENT_LABELS).filter((k) => cfg.events[k] ?? true).length;

  return (
    <SettingsSection
      id="push-notifications"
      icon={Bell}
      accent="violet"
      title="Push Notifications"
      description="Control which push alerts your team receives. The in-app bell always records every event."
      status={
        cfg.push_enabled
          ? { label: `${activeEvents}/${Object.keys(EVENT_LABELS).length} events`, tone: "on" }
          : { label: "Push off", tone: "off" }
      }
      dirty={state === "dirty"}
    >
      <div className="space-y-4">
      {/* Master switch */}
      <div className="flex items-center justify-between p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
        <div>
          <p className="font-body text-sm font-semibold text-ink">Enable push notifications</p>
          <p className="font-body text-xs text-ink-muted mt-0.5">Master switch for all phone/desktop pushes.</p>
        </div>
        <Toggle on={cfg.push_enabled} disabled={!canManage} onClick={() => patch({ push_enabled: !cfg.push_enabled })} />
      </div>

      {/* Per-event toggles */}
      <div className="space-y-2">
        <p className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Per-event push</p>
        {Object.keys(EVENT_LABELS).map((key) => {
          const on = cfg.events[key] ?? true;
          return (
            <div key={key} className="flex items-center justify-between p-3 rounded-xl bg-surface-subtle border border-border-subtle">
              <span className="font-body text-sm text-ink">{EVENT_LABELS[key]}</span>
              <Toggle
                on={on}
                disabled={!canManage || !cfg.push_enabled}
                onClick={() => patch({ events: { ...cfg.events, [key]: !on } })}
              />
            </div>
          );
        })}
      </div>

      {/* Claimable threshold + audience */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
          <label className="font-body text-sm font-semibold text-ink">Claimable after (minutes)</label>
          <p className="font-body text-xs text-ink-muted mt-0.5 mb-2">How long after the slot a callback opens to claim.</p>
          <input
            type="number" min={1} max={120}
            value={cfg.claimable_threshold_minutes}
            disabled={!canManage}
            onChange={(e) => patch({ claimable_threshold_minutes: Math.max(1, Math.min(120, parseInt(e.target.value) || 1)) })}
            className="w-24 px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
          />
        </div>
        <div className="p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
          <label className="font-body text-sm font-semibold text-ink">Claimable broadcast to</label>
          <p className="font-body text-xs text-ink-muted mt-0.5 mb-2">Who gets the &quot;open to claim&quot; alert.</p>
          <select
            value={cfg.claimable_audience}
            disabled={!canManage}
            onChange={(e) => patch({ claimable_audience: e.target.value as NotificationConfig["claimable_audience"] })}
            className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm text-ink focus:outline-none focus:border-primary"
          >
            {AUDIENCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>

          {cfg.claimable_audience === "specific" && (
            <div className="mt-3 space-y-1.5 max-h-44 overflow-y-auto rounded-xl border border-border bg-white p-2">
              {callers.length === 0 ? (
                <p className="font-body text-xs text-ink-muted px-1 py-2">No telecallers found.</p>
              ) : (
                callers.map((c) => {
                  const checked = cfg.claimable_caller_ids.includes(c.id);
                  return (
                    <label key={c.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-surface-subtle cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={!canManage}
                        onChange={() =>
                          patch({
                            claimable_caller_ids: checked
                              ? cfg.claimable_caller_ids.filter((id) => id !== c.id)
                              : [...cfg.claimable_caller_ids, c.id],
                          })
                        }
                        className="accent-primary"
                      />
                      <span className="font-body text-sm text-ink">{c.name}</span>
                    </label>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>

      {/* Quiet hours */}
      <div className="p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-body text-sm font-semibold text-ink">Quiet hours</p>
            <p className="font-body text-xs text-ink-muted mt-0.5">Suppress pushes overnight (in-app bell still records them).</p>
          </div>
          <Toggle on={cfg.quiet_hours.enabled} disabled={!canManage} onClick={() => patch({ quiet_hours: { ...cfg.quiet_hours, enabled: !cfg.quiet_hours.enabled } })} />
        </div>
        {cfg.quiet_hours.enabled && (
          <div className="mt-3 flex items-center gap-2">
            <HourSelect value={cfg.quiet_hours.start_hour} disabled={!canManage} onChange={(h) => patch({ quiet_hours: { ...cfg.quiet_hours, start_hour: h } })} />
            <span className="text-ink-muted text-sm">to</span>
            <HourSelect value={cfg.quiet_hours.end_hour} disabled={!canManage} onChange={(h) => patch({ quiet_hours: { ...cfg.quiet_hours, end_hour: h } })} />
            <span className="text-ink-muted text-xs">IST</span>
          </div>
        )}
      </div>

      {/* WhatsApp alerts on segment change */}
      <WhatsAppAlertSection
        title="WhatsApp lead notifications"
        subtitle="Message your team on WhatsApp when a lead's segment changes."
        segmentsLabel="Notify for segments"
        delayHelp="How long the lead must stay in the segment before sending the notification. Set to 0 to send immediately."
        block={cfg.whatsapp_notifications}
        approvedTemplates={approvedTemplates}
        canManage={canManage}
        onChange={(next) => patch({ whatsapp_notifications: next })}
      />

      {/* WhatsApp alerts on escalation */}
      <WhatsAppAlertSection
        title="WhatsApp escalation alerts"
        subtitle="Message your team on WhatsApp when a conversation is escalated to a human."
        segmentsLabel="Alert for segments"
        delayHelp="How long to wait before alerting. If a teammate claims or resolves the handover first, the message is not sent."
        block={cfg.whatsapp_escalation_notifications}
        approvedTemplates={approvedTemplates}
        canManage={canManage}
        onChange={(next) => patch({ whatsapp_escalation_notifications: next })}
      />

      </div>

      <SectionFooter
        status={<SaveStatus state={state} dirty={state === "dirty"} idleLabel={cfg.push_enabled ? "Push alerts are on" : "Push alerts are off"} />}
      >
        <SaveButton state={state} dirty={state === "dirty"} disabled={!canManage} onClick={save} />
      </SectionFooter>
    </SettingsSection>
  );
}

/**
 * One WhatsApp alert configuration block: segments, recipients, template, delay.
 * Shared by the segment-change and escalation alerts, which differ only in copy.
 */
function WhatsAppAlertSection({
  title,
  subtitle,
  segmentsLabel,
  delayHelp,
  block,
  approvedTemplates,
  canManage,
  onChange,
}: {
  title: string;
  subtitle: string;
  segmentsLabel: string;
  delayHelp: string;
  block: WhatsAppBlock;
  approvedTemplates: WabaTemplate[];
  canManage: boolean;
  onChange: (next: WhatsAppBlock) => void;
}) {
  const [phoneInput, setPhoneInput] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);

  const selectedTemplate = approvedTemplates.find((t) => t.id === block.template_id) || null;

  function toggleSegment(segment: (typeof SEGMENTS)[number]) {
    const active = block.target_segments.includes(segment);
    onChange({
      ...block,
      target_segments: active
        ? block.target_segments.filter((s) => s !== segment)
        : [...block.target_segments, segment],
    });
  }

  function addPhone() {
    const trimmed = phoneInput.trim();
    if (!E164_REGEX.test(trimmed)) {
      setPhoneError("Enter a valid number in E.164 format, e.g. +919876543210");
      return;
    }
    if (block.recipient_phones.includes(trimmed)) {
      setPhoneError("This number is already added.");
      return;
    }
    onChange({ ...block, recipient_phones: [...block.recipient_phones, trimmed] });
    setPhoneInput("");
    setPhoneError(null);
  }

  function removePhone(phone: string) {
    onChange({ ...block, recipient_phones: block.recipient_phones.filter((p) => p !== phone) });
  }

  return (
    <div className="p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-body text-sm font-semibold text-ink">{title}</p>
          <p className="font-body text-xs text-ink-muted mt-0.5">{subtitle}</p>
        </div>
        <Toggle
          on={block.enabled}
          disabled={!canManage}
          onClick={() => onChange({ ...block, enabled: !block.enabled })}
        />
      </div>

      {block.enabled && (
        <div className="mt-4 space-y-4">
          <div>
            <p className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2">{segmentsLabel}</p>
            <div className="flex flex-wrap gap-2">
              {SEGMENTS.map((s) => {
                const active = block.target_segments.includes(s);
                return (
                  <button
                    key={s}
                    type="button"
                    aria-pressed={active}
                    disabled={!canManage}
                    onClick={() => toggleSegment(s)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full font-mono text-xs font-semibold border transition-colors ${
                      active ? SEGMENT_STYLES[s] : "bg-white text-ink-muted border-border"
                    }`}
                  >
                    {s} · {SEGMENT_LABELS[s]}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <p className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2">Recipient phone numbers</p>
            {block.recipient_phones.length > 0 && (
              <div className="space-y-1.5 mb-2">
                {block.recipient_phones.map((phone) => (
                  <div key={phone} className="flex items-center justify-between px-3 py-2 rounded-xl bg-white border border-border">
                    <span className="font-mono text-sm text-ink">{phone}</span>
                    <button
                      type="button"
                      onClick={() => removePhone(phone)}
                      className="text-ink-muted hover:text-red-600 transition-colors"
                      aria-label={`Remove ${phone}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={phoneInput}
                disabled={!canManage}
                onChange={(e) => { setPhoneInput(e.target.value); setPhoneError(null); }}
                placeholder="+919876543210"
                className="flex-1 px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
              />
              <button
                type="button"
                onClick={addPhone}
                disabled={!canManage}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-border text-sm font-semibold text-ink hover:border-primary transition-colors flex-shrink-0"
              >
                <Plus size={14} />Add Number
              </button>
            </div>
            {phoneError && <p className="font-body text-xs text-red-600 mt-1.5">{phoneError}</p>}
          </div>

          <div>
            <label className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2 block">Message template</label>
            <select
              value={block.template_id ?? ""}
              disabled={!canManage}
              onChange={(e) => onChange({ ...block, template_id: e.target.value || null })}
              className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm text-ink focus:outline-none focus:border-primary"
            >
              <option value="">Select a template…</option>
              {approvedTemplates.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
            {selectedTemplate && (
              <div className="mt-2 p-3 rounded-xl bg-white border border-border-subtle">
                <p className="font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted mb-1">Preview</p>
                <p className="font-mono text-xs text-ink-muted whitespace-pre-wrap">
                  {selectedTemplate.body_text || "No body text available."}
                </p>
              </div>
            )}
          </div>

          <div>
            <label className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2 block">Delay before sending (minutes)</label>
            <input
              type="number" min={0} max={1440}
              value={block.delay_minutes ?? 5}
              disabled={!canManage}
              onChange={(e) =>
                onChange({ ...block, delay_minutes: Math.max(0, Math.min(1440, parseInt(e.target.value) || 0)) })
              }
              className="w-24 px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
            />
            <p className="font-body text-[11px] text-ink-muted mt-1">{delayHelp}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function Toggle({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <div className={`relative inline-flex p-0.5 rounded-full bg-border-subtle/80 border border-border/40 select-none flex-shrink-0 ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={on ? onClick : undefined}
        className={`relative z-10 px-3 py-0.5 text-xs font-label font-bold rounded-full transition-all duration-300 ${
          !on ? "bg-white text-ink shadow-[0_2px_8px_rgba(28,25,23,0.06)]" : "text-ink-muted hover:text-ink"
        } ${disabled ? "cursor-not-allowed" : ""}`}
      >
        Off
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={on ? undefined : onClick}
        className={`relative z-10 px-3 py-0.5 text-xs font-label font-bold rounded-full transition-all duration-300 ${
          on ? "bg-gradient-to-r from-primary to-violet-500 text-white shadow-[0_2px_8px_rgba(91,33,182,0.2)]" : "text-ink-muted hover:text-ink"
        } ${disabled ? "cursor-not-allowed" : ""}`}
      >
        On
      </button>
    </div>
  );
}

function HourSelect({ value, onChange, disabled }: { value: number; onChange: (h: number) => void; disabled?: boolean }) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(parseInt(e.target.value))}
      className="px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
    >
      {Array.from({ length: 24 }, (_, h) => (
        <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
      ))}
    </select>
  );
}
