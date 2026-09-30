import { describe, expect, it } from "vitest";
import {
  NEEDS_MANAGE,
  OWNER_ONLY,
  bulkBlockedReason,
  bulkLabel,
  bulkTargets,
  chunkIds,
  dismissedSourceLabel,
  fixBlockedReason,
  mergeDismissResults,
  mergeFixResults,
  parseDismissResult,
  parseFixResult,
  parseRestoreResult,
  predictedSkip,
  sourceLabel,
  summarizeDismiss,
  summarizeFix,
  summarizeRestore,
  toggleId,
} from "./consistencyLogic";
import type { Issue } from "./types";

function issue(patch: Partial<Issue> = {}): Issue {
  return {
    id: "a1",
    kind: "price",
    where: "description",
    document_name: null,
    editable: true,
    quote: "Palm reading Rs 49",
    topic: "Price",
    truth: "Rs 29",
    proposed: "Palm reading Rs 29",
    section: "how_to_buy",
    section_label: "How customers buy",
    ...patch,
  };
}

describe("sourceLabel", () => {
  it("names the Description section", () => {
    expect(sourceLabel(issue())).toBe("Description > How customers buy");
  });
  it("says plain Description when no section was found", () => {
    expect(sourceLabel(issue({ section: null, section_label: null }))).toBe("Description");
    expect(sourceLabel(issue({ section_label: undefined }))).toBe("Description");
  });
  it("names the knowledge file", () => {
    expect(sourceLabel(issue({ where: "knowledge", document_name: "Diwali price list.pdf", section_label: null }))).toBe(
      "Knowledge > Diwali price list.pdf",
    );
  });
  it("falls back when a file has no name", () => {
    expect(sourceLabel(issue({ where: "knowledge", document_name: null }))).toBe("Knowledge > a document");
  });
});

describe("dismissedSourceLabel", () => {
  it("uses the same wording as a live row", () => {
    expect(
      dismissedSourceLabel({ where: "description", document_name: null, section_label: "How customers buy" }),
    ).toBe("Description > How customers buy");
  });
});

describe("fixBlockedReason", () => {
  it("lets an owner fix anything", () => {
    expect(fixBlockedReason(issue(), { canManage: true, isOwner: true })).toBeNull();
  });
  it("says Owner only for a Description fix by a non-owner manager", () => {
    expect(fixBlockedReason(issue(), { canManage: true, isOwner: false })).toBe(OWNER_ONLY);
  });
  it("lets a non-owner manager fix a file", () => {
    expect(fixBlockedReason(issue({ where: "knowledge" }), { canManage: true, isOwner: false })).toBeNull();
  });
  it("Needs manage access wins over Owner only", () => {
    expect(fixBlockedReason(issue(), { canManage: false, isOwner: false })).toBe(NEEDS_MANAGE);
    expect(fixBlockedReason(issue(), { canManage: false, isOwner: true })).toBe(NEEDS_MANAGE);
  });
});

describe("bulkBlockedReason", () => {
  it("needs manage access for both actions", () => {
    expect(bulkBlockedReason({ canManage: false, isOwner: true })).toBe(NEEDS_MANAGE);
    expect(bulkBlockedReason({ canManage: true, isOwner: false })).toBeNull();
  });
});

describe("predictedSkip", () => {
  const owner = { canManage: true, isOwner: true };
  it("warns about a Description item for a non-owner", () => {
    expect(predictedSkip(issue(), "fix", { canManage: true, isOwner: false })).toMatch(/owner only/i);
  });
  it("warns about an item with no suggested wording", () => {
    expect(predictedSkip(issue({ proposed: null }), "fix", owner)).toMatch(/no suggested wording/i);
  });
  it("warns about a file that is not sorted", () => {
    expect(predictedSkip(issue({ where: "knowledge", editable: false }), "fix", owner)).toMatch(/not sorted/i);
  });
  it("never warns on dismiss", () => {
    expect(predictedSkip(issue({ proposed: null }), "dismiss", { canManage: true, isOwner: false })).toBeNull();
  });
  it("is null for a clean item", () => {
    expect(predictedSkip(issue(), "fix", owner)).toBeNull();
  });
});

describe("selection", () => {
  it("toggleId returns a new set", () => {
    const start = new Set(["a"]);
    const added = toggleId(start, "b");
    expect(Array.from(added).sort()).toEqual(["a", "b"]);
    expect(Array.from(start)).toEqual(["a"]);
    expect(Array.from(toggleId(added, "a"))).toEqual(["b"]);
  });
  it("bulkTargets is everything when nothing is ticked", () => {
    const list = [issue({ id: "1" }), issue({ id: "2" })];
    expect(bulkTargets(list, new Set()).map((i) => i.id)).toEqual(["1", "2"]);
    expect(bulkTargets(list, new Set(["2", "gone"])).map((i) => i.id)).toEqual(["2"]);
  });
  it("bulkLabel counts all or the ticked ones", () => {
    expect(bulkLabel("fix", 5, 0)).toBe("Fix all (5)");
    expect(bulkLabel("dismiss", 5, 0)).toBe("Dismiss all (5)");
    expect(bulkLabel("fix", 5, 2)).toBe("Fix selected (2)");
  });
});

describe("chunkIds", () => {
  it("splits into batches the server accepts", () => {
    const ids = Array.from({ length: 205 }, (_, i) => String(i));
    expect(chunkIds(ids, 100).map((c) => c.length)).toEqual([100, 100, 5]);
    expect(chunkIds([], 100)).toEqual([]);
  });
});

describe("parse results", () => {
  it("tolerates missing arrays", () => {
    expect(parseFixResult({ success: true })).toEqual({ applied: [], skipped: [], failed: [] });
    expect(parseDismissResult(null)).toEqual({ dismissed: [], skipped: [] });
    expect(parseRestoreResult(undefined)).toEqual({ restored: [], skipped: [] });
  });
  it("keeps well-formed notes and drops malformed ones", () => {
    const parsed = parseFixResult({
      applied: ["a", 3],
      skipped: [{ id: "b", reason: "Owner only", code: "owner_only" }, { nope: 1 }],
      failed: [{ id: "c", reason: "Text changed", code: "text_changed" }],
    });
    expect(parsed.applied).toEqual(["a"]);
    expect(parsed.skipped).toEqual([{ id: "b", reason: "Owner only", code: "owner_only" }]);
    expect(parsed.failed).toHaveLength(1);
  });
});

describe("merge results", () => {
  it("concatenates chunked fix results", () => {
    const merged = mergeFixResults(
      { applied: ["a"], skipped: [{ id: "s", reason: "r" }], failed: [] },
      { applied: ["b"], skipped: [], failed: [{ id: "f", reason: "r" }] },
    );
    expect(merged.applied).toEqual(["a", "b"]);
    expect(merged.skipped).toHaveLength(1);
    expect(merged.failed).toHaveLength(1);
  });
  it("concatenates chunked dismiss results", () => {
    expect(mergeDismissResults({ dismissed: ["a"], skipped: [] }, { dismissed: ["b"], skipped: [] }).dismissed).toEqual(["a", "b"]);
  });
});

describe("summarizeFix", () => {
  it("reports applied, skipped and failed, none silent", () => {
    const text = summarizeFix({
      applied: ["1", "2", "3", "4", "5"],
      skipped: [
        { id: "6", reason: "Owner only", code: "owner_only" },
        { id: "7", reason: "Owner only", code: "owner_only" },
      ],
      failed: [{ id: "8", reason: "The quoted text changed.", code: "text_changed" }],
    });
    expect(text).toBe("Fixed 5. Skipped 2 (owner only). 1 failed: the quoted text changed.");
  });
  it("groups several skip reasons", () => {
    const text = summarizeFix({
      applied: ["1"],
      skipped: [
        { id: "2", reason: "x", code: "owner_only" },
        { id: "3", reason: "x", code: "owner_only" },
        { id: "4", reason: "x", code: "no_proposal" },
      ],
      failed: [],
    });
    expect(text).toBe("Fixed 1. Skipped 3 (2 owner only, 1 no suggested wording).");
  });
  it("lists distinct failure reasons, capped", () => {
    const failed = ["a", "b", "c", "d"].map((r, i) => ({ id: String(i), reason: `Reason ${r}.` }));
    expect(summarizeFix({ applied: [], skipped: [], failed })).toBe(
      "Nothing was fixed. 4 failed: reason a; reason b; reason c and 1 more.",
    );
  });
  it("falls back to the server sentence for an unknown skip code", () => {
    expect(summarizeFix({ applied: [], skipped: [{ id: "1", reason: "Odd thing.", code: "brand_new" }], failed: [] })).toBe(
      "Nothing was fixed. Skipped 1 (odd thing).",
    );
  });
  it("keeps a leading currency code or name as written", () => {
    expect(summarizeFix({ applied: [], skipped: [], failed: [{ id: "1", reason: "Rs 49 is not on your Services page." }] })).toBe(
      "Nothing was fixed. 1 failed: Rs 49 is not on your Services page.",
    );
  });
  it("says so when nothing happened at all", () => {
    expect(summarizeFix({ applied: [], skipped: [], failed: [] })).toBe("Nothing was fixed.");
  });
});

describe("summarizeDismiss and summarizeRestore", () => {
  it("dismiss", () => {
    expect(
      summarizeDismiss({ dismissed: ["1", "2"], skipped: [{ id: "3", reason: "Gone", code: "not_found" }] }),
    ).toBe("Dismissed 2. Skipped 1 (no longer listed).");
  });
  it("restore", () => {
    expect(summarizeRestore({ restored: ["1"], skipped: [] })).toBe("Restored 1.");
    expect(summarizeRestore({ restored: [], skipped: [{ id: "1", reason: "x", code: "not_dismissed" }] })).toBe(
      "Nothing was restored. Skipped 1 (not dismissed).",
    );
  });
});
