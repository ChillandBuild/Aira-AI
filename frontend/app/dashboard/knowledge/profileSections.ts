import { wordCount as countWords } from "./descriptionDiff";

export interface ProfileSection {
  key: string;
  heading: string;
  label: string;
  hint: string;
  word_limit: number;
  text: string;
  words: number;
}

export interface ProfileResponse {
  sections: ProfileSection[];
  other: string;
  total_words: number;
  hard_limit: number;
  is_structured: boolean;
}

export type SectionState = "ok" | "over";

// Section order as they appear in the UI
export const SECTION_KEYS_ORDERED = [
  "about",
  "how_to_buy",
  "who",
  "voice",
  "job",
  "never",
  "hours_contact",
  "handover",
] as const;

// Key of the section that holds the "when Anril brings in your team" wording.
export const HANDOVER_SECTION_KEY = "handover";

// Fallback help text for the two newest sections, used when the server sends no hint.
export const SECTION_HELP_FALLBACK: Record<string, string> = {
  hours_contact: "Mon–Sat 10am–7pm. Call 98xxxxxx10.",
  handover: "Our team will call you within 30 minutes.",
};

export function wordCount(text: string): number {
  return countWords(text);
}

export function totalWords(sections: Record<string, string>, other: string): number {
  let total = countWords(other);
  for (const text of Object.values(sections)) {
    total += countWords(text);
  }
  return total;
}

export function sectionState(words: number, limit: number): SectionState {
  return words > limit ? "over" : "ok";
}
