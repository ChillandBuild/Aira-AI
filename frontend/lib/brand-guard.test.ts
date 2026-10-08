import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Brand rules (Navy + Teal rebrand): WhatsApp's own greens and the old violet
// brand never appear in our UI. This scan keeps them from creeping back in
// through a hard-coded hex.
const ROOT = path.resolve(__dirname, "..");
const SCANNED_DIRS = ["app", "components", "lib"];
const SOURCE_FILE = /\.(ts|tsx)$/;
const TEST_FILE = /\.test\.(ts|tsx)$/;

const FORBIDDEN: { label: string; pattern: RegExp }[] = [
  { label: "WhatsApp green #25D366", pattern: /#25D366/i },
  { label: "WhatsApp dark green #075E54", pattern: /#075E54/i },
  { label: "WhatsApp bubble green #DCF8C6", pattern: /#DCF8C6/i },
  // Old violet brand. Use the primary-* tokens (teal) instead.
  { label: "old brand violet #5b21b6 / #4c1d95 / #2e1065", pattern: /#(5b21b6|4c1d95|2e1065)/i },
];

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return SOURCE_FILE.test(name) && !TEST_FILE.test(name) ? [full] : [];
  });
}

const files = SCANNED_DIRS.flatMap((dir) => sourceFiles(path.join(ROOT, dir)));

describe("brand guard", () => {
  it("scans a real source tree", () => {
    expect(files.length).toBeGreaterThan(100);
  });

  it.each(FORBIDDEN)("no file contains $label", ({ pattern }) => {
    const hits = files.flatMap((file) =>
      readFileSync(file, "utf8")
        .split("\n")
        .flatMap((line, i) => (pattern.test(line) ? [`${path.relative(ROOT, file)}:${i + 1}`] : [])),
    );
    expect(hits).toEqual([]);
  });
});
