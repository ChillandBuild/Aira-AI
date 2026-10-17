import Link from "next/link";
import { AnrilLogo } from "@/components/logo";
import { CONTACT_EMAIL, LEGAL_LINKS, MAKER } from "./content";
import { Frame } from "./primitives";
import s from "./SiteFooter.module.css";

export function SiteFooter() {
  return (
    <Frame>
      <footer className={s.footer}>
        <div className={s.brand}>
          <Link prefetch={false} href="/new" className={s.logo} aria-label="Anril AI home">
            <AnrilLogo height={22} aria-hidden="true" focusable="false" />
          </Link>
          <p>
            A product of{" "}
            <a href={MAKER.href} rel="noopener">
              {MAKER.name}
            </a>
          </p>
        </div>
        <nav aria-label="Footer" className={s.nav}>
          {LEGAL_LINKS.map((l) => (
            <Link prefetch={false} key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
        </nav>
      </footer>
    </Frame>
  );
}
