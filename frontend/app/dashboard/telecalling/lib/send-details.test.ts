import { describe, expect, it } from "vitest";
import { blankVariables, renderTemplate, templateLabel } from "./send-details";

describe("send details helpers", () => {
  it("renders filled blanks and keeps empty ones visible", () => {
    expect(renderTemplate("Hi {{1}}, from {{2}}. {{3}}", ["Priya", "Astro Tamil", " "])).toBe("Hi Priya, from Astro Tamil. {{3}}");
  });

  it("counts blanks", () => {
    expect(blankVariables(["a", "", "  "])).toBe(2);
  });

  it("names templates with their language", () => {
    expect(templateLabel({ name: "call_details_share", language: "ta" })).toBe("call_details_share · Tamil");
    expect(templateLabel({ name: "promo", language: "xx" })).toBe("promo · xx");
  });
});
