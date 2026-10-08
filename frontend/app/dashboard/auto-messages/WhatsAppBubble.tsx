/** What the customer's phone will show. Uses WhatsApp's own chat colours on purpose, so it reads as "their phone", not as our UI. */
export function WhatsAppBubble({
  title,
  headerMedia,
  body,
  buttons,
  time,
}: {
  /** Small caption above the chat, e.g. "Priya will get". */
  title?: string;
  /** Template header type (IMAGE, VIDEO, DOCUMENT); shown as a grey block. */
  headerMedia?: string | null;
  /** The message text with sample values already filled in. */
  body: string;
  buttons: string[];
  time?: string;
}) {
  const stamp = time ?? new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
  return (
    <figure className="m-0 w-full rounded-2xl bg-[#e5ddd5] p-3" aria-label="Preview of the WhatsApp message">
      {title && <figcaption className="mb-2 font-label text-[11px] font-bold text-ink-secondary">{title}</figcaption>}
      <div className="max-w-[92%] overflow-hidden rounded-[4px_12px_12px_12px] bg-white px-3 pb-1.5 pt-2 shadow-sm">
        {headerMedia && (
          <div className="mb-2 flex h-20 items-center justify-center rounded-lg bg-surface-mid font-body text-[11px] text-ink-secondary">
            {`The template's ${headerMedia.toLowerCase()}`}
          </div>
        )}
        <p className="whitespace-pre-wrap break-words font-body text-[13px] leading-relaxed text-ink">{body}</p>
        <p className="mt-0.5 text-right font-body text-[10px] text-ink-secondary">{stamp}</p>
        {buttons.length > 0 && (
          <ul className="m-0 mt-1 list-none divide-y divide-border-subtle border-t border-border-subtle p-0">
            {buttons.map((b) => (
              <li key={b} className="py-2 text-center font-body text-[13px] font-semibold text-sky-700">
                {b}
              </li>
            ))}
          </ul>
        )}
      </div>
    </figure>
  );
}
