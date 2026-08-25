import { describe, it, expect } from "vitest";
import { collectAllKeys, uniqueKey } from "./packageKeys";

describe("collectAllKeys", () => {
  it("collects package keys at every depth plus addon keys", () => {
    const packages = [
      { key: "basic", name: "Basic", amount_paise: 0, description: "", active: true, options: [
        { key: "basic_q", name: "One Question", amount_paise: 10000, description: "", active: true },
      ]},
      { key: "premium", name: "Premium", amount_paise: 50000, description: "", active: true, addons: [
        { key: "pdf", name: "PDF", amount_paise: 20000, description: "", active: true },
      ]},
    ];
    expect(collectAllKeys(packages)).toEqual(new Set(["basic", "basic_q", "premium", "pdf"]));
  });
});

describe("uniqueKey", () => {
  it("returns the base key when it's free", () => {
    expect(uniqueKey("basic", new Set(["premium"]))).toBe("basic");
  });

  it("appends a numeric suffix on collision", () => {
    expect(uniqueKey("basic", new Set(["basic"]))).toBe("basic_2");
  });

  it("keeps incrementing past multiple collisions", () => {
    expect(uniqueKey("basic", new Set(["basic", "basic_2", "basic_3"]))).toBe("basic_4");
  });
});
