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
export const SECTION_KEYS_ORDERED = ["about", "how_to_buy", "who", "voice", "job", "never"] as const;

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
