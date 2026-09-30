import Link from "next/link";
import { cn } from "@/lib/utils";
import { SectionCard } from "./SectionCard";
import { ROW_LINK_CLASS } from "./WaitingRow";
import type { BrainConnection, BrainQuota, BrainStatus, ConnectionState, QuotaMetric } from "./types";

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  ok: "Connected",
  token_problem: "Connection problem: reconnect your channel",
  quiet: "Connected, but no recent messages",
  unknown: "Connection status unknown",
};

const CONNECTION_TONE: Record<ConnectionState, string> = {
  ok: "bg-emerald-50 text-success",
  token_problem: "bg-rose-50 text-danger",
  quiet: "bg-amber-50 text-warning",
  unknown: "bg-surface-mid text-ink-secondary",
};

function StatusRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-xl border border-border-subtle bg-surface-low px-3 py-2.5">
      <span className="font-body text-sm font-semibold text-ink">{label}</span>
      <span className="flex min-w-0 flex-wrap items-center gap-2">{children}</span>
    </li>
  );
}

function Pill({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={cn("break-words rounded-full px-2 py-0.5 font-label text-[10px] font-bold", tone)}>{children}</span>;
}

function metricLabel(metric: QuotaMetric): string {
  return `${metric.metric.replace(/_/g, " ")}: ${metric.used} of ${metric.hard_cap} used`;
}

function QuotaRow({ quota }: { quota: BrainQuota }) {
  return (
    <StatusRow label="Usage cap">
      {quota.metrics.map((metric) => (
        <Pill key={metric.metric} tone="bg-amber-50 text-warning">
          {metricLabel(metric)}
        </Pill>
      ))}
    </StatusRow>
  );
}

function ConnectionRow({ connection }: { connection: BrainConnection }) {
  return (
    <StatusRow label="WhatsApp connection">
      <Pill tone={CONNECTION_TONE[connection.state]}>{CONNECTION_LABEL[connection.state]}</Pill>
      {connection.state === "token_problem" && (
        <Link href="/dashboard/settings/connect-channels" className={ROW_LINK_CLASS}>
          Fix
        </Link>
      )}
    </StatusRow>
  );
}

export function CanReply({ status }: { status: BrainStatus }) {
  const isOn = status.auto_reply === "on";
  return (
    <SectionCard title="Aira can reply">
      <ul className="flex flex-col gap-2">
        <StatusRow label="Auto-reply">
          <Pill tone={isOn ? "bg-emerald-50 text-success" : "bg-surface-mid text-ink-secondary"}>
            {isOn ? "On" : "Off"}
          </Pill>
          <Link href="/dashboard/settings/auto-reply" className={ROW_LINK_CLASS}>
            Change
          </Link>
        </StatusRow>
        {status.connection && <ConnectionRow connection={status.connection} />}
        {status.quota && status.quota.metrics.length > 0 && <QuotaRow quota={status.quota} />}
      </ul>
    </SectionCard>
  );
}
