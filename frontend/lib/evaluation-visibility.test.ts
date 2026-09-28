import { describe, expect, it } from "vitest";
import { showsEvaluation } from "./evaluation-visibility";

describe("showsEvaluation", () => {
  it("shows evaluation UI only for telecmi", () => {
    expect(showsEvaluation("telecmi")).toBe(true);
  });

  it("hides evaluation UI for sim_basic", () => {
    expect(showsEvaluation("sim_basic")).toBe(false);
  });

  it("hides evaluation UI while the provider is still unknown", () => {
    expect(showsEvaluation(undefined)).toBe(false);
    expect(showsEvaluation(null)).toBe(false);
  });
});
