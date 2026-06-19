"use client";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: number | string;
  sub?: string;
  accent?: boolean;
}

export function StatCard({ label, value, sub, accent }: StatCardProps) {
  return (
    <div
      className={cn(
        "card card-hover",
        accent
          ? "border-transparent text-white"
          : "bg-surface"
      )}
      style={accent ? { background: "linear-gradient(135deg, #2e1065, #5b21b6)" } : {}}
    >
      <p className={cn(
        "stat-label mb-2",
        accent ? "text-purple-200/60" : ""
      )}>
        {label}
      </p>
      <p className={cn(
        "stat-num",
        accent ? "text-white" : "text-ink"
      )}>
        {value}
      </p>
      {sub && (
        <p className={cn(
          "mt-1 text-xs",
          accent ? "text-purple-200/60" : "text-ink-muted"
        )}>
          {sub}
        </p>
      )}
    </div>
  );
}
