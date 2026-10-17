import type { ReactNode } from "react";
import s from "./InfoGrid.module.css";

export type InfoItem = { id?: string; title: string; body: ReactNode };

/** A hairline grid of short titled blocks, used by the inner pages for topics, plans and industries. */
export function InfoGrid({ items, label, className }: { items: readonly InfoItem[]; label?: string; className?: string }) {
  return (
    <ul className={className ? `${s.grid} ${className}` : s.grid} aria-label={label}>
      {items.map((item) => (
        <li key={item.title} id={item.id} className={s.cell}>
          <h2 className={s.title}>{item.title}</h2>
          <div className={s.body}>{item.body}</div>
        </li>
      ))}
    </ul>
  );
}
