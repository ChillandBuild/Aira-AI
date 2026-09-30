import { describe, it, expect } from "vitest";
import {
  wordCount,
  totalWords,
  sectionState,
  SECTION_KEYS_ORDERED,
  SECTION_HELP_FALLBACK,
  HANDOVER_SECTION_KEY,
} from "./profileSections";

describe("profileSections", () => {
  describe("wordCount", () => {
    it("counts words correctly", () => {
      expect(wordCount("")).toBe(0);
      expect(wordCount("hello")).toBe(1);
      expect(wordCount("hello world")).toBe(2);
      expect(wordCount("  hello   world  ")).toBe(2);
      expect(wordCount("one two three four five")).toBe(5);
    });

    it("handles multiple spaces and newlines", () => {
      expect(wordCount("hello\n\nworld")).toBe(2);
      expect(wordCount("a  b  c")).toBe(3);
    });
  });

  describe("totalWords", () => {
    it("sums words from all sections and other", () => {
      const sections = {
        about: "hello world",
        how_to_buy: "buy now",
        who: "customers",
      };
      const other = "extra text";
      expect(totalWords(sections, other)).toBe(7); // 2 + 2 + 1 + 2
    });

    it("handles empty sections", () => {
      const sections = {
        about: "",
        how_to_buy: "buy now",
      };
      expect(totalWords(sections, "")).toBe(2);
    });

    it("counts only other when no sections", () => {
      expect(totalWords({}, "one two three")).toBe(3);
    });
  });

  describe("totalWords with 8 sections", () => {
    it("counts the new sections toward the total", () => {
      const sections = { about: "one two", hours_contact: "Mon to Sat", handover: "we call you" };
      expect(totalWords(sections, "")).toBe(8);
    });
  });

  describe("sectionState", () => {
    it("returns ok when under limit", () => {
      expect(sectionState(10, 50)).toBe("ok");
      expect(sectionState(50, 50)).toBe("ok");
    });

    it("returns over when exceeding limit", () => {
      expect(sectionState(51, 50)).toBe("over");
      expect(sectionState(100, 50)).toBe("over");
    });
  });

  describe("SECTION_KEYS_ORDERED", () => {
    it("has the correct order", () => {
      expect(SECTION_KEYS_ORDERED).toEqual([
        "about",
        "how_to_buy",
        "who",
        "voice",
        "job",
        "never",
        "hours_contact",
        "handover",
      ]);
    });

    it("has 8 sections with the two new ones last", () => {
      expect(SECTION_KEYS_ORDERED).toHaveLength(8);
      expect(SECTION_KEYS_ORDERED.slice(-2)).toEqual(["hours_contact", "handover"]);
    });

    it("exposes the handover key and help text for the new sections", () => {
      expect(SECTION_KEYS_ORDERED).toContain(HANDOVER_SECTION_KEY);
      expect(SECTION_HELP_FALLBACK.hours_contact).toBeTruthy();
      expect(SECTION_HELP_FALLBACK.handover).toBeTruthy();
    });
  });
});
