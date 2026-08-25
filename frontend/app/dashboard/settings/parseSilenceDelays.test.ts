import { describe, it, expect } from "vitest";
import { parseSilenceDelays } from "./parseSilenceDelays";

describe("parseSilenceDelays", () => {
  it("parses a single delay", () => {
    expect(parseSilenceDelays("5")).toEqual([5]);
  });

  it("parses multiple strictly increasing delays", () => {
    expect(parseSilenceDelays("5,60")).toEqual([5, 60]);
  });

  it("rejects non-increasing values", () => {
    expect(parseSilenceDelays("60,5")).toBeNull();
  });

  it("rejects more than 3 values", () => {
    expect(parseSilenceDelays("1,2,3,4")).toBeNull();
  });

  it("rejects values outside 1-1440", () => {
    expect(parseSilenceDelays("0")).toBeNull();
    expect(parseSilenceDelays("1441")).toBeNull();
  });

  it("rejects empty input", () => {
    expect(parseSilenceDelays("")).toBeNull();
  });
});
