import type { Metadata } from "next";
import Link from "next/link";
import { Mail, MapPin } from "lucide-react";
import { LegalPageShell } from "@/components/legal/LegalPageShell";

export const metadata: Metadata = {
  title: "Contact",
  description: "Get in touch with the AIRA team at Bloom Matrix.",
};

export default function ContactPage() {
  return (
    <LegalPageShell title="Contact Us" subtitle="AIRA — a Bloom Matrix product" effectiveDate="14 June 2026">
      <p className="text-sm leading-relaxed text-ink-secondary mb-10">
        For support, sales, privacy requests, or any other questions about AIRA, reach us directly using the details
        below. We typically respond within one business day.
      </p>

      <div className="grid sm:grid-cols-2 gap-5 mb-10">
        <a
          href="mailto:aira@bloommatrix.in"
          className="card card-hover hover:border-primary/40 transition-colors block"
        >
          <div className="w-10 h-10 rounded-lg bg-primary-light flex items-center justify-center mb-4">
            <Mail size={18} className="text-primary" />
          </div>
          <p className="text-sm font-semibold text-ink mb-1">Email Support</p>
          <p className="text-sm text-ink-secondary">aira@bloommatrix.in</p>
        </a>

        <div className="card">
          <div className="w-10 h-10 rounded-lg bg-primary-light flex items-center justify-center mb-4">
            <MapPin size={18} className="text-primary" />
          </div>
          <p className="text-sm font-semibold text-ink mb-1">Registered Office</p>
          <p className="text-sm text-ink-secondary leading-relaxed">
            352-1, Srinivasapuram Street, Avinashi, Tiruppur, Tamil Nadu – 641654, India
          </p>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-ink-secondary">
        Data deletion or privacy requests can be sent to{" "}
        <a href="mailto:aira@bloommatrix.in" className="text-primary hover:underline">
          aira@bloommatrix.in
        </a>{" "}
        with the subject line &ldquo;Data Deletion Request&rdquo;. See our{" "}
        <Link href="/privacy-policy" className="text-primary hover:underline">
          Privacy Policy
        </Link>{" "}
        and{" "}
        <Link href="/terms-and-conditions" className="text-primary hover:underline">
          Terms &amp; Conditions
        </Link>{" "}
        for further details.
      </p>
    </LegalPageShell>
  );
}
