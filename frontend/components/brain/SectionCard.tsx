import type { ReactNode } from "react";

interface SectionCardProps {
  id?: string;
  title: string;
  subtitle?: string;
  children: ReactNode;
}

export function SectionCard({ id, title, subtitle, children }: SectionCardProps) {
  return (
    <section id={id} className="scroll-mt-20 min-w-0 rounded-2xl border border-border bg-white p-4 sm:p-5">
      <h2 className="font-display text-sm font-extrabold text-ink">{title}</h2>
      {subtitle && <p className="mt-0.5 font-body text-xs text-ink-secondary">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}
