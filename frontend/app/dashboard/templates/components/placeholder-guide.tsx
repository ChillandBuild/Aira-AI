"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Lightbulb, Wand2 } from "lucide-react";

/*
  Placeholder guide on the template editor. Aira is sold to many businesses,
  so this explains the one mechanism every template shares — numbered
  placeholders filled in order — without naming any client. The examples are
  one click away from being the body, samples included, so a first template
  can be written by someone who has never seen a WhatsApp template before.
*/

type Example = {
  title: string;
  when: string;
  body: string;
  samples: Record<number, string>;
};

const EXAMPLES: Example[] = [
  {
    title: "No placeholder",
    when: "Same text for everyone. Simplest to get approved.",
    body: "Your request has been received. We will get back to you within one working day.",
    samples: {},
  },
  {
    title: "One placeholder: {{1}} = customer's name",
    when: "A personal greeting. Your app sends the name as the first value.",
    body: "Hi {{1}}, thanks for reaching out. Your request has been received and our team is on it.",
    samples: { 1: "Priya" },
  },
  {
    title: "Two: {{1}} = name, {{2}} = what it is about",
    when: "An order, booking, ticket or service name as the second value.",
    body: "Hi {{1}}\nYour {{2}} is ready. Open the app to see it.",
    samples: { 1: "Priya", 2: "Order #4821" },
  },
  {
    title: "Three: {{1}} = name, {{2}} = subject, {{3}} = your brand",
    when: "Lets one template serve several apps or brands.",
    body: "Hi {{1}}, thank you for choosing {{3}}.\n\nHere is an update on your {{2}}. Reply to this message if you have any questions.",
    samples: { 1: "Priya", 2: "Order #4821", 3: "Acme Stores" },
  },
];

export default function PlaceholderGuide({ onUse }: { onUse: (body: string, samples: Record<number, string>) => void }) {
  const [open, setOpen] = useState(false);
  const [confirmIdx, setConfirmIdx] = useState<number | null>(null);

  return (
    <div className="rounded-2xl border border-primary-100 bg-primary-50/40">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        <Lightbulb size={14} className="text-primary-600" />
        <span className="font-body text-sm font-semibold text-ink">How placeholders work, with examples to start from</span>
        <span className="ml-auto text-ink-muted">{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
      </button>

      {open && (
        <div className="space-y-4 px-4 pb-4 font-body text-xs text-ink-secondary">
          <ul className="list-disc space-y-1 pl-5">
            <li>
              A placeholder is <code className="font-mono">{"{{1}}"}</code>, <code className="font-mono">{"{{2}}"}</code>, <code className="font-mono">{"{{3}}"}</code>… in the body. Numbers only, starting at 1, no gaps.
            </li>
            <li>
              <strong>The numbers carry no meaning of their own.</strong> Whoever sends the template fills them in order. From a broadcast in Aira you pick a lead field for each one. From your own app through the API, your app sends a list of values: the first fills <code className="font-mono">{"{{1}}"}</code>, the second <code className="font-mono">{"{{2}}"}</code>, and so on.
            </li>
            <li>
              An app may send <strong>more</strong> values than a template uses; the extras are ignored. That is how one app can send the same fixed list to every template. Sending <strong>fewer</strong> is refused, because WhatsApp would refuse it too.
            </li>
            <li>
              Meta&apos;s reviewer needs a <strong>sample value</strong> for each placeholder. Give a realistic one; the sample is never sent to anyone.
            </li>
            <li>
              Keep placeholders in the body. A placeholder in the header or in a button link cannot be filled by an app.
            </li>
          </ul>

          <div className="grid gap-3 md:grid-cols-2">
            {EXAMPLES.map((ex, i) => (
              <div key={ex.title} className="flex flex-col rounded-xl border border-border-subtle bg-white p-3">
                <p className="font-semibold text-ink">{ex.title}</p>
                <p className="mt-0.5 text-[11px] text-ink-muted">{ex.when}</p>
                <pre className="mt-2 flex-1 whitespace-pre-wrap rounded-lg bg-surface-subtle p-2.5 font-mono text-[11px] leading-relaxed text-ink">{ex.body}</pre>
                {confirmIdx === i ? (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-[11px] text-ink-muted">Replace what is in the body?</span>
                    <button
                      type="button"
                      onClick={() => { onUse(ex.body, ex.samples); setConfirmIdx(null); }}
                      className="rounded-md bg-primary-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-primary-700"
                    >
                      Yes, use it
                    </button>
                    <button type="button" onClick={() => setConfirmIdx(null)} className="text-[11px] text-ink-muted hover:text-ink">Keep mine</button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmIdx(i)}
                    className="mt-2 inline-flex items-center gap-1 self-start rounded-md border border-primary-200 bg-primary-50 px-2 py-1 text-[11px] font-semibold text-primary-700 hover:border-primary-400"
                  >
                    <Wand2 size={11} /> Use this example
                  </button>
                )}
              </div>
            ))}
          </div>

          <p className="text-[11px] text-ink-muted">
            Your own app&apos;s developer will find what each placeholder number receives, and how extra values are handled, on the
            <strong> Developer</strong> page in the sidebar.
          </p>
        </div>
      )}
    </div>
  );
}
