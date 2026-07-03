export type Button = {
  type: 'QUICK_REPLY' | 'URL' | 'PHONE_NUMBER' | 'WHATSAPP_CALL' | 'COPY_CODE' | 'ONE_TAP';
  text: string;
  url?: string;
  phone?: string;
  country?: string;
  offer_code?: string;
  active_for_days?: number;
  autofill_text?: string;
  package_name?: string;
  signature_hash?: string;
};

export type CarouselCard = {
  header_media_type: 'IMAGE' | 'VIDEO';
  header_media_url: string;
  body_text: string;
  buttons: Array<{ type: string; text: string; url?: string }>;
};

export type Template = {
  id: string;
  name: string;
  category: string;
  language: string;
  body_text: string;
  header_text?: string;
  header_media_type?: string;
  header_media_url?: string;
  header_media_id?: string;
  footer_text?: string;
  buttons?: Button[];
  carousel_cards?: CarouselCard[];
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'PAUSED';
  meta_template_id?: string;
  rejection_reason?: string;
  submitted_at?: string;
  approved_at?: string;
  variations?: string[];
};

export function detectVariables(text: string): number[] {
  const regex = /\{\{(\d+)\}\}/g;
  const nums = new Set<number>();
  let match;
  while ((match = regex.exec(text)) !== null) {
    nums.add(parseInt(match[1], 10));
  }
  return Array.from(nums).sort((a, b) => a - b);
}

/** Mirrors Meta's hard template rules (subcodes 2388299 / leading-trailing, non-sequential numbering) so submissions fail fast in the UI instead of round-tripping to the Graph API. */
export function validateTemplateBody(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;

  if (/^\{\{\d+\}\}/.test(trimmed)) {
    return "Variables can't be at the start of the template.";
  }
  if (/\{\{\d+\}\}$/.test(trimmed)) {
    return "Variables can't be at the end of the template.";
  }

  const vars = detectVariables(trimmed);
  if (vars.length > 0) {
    const expected = Array.from({ length: vars.length }, (_, i) => i + 1);
    if (JSON.stringify(vars) !== JSON.stringify(expected)) {
      return `Variables must be numbered sequentially starting from {{1}} with no gaps (found ${vars
        .map((v) => `{{${v}}}`)
        .join(", ")}).`;
    }
  }

  return null;
}

/** Meta doesn't publish its exact words-to-variables ratio formula (subcode 2388293) — this is a non-blocking heuristic to warn before submission, not a hard rule. */
export function templateBodyWarning(text: string): string | null {
  const vars = detectVariables(text);
  if (vars.length === 0) return null;
  const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
  if (wordCount / vars.length < 6) {
    return "This may have too many variables for its length — Meta often rejects a low word-to-variable ratio. Consider adding more descriptive text or reducing variables.";
  }
  return null;
}

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'en_US', label: 'English (US)' },
  { code: 'en_IN', label: 'English (IND)' },
  { code: 'hi', label: 'Hindi' },
  { code: 'kn', label: 'Kannada' },
  { code: 'ml', label: 'Malayalam' },
  { code: 'ta', label: 'Tamil' },
  { code: 'te', label: 'Telugu' },
] as const;

export const CATEGORIES = [
  { value: 'MARKETING', label: 'Marketing', description: 'Promotions, offers, and updates' },
  { value: 'UTILITY', label: 'Utility', description: 'Order updates, alerts, and confirmations' },
  { value: 'AUTHENTICATION', label: 'Authentication', description: 'OTP and verification codes' },
] as const;

export const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  APPROVED: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
  PENDING: { bg: 'bg-amber-50', text: 'text-amber-700', dot: 'bg-amber-500' },
  REJECTED: { bg: 'bg-red-50', text: 'text-red-700', dot: 'bg-red-500' },
  PAUSED: { bg: 'bg-[#f0ece4]', text: 'text-[#57534e]', dot: 'bg-[#a8a29e]' },
};

export const CATEGORY_COLORS: Record<string, { bg: string; text: string }> = {
  MARKETING: { bg: 'bg-purple-50', text: 'text-purple-700' },
  UTILITY: { bg: 'bg-blue-50', text: 'text-blue-700' },
  AUTHENTICATION: { bg: 'bg-teal-50', text: 'text-teal-700' },
};
