import Link from "next/link";
import ui from "./site.module.css";
import { CHANNELS, INDUSTRIES } from "./content";
import { Kicker } from "./primitives";
import s from "./HomeBlocks.module.css";

/** The channels Anril AI answers on, in place of a customer logo strip. */
export function ChannelStrip() {
  return (
    <section className={s.chans} aria-labelledby="chans-h">
      <h2 id="chans-h" className={s.chansH}>Works where your customers already message</h2>
      <ul>
        {CHANNELS.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
    </section>
  );
}

// Facts about the product, not customer results.
const FACTS = [
  { mark: "4", text: "modules in one platform: Reach, Engage, CallIQ and Commerce." },
  { mark: "24/7", text: "AI replies to enquiries, including nights, weekends and holidays." },
  { mark: "3", text: "lead marks, hot, warm and cold, updated with every new message." },
] as const;

export function ProductFacts() {
  return (
    <section className={s.figs} aria-label="Anril AI at a glance">
      {FACTS.map(({ mark, text }) => (
        <p key={text}>
          <span className={s.big}>{mark}</span> {text}
        </p>
      ))}
    </section>
  );
}

export function IndustryList() {
  return (
    <section className={`${ui.band} ${s.ind}`} id="industries" aria-labelledby="ind-h">
      <Kicker>Industries</Kicker>
      <h2 className={ui.secH} id="ind-h">Built for businesses that run on enquiries</h2>
      <p className={ui.lede}>Businesses in India and overseas use Anril AI to answer every enquiry and call the right lead first.</p>
      <ul>
        {INDUSTRIES.map((i) => (
          <li key={i.id}>
            <Link prefetch={false} href={`/new/industries#${i.id}`}>{i.name}</Link>
          </li>
        ))}
        <li>
          <Link prefetch={false} href="/new/industries#more">Any business</Link>
        </li>
      </ul>
    </section>
  );
}
