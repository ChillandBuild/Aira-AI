import type { ReactNode } from "react";
import ui from "./site.module.css";

/** The centred, hairline-framed column every section below the hero sits in. */
export function Frame({ children }: { children: ReactNode }) {
  return (
    <div className={ui.page}>
      <div className={ui.frame}>{children}</div>
    </div>
  );
}

/** Copper label with a trailing rule, as in the mockup ("01 Answer"). */
export function Kicker({ children }: { children: ReactNode }) {
  return <span className={`${ui.kicker} ${ui.num}`}>{children}</span>;
}

/** Small mono note marking example or illustrative content. */
export function Eg({ children }: { children: ReactNode }) {
  return <span className={ui.eg}>{children}</span>;
}
