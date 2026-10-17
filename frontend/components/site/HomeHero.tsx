import { getImageProps } from "next/image";
import { DEMO_HREF, DEMO_LABEL } from "./content";
import desktopPhoto from "./images/hero-desktop.jpg";
import mobilePhoto from "./images/hero-mobile.jpg";
import s from "./HomeHero.module.css";

// The laptop screen is a crisp 2x redraw of the dashboard composited into the photo (same layout,
// numbers and "Your Business" account name), so its text stays readable. Example numbers only.
const ALT = "A laptop on a sunlit desk showing the Anril AI dashboard, with a hand on the keyboard";

/** The whole photo at its own 16:9 shape (portrait crop on phones), with copy on its darker left side. */
export function HomeHero() {
  // q75: about 96 KB AVIF on desktop, 68 KB on phones. q60 smears the small labels on the laptop screen.
  const common = { alt: ALT, sizes: "100vw", quality: 75, priority: true } as const;
  const { props: { srcSet: mobileSrcSet } } = getImageProps({ ...common, src: mobilePhoto });
  const { props: desktopImg } = getImageProps({ ...common, src: desktopPhoto });

  return (
    <section className={s.hero} aria-labelledby="hero-h">
      <picture>
        <source media="(max-width: 700px)" srcSet={mobileSrcSet} sizes="100vw" />
        {/* eslint-disable-next-line @next/next/no-img-element -- art-directed <picture> built from getImageProps */}
        <img {...desktopImg} alt={ALT} className={s.photo} />
      </picture>
      <div className={s.copy}>
        <h1 id="hero-h" className={s.title}>
          Answer every enquiry.<br /> Call the right lead first.
        </h1>
        <p className={s.sub}>
          Anril AI answers every enquiry on WhatsApp, web chat and phone, shows you which leads are ready to buy, and
          gets your telecallers calling them first.
        </p>
        <div className={s.cta}>
          <a className={`${s.pill} ${s.white}`} href={DEMO_HREF}>
            {DEMO_LABEL}
          </a>
          <a className={`${s.pill} ${s.grey}`} href="#how">
            See how it works
          </a>
        </div>
      </div>
    </section>
  );
}
