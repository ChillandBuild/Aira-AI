import { cn } from "@/lib/utils";

export type Channel = "whatsapp" | "instagram" | "facebook" | "telegram";

/**
 * Conversations carry a `source` that mixes acquisition origin ("upload",
 * "manual") with the messaging channel. Anything that isn't an explicit
 * social channel is delivered over WhatsApp, so it falls back to that.
 */
export function getChannel(source?: string | null): Channel {
  if (source === "instagram" || source === "telegram" || source === "facebook") return source;
  return "whatsapp";
}

export const CHANNEL_LABEL: Record<Channel, string> = {
  whatsapp: "WhatsApp",
  instagram: "Instagram",
  facebook: "Facebook",
  telegram: "Telegram",
};

/** Brand marks, drawn white so they sit on the brand-coloured disc below. */
function WhatsAppGlyph({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884a9.82 9.82 0 0 1 6.99 2.896 9.825 9.825 0 0 1 2.895 6.994c-.003 5.45-4.437 9.885-9.885 9.885M20.52 3.449C18.24 1.245 15.24 0 12.045 0 5.463 0 .104 5.359.101 11.947c0 2.096.549 4.142 1.595 5.945L0 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.582 0 11.94-5.359 11.944-11.949a11.88 11.88 0 0 0-3.417-8.396" />
    </svg>
  );
}

function InstagramGlyph({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="2" y="2" width="20" height="20" rx="5.5" ry="5.5" />
      <circle cx="12" cy="12" r="4.2" />
      <circle cx="17.6" cy="6.4" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

function TelegramGlyph({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M22.05 3.2 2.4 10.78c-1.14.45-1.13 1.09-.2 1.38l4.9 1.53 1.9 5.8c.23.63.11.88.77.88.51 0 .74-.23 1.03-.51l2.45-2.38 5.1 3.76c.94.52 1.61.25 1.84-.87l3.34-15.7c.34-1.37-.52-1.99-1.48-1.56M7.9 13.4l11.07-6.98c.55-.34 1.05-.15.64.22l-9.48 8.55-.37 3.93z" />
    </svg>
  );
}

function FacebookGlyph({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M17.5 2h-3.1a5.2 5.2 0 0 0-5.2 5.2V10H6.6v4h2.6v8h4.2v-8h2.9l.6-4h-3.5V7.6c0-.66.54-1.2 1.2-1.2h2.9z" />
    </svg>
  );
}

const GLYPH: Record<Channel, (p: { size: number }) => JSX.Element> = {
  whatsapp: WhatsAppGlyph,
  instagram: InstagramGlyph,
  facebook: FacebookGlyph,
  telegram: TelegramGlyph,
};

/** Brand discs. Instagram gets its gradient; the rest are flat brand colours. */
const DISC: Record<Channel, string> = {
  whatsapp: "bg-[#25D366]",
  instagram: "bg-[radial-gradient(circle_at_28%_106%,#fdf497_0%,#fd5949_45%,#d6249f_60%,#285AEB_90%)]",
  facebook: "bg-[#1877F2]",
  telegram: "bg-[linear-gradient(180deg,#37BBFE_0%,#007DBB_100%)]",
};

interface ChannelAvatarProps {
  /** Raw `lead.source`; anything non-social resolves to WhatsApp. */
  source?: string | null;
  /** Diameter in px. */
  size?: number;
  className?: string;
}

/**
 * The conversation avatar. Shows the channel the message arrived on rather
 * than the contact's initials — most inbound leads are anonymous handles or
 * bare phone numbers, so the channel is the more useful identifier.
 */
export function ChannelAvatar({ source, size = 44, className }: ChannelAvatarProps) {
  const channel = getChannel(source);
  const Glyph = GLYPH[channel];
  return (
    <div
      className={cn(
        "rounded-full flex items-center justify-center text-white shrink-0 select-none shadow-sm ring-1 ring-black/5",
        DISC[channel],
        className
      )}
      style={{ width: size, height: size }}
      title={CHANNEL_LABEL[channel]}
      aria-label={CHANNEL_LABEL[channel]}
      role="img"
    >
      <Glyph size={Math.round(size * 0.58)} />
    </div>
  );
}
