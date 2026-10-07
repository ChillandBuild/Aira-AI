import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildComponents, normalizeEvent, normalizePhone, parsePayload, type Context } from "../src/core.js";

const VECTORS = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "spec", "vectors");
const load = (name: string) => JSON.parse(readFileSync(join(VECTORS, name), "utf8"));

const components = load("components.json");
const normalize = load("normalize.json");
const parse = load("parse.json");

describe("components vectors", () => {
  for (const c of components.cases) {
    it(c.name, () => {
      expect(buildComponents(c.template, c.rule, c.ctx as Context)).toEqual(c.expected_components);
    });
  }
});

describe("normalize_event vectors", () => {
  for (const [input, expected] of normalize.events as [string | null, string | null][]) {
    it(`event ${JSON.stringify(input)} -> ${expected}`, () => {
      expect(normalizeEvent(input)).toBe(expected);
    });
  }
});

describe("normalize_phone vectors", () => {
  for (const [input, expected] of normalize.phones as [string | null, string | null][]) {
    it(`phone ${JSON.stringify(input)} -> ${expected}`, () => {
      expect(normalizePhone(input)).toBe(expected);
    });
  }
});

describe("parse_payload vectors", () => {
  for (const c of parse.cases) {
    it(c.name, () => {
      expect(parsePayload(c.payload)).toEqual(c.expected);
    });
  }
});

describe("python/js regex differences", () => {
  const ctx = (extra: Record<string, string>): Context => ({
    first_name: "A", full_name: "A", page_url: "", phone: "+91", extra,
  });
  const spec = { variables: [{ source: "extra", key: "k", fallback: "FB" }] };
  const tpl = { body_text: "{{1}}" };
  const out = (value: string) =>
    (buildComponents(tpl, spec, ctx({ k: value })) as any)[0].parameters[0].text;

  it("unicode letters count as word chars (python \\b)", () => {
    expect(out("éa.com")).toBe("éa.com");
    expect(out("a.comé")).toBe("a.comé");
    expect(out("a.com")).toBe("FB");
  });
  it("python-only whitespace (\\x1f, \\x85) is collapsed; \\ufeff is not", () => {
    expect(out("a\x1fb\x85c")).toBe("a b c");
    expect(out("a﻿b")).toBe("a﻿b");
  });
  it("truncates by code point, not UTF-16 unit", () => {
    expect(Array.from(out("\u{1F600}".repeat(600))).length).toBe(500);
  });
});
