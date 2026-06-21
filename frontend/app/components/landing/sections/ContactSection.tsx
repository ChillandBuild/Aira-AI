"use client";

import { useState, useCallback } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Phone,
  Users,
  Zap,
  Mail,
} from "lucide-react";
import { INDUSTRIES } from "../landing.data";

export default function ContactSection() {
  const [formData, setFormData] = useState({ name: "", email: "", phone: "", company: "", industry: "" });
  const [formSubmitted, setFormSubmitted] = useState(false);
  const [formSubmitting, setFormSubmitting] = useState(false);

  const handleFormSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setFormSubmitting(true);
    await new Promise((resolve) => setTimeout(resolve, 1500));
    setFormSubmitting(false);
    setFormSubmitted(true);
  }, []);

  return (
    <section id="contact" className="py-20 md:py-28 relative">
      <div className="river-separator"></div>
      <div className="max-w-7xl mx-auto px-6 md:px-10 pt-16">
        <div className="cta-section p-8 md:p-16 reveal">
          <div className="relative z-10 grid lg:grid-cols-2 gap-12 items-center">
            {/* Left — CTA Copy */}
            <div>
              <p className="section-eyebrow mb-4">READY TO GROW?</p>
              <h2 className="section-title mb-5">
                Ready to Turn Enquiries<br />
                <span className="hero-title-gradient">Into Revenue?</span>
              </h2>
              <p className="section-subtitle mb-8">
                Book a demo with our team and see how AIRA can help your business grow. Our experts will walk you through the platform and set up your account.
              </p>
              <div className="flex flex-wrap gap-6 mb-6">
                {[
                  { icon: Phone, text: "Personalized Demo" },
                  { icon: Users, text: "Dedicated Account Manager" },
                  { icon: Zap, text: "Go Live in 48 Hours" },
                ].map((item) => (
                  <div key={item.text} className="flex items-center gap-2 text-sm text-ink-secondary">
                    <item.icon size={14} className="text-primary" />
                    {item.text}
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap gap-4">
                <a href="mailto:hello@aira.ai" className="btn-accent">
                  <Mail size={16} />
                  Talk to an Expert
                </a>
              </div>
            </div>

            {/* Right — Demo Form */}
            <div className="demo-form-card">
              {formSubmitted ? (
                <div className="text-center py-10">
                  <div className="w-16 h-16 rounded-full bg-primary-light border border-primary-muted flex items-center justify-center mx-auto mb-5">
                    <CheckCircle2 size={32} className="text-primary" />
                  </div>
                  <h3 className="font-bold text-xl text-ink mb-2">Thank You!</h3>
                  <p className="text-sm text-ink-secondary max-w-xs mx-auto">
                    Our team will reach out to you within 24 hours to schedule your personalized demo.
                  </p>
                </div>
              ) : (
                <>
                  <h3 className="font-bold text-lg text-ink mb-1">Book a Demo</h3>
                  <p className="text-xs text-ink-muted mb-6">
                    Fill in your details and our team will get in touch.
                  </p>
                  <form onSubmit={handleFormSubmit} className="flex flex-col gap-4">
                    <div>
                      <label htmlFor="demo-name" className="form-label">Full Name</label>
                      <input
                        id="demo-name"
                        type="text"
                        required
                        placeholder="Your name"
                        className="form-input-dark"
                        value={formData.name}
                        onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label htmlFor="demo-email" className="form-label">Work Email</label>
                      <input
                        id="demo-email"
                        type="email"
                        required
                        placeholder="you@company.com"
                        className="form-input-dark"
                        value={formData.email}
                        onChange={(e) => setFormData((p) => ({ ...p, email: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label htmlFor="demo-phone" className="form-label">Phone Number</label>
                      <input
                        id="demo-phone"
                        type="tel"
                        required
                        placeholder="+91 98765 43210"
                        className="form-input-dark"
                        value={formData.phone}
                        onChange={(e) => setFormData((p) => ({ ...p, phone: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label htmlFor="demo-company" className="form-label">Company Name</label>
                      <input
                        id="demo-company"
                        type="text"
                        required
                        placeholder="Your company"
                        className="form-input-dark"
                        value={formData.company}
                        onChange={(e) => setFormData((p) => ({ ...p, company: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label htmlFor="demo-industry" className="form-label">Industry</label>
                      <select
                        id="demo-industry"
                        className="form-input-dark"
                        value={formData.industry}
                        onChange={(e) => setFormData((p) => ({ ...p, industry: e.target.value }))}
                        required
                      >
                        <option value="" disabled>Select your industry</option>
                        {INDUSTRIES.map((ind) => (
                          <option key={ind.name} value={ind.name}>{ind.name}</option>
                        ))}
                        <option value="Other">Other</option>
                      </select>
                    </div>
                    <button
                      type="submit"
                      disabled={formSubmitting}
                      className="btn-accent w-full justify-center mt-2"
                    >
                      {formSubmitting ? (
                        <>
                          <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                          Submitting...
                        </>
                      ) : (
                        <>
                          Book a Demo
                          <ArrowRight size={16} />
                        </>
                      )}
                    </button>
                  </form>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
