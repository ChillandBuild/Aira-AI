import { describe, it, expect } from "vitest";
import { chargePaise, gstPaise, parseGstPercent } from "./gst";

describe("gstPaise", () => {
  it("rounds 18% of 4900 paise to 882", () => {
    expect(gstPaise(4900, 18)).toBe(882);
  });

  it("rounds half-paise up", () => {
    expect(gstPaise(1050, 5)).toBe(53);
  });

  it("returns 0 when pct is 0 or amount is not positive", () => {
    expect(gstPaise(4900, 0)).toBe(0);
    expect(gstPaise(0, 18)).toBe(0);
    expect(gstPaise(-100, 18)).toBe(0);
  });
});

describe("chargePaise", () => {
  it("adds GST on top of the list price", () => {
    expect(chargePaise(4900, 18)).toBe(5782);
  });

  it("equals the list price when pct is 0", () => {
    expect(chargePaise(4900, 0)).toBe(4900);
  });
});

describe("parseGstPercent", () => {
  it("treats empty input as 0 with no error", () => {
    expect(parseGstPercent("  ")).toEqual({ value: 0, error: null });
  });

  it("accepts the 0 and 40 boundaries and decimals", () => {
    expect(parseGstPercent("0").error).toBeNull();
    expect(parseGstPercent("40").value).toBe(40);
    expect(parseGstPercent("2.5").value).toBe(2.5);
  });

  it("rejects out-of-range and non-numeric input", () => {
    expect(parseGstPercent("41").error).not.toBeNull();
    expect(parseGstPercent("-1").error).not.toBeNull();
    expect(parseGstPercent("abc").error).not.toBeNull();
  });
});
