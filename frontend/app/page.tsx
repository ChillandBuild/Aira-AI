"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  MessageSquare,
  Send,
  ArrowRight,
  CheckCircle2,
  Menu,
  X,
  Activity,
  Phone,
  BarChart3,
  Users,
  Zap,
  Shield,
  GraduationCap,
  Building2,
  Heart,
  Car,
  Factory,
  Landmark,
  Bot,
  PhoneCall,
  TrendingUp,
  MessageCircle,
  Star,
  Clock,
  Target,
  Headset,
  Mail,
} from "lucide-react";
import "./landing.css";

// Custom SVG Icons
function WhatsAppIcon({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
    </svg>
  );
}

function InstagramIcon({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

function FacebookIcon({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
    </svg>
  );
}

function LinkedInIcon({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
    </svg>
  );
}

function YouTubeIcon({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
    </svg>
  );
}

// Chat Simulator Data
const SIMULATED_MESSAGES = [
  { sender: "customer", text: "Hi! I'm interested in the Enterprise plan for my 20-person agency.", time: "14:02" },
  { sender: "aira", text: "Great! I can help with that. Based on your team size, you'd qualify for our Priority Onboarding. Would you like to see a custom demo?", time: "14:02" },
  { sender: "customer", text: "Yes, Thursday at 10 AM works.", time: "14:03" },
  { sender: "aira", text: "Perfect. Appointment confirmed. I've sent a calendar invite and a brief prep doc to your email. See you then!", time: "14:03" },
  { sender: "system", text: "Lead Scored: 9.8/10 (Hot) • Routed to priority telecaller queue", time: "14:03" },
];

// Problem Data
const PROBLEMS = [
  { icon: MessageCircle, title: "Enquiries go unanswered", desc: "Leads slip through WhatsApp, web, and social channels without any response." },
  { icon: Clock, title: "Follow-ups get missed", desc: "Manual tracking leads to forgotten callbacks and cold prospects." },
  { icon: TrendingUp, title: "Hot leads turn cold", desc: "Without instant AI response, high-intent leads lose interest quickly." },
  { icon: Target, title: "Telecaller performance is hard to measure", desc: "No visibility into call quality, outcomes, or team performance." },
  { icon: Landmark, title: "Revenue opportunities are lost", desc: "Disjointed systems mean you can't optimize the full enquiry-to-revenue pipeline." },
];

// Flow Steps
const FLOW_STEPS = [
  { icon: MessageSquare, title: "Enquiry", desc: "Customer reaches out on WhatsApp, Website or Ads" },
  { icon: Bot, title: "AI Conversation", desc: "Instant, human-like AI conversations 24/7" },
  { icon: Star, title: "Lead Qualification", desc: "AI identifies intent and scores the lead" },
  { icon: PhoneCall, title: "Telecaller Assignment", desc: "Smart assignment to the right team member" },
  { icon: BarChart3, title: "AI Evaluation", desc: "Calls are tracked and performance is evaluated" },
  { icon: TrendingUp, title: "Revenue", desc: "Timely follow-ups close deals and drive growth" },
];

// Platform Features
const PLATFORM_FEATURES = [
  {
    icon: Bot,
    title: "Inbound AI Conversations",
    desc: "Automate WhatsApp & web conversations and never miss an enquiry.",
    tags: ["WhatsApp", "Web Chat"],
  },
  {
    icon: Send,
    title: "Bulk WhatsApp Campaigns",
    desc: "Run campaigns, manage templates and track real-time performance.",
    tags: ["Campaigns", "Templates"],
  },
  {
    icon: Headset,
    title: "Telecaller Intelligence",
    desc: "Track calls, evaluate performance and improve team productivity.",
    tags: ["Voice Logs", "Whisper AI"],
  },
  {
    icon: BarChart3,
    title: "Revenue Insights",
    desc: "Get real-time analytics and insights to make better decisions.",
    tags: ["Analytics", "Reports"],
  },
];

// Industries
const INDUSTRIES = [
  { icon: GraduationCap, name: "Education" },
  { icon: Building2, name: "Real Estate" },
  { icon: Heart, name: "Healthcare" },
  { icon: Car, name: "Automotive" },
  { icon: Factory, name: "Manufacturing" },
  { icon: Landmark, name: "Financial Services" },
];

export default function LandingPage() {
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [navScrolled, setNavScrolled] = useState(false);
  const [chatMessages, setChatMessages] = useState<typeof SIMULATED_MESSAGES>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  // Demo form state
  const [formData, setFormData] = useState({ name: "", email: "", phone: "", company: "", industry: "" });
  const [formSubmitted, setFormSubmitted] = useState(false);
  const [formSubmitting, setFormSubmitting] = useState(false);

  // Scroll-triggered reveal
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );

    document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  // Nav scroll effect
  useEffect(() => {
    const handleScroll = () => setNavScrolled(window.scrollY > 40);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // Chat Simulator Loop
  useEffect(() => {
    if (currentStep < SIMULATED_MESSAGES.length) {
      const currentMsg = SIMULATED_MESSAGES[currentStep];
      let delay = 1000;

      if (currentMsg.sender === "aira") {
        setIsTyping(true);
        delay = 2000;
      } else if (currentMsg.sender === "system") {
        delay = 1500;
      }

      const timer = setTimeout(() => {
        setIsTyping(false);
        setChatMessages((prev) => [...prev, currentMsg]);
        setCurrentStep((prev) => prev + 1);
      }, delay);

      return () => clearTimeout(timer);
    } else {
      const resetTimer = setTimeout(() => {
        setChatMessages([]);
        setCurrentStep(0);
      }, 5000);
      return () => clearTimeout(resetTimer);
    }
  }, [currentStep]);

  useEffect(() => {
    // Scroll only the chat container — scrollIntoView would yank the whole page.
    const el = chatScrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [chatMessages, isTyping]);

  // Form handler
  const handleFormSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setFormSubmitting(true);
    // Simulate submission delay
    await new Promise((resolve) => setTimeout(resolve, 1500));
    setFormSubmitting(false);
    setFormSubmitted(true);
  }, []);

  const scrollToSection = (id: string) => {
    setMobileMenuOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="landing-page">
      {/* Noise Texture Overlay */}
      <div className="noise-overlay" aria-hidden="true"></div>

      {/* Fluid Background Orbs */}
      <div className="fluid-bg" aria-hidden="true">
        <div className="fluid-orb fluid-orb-1"></div>
        <div className="fluid-orb fluid-orb-2"></div>
        <div className="fluid-orb fluid-orb-3"></div>
        <div className="fluid-orb fluid-orb-4"></div>
      </div>

      {/* ─── NAVIGATION ─── */}
      <nav className={`nav-landing ${navScrolled ? "scrolled" : ""}`} id="nav-main">
        <div className="max-w-7xl mx-auto px-6 md:px-10 flex justify-between items-center h-[72px]">
          {/* Logo */}
          <button onClick={() => scrollToSection("hero")} className="flex items-center gap-2.5 group">
            <span className="nav-logo-text">Aira</span>
            <span className="text-ink-muted text-xs font-medium hidden sm:inline ml-1 border-l border-border pl-2.5">AI Revenue Acceleration</span>
          </button>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-8">
            <button onClick={() => scrollToSection("hero")} className="nav-link">Home</button>
            <button onClick={() => scrollToSection("features")} className="nav-link">Features</button>
            <button onClick={() => scrollToSection("industries")} className="nav-link">Industries</button>
            <button onClick={() => scrollToSection("platform")} className="nav-link">Pricing</button>
            <button onClick={() => scrollToSection("contact")} className="nav-link">About Us</button>
            <button onClick={() => scrollToSection("contact")} className="nav-link">Contact</button>
          </div>

          {/* Desktop Actions */}
          <div className="hidden md:flex items-center gap-3">
            <button
              onClick={() => router.push("/login")}
              id="nav-login-btn"
              className="btn-login"
            >
              Login
            </button>
            <button
              onClick={() => scrollToSection("contact")}
              id="nav-demo-btn"
              className="btn-accent text-sm py-2 px-5"
            >
              Book a Demo
              <ArrowRight size={14} />
            </button>
          </div>

          {/* Mobile Toggle */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden text-ink-secondary hover:text-ink transition-colors"
            aria-label="Toggle Menu"
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="mobile-menu-overlay md:hidden">
            <div className="pt-24 px-8 flex flex-col gap-6">
              {[{id: "hero", label: "Home"}, {id: "features", label: "Features"}, {id: "industries", label: "Industries"}, {id: "platform", label: "Pricing"}, {id: "contact", label: "About Us"}, {id: "contact", label: "Contact"}].map((item) => (
                <button
                  key={item.label}
                  onClick={() => scrollToSection(item.id)}
                  className="text-left text-lg font-medium text-ink-secondary hover:text-ink transition-colors"
                >
                  {item.label}
                </button>
              ))}
              <div className="river-separator my-4"></div>
              <button
                onClick={() => { setMobileMenuOpen(false); router.push("/login"); }}
                className="btn-login w-full justify-center"
              >
                Login
              </button>
              <button
                onClick={() => { setMobileMenuOpen(false); scrollToSection("contact"); }}
                className="btn-accent w-full justify-center"
              >
                Book a Demo
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}
      </nav>

      <main className="relative z-[2]">
        {/* ─── HERO SECTION ─── */}
        <section id="hero" className="hero-section pt-32 pb-20 md:pt-40 md:pb-32">
          <div className="max-w-7xl mx-auto px-6 md:px-10 grid lg:grid-cols-2 gap-16 items-center">
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
                  id="hero-demo-btn"
                  className="btn-accent"
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
                      <div className="w-5 h-5 rounded-full bg-gradient-to-br from-[#4c1d95] to-[#5b21b6] flex items-center justify-center">
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

        {/* ─── PROBLEM SECTION ─── */}
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

        {/* ─── HOW AIRA WORKS ─── */}
        <section id="how-it-works" className="py-20 md:py-28 relative">
          <div className="river-separator"></div>
          <div className="max-w-7xl mx-auto px-6 md:px-10 pt-16">
            <div className="text-center mb-16 reveal">
              <p className="section-eyebrow mb-3">HOW AIRA WORKS</p>
              <h2 className="section-title">From Enquiry to Revenue</h2>
            </div>

            <div className="flex flex-wrap justify-center items-start gap-2 md:gap-0">
              {FLOW_STEPS.map((step, i) => (
                <div key={step.title} className="flex items-start">
                  <div className={`flow-step w-32 md:w-40 reveal reveal-delay-${Math.min(i + 1, 5)}`}>
                    <div className="flow-step-icon">
                      <step.icon size={28} className="text-primary" />
                    </div>
                    <h4 className="font-bold text-sm text-ink mb-1">{step.title}</h4>
                    <p className="text-[11px] text-ink-secondary leading-relaxed px-1">{step.desc}</p>
                  </div>
                  {i < FLOW_STEPS.length - 1 && (
                    <div className="flow-arrow hidden md:flex pt-6">
                      <ArrowRight size={18} className="text-ink-muted mx-1" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── PLATFORM FEATURES (Bento) ─── */}
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

        {/* ─── LIVE DEMO SIMULATOR ─── */}
        <section id="demo" className="py-20 md:py-28 relative">
          <div className="river-separator"></div>
          <div className="max-w-5xl mx-auto px-6 md:px-10 pt-16">
            <div className="text-center mb-10 reveal">
              <p className="section-eyebrow mb-3">LIVE PREVIEW</p>
              <h2 className="section-title">Watch Aira AI in Action</h2>
              <p className="section-subtitle mx-auto mt-3">
                Real-time simulation of incoming leads being captured, scored, and automated.
              </p>
            </div>

            <div className="glass-dark rounded-2xl overflow-hidden reveal">
              <div className="flex flex-col md:flex-row">
                {/* Left Panel */}
                <div className="md:w-[35%] p-8 border-b md:border-b-0 md:border-r border-border-subtle">
                  <h4 className="font-bold text-base text-ink mb-3 flex items-center gap-2">
                    <Activity size={16} className="text-primary animate-pulse" />
                    Live Agent
                  </h4>
                  <p className="text-xs text-ink-secondary leading-relaxed mb-8">
                    Aira monitors webhooks, verifies signatures, queries the knowledge base, routes callbacks, and logs telecaller activity.
                  </p>
                  <div className="space-y-4">
                    {[
                      { label: "Signature Verified", active: true, color: "#059669" },
                      { label: "RAG Query Context", active: true, color: "#5b21b6" },
                      { label: "Lead Handover", active: currentStep >= 5, color: currentStep >= 5 ? "#059669" : "#a8a29e" },
                    ].map((item) => (
                      <div key={item.label} className="flex items-center gap-3">
                        <div
                          className="w-2 h-2 rounded-full transition-colors duration-300"
                          style={{ backgroundColor: item.color }}
                        ></div>
                        <span className={`font-mono text-xs transition-colors duration-300 ${item.active ? "text-ink" : "text-ink-muted"}`}>
                          {item.label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Right Panel — Chat */}
                <div className="md:w-[65%] p-8 flex flex-col justify-between min-h-[380px]">
                  <div ref={chatScrollRef} className="flex flex-col gap-3 overflow-y-auto max-h-[300px] pr-2">
                    {chatMessages.map((msg, i) => {
                      if (msg.sender === "system") {
                        return (
                          <div key={i} className="flex justify-center my-2" style={{ animation: "slideUp 0.4s ease forwards" }}>
                            <div className="success-pill">
                              <CheckCircle2 size={12} />
                              {msg.text}
                            </div>
                          </div>
                        );
                      }
                      const isAira = msg.sender === "aira";
                      return (
                        <div
                          key={i}
                          className={`flex flex-col max-w-[80%] ${isAira ? "self-end" : "self-start"}`}
                          style={{ animation: "slideUp 0.4s ease forwards" }}
                        >
                          <div className={isAira ? "chat-bubble-aira" : "chat-bubble-customer"}>
                            {msg.text}
                          </div>
                          <span className={`text-[10px] mt-1 ${isAira ? "self-end text-primary/70" : "self-start text-ink-muted"}`}>
                            {isAira ? "Aira AI" : "Lead"} • {msg.time}
                          </span>
                        </div>
                      );
                    })}

                    {isTyping && (
                      <div className="self-end flex items-center gap-1.5 chat-bubble-aira max-w-[80%]">
                        <div className="typing-dot" style={{ animationDelay: "0ms" }}></div>
                        <div className="typing-dot" style={{ animationDelay: "160ms" }}></div>
                        <div className="typing-dot" style={{ animationDelay: "320ms" }}></div>
                      </div>
                    )}
                    <div ref={chatEndRef} />
                  </div>

                  <div className="border-t border-border-subtle pt-4 flex justify-between items-center text-[10px] text-ink-muted">
                    <span className="flex items-center gap-1.5">
                      <WhatsAppIcon size={12} className="text-[#25d366]" />
                      Channel: WhatsApp API
                    </span>
                    <span>Active Session: 24h</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── INDUSTRIES ─── */}
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

        {/* ─── CTA + CONTACT FORM ─── */}
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
      </main>

      {/* ─── FOOTER ─── */}
      <footer className="footer-dark relative z-[2]">
        <div className="max-w-7xl mx-auto px-6 md:px-10 py-16">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-8 mb-12">
            {/* Brand */}
            <div className="col-span-2">
              <div className="flex items-center gap-2.5 mb-4">
                <span className="nav-logo-text">Aira</span>
              </div>
              <p className="text-xs text-ink-secondary leading-relaxed max-w-xs mb-5">
                We help businesses automate conversations, qualify leads, evaluate telecallers and accelerate revenue.
              </p>
              <div className="flex gap-3">
                {[
                  { Icon: LinkedInIcon, label: "LinkedIn" },
                  { Icon: FacebookIcon, label: "Facebook" },
                  { Icon: InstagramIcon, label: "Instagram" },
                  { Icon: YouTubeIcon, label: "YouTube" },
                ].map(({ Icon, label }) => (
                  <a
                    key={label}
                    href="#"
                    aria-label={label}
                    className="w-8 h-8 rounded-lg bg-surface border border-border flex items-center justify-center hover:border-primary/40 hover:bg-primary-light transition-all"
                  >
                    <Icon size={14} className="text-ink-muted hover:text-primary" />
                  </a>
                ))}
              </div>
            </div>

            {/* Links */}
            {[
              {
                title: "Platform",
                links: ["Features", "Integrations", "Security", "Pricing"],
              },
              {
                title: "Company",
                links: ["About Us", "Careers", "Blog", "Contact Us"],
              },
              {
                title: "Resources",
                links: ["Help Centre", "Documentation", "API"],
              },
              {
                title: "Legal",
                links: ["Privacy Policy", "Terms & Conditions"],
              },
            ].map((col) => (
              <div key={col.title}>
                <p className="footer-heading">{col.title}</p>
                <div className="flex flex-col gap-2.5">
                  {col.links.map((link) => (
                    <a key={link} href="#" className="footer-link">
                      {link}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Newsletter */}
          <div className="river-separator mb-8"></div>
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div className="text-xs text-ink-muted">
              © {new Date().getFullYear()} Aira AI. All rights reserved.
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-ink-muted">Stay Updated</span>
              <div className="flex">
                <input
                  type="email"
                  placeholder="Enter your email"
                  className="form-input-dark text-xs px-3 py-2 rounded-r-none w-48"
                />
                <button className="px-4 py-2 bg-gradient-to-r from-[#4c1d95] to-[#5b21b6] text-white text-xs font-semibold rounded-r-lg rounded-l-none hover:opacity-90 transition-opacity">
                  Subscribe
                </button>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
