import { DealSource } from "@/lib/api";

const SOURCE_LABEL: Record<DealSource, string> = {
  whatsapp: "WhatsApp",
  form: "Form",
  call: "Call",
  walk_in: "Walk-in",
  manual: "Manual",
  indiamart: "IndiaMART",
  justdial: "JustDial",
};

export function SourceBadge({ source, className = "" }: { source: DealSource; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full bg-surface-subtle px-2 py-0.5 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted whitespace-nowrap ${className}`}
    >
      {SOURCE_LABEL[source] ?? source}
    </span>
  );
}
