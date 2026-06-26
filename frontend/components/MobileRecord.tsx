"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function MobileRecordCard({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <article
      className={cn(
        "rounded-2xl border border-surface-mid bg-white p-4 shadow-sm",
        className
      )}
    >
      {children}
    </article>
  );
}

export function MobileRecordHeader({
  title,
  subtitle,
  aside,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate font-body text-sm font-bold text-on-surface">
          {title}
        </div>
        {subtitle && (
          <div className="mt-1 text-xs leading-snug text-on-surface-muted">
            {subtitle}
          </div>
        )}
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </div>
  );
}

export function MobileRecordGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mt-4 grid grid-cols-2 gap-3", className)}>
      {children}
    </div>
  );
}

export function MobileRecordField({
  label,
  value,
  className,
}: {
  label: string;
  value: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 rounded-xl bg-surface-low px-3 py-2.5", className)}>
      <div className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">
        {label}
      </div>
      <div className="mt-1 min-w-0 text-sm font-semibold text-on-surface">
        {value}
      </div>
    </div>
  );
}
