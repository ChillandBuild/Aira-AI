"use client";

import { CopyButton } from "@/app/dashboard/settings/connect-channels/ui";

/*
  Layout pieces for the sections added to the Developer page. They copy the look of
  the page's own Section and Code so the new sections sit beside Ansar's without
  touching them.
*/

export function DevSection({ id, icon: Icon, title, intro, children }: {
  id: string;
  icon: React.ElementType;
  title: string;
  intro?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="card rounded-3xl p-6 scroll-mt-24">
      <div className="mb-4 flex items-start gap-3">
        <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
          <Icon size={16} />
        </span>
        <div>
          <h2 className="font-display text-lg font-bold text-ink">{title}</h2>
          {intro && <p className="mt-0.5 font-body text-sm text-ink-secondary">{intro}</p>}
        </div>
      </div>
      <div className="space-y-4 font-body text-sm text-ink-secondary">{children}</div>
    </section>
  );
}

export function CodeBox({ code, copy = true }: { code: string; copy?: boolean }) {
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-2xl border border-border-subtle bg-[#0A1528] p-4 pr-20 font-mono text-[12px] leading-relaxed text-[#f5f3ef]">
        {code}
      </pre>
      {copy && (
        <div className="absolute right-3 top-3">
          <CopyButton text={code} />
        </div>
      )}
    </div>
  );
}

/** A single value (URL, key, code) in a tinted box with a copy button. */
export function CopyValue({ value, label }: { value: string; label?: string }) {
  return (
    <div>
      {label && <p className="mb-1 font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted">{label}</p>}
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 select-all break-all rounded-xl border border-border bg-surface-subtle px-3 py-2.5 font-mono text-[11px] font-medium text-primary">
          {value}
        </code>
        <CopyButton text={value} />
      </div>
    </div>
  );
}

export function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 font-body text-xs text-rose-700">
      {message}
    </p>
  );
}
