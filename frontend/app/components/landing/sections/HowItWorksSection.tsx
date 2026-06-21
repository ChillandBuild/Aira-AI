"use client";

import RiverDelta from "../RiverDelta";

export default function HowItWorksSection() {
  return (
    <section id="how-it-works" className="py-20 md:py-28 relative">
      <div className="river-separator"></div>
      <div className="max-w-7xl mx-auto px-6 md:px-10 pt-16">
        <div className="text-center mb-16 reveal">
          <p className="section-eyebrow mb-3">HOW AIRA WORKS</p>
          <h2 className="section-title">From Enquiry to Revenue</h2>
        </div>

        <div className="reveal">
          <RiverDelta />
        </div>
      </div>
    </section>
  );
}
