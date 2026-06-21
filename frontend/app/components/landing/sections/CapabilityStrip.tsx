"use client";

import { Layers, Zap, Timer, Headset } from "lucide-react";

const CAPABILITIES = [
  { icon: Layers, label: "4 Channels", sub: "WhatsApp, Instagram, Telegram, Facebook" },
  { icon: Zap, label: "24/7 AI Response", sub: "Always-on automated replies" },
  { icon: Timer, label: "< 2s Reply Time", sub: "Instant lead engagement" },
  { icon: Headset, label: "Built-in Telecalling", sub: "Calls + AI coaching in one platform" },
] as const;

export default function CapabilityStrip() {
  return (
    <section className="py-8 relative">
      <div className="max-w-7xl mx-auto px-6 md:px-10">
        <div className="capability-strip glass-dark rounded-2xl grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-0 px-6 py-5 reveal">
          {CAPABILITIES.map((cap) => (
            <div key={cap.label} className="capability-item">
              <div className="capability-icon">
                <cap.icon size={20} className="text-primary" />
              </div>
              <div>
                <p className="font-bold text-sm text-ink leading-tight">{cap.label}</p>
                <p className="text-xs text-ink-muted leading-snug mt-0.5">{cap.sub}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
