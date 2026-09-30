import Link from "next/link";
import { headlineSentence } from "./brainLogic";
import type { BrainHeadline } from "./types";

export function HeadlineStrip({ headline }: { headline: BrainHeadline }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-2xl border border-border bg-white px-4 py-3 sm:px-5">
      <p className="min-w-0 break-words font-body text-sm text-ink">{headlineSentence(headline)}</p>
      <Link
        href="/dashboard/conversations"
        className="shrink-0 font-label text-xs font-bold text-primary hover:text-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        See it
      </Link>
    </div>
  );
}
