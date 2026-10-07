/**
 * Helpers that reproduce Python str semantics, so the vectors generated from the backend pass
 * byte-for-byte. Differences handled here:
 *  - Python str.strip() / re \s use Unicode whitespace (includes \x1c-\x1f, \x85; excludes ﻿).
 *  - Python slicing counts code points; JS counts UTF-16 units.
 *  - Python re \d / \w / \b are Unicode aware; JS needs \p{Nd} / \p{L}\p{N}_ and lookarounds.
 *  - str(True) is "True", str(None) is "None".
 */

const WS_CHARS = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";

/** Regex source for one Python-style whitespace char. */
export const PY_WS = `[${WS_CHARS}]`;
const PY_WS_RUN = new RegExp(`${PY_WS}+`, "gu");
const PY_STRIP = new RegExp(`^${PY_WS}+|${PY_WS}+$`, "gu");

/** Python str.strip(). */
export function pyStrip(value: string): string {
  return value.replace(PY_STRIP, "");
}

/** Python re.sub(r"\s+", " ", value). */
export function collapseWhitespace(value: string): string {
  return value.replace(PY_WS_RUN, " ");
}

/** Python value[:n] (by code point). */
export function pySlice(value: string, max: number): string {
  const points = Array.from(value);
  return points.length <= max ? value : points.slice(0, max).join("");
}

/** Python len(str) (by code point). */
export function pyLen(value: string): number {
  return Array.from(value).length;
}

/** Python str(value) for the JSON scalars we see; objects are not expected here. */
export function pyStr(value: unknown): string {
  if (value === true) return "True";
  if (value === false) return "False";
  if (value === null || value === undefined) return "None";
  return String(value);
}

/** Python truthiness for JSON values. */
export function pyTruthy(value: unknown): boolean {
  if (value === null || value === undefined || value === false || value === 0 || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as object).length > 0;
  return true;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** dict.get(key) that never reads the prototype chain. */
export function ownGet(record: unknown, key: string): unknown {
  return isRecord(record) && Object.prototype.hasOwnProperty.call(record, key) ? record[key] : undefined;
}
