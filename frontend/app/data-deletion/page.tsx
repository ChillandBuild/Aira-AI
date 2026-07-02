import type { Metadata } from "next";
import Link from "next/link";
import { LegalPageShell, LegalSection, LegalList } from "@/components/legal/LegalPageShell";

export const metadata: Metadata = {
  title: "Data Deletion",
  description: "How to request deletion of your personal data from AIRA, a Bloom Matrix product.",
};

export default function DataDeletionPage() {
  return (
    <LegalPageShell title="Data Deletion" subtitle="AIRA — a Bloom Matrix product" effectiveDate="14 June 2026">
      <p className="text-sm leading-relaxed text-ink-secondary mb-10">
        This page explains how you can request deletion of personal data associated with your use of AIRA, a
        product operated by Bloom Matrix. It applies to AIRA business users, their team members, and individuals
        who have interacted with a business through AIRA-connected channels (WhatsApp, Instagram, Facebook
        Messenger, and Telegram).
      </p>

      <LegalSection title="1. Your Right to Request Deletion">
        <p>
          You may request deletion of your personal data at any time. This right is available to all users who
          can access AIRA, as well as to individuals whose data has been processed through AIRA on behalf of a
          business customer.
        </p>
      </LegalSection>

      <LegalSection title="2. How to Submit a Deletion Request">
        <p>
          Email{" "}
          <a href="mailto:aira@bloommatrix.in" className="text-primary hover:underline">
            aira@bloommatrix.in
          </a>{" "}
          with the subject line &ldquo;Data Deletion Request&rdquo;. Include enough information for us to
          identify the relevant account or data, such as:
        </p>
        <LegalList
          items={[
            "The email address or phone number associated with the account",
            "The business (tenant) name, if known",
            "A brief description of the data you want deleted",
          ]}
        />
        <p>
          We will verify the request and delete the relevant personal data without undue delay, and in any event
          within thirty (30) days, unless we are legally required or permitted to retain it (for example, for
          legal, tax, security, or dispute-resolution purposes).
        </p>
      </LegalSection>

      <LegalSection title="3. Deleting Data via Connected Platforms">
        <p>
          If your data reached AIRA through a connected third-party platform — the WhatsApp Business Platform,
          Meta Business Manager, Facebook, Instagram, or Telegram — you may also revoke AIRA&rsquo;s access at
          any time through that platform&rsquo;s own settings. Certain data controlled directly by those
          platforms can only be deleted through the platform itself, and revoking access there does not
          automatically delete data already stored in AIRA — submit a request as described in Section 2 for that.
        </p>
      </LegalSection>

      <LegalSection title="4. If a Business Customer Uploaded Your Data">
        <p>
          Where a business customer using AIRA has uploaded your contact or communication data (for example, as
          a lead or customer record), that business acts as the controller of your data. If you are an
          end-customer of an AIRA business customer, you may direct your deletion request to that business
          directly. Bloom Matrix will assist the business in fulfilling such requests when contacted through the
          process above.
        </p>
      </LegalSection>

      <LegalSection title="5. What Happens After Account Termination">
        <p>
          Upon termination or closure of a customer account, we delete or anonymize the associated personal data
          within a commercially reasonable period, subject to legal retention requirements described in our{" "}
          <Link href="/privacy-policy" className="text-primary hover:underline">
            Privacy Policy
          </Link>
          .
        </p>
      </LegalSection>

      <LegalSection title="6. Contact">
        <LegalList
          items={[
            "Bloom Matrix",
            <>Support Email: <a href="mailto:aira@bloommatrix.in" className="text-primary hover:underline">aira@bloommatrix.in</a></>,
          ]}
        />
        <p>Registered Office Address:</p>
        <LegalList items={["352-1, Srinivasapuram Street, Avinashi, Tiruppur, Tamil Nadu – 641654, India"]} />
        <p>
          For more on how we collect, use, and protect data generally, see our{" "}
          <Link href="/privacy-policy" className="text-primary hover:underline">
            Privacy Policy
          </Link>
          .
        </p>
      </LegalSection>
    </LegalPageShell>
  );
}
