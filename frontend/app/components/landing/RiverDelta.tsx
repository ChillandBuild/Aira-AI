"use client";

import { ArrowRight } from "lucide-react";
import { FLOW_STEPS } from "./landing.data";
import { useReducedMotion } from "./useReducedMotion";

// Channels feed in as tributaries at the river's source.
const TRIBUTARIES = ["WhatsApp", "Instagram", "Ads", "Website"];

// The river's wave, shared by the bed, the flowing current, and the particles.
const RIVER_PATH =
  "M0 120 C 180 50, 280 190, 460 120 S 740 50, 920 120 S 1120 190, 1200 120";

// Slight vertical lift per node so each step sits on a crest/trough of the wave.
const NODE_LIFT = [0, -22, 12, -12, 22, 0];

/**
 * "How Aira Works" as a river delta: channel tributaries converge into one
 * AI current that carries each enquiry downstream to revenue. On desktop a
 * flowing SVG river runs beneath the six steps with particles drifting along
 * it; on mobile / reduced-motion it collapses to a clean vertical current.
 */
export default function RiverDelta() {
  const { reducedMotion } = useReducedMotion();

  return (
    <div className="river-delta">
      {/* Tributaries */}
      <div className="delta-tributaries">
        {TRIBUTARIES.map((t) => (
          <span key={t} className="tributary-chip">
            {t}
          </span>
        ))}
      </div>

      {/* Desktop flowing river behind the steps */}
      <div className="delta-river" aria-hidden="true">
        <svg viewBox="0 0 1200 240" preserveAspectRatio="none" className="delta-river-svg" fill="none">
          <defs>
            <linearGradient id="delta-current" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#4c1d95" stopOpacity="0.25" />
              <stop offset="50%" stopColor="#7c3aed" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#5b21b6" stopOpacity="0.25" />
            </linearGradient>
            <path id="delta-path" d={RIVER_PATH} />
          </defs>
          <path d={RIVER_PATH} className="delta-bed" stroke="url(#delta-current)" />
          <path d={RIVER_PATH} className="delta-flow" stroke="#a78bfa" />
          {!reducedMotion &&
            [0, 1, 2, 3, 4].map((i) => (
              <circle key={i} r={3} className="delta-particle" fill="#7c3aed">
                <animateMotion dur={`${5 + i * 1.4}s`} begin={`${i * 0.9}s`} repeatCount="indefinite">
                  <mpath href="#delta-path" />
                </animateMotion>
              </circle>
            ))}
        </svg>
      </div>

      {/* Steps */}
      <div className="delta-steps">
        {FLOW_STEPS.map((step, i) => (
          <div key={step.title} className="delta-step-wrap">
            <div
              className="flow-step delta-step"
              style={{ "--node-lift": `${NODE_LIFT[i] ?? 0}px` } as React.CSSProperties}
            >
              <div className="flow-step-icon">
                <step.icon size={26} className="text-primary" />
              </div>
              <h4 className="font-bold text-sm text-ink mb-1">{step.title}</h4>
              <p className="text-[11px] text-ink-secondary leading-relaxed px-1">{step.desc}</p>
            </div>
            {i < FLOW_STEPS.length - 1 && (
              <div className="delta-arrow" aria-hidden="true">
                <ArrowRight size={16} className="text-ink-muted" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
