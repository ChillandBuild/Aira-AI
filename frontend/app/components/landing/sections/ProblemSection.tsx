"use client";

import { PROBLEMS } from "../landing.data";

export default function ProblemSection() {
  return (
    <section id="features" className="py-20 md:py-28 relative">
      <div className="river-separator"></div>
      <div className="max-w-7xl mx-auto px-6 md:px-10 pt-16">
        <div className="text-center mb-16 reveal">
          <p className="section-eyebrow mb-3">THE PROBLEM</p>
          <h2 className="section-title">Leads Are Lost in the Gaps</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-5">
          {PROBLEMS.map((problem, i) => (
            <div
              key={problem.title}
              className={`problem-card glass-dark reveal reveal-delay-${i + 1}`}
            >
              <div className="problem-icon-wrap">
                <problem.icon size={24} className="text-primary" />
              </div>
              <h3 className="font-bold text-sm text-ink mb-1.5">{problem.title}</h3>
              <p className="text-xs text-ink-secondary leading-relaxed">{problem.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
