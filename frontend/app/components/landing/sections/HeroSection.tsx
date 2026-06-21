"use client";

import {
  ArrowRight,
  CheckCircle2,
  Activity,
  Zap,
  Shield,
  Bot,
} from "lucide-react";
import HeroRipple from "../HeroRipple";

interface HeroSectionProps {
  scrollToSection: (id: string) => void;
  ripple: (e: React.PointerEvent<HTMLElement>) => void;
}

export default function HeroSection({ scrollToSection, ripple }: HeroSectionProps) {
  return (
    <section id="hero" className="hero-section pt-32 pb-20 md:pt-40 md:pb-32">
      <HeroRipple />
      <div className="relative z-10 max-w-7xl mx-auto px-6 md:px-10 grid lg:grid-cols-2 gap-16 items-center">
        {/* Left — Copy */}
        <div className="flex flex-col gap-7 reveal visible">
          <div className="hero-badge">
            <div className="w-2 h-2 rounded-full bg-primary pulse-accent"></div>
            AI-Powered. Human-Centric. Revenue-Focused.
          </div>

          <h1 className="hero-title">
            Turn Every{" "}
            <br className="hidden sm:block" />
            Enquiry Into{" "}
            <br className="hidden sm:block" />
            <span className="hero-title-gradient">Revenue</span>
          </h1>

          <p className="hero-subtitle">
            AIRA helps businesses automate conversations, qualify leads, evaluate telecallers and convert more customers.
          </p>

          <div className="flex flex-wrap gap-4 pt-2">
            <button
              onClick={() => scrollToSection("contact")}
              onPointerDown={ripple}
              id="hero-demo-btn"
              className="btn-accent ripple-host"
            >
              Book a Demo
              <ArrowRight size={16} />
            </button>
            <button
              onClick={() => scrollToSection("demo")}
              className="btn-ghost-dark"
            >
              <Activity size={16} className="text-primary" />
              Watch Demo
            </button>
          </div>

          <div className="flex items-center gap-6 pt-4 text-xs text-ink-muted">
            <span className="flex items-center gap-1.5">
              <Shield size={13} className="text-primary" />
              Secure
            </span>
            <span className="flex items-center gap-1.5">
              <CheckCircle2 size={13} className="text-primary" />
              Reliable
            </span>
            <span className="flex items-center gap-1.5">
              <Zap size={13} className="text-primary" />
              Built for Growing Businesses
            </span>
          </div>
        </div>

        {/* Right — Dashboard Mockup */}
        <div className="relative reveal visible" style={{ animationDelay: "0.15s" }}>
          <div className="absolute -inset-8 bg-gradient-to-br from-[#5b21b6]/10 to-[#7c3aed]/5 blur-3xl rounded-3xl pointer-events-none"></div>
          <div className="dashboard-mockup relative z-10">
            {/* Window Chrome */}
            <div className="window-chrome">
              <div className="window-dot bg-[#ef4444]/70"></div>
              <div className="window-dot bg-[#f59e0b]/70"></div>
              <div className="window-dot bg-[#22c55e]/70"></div>
              <span className="ml-3 text-[10px] font-mono text-ink-muted">Aira — Dashboard</span>
            </div>
            {/* Dashboard Content */}
            <div className="bg-background p-6">
              {/* Stats Row */}
              <div className="grid grid-cols-4 gap-3 mb-5">
                {[
                  { label: "Total Enquiries", value: "512", change: "+9%", up: true },
                  { label: "Qualified Leads", value: "128", change: "+24%", up: true },
                  { label: "Hot Leads", value: "43", change: "+17%", up: true },
                  { label: "Conversion Rate", value: "16.8%", change: "+5%", up: true },
                ].map((stat) => (
                  <div key={stat.label} className="bg-surface rounded-lg p-3 border border-border-subtle">
                    <p className="text-[8px] text-ink-muted font-medium uppercase tracking-wider">{stat.label}</p>
                    <p className="text-lg font-bold text-ink font-mono mt-1">{stat.value}</p>
                    <p className={`text-[9px] font-mono mt-0.5 ${stat.up ? "text-success" : "text-danger"}`}>
                      {stat.change}
                    </p>
                  </div>
                ))}
              </div>
              {/* Chart placeholder */}
              <div className="bg-surface rounded-lg p-4 border border-border-subtle mb-4">
                <p className="text-[10px] text-ink-muted font-medium mb-3">Lead Funnel</p>
                <div className="flex flex-col gap-1.5">
                  {[
                    { label: "Enquiries", width: "100%", color: "#2e1065" },
                    { label: "Qualified", width: "65%", color: "#5b21b6" },
                    { label: "Interested", width: "42%", color: "#7c3aed" },
                    { label: "Converted", width: "25%", color: "#a78bfa" },
                  ].map((bar) => (
                    <div key={bar.label} className="flex items-center gap-2">
                      <span className="text-[8px] text-ink-muted w-14 text-right">{bar.label}</span>
                      <div className="flex-1 h-4 bg-surface-mid rounded-sm overflow-hidden">
                        <div
                          className="h-full rounded-sm transition-all duration-1000"
                          style={{ width: bar.width, background: bar.color }}
                        ></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {/* AI Chat Preview */}
              <div className="bg-surface rounded-lg p-3 border border-border-subtle">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-5 h-5 rounded-full bg-gradient-to-br from-[#2e1065] to-[#5b21b6] flex items-center justify-center">
                    <Bot size={10} className="text-white" />
                  </div>
                  <span className="text-[9px] font-semibold text-ink">Aira Assistant</span>
                  <div className="w-1.5 h-1.5 rounded-full bg-success ml-auto"></div>
                  <span className="text-[8px] text-success">Online</span>
                </div>
                <p className="text-[10px] text-ink-secondary bg-background rounded-md p-2">
                  Hi 👋 How can I help you today?
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
