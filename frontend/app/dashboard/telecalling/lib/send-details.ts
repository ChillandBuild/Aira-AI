import type { SendDetailsTemplate, SendDetailsVariable } from "@/lib/api";

export const VARIABLE_LABEL: Record<NonNullable<SendDetailsVariable["role"]>, string> = {
  customer_name: "Customer name",
  business_name: "Business name",
  details: "Details",
  next_step: "Next step",
};

const LANGUAGE_NAME: Record<string, string> = {
  en: "English", en_US: "English", en_GB: "English", ta: "Tamil", hi: "Hindi", te: "Telugu", ml: "Malayalam", kn: "Kannada",
};

export function templateLabel(t: Pick<SendDetailsTemplate, "name" | "language">): string {
  return `${t.name} · ${LANGUAGE_NAME[t.language] ?? t.language}`;
}

export function renderTemplate(body: string, values: string[]): string {
  return body.replace(/\{\{\s*(\d+)\s*\}\}/g, (match, n: string) => {
    const value = values[Number(n) - 1];
    return value && value.trim() ? value : match;
  });
}

export function blankVariables(values: string[]): number {
  return values.filter((v) => !v.trim()).length;
}
