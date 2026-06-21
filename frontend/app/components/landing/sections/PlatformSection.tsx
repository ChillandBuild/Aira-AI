"use client";

import { ArrowRight } from "lucide-react";
import { PLATFORM_FEATURES } from "../landing.data";

interface PlatformSectionProps {
  scrollToSection: (id: string) => void;
}

export default function PlatformSection({ scrollToSection }: PlatformSectionProps) {
  return (
    <section id="platform" className="py-20 md:py-28 relative">
      <div className="river-separator"></div>
      <div className="max-w-7xl mx-auto px-6 md:px-10 pt-16">
        <div className="text-center mb-16 reveal">
          <p className="section-eyebrow mb-3">OUR PLATFORM</p>
          <h2 className="section-title">Everything You Need in One Place</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {PLATFORM_FEATURES.map((feature, i) => (
            <div
              key={feature.title}
              className={`bento-card glass-dark glow-border reveal reveal-delay-${i + 1}`}
            >
              <div className="bento-icon">
                <feature.icon size={22} className="text-primary" />
              </div>
              <h3 className="font-bold text-base text-ink mb-2">{feature.title}</h3>
              <p className="text-sm text-ink-secondary leading-relaxed mb-4">{feature.desc}</p>
              <div className="flex flex-wrap gap-2 mt-auto">
                {feature.tags.map((tag) => (
                  <span key={tag} className="bento-tag">{tag}</span>
                ))}
              </div>
              <button
                onClick={() => scrollToSection("contact")}
                className="mt-4 text-xs font-semibold text-primary flex items-center gap-1 hover:gap-2 transition-all"
              >
                Learn More <ArrowRight size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
