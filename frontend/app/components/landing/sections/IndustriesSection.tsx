"use client";

import { INDUSTRIES } from "../landing.data";

export default function IndustriesSection() {
  return (
    <section id="industries" className="py-20 md:py-28 relative">
      <div className="river-separator"></div>
      <div className="max-w-7xl mx-auto px-6 md:px-10 pt-16">
        <div className="text-center mb-14 reveal">
          <p className="section-eyebrow mb-3">BUILT FOR GROWING BUSINESSES</p>
          <h2 className="section-title">Industries We Serve</h2>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 reveal">
          {INDUSTRIES.map((industry) => (
            <div key={industry.name} className="industry-card glass-dark glow-border">
              <div className="industry-icon">
                <industry.icon size={24} className="text-primary" />
              </div>
              <span className="text-sm font-medium text-ink">{industry.name}</span>
            </div>
          ))}
        </div>
        <p className="text-center text-sm text-ink-muted mt-6 reveal">
          And more industries looking to grow faster.
        </p>
      </div>
    </section>
  );
}
