import type { ReactNode } from "react";
import Link from "next/link";
import { AiraLogo } from "@/components/logo";

interface LegalPageShellProps {
  title: string;
  subtitle: string;
  effectiveDate: string;
  children: ReactNode;
}

export function LegalPageShell({ title, subtitle, effectiveDate, children }: LegalPageShellProps) {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="max-w-3xl mx-auto px-6 py-6 flex items-center justify-between">
          <Link href="/" aria-label="Aira home">
            <AiraLogo height={26} className="text-primary" />
          </Link>
          <nav className="flex gap-5 text-sm text-ink-secondary">
            <Link href="/privacy-policy" className="hover:text-primary transition-colors">
              Privacy Policy
            </Link>
            <Link href="/terms-and-conditions" className="hover:text-primary transition-colors">
              Terms &amp; Conditions
            </Link>
            <Link href="/contact" className="hover:text-primary transition-colors">
              Contact
            </Link>
            <Link href="/data-deletion" className="hover:text-primary transition-colors">
              Data Deletion
            </Link>
          </nav>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-14">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary mb-2">{subtitle}</p>
        <h1 className="text-3xl md:text-4xl font-bold text-ink mb-2">{title}</h1>
        <p className="text-sm text-ink-muted mb-10">Effective Date: {effectiveDate}</p>
        <article>{children}</article>
      </main>

      <footer className="border-t border-border">
        <div className="max-w-3xl mx-auto px-6 py-8 text-xs text-ink-muted flex flex-col sm:flex-row justify-between gap-3">
          <span>Bloom Matrix — 352-1, Srinivasapuram Street, Avinashi, Tiruppur, Tamil Nadu – 641654, India</span>
          <a href="mailto:aira@bloommatrix.in" className="hover:text-primary transition-colors">
            aira@bloommatrix.in
          </a>
        </div>
      </footer>
    </div>
  );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="text-lg font-semibold text-ink mt-2 mb-3">{title}</h2>
      <div className="space-y-3 text-sm leading-relaxed text-ink-secondary">{children}</div>
    </section>
  );
}

export function LegalList({ items }: { items: ReactNode[] }) {
  return (
    <ul className="list-disc pl-5 space-y-1.5">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}
