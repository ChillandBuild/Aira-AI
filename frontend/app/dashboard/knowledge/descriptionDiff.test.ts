import { describe, it, expect } from "vitest";
import type { KnowledgeHunk, KnowledgeReview } from "@/lib/api";
import {
  applyHunks,
  buildFinalDescription,
  insertUnderHeading,
  isHeadingLine,
  lineDiff,
  normalizeText,
  replaceExactLine,
  splitLines,
  wordCount,
} from "./descriptionDiff";

const BASE = "ABOUT US\nWe are AstroTamil.\n\nWHAT YOU MUST NEVER DO\n- Never predict.";

function review(partial: Partial<KnowledgeReview>): KnowledgeReview {
  return {
    review_id: "r", document_id: "d", document_name: "f.docx", origin: "upload", stale: false,
    base_version_id: "v", base_description: BASE, proposed_description: BASE, hunks: [], conflicts: [],
    fact_disagreements: [], facts: "", unverified: [], left_out: [], left_out_rules: [], truncated: false,
    replaces_document: null, word_count: 0, soft_word_limit: 1200, ...partial,
  };
}

// Same hunk the backend emits for "- Never predict." -> "- Never predict dates." plus an added line.
const HUNKS: KnowledgeHunk[] = [
  { id: "h1", kind: "change", start: 4, old_lines: ["- Never predict."], new_lines: ["- Never predict dates.", "- Never guarantee."], touches_client_lines: true },
];

describe("splitLines", () => {
  it("matches the backend splitter", () => {
    expect(splitLines("a\r\nb\n")).toEqual(["a", "b"]);
    expect(splitLines("a\n\n")).toEqual(["a", ""]);
    expect(splitLines("")).toEqual([]);
  });
});

describe("applyHunks", () => {
  it("applies ticked hunks and keeps unticked ones", () => {
    expect(applyHunks(BASE, HUNKS, new Set(["h1"]))).toBe(
      "ABOUT US\nWe are AstroTamil.\n\nWHAT YOU MUST NEVER DO\n- Never predict dates.\n- Never guarantee.",
    );
    expect(applyHunks(BASE, HUNKS, new Set())).toBe(BASE);
  });
});

describe("headings", () => {
  it("detects uppercase headings but not caseless scripts", () => {
    expect(isHeadingLine("WHAT YOU MUST NEVER DO")).toBe(true);
    expect(isHeadingLine("- Never predict.")).toBe(false);
    expect(isHeadingLine("வணக்கம்")).toBe(false);
  });

  it("inserts at the end of the heading's section, or at the end", () => {
    expect(splitLines(insertUnderHeading(BASE, "about us", "Since 2025.")).slice(0, 3)).toEqual([
      "ABOUT US", "We are AstroTamil.", "Since 2025.",
    ]);
    expect(splitLines(insertUnderHeading(BASE, "GREETINGS", "Say vanakkam.")).pop()).toBe("Say vanakkam.");
    expect(insertUnderHeading("", "X", "Only line")).toBe("Only line");
  });
});

describe("replaceExactLine", () => {
  it("swaps a whitespace-equal line or reports it gone", () => {
    expect(replaceExactLine("Price  29.\nOther", "Price 29.", "Price 49.")).toBe("Price 49.\nOther");
    expect(replaceExactLine("Other", "Price 29.", "Price 49.")).toBeNull();
  });
});

describe("buildFinalDescription", () => {
  it("combines hunks, a conflict pick and a price update like the server", () => {
    const r = review({
      base_description: BASE + "\n- Starts from 29.",
      hunks: HUNKS,
      conflicts: [{ id: "c1", topic: "t", heading: "ABOUT US", option_a: "A", source_a: "", option_b: "Say vanakkam.", source_b: "" }],
      fact_disagreements: [{
        id: "d1", where: "description", topic: "price", new_value: "49", existing_value: "29",
        document_name: null, existing_line: "- Starts from 29.", proposed_line: "- Starts from 49.", client_line: false,
      }],
    });
    const out = buildFinalDescription(r, {
      acceptedHunkIds: new Set(["h1"]),
      conflictChoices: { c1: "b" },
      acceptedUpdateIds: new Set(["d1"]),
    });
    expect(splitLines(out)).toEqual([
      "ABOUT US", "We are AstroTamil.", "Say vanakkam.", "", "WHAT YOU MUST NEVER DO",
      "- Never predict dates.", "- Never guarantee.", "- Starts from 49.",
    ]);
  });

  it("leaves both conflict options out by default", () => {
    const r = review({ conflicts: [{ id: "c1", topic: "t", heading: "", option_a: "A", source_a: "", option_b: "B", source_b: "" }] });
    expect(buildFinalDescription(r, { acceptedHunkIds: new Set(), conflictChoices: {}, acceptedUpdateIds: new Set() })).toBe(BASE);
  });
});

describe("small helpers", () => {
  it("normalizeText ignores spacing and blank lines", () => {
    expect(normalizeText("a  b\n\n c ")).toBe(normalizeText("a b\nc"));
  });

  it("wordCount counts words", () => {
    expect(wordCount("  one two\nthree ")).toBe(3);
  });

  it("lineDiff marks added and removed lines", () => {
    expect(lineDiff("a\nb\nc", "a\nc\nd")).toEqual([
      { type: "same", text: "a" }, { type: "remove", text: "b" }, { type: "same", text: "c" }, { type: "add", text: "d" },
    ]);
  });
});
