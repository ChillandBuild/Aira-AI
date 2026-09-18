import type {
  KnowledgeConflictChoice,
  KnowledgeHunk,
  KnowledgeReview,
} from "@/lib/api";

// Mirror of backend/app/services/description_diff.py (and the tail of
// knowledge_sort.compute_final_description) so the review screen can preview the exact
// Description the server will save. The server stays authoritative; hunk positions
// index into splitLines() on both sides, so the two splitters must stay identical.

export function normalize(line: string | null | undefined): string {
  return (line ?? "").split(/\s+/).filter(Boolean).join(" ");
}

/** \r\n and \r become \n, and one trailing newline is ignored — same as lines_of(). */
export function splitLines(text: string | null | undefined): string[] {
  const t = (text ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!t) return [];
  const parts = t.split("\n");
  if (parts[parts.length - 1] === "") parts.pop();
  return parts;
}

/** Whole-text comparison key: blank lines and spacing don't count as changes. */
export function normalizeText(text: string | null | undefined): string {
  return splitLines(text).map(normalize).filter(Boolean).join("\n");
}

export function applyHunks(current: string, hunks: KnowledgeHunk[], accepted: Set<string>): string {
  const a = splitLines(current);
  const out: string[] = [];
  let pos = 0;
  for (const h of hunks) {
    out.push(...a.slice(pos, h.start));
    out.push(...(accepted.has(h.id) ? h.new_lines : h.old_lines));
    pos = h.start + h.old_lines.length;
  }
  out.push(...a.slice(pos));
  return out.join("\n");
}

/** An UPPERCASE line such as "WHAT YOU MUST NEVER DO"; needs an ASCII capital so a
 *  line in a caseless script (Tamil, Hindi) is never taken for a heading. */
export function isHeadingLine(line: string): boolean {
  const s = line.trim();
  return s.length > 0 && s.length <= 60 && s === s.toUpperCase() && /[A-Z]/.test(s);
}

export function insertUnderHeading(text: string, heading: string, line: string): string {
  const lines = splitLines(text);
  const target = normalize(heading).toUpperCase();
  const idx = target ? lines.findIndex((l) => normalize(l).toUpperCase() === target) : -1;
  if (idx === -1) return lines.length ? [...lines, line].join("\n") : line;
  let end = idx + 1;
  while (end < lines.length && !isHeadingLine(lines[end])) end++;
  while (end > idx + 1 && !lines[end - 1].trim()) end--;
  lines.splice(end, 0, line);
  return lines.join("\n");
}

export function replaceExactLine(text: string, oldLine: string, newLine: string): string | null {
  const lines = splitLines(text);
  const target = normalize(oldLine);
  const i = target ? lines.findIndex((l) => normalize(l) === target) : -1;
  if (i === -1) return null;
  lines[i] = newLine;
  return lines.join("\n");
}

export function wordCount(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

export interface ReviewChoices {
  acceptedHunkIds: Set<string>;
  conflictChoices: Record<string, KnowledgeConflictChoice>;
  acceptedUpdateIds: Set<string>;
}

/** The Description Apply would save — mirrors compute_final_description(). */
export function buildFinalDescription(review: KnowledgeReview, choices: ReviewChoices): string {
  let text = applyHunks(review.base_description, review.hunks, choices.acceptedHunkIds);
  for (const c of review.conflicts) {
    const pick = choices.conflictChoices[c.id] ?? "none";
    if (pick === "a" || pick === "b") {
      text = insertUnderHeading(text, c.heading, pick === "a" ? c.option_a : c.option_b);
    }
  }
  for (const d of review.fact_disagreements) {
    if (d.where === "description" && choices.acceptedUpdateIds.has(d.id) && d.existing_line && d.proposed_line) {
      const replaced = replaceExactLine(text, d.existing_line, d.proposed_line);
      if (replaced !== null) text = replaced;
    }
  }
  return text.trim();
}

export type DiffRow = { type: "same" | "add" | "remove"; text: string };

/** Plain LCS line diff for the History view — display only. */
export function lineDiff(before: string, after: string): DiffRow[] {
  const a = splitLines(before);
  const b = splitLines(after);
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] =
        normalize(a[i]) === normalize(b[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (normalize(a[i]) === normalize(b[j])) {
      rows.push({ type: "same", text: b[j] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push({ type: "remove", text: a[i++] });
    } else {
      rows.push({ type: "add", text: b[j++] });
    }
  }
  while (i < n) rows.push({ type: "remove", text: a[i++] });
  while (j < m) rows.push({ type: "add", text: b[j++] });
  return rows;
}
