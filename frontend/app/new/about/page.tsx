import type { Metadata } from "next";
import Link from "next/link";
import ui from "@/components/site/site.module.css";
import { CONTACT_EMAIL, MAKER } from "@/components/site/content";
import { DemoSection } from "@/components/site/DemoSection";
import { InfoGrid } from "@/components/site/InfoGrid";
import { PageIntro } from "@/components/site/PageIntro";
import { Frame, Kicker } from "@/components/site/primitives";

export const metadata: Metadata = {
  title: "Company",
  description: `Anril AI is a product of ${MAKER.name}. Talk to us: ${CONTACT_EMAIL}.`,
};

const ABOUT = [
  {
    title: "Who we are",
    body: (
      <>
        <p>Anril AI is a product of {MAKER.name}.</p>
        <a href={MAKER.href} rel="noopener">
          Visit {MAKER.name}
        </a>
      </>
    ),
  },
  {
    title: "What we build",
    body: (
      <>
        <p>
          A business communication and sales growth platform. Four modules, Reach, Engage, CallIQ and Commerce, take a
          business from first message to final sale.
        </p>
        <Link prefetch={false} href="/new/pricing">
          See the four modules
        </Link>
      </>
    ),
  },
  {
    title: "Who it is for",
    body: (
      <>
        <p>
          Any business whose customers ask before they buy, from coaching institutes to car showrooms. Our customers
          are in India and overseas.
        </p>
        <Link prefetch={false} href="/new/industries">
          See examples by industry
        </Link>
      </>
    ),
  },
];

export default function AboutPage() {
  return (
    <Frame>
      <PageIntro
        title="About Anril AI"
        lede="From first message to final sale. Anril AI answers enquiries, shows you which leads are ready to buy, and helps your team call the right lead first."
      />
      <InfoGrid items={ABOUT} label="About" />
      <section className={ui.band} id="contact" aria-labelledby="contact-h">
        <Kicker>Contact</Kicker>
        <h2 className={ui.secH} id="contact-h">Talk to us</h2>
        <p className={ui.lede}>
          Email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>, or book a demo below.
        </p>
      </section>
      <DemoSection />
    </Frame>
  );
}
