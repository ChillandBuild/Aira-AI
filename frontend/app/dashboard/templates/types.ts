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

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'ta', label: 'Tamil' },
  { code: 'te', label: 'Telugu' },
  { code: 'ar', label: 'Arabic' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'de', label: 'German' },
  { code: 'id', label: 'Indonesian' },
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
