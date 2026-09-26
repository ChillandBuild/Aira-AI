import { cn } from "@/lib/utils";

export function StatCard({
  icon,
  label,
  value,
  tone = "border-t-primary-500",
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  tone?: string;
}) {
  return (
    <div className={cn("bg-white rounded-card border border-border border-t-4 p-5 shadow-sm transition-all", tone)}>
      <div className="flex items-center gap-2 text-ink-muted mb-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wider font-label">{label}</span>
      </div>
      <p className="text-2xl font-bold text-ink">{typeof value === "number" ? value.toLocaleString() : value}</p>
    </div>
  );
}
