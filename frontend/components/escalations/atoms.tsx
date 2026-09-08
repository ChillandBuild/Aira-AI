"use client";
import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  AlertOctagon,
  Check,
  Clock,
  Copy,
  HelpCircle,
  MessageSquare,
  RotateCw,
  Sparkles,
  User,
  UserCheck,
} from "lucide-react";
import { SegmentBadge } from "@/components/segment-badge";
import { cn, formatPhone } from "@/lib/utils";
import {
  TRIGGERS,
  channelOf,
  initialsOf,
  type EscalationLead,
  type Severity,
} from "@/lib/escalations";

const TRIGGER_ICONS: Record<string, LucideIcon> = {
  "User requested a human agent": UserCheck,
  "AI failed to generate a response": AlertOctagon,
  "AI gave a generic fallback reply": HelpCircle,
  "User repeated the same question": RotateCw,
  "AI indicated team will follow up": Clock,
};

function WhatsAppIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884a9.82 9.82 0 0 1 6.99 2.896 9.825 9.825 0 0 1 2.895 6.994c-.003 5.45-4.437 9.885-9.885 9.885M20.52 3.449C18.24 1.245 15.24 0 12.045 0 5.463 0 .104 5.359.101 11.947c0 2.096.549 4.142 1.595 5.945L0 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.582 0 11.94-5.359 11.944-11.949a11.88 11.88 0 0 0-3.417-8.396" />
    </svg>
  );
}

/** Why the AI handed over, as a refined badge with contextual icon */
export function TriggerChip({ reason }: { reason: string | null }) {
  if (!reason) return <span className="font-body text-xs text-slate-400">—</span>;
  const known = TRIGGERS[reason];
  const Icon = TRIGGER_ICONS[reason] ?? Sparkles;
  return (
    <span
      title={reason}
      className={cn(
        "inline-flex max-w-[190px] items-center gap-1.5 truncate rounded-full border px-2.5 py-1 font-label text-[11px] font-semibold leading-tight shadow-2xs",
        known?.className ?? "bg-slate-50 text-slate-700 border-slate-200"
      )}
    >
      <Icon size={12} className="shrink-0 opacity-80" />
      <span className="truncate">{known?.label ?? reason}</span>
    </span>
  );
}

export function ChannelCell({ lead }: { lead: EscalationLead }) {
  const [copied, setCopied] = useState(false);
  const ch = channelOf(lead);
  const handle = ch.label === "WhatsApp" ? formatPhone(ch.handle) : ch.handle;

  function copyHandle(e: React.MouseEvent) {
    e.stopPropagation();
    if (!handle || handle === "unknown") return;
    navigator.clipboard.writeText(ch.handle);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="inline-flex items-center gap-2 text-left group/channel">
      <span
        className={cn(
          "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border font-medium text-[11px] shadow-2xs shrink-0",
          ch.label === "WhatsApp"
            ? "bg-emerald-50 text-emerald-700 border-emerald-200/80"
            : ch.label === "Telegram"
              ? "bg-sky-50 text-sky-700 border-sky-200/80"
              : ch.label === "Instagram"
                ? "bg-pink-50 text-pink-700 border-pink-200/80"
                : "bg-blue-50 text-blue-700 border-blue-200/80"
        )}
      >
        {ch.label === "WhatsApp" ? <WhatsAppIcon className="text-emerald-600 shrink-0" /> : <MessageSquare size={11} className="shrink-0" />}
        <span>{ch.label}</span>
      </span>
      <span className="font-mono text-xs tracking-tight text-slate-700 font-medium">
        {handle}
      </span>
      {handle && handle !== "unknown" && (
        <button
          onClick={copyHandle}
          type="button"
          title={copied ? "Copied!" : "Copy handle"}
          className="opacity-0 group-hover/channel:opacity-100 focus:opacity-100 p-1 text-slate-400 hover:text-slate-700 rounded transition-all"
        >
          {copied ? <Check size={11} className="text-emerald-600" /> : <Copy size={11} />}
        </button>
      )}
    </div>
  );
}

export function LeadCell({ lead }: { lead: EscalationLead }) {
  const hasName = Boolean(lead?.name && lead.name.trim() && lead.name.trim().toLowerCase() !== "unknown lead");
  const displayName = hasName
    ? lead!.name!
    : lead?.phone
      ? formatPhone(lead.phone)
      : lead?.tg_username
        ? `@${lead.tg_username}`
        : "Unsaved Lead";

  const subtitle = hasName
    ? lead?.phone
      ? formatPhone(lead.phone)
      : lead?.tg_username
        ? `@${lead.tg_username}`
        : "Lead"
    : "Direct Inbound";

  const initials = hasName ? initialsOf(lead!.name!) : null;

  return (
    <div className="flex items-center gap-3 text-left">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-100 to-purple-100 text-[#5b21b6] font-mono text-[11px] font-bold ring-1 ring-purple-200/70 shadow-2xs">
        {initials ? initials : <User size={14} className="text-[#5b21b6]" />}
      </div>

      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate font-heading text-[13px] font-bold tracking-tight text-slate-900" title={displayName}>
            {displayName}
          </span>
          {lead?.segment && <SegmentBadge segment={lead.segment} />}
        </div>
        <span className="truncate font-body text-[11px] text-slate-400">
          {subtitle}
        </span>
      </div>
    </div>
  );
}

/** A person, or an explicit absence with clean avatar and label. */
export function PersonCell({ name, empty }: { name: string | null; empty: string }) {
  if (!name) {
    return (
      <div className="flex items-center gap-2 text-left">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-400 font-mono text-[10px] ring-1 ring-slate-200/60">
          <User size={12} />
        </div>
        <span className="font-body text-xs text-slate-400 italic">{empty}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-left">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-100 to-purple-100 text-[#5b21b6] font-mono text-[10.5px] font-bold ring-1 ring-purple-200/70 shadow-2xs">
        {initialsOf(name)}
      </div>
      <span className="truncate font-body text-xs font-semibold text-slate-800" title={name}>
        {name}
      </span>
    </div>
  );
}

export function DurationCell({ text, severity, sub }: { text: string; severity: Severity; sub?: string }) {
  const toneConfig = {
    bad: {
      badge: "bg-rose-50 text-rose-700 border-rose-200/80 shadow-2xs",
      dot: "bg-rose-500 animate-pulse",
      label: "Over 24h SLA",
    },
    warn: {
      badge: "bg-amber-50 text-amber-700 border-amber-200/80 shadow-2xs",
      dot: "bg-amber-500",
      label: "Waiting >4h",
    },
    ok: {
      badge: "bg-emerald-50 text-emerald-700 border-emerald-200/80 shadow-2xs",
      dot: "bg-emerald-500",
      label: "Within SLA",
    },
  }[severity];

  return (
    <div className="flex flex-col items-center">
      <span
        title={toneConfig.label}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-0.5 font-mono text-xs font-bold tabular-nums",
          toneConfig.badge
        )}
      >
        <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", toneConfig.dot)} />
        {text}
      </span>
      {sub && <span className="mt-0.5 block font-body text-[10.5px] text-slate-400">{sub}</span>}
    </div>
  );
}

export function TableEmpty({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="mx-auto my-12 max-w-md rounded-2xl border border-border/80 bg-surface p-10 text-center shadow-card">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-purple-50/70 border border-purple-100">
        {icon}
      </div>
      <p className="font-heading text-base font-bold text-slate-900">{title}</p>
      <p className="mt-1 font-body text-xs text-slate-500">{body}</p>
    </div>
  );
}

export function TableSkeleton({ columns, rows = 5 }: { columns: number; rows?: number }) {
  return (
    <tbody>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r} className="border-b border-border-subtle">
          {Array.from({ length: columns }).map((_, c) => (
            <td key={c} className="px-4 py-3.5 first:pl-8 last:pr-8">
              <span
                className="block h-3.5 animate-pulse rounded-full bg-slate-100"
                style={{ width: c === 0 ? "70%" : c === columns - 1 ? "45%" : "55%" }}
              />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}
