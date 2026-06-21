"use client";

import { useState } from "react";
import { CheckCircle2, X, ChevronDown } from "lucide-react";
import { PRICING_TIERS, FAQ_ITEMS } from "../landing.data";

interface PricingSectionProps {
  scrollToSection: (id: string) => void;
}

function formatPrice(price: number): string {
  return price.toLocaleString("en-IN");
}

export default function PricingSection({ scrollToSection }: PricingSectionProps) {
  const [isAnnual, setIsAnnual] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const savingsPercent = isAnnual ? 56 : 45;
  const growthPrice = isAnnual ? 4799 : 5999;

  return (
    <section id="pricing" className="py-20 md:py-28 relative">
      <div className="river-separator" />
      <div className="max-w-7xl mx-auto px-6 md:px-10 pt-16">
        {/* Header */}
        <div className="text-center mb-12 reveal">
          <p className="section-eyebrow mb-3">SIMPLE, TRANSPARENT PRICING</p>
          <h2 className="section-title mb-4">One Platform. One Price.</h2>
          <p className="section-subtitle mx-auto">
            Replace your WhatsApp tool, telecalling CRM, and analytics dashboard with AIRA.
          </p>
        </div>

        {/* Toggle */}
        <div className="flex justify-center mb-12 reveal reveal-delay-1">
          <div className="pricing-toggle">
            <button
              className={`pricing-toggle-btn ${!isAnnual ? "active" : ""}`}
              onClick={() => setIsAnnual(false)}
            >
              Monthly
            </button>
            <button
              className={`pricing-toggle-btn ${isAnnual ? "active" : ""}`}
              onClick={() => setIsAnnual(true)}
            >
              Annual
            </button>
          </div>
          <span className="ml-3 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            Save 20%
          </span>
        </div>

        {/* Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
          {PRICING_TIERS.map((tier, i) => (
            <div
              key={tier.name}
              className={`pricing-card glass-dark rounded-2xl p-6 flex flex-col reveal reveal-delay-${i + 1} ${
                tier.highlight ? "pricing-card-highlight" : ""
              }`}
            >
              {tier.badge && (
                <span className="pricing-badge">{tier.badge}</span>
              )}

              <h3 className="text-lg font-bold text-ink mb-1">{tier.name}</h3>
              <p className="text-xs text-ink-secondary mb-4">{tier.description}</p>

              {/* Price */}
              <div className="mb-4">
                {tier.monthlyPrice !== null && tier.annualPrice !== null ? (
                  <>
                    <div className="pricing-price">
                      <span className="text-base font-semibold text-ink-secondary">₹</span>
                      {formatPrice(isAnnual ? tier.annualPrice : tier.monthlyPrice)}
                      <span className="text-sm font-normal text-ink-secondary">/mo</span>
                    </div>
                    {isAnnual && (
                      <p className="text-xs text-ink-muted mt-1 line-through">
                        ₹{formatPrice(tier.monthlyPrice)}/mo
                      </p>
                    )}
                  </>
                ) : (
                  <div className="pricing-price">Custom</div>
                )}
              </div>

              <p className="text-xs text-ink-secondary mb-1">{tier.users}</p>
              {tier.extraUserPrice && (
                <p className="text-xs text-ink-muted mb-4">({tier.extraUserPrice})</p>
              )}
              {!tier.extraUserPrice && <div className="mb-4" />}

              {/* Features */}
              <ul className="flex-1 space-y-2 mb-6">
                {tier.features.map((f) => (
                  <li key={f.text} className="pricing-feature">
                    {f.included ? (
                      <CheckCircle2 size={14} className="text-success shrink-0 mt-0.5" />
                    ) : (
                      <X size={14} className="text-ink-muted shrink-0 mt-0.5" />
                    )}
                    <span className={f.included ? "text-ink-secondary" : "text-ink-muted"}>
                      {f.text}
                    </span>
                  </li>
                ))}
              </ul>

              {/* CTA */}
              <button
                onClick={() => scrollToSection("contact")}
                className={`w-full justify-center ${tier.highlight ? "btn-accent" : "btn-ghost-dark"}`}
              >
                {tier.cta}
              </button>
            </div>
          ))}
        </div>

        {/* Trust line */}
        <p className="text-center text-xs text-ink-muted mb-16 reveal">
          WhatsApp messages charged at Meta&apos;s cost — zero markup from AIRA
        </p>

        {/* Replace 3 Tools comparison */}
        <div className="pricing-comparison glass-dark rounded-2xl p-8 mb-16 reveal">
          <h3 className="text-lg font-bold text-ink mb-6 text-center">Replace 3 Tools</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {/* Without AIRA */}
            <div>
              <p className="text-sm font-semibold text-ink-secondary mb-4">Without AIRA</p>
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-ink-secondary">WhatsApp Tool</span>
                  <span className="text-ink-secondary">₹3,000/mo</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-ink-secondary">Telecalling CRM</span>
                  <span className="text-ink-secondary">₹5,000/mo</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-ink-secondary">Analytics Dashboard</span>
                  <span className="text-ink-secondary">₹3,000/mo</span>
                </div>
                <div className="border-t border-border pt-3 flex justify-between">
                  <span className="text-sm font-bold text-ink">Total</span>
                  <span className="text-sm font-bold text-ink line-through">₹11,000/mo</span>
                </div>
              </div>
            </div>

            {/* With AIRA */}
            <div className="flex flex-col items-center justify-center text-center">
              <p className="text-sm font-semibold text-ink-secondary mb-3">With AIRA</p>
              <p className="text-3xl font-bold text-ink mb-2">
                ₹{formatPrice(growthPrice)}
                <span className="text-sm font-normal text-ink-secondary">/mo</span>
              </p>
              <p className="text-xs text-ink-muted mb-4">Growth plan</p>
              <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                Save {savingsPercent}%
              </span>
            </div>
          </div>
        </div>

        {/* FAQ */}
        <div className="max-w-3xl mx-auto reveal">
          <h3 className="section-title text-center mb-8">Frequently Asked Questions</h3>
          <div className="space-y-3">
            {FAQ_ITEMS.map((item, i) => (
              <div key={i} className="pricing-faq-item glass-dark rounded-xl overflow-hidden">
                <button
                  className="pricing-faq-header"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  aria-expanded={openFaq === i}
                >
                  <span className="text-sm font-semibold text-ink">{item.question}</span>
                  <ChevronDown
                    size={16}
                    className={`text-ink-muted shrink-0 transition-transform duration-300 ${
                      openFaq === i ? "rotate-180" : ""
                    }`}
                  />
                </button>
                <div
                  className="pricing-faq-body"
                  style={{ maxHeight: openFaq === i ? "200px" : "0px" }}
                >
                  <p className="text-sm text-ink-secondary leading-relaxed px-5 pb-4">
                    {item.answer}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
