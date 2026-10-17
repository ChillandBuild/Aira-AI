import type { Metadata } from "next";
import { INDUSTRIES } from "@/components/site/content";
import { DemoSection } from "@/components/site/DemoSection";
import card from "@/components/site/FeatureRow.module.css";
import { InfoGrid } from "@/components/site/InfoGrid";
import { PageIntro } from "@/components/site/PageIntro";
import { Eg, Frame } from "@/components/site/primitives";

export const metadata: Metadata = {
  title: "Industries",
  description:
    "Anril AI works for any business whose customers ask before they buy: education, real estate, healthcare, automotive, manufacturing, financial services and more.",
};

// What people ask is a plain description of each trade; the conversation and what
// happens next are illustrations, marked as examples on the page.
const ITEMS = [
  ...INDUSTRIES.map((i) => ({
    id: i.id,
    title: i.name,
    body: (
      <>
        <p>People often ask about {i.asks.charAt(0).toLowerCase() + i.asks.slice(1)}</p>
        <div className={`${card.msg} ${card.in}`}>
          {i.example}
          <small>Enquiry</small>
        </div>
        <div className={`${card.msg} ${card.out}`}>
          {i.reply}
          <small>Anril AI</small>
        </div>
        <p>{i.outcome}</p>
        <Eg>Example conversation</Eg>
      </>
    ),
  })),
  {
    id: "more",
    title: "Your business",
    body: (
      <>
        <p>
          Retail, travel, events, home services, hospitality: if your customers ask before they buy, Anril AI answers
          them, marks each lead hot, warm or cold, and sends the hot ones to your team.
        </p>
        <p>Tell us how enquiries reach you today, and we will show you how Anril AI would handle them.</p>
        <a href="#demo">Book a demo</a>
      </>
    ),
  },
];

export default function IndustriesPage() {
  return (
    <Frame>
      <PageIntro
        title="Built for any business that runs on enquiries"
        lede="Wherever people ask before they buy, Anril AI answers the enquiry, marks the lead hot, warm or cold, and sends the hot ones to your team. Here is how that could look in a few industries."
      >
        <Eg>The conversations below are examples, not customer data.</Eg>
      </PageIntro>
      <InfoGrid items={ITEMS} label="Industries" />
      <DemoSection />
    </Frame>
  );
}
