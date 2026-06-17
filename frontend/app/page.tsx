"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Outfit, Inter } from "next/font/google";
import {
  Sparkles,
  MessageSquare,
  Send,
  Database,
  Network,
  Headset,
  CalendarDays,
  CheckCircle2,
  Menu,
  X,
  Activity
} from "lucide-react";

// Custom SVG Icons for Instagram & Facebook (Baseline SVG)
function InstagramIcon({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

function FacebookIcon({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
    </svg>
  );
}
import "./landing.css";

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
  display: "swap",
  weight: ["400", "500", "600", "700", "800"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  weight: ["300", "400", "500", "600", "700"],
});

// Chat Simulator Data
const SIMULATED_MESSAGES = [
  { sender: "customer", text: "Hi! I'm interested in the Enterprise plan for my 20-person agency.", time: "14:02" },
  { sender: "aira", text: "Great! I can help with that. Based on your size, you'd qualify for our Priority Onboarding. Would you like to see a custom demo?", time: "14:02" },
  { sender: "customer", text: "Yes, Thursday at 10 AM works.", time: "14:03" },
  { sender: "aira", text: "Perfect. Appointment confirmed. I've sent a calendar invite and a brief prep doc to your email. See you then!", time: "14:03" },
  { sender: "system", text: "Lead Scored: 9.8/10 (Hot) • Routed to priority telecaller queue", time: "14:03" },
];

export default function LandingPage() {
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<typeof SIMULATED_MESSAGES>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

  // Mesh gradient mouse tracking
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({
        x: (e.clientX / window.innerWidth) * 25,
        y: (e.clientY / window.innerHeight) * 25,
      });
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
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
      // Loop simulator with a reset delay
      const resetTimer = setTimeout(() => {
        setChatMessages([]);
        setCurrentStep(0);
      }, 5000);
      return () => clearTimeout(resetTimer);
    }
  }, [currentStep]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, isTyping]);

  return (
    <div className={`${outfit.variable} ${inter.variable} landing-container font-sans overflow-x-hidden selection:bg-emerald-500/30 selection:text-emerald-300`}>
      {/* Top Navigation Bar */}
      <nav className="fixed top-0 w-full z-50 bg-[#050505]/70 backdrop-blur-xl border-b border-white/5 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 md:px-12 flex justify-between items-center h-20">
          <div className="flex items-center gap-2.5">
            <div className="w-3.5 h-3.5 bg-emerald-500 rounded-full pulse-dot"></div>
            <span className="font-display font-bold text-xl text-white tracking-tight">Aira AI</span>
          </div>

          {/* Desktop Navbar Links */}
          <div className="hidden md:flex gap-8 items-center">
            <a href="#features" className="text-white hover:text-emerald-400 transition-colors font-medium text-sm">Features</a>
            <a href="#integrations" className="text-[#94a3b8] hover:text-emerald-400 transition-colors font-medium text-sm">Integrations</a>
            <a href="#pricing" className="text-[#94a3b8] hover:text-emerald-400 transition-colors font-medium text-sm">Pricing</a>
          </div>

          <div className="hidden md:flex items-center gap-4">
            <button
              onClick={() => router.push("/login")}
              id="nav-login-btn"
              className="px-5 py-2.5 rounded-xl text-emerald-400 hover:bg-white/5 transition-all font-semibold text-sm"
            >
              Login
            </button>
            <button
              onClick={() => router.push("/login")}
              id="nav-start-btn"
              className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-sm emerald-glow transition-all active:scale-[0.98]"
            >
              Get Started
            </button>
          </div>

          {/* Mobile Menu Button */}
          <div className="md:hidden flex items-center">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="text-[#94a3b8] hover:text-white transition-colors"
              aria-label="Toggle Menu"
            >
              {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile Dropdown Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden w-full bg-[#090d16] border-b border-white/10 px-6 py-6 flex flex-col gap-5 animate-fade-in">
            <a href="#features" onClick={() => setMobileMenuOpen(false)} className="text-white hover:text-emerald-400 transition-colors font-medium text-base">Features</a>
            <a href="#integrations" onClick={() => setMobileMenuOpen(false)} className="text-[#94a3b8] hover:text-emerald-400 transition-colors font-medium text-base">Integrations</a>
            <a href="#pricing" onClick={() => setMobileMenuOpen(false)} className="text-[#94a3b8] hover:text-emerald-400 transition-colors font-medium text-base">Pricing</a>
            <hr className="border-white/10 my-1" />
            <div className="flex flex-col gap-3">
              <button
                onClick={() => { setMobileMenuOpen(false); router.push("/login"); }}
                className="w-full py-3 rounded-xl text-emerald-400 hover:bg-white/5 transition-all font-semibold text-base border border-emerald-500/20"
              >
                Login
              </button>
              <button
                onClick={() => { setMobileMenuOpen(false); router.push("/login"); }}
                className="w-full py-3 rounded-xl bg-emerald-500 text-black font-semibold text-base transition-all text-center"
              >
                Get Started
              </button>
            </div>
          </div>
        )}
      </nav>

      <main className="pt-28">
        {/* Hero Section */}
        <section className="max-w-7xl mx-auto px-6 md:px-12 grid md:grid-cols-2 gap-12 items-center relative py-16 md:py-24">
          <div
            className="absolute -z-10 top-0 left-0 w-full h-full mesh-gradient pointer-events-none"
            style={{ transform: `translate(${mousePosition.x}px, ${mousePosition.y}px)` }}
          ></div>
          
          <div className="flex flex-col gap-6 animate-fade-in">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 self-start font-medium text-xs tracking-wider uppercase">
              <Sparkles size={13} className="text-emerald-400" />
              AI-Powered Conversational CRM
            </span>
            <h1 className="font-display font-extrabold text-4xl md:text-5xl lg:text-6xl text-white leading-tight">
              Zero-Leads-Lost <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-indigo-400">Conversational Automation</span>
            </h1>
            <p className="font-sans text-base md:text-lg text-[#94a3b8] max-w-xl leading-relaxed">
              Empower your business with real-time multichannel lead capture, instant RAG-based AI auto-replies, smart composite lead scoring, and automated click-to-call TeleCMI dialing.
            </p>
            <div className="flex flex-wrap gap-4 pt-4">
              <button
                onClick={() => router.push("/login")}
                id="hero-start-btn"
                className="px-8 py-4 rounded-xl bg-emerald-500 text-black font-bold text-base hover:scale-[1.02] emerald-glow active:scale-[0.98] transition-all"
              >
                Get Started Free
              </button>
              <a
                href="#demo"
                className="px-8 py-4 rounded-xl border border-white/10 hover:border-emerald-500/30 text-white font-semibold text-base hover:bg-white/5 transition-all text-center"
              >
                Watch Simulator
              </a>
            </div>
          </div>

          <div className="relative group animate-fade-in" style={{ animationDelay: "0.2s" }}>
            <div className="absolute -inset-4 bg-emerald-500/20 blur-3xl opacity-20 group-hover:opacity-30 transition-opacity rounded-3xl"></div>
            <div className="relative z-10 glass-card p-1.5 rounded-3xl overflow-hidden shadow-2xl">
              <img
                alt="Aira AI High fidelity B2B Conversational Dashboard mockup"
                className="rounded-2xl border border-white/10 w-full object-cover"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuCajZF41CUGOKIRMzkWb5M4Y0-58_hVWzRmispcNBtL4Z1RSR63L8ZeJD52GJrBAgNzsN01C-lsrIHUOZ9UzGU8y_hM9Urxu7ZrOEr4ZCa8ZpKk_nqhs2L-28lT23CMAPlin28f_wuopFi9xb-4GMIKSwU-slUw1dL4CNCui05Ls7GwbB5OyM-5Aw97ReIm0KWssz85I-YRwKncYXpN8TWnQY511xBnXj2QZMt0f7dUcl6ynE4SMTZVLAqc8I0mu5V1vD2-wV_UIkOD"
              />
            </div>
          </div>
        </section>

        {/* Integrations Row */}
        <section id="integrations" className="py-12 border-y border-white/5 bg-gradient-to-r from-emerald-950/5 via-indigo-950/5 to-emerald-950/5 overflow-hidden">
          <div className="max-w-7xl mx-auto px-6 md:px-12">
            <p className="text-center font-semibold text-xs text-[#64748b] mb-8 uppercase tracking-widest">Instant Multi-Tenant Webhook Integration</p>
            <div className="flex flex-wrap justify-center items-center gap-6 md:gap-10">
              <div className="glass-card px-5 py-3 rounded-2xl flex items-center gap-3">
                <MessageSquare className="text-emerald-400" size={20} />
                <span className="font-semibold text-[#e2e8f0] text-sm">WhatsApp Cloud API</span>
              </div>
              <div className="glass-card px-5 py-3 rounded-2xl flex items-center gap-3">
                <InstagramIcon className="text-purple-400" size={20} />
                <span className="font-semibold text-[#e2e8f0] text-sm">Instagram Webhooks</span>
              </div>
              <div className="glass-card px-5 py-3 rounded-2xl flex items-center gap-3">
                <FacebookIcon className="text-blue-400" size={20} />
                <span className="font-semibold text-[#e2e8f0] text-sm">Messenger API</span>
              </div>
              <div className="glass-card px-5 py-3 rounded-2xl flex items-center gap-3">
                <Send className="text-sky-400" size={20} />
                <span className="font-semibold text-[#e2e8f0] text-sm">Telegram Bot API</span>
              </div>
            </div>
          </div>
        </section>

        {/* Core Features Grid */}
        <section id="features" className="max-w-7xl mx-auto px-6 md:px-12 py-20 md:py-28 relative">
          <div className="text-center mb-16 md:mb-20">
            <span className="text-emerald-400 font-bold text-xs uppercase tracking-wider">Engineered for Results</span>
            <h2 className="font-display font-extrabold text-3xl md:text-4xl text-white mt-2">Enterprise-Grade Sales Tech Stack</h2>
            <p className="text-[#94a3b8] font-sans text-sm md:text-base max-w-xl mx-auto mt-3">High-performance tools to scale operations, increase speeds, and eliminate human latency.</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* feature 1 */}
            <div className="glass-card p-8 rounded-3xl flex flex-col gap-4 relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-6 opacity-[0.02] group-hover:opacity-[0.06] transition-all">
                <Database size={100} className="text-white" />
              </div>
              <div className="w-12 h-12 bg-emerald-500/10 rounded-2xl flex items-center justify-center border border-emerald-500/20">
                <Database className="text-emerald-400" size={22} />
              </div>
              <h3 className="font-display font-bold text-lg text-white mt-2">RAG Knowledge Base</h3>
              <p className="text-[#94a3b8] text-sm leading-relaxed">
                Connect your business files. Employs pgvector database and Jina v3 embeddings for instant, accurate auto-replies via Groq Llama 3.3.
              </p>
              <div className="mt-auto pt-6 flex gap-2">
                <span className="px-2.5 py-1 rounded-lg bg-white/5 text-xs text-[#94a3b8] font-mono">pgvector</span>
                <span className="px-2.5 py-1 rounded-lg bg-white/5 text-xs text-[#94a3b8] font-mono">Jina v3</span>
              </div>
            </div>

            {/* feature 2 */}
            <div className="glass-card p-8 rounded-3xl flex flex-col gap-4 relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-6 opacity-[0.02] group-hover:opacity-[0.06] transition-all">
                <Network size={100} className="text-white" />
              </div>
              <div className="w-12 h-12 bg-emerald-500/10 rounded-2xl flex items-center justify-center border border-emerald-500/20">
                <Network className="text-emerald-400" size={22} />
              </div>
              <h3 className="font-display font-bold text-lg text-white mt-2">Visual Bot Flows</h3>
              <p className="text-[#94a3b8] text-sm leading-relaxed">
                A drag-and-drop node graph canvas for building WhatsApp flows. Built-in pause-on-reply logic for seamless agent handover.
              </p>
              <div className="mt-auto pt-6 flex gap-2">
                <span className="px-2.5 py-1 rounded-lg bg-white/5 text-xs text-[#94a3b8] font-mono">Resumable</span>
                <span className="px-2.5 py-1 rounded-lg bg-white/5 text-xs text-[#94a3b8] font-mono">Autopilot</span>
              </div>
            </div>

            {/* feature 3 */}
            <div className="glass-card p-8 rounded-3xl flex flex-col gap-4 relative overflow-hidden group border-emerald-500/20">
              <div className="absolute top-0 right-0 p-6 opacity-[0.04] group-hover:opacity-[0.08] transition-all">
                <Headset size={100} className="text-emerald-500" />
              </div>
              <div className="w-12 h-12 bg-emerald-500/10 rounded-2xl flex items-center justify-center border border-emerald-500/20">
                <Headset className="text-emerald-400" size={22} />
              </div>
              <h3 className="font-display font-bold text-lg text-white mt-2">Telecalling Cockpit</h3>
              <p className="text-[#94a3b8] text-sm leading-relaxed">
                Click-to-call TeleCMI dialing. Includes Groq Whisper transcriptions, automated call scoring, and interactive AI wrap-up coaching.
              </p>
              <div className="mt-auto pt-6 flex gap-2">
                <span className="px-2.5 py-1 rounded-lg bg-emerald-500/10 text-xs text-emerald-400 font-mono">Voice Logs</span>
                <span className="px-2.5 py-1 rounded-lg bg-white/5 text-xs text-[#94a3b8] font-mono">Whisper</span>
              </div>
            </div>

            {/* feature 4 */}
            <div className="glass-card p-8 rounded-3xl flex flex-col gap-4 relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-6 opacity-[0.02] group-hover:opacity-[0.06] transition-all">
                <CalendarDays size={100} className="text-white" />
              </div>
              <div className="w-12 h-12 bg-emerald-500/10 rounded-2xl flex items-center justify-center border border-emerald-500/20">
                <CalendarDays className="text-emerald-400" size={22} />
              </div>
              <h3 className="font-display font-bold text-lg text-white mt-2">Smart Bookings</h3>
              <p className="text-[#94a3b8] text-sm leading-relaxed">
                Automated booking state machine linking follow-ups. Generates Razorpay payment links directly in the messaging stream.
              </p>
              <div className="mt-auto pt-6 flex gap-2">
                <span className="px-2.5 py-1 rounded-lg bg-white/5 text-xs text-[#94a3b8] font-mono">Razorpay</span>
                <span className="px-2.5 py-1 rounded-lg bg-white/5 text-xs text-[#94a3b8] font-mono">Scheduler</span>
              </div>
            </div>
          </div>
        </section>

        {/* Live Simulator Widget */}
        <section id="demo" className="max-w-4xl mx-auto px-6 md:px-12 py-16">
          <div className="text-center mb-10">
            <h2 className="font-display font-extrabold text-2xl md:text-3xl text-white">Watch Aira AI in Action</h2>
            <p className="text-[#94a3b8] text-sm mt-1">Real-time simulation of incoming leads being captured, scored, and automated.</p>
          </div>
          
          <div className="glass-card rounded-[2rem] overflow-hidden flex flex-col md:flex-row shadow-2xl border border-white/10">
            {/* Simulator sidebar */}
            <div className="md:w-1/3 bg-white/[0.01] p-8 border-b md:border-b-0 md:border-r border-white/5">
              <h4 className="font-display font-bold text-lg text-white mb-3 flex items-center gap-2">
                <Activity size={18} className="text-emerald-400 animate-pulse" />
                Live Agent
              </h4>
              <p className="text-xs text-[#94a3b8] leading-relaxed mb-8">
                Aira monitors custom webhooks, verifies signatures, queries pgvector, routes callback schedules, and logs telecaller logs.
              </p>
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 pulse-dot"></div>
                  <span className="font-mono text-xs text-[#e2e8f0]">Signature Verified</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-indigo-500"></div>
                  <span className="font-mono text-xs text-[#e2e8f0]">RAG Query Context</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full transition-colors duration-300 ${currentStep >= 5 ? 'bg-emerald-500' : 'bg-white/20'}`}></div>
                  <span className={`font-mono text-xs transition-colors duration-300 ${currentStep >= 5 ? 'text-[#e2e8f0]' : 'text-[#64748b]'}`}>Lead Handover</span>
                </div>
              </div>
            </div>

            {/* Chat screen */}
            <div className="md:w-2/3 p-8 flex flex-col justify-between bg-[#070707] min-h-[360px]">
              <div className="flex flex-col gap-4 overflow-y-auto max-h-[280px] pr-2 scrollbar-thin">
                {chatMessages.map((msg, i) => {
                  if (msg.sender === "system") {
                    return (
                      <div key={i} className="flex justify-center my-2 animate-fade-in">
                        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-4 py-1.5 rounded-full font-semibold text-xs flex items-center gap-1.5 shadow-sm">
                          <CheckCircle2 size={13} />
                          {msg.text}
                        </div>
                      </div>
                    );
                  }

                  const isAira = msg.sender === "aira";
                  return (
                    <div
                      key={i}
                      className={`flex flex-col max-w-[80%] animate-fade-in ${isAira ? "self-end" : "self-start"}`}
                    >
                      <div
                        className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                          isAira
                            ? "bg-emerald-500/15 border border-emerald-500/20 text-[#e2e8f0] rounded-tr-none"
                            : "bg-white/5 border border-white/5 text-[#e2e8f0] rounded-tl-none"
                        }`}
                      >
                        {msg.text}
                      </div>
                      <span className={`text-[10px] mt-1 ${isAira ? "self-end text-emerald-500/60" : "self-start text-[#64748b]"}`}>
                        {isAira ? "Aira AI" : "Lead"} • {msg.time}
                      </span>
                    </div>
                  );
                })}
                
                {isTyping && (
                  <div className="self-end flex items-center gap-1 bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 rounded-2xl rounded-tr-none max-w-[80%]">
                    <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }}></div>
                    <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }}></div>
                    <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }}></div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
              
              <div className="border-t border-white/5 pt-4 flex justify-between items-center text-[10px] text-[#64748b]">
                <span>Channel: WhatsApp API</span>
                <span>Active Session Window: 24h</span>
              </div>
            </div>
          </div>
        </section>

        {/* Final Call to Action */}
        <section className="max-w-7xl mx-auto px-6 md:px-12 py-20 text-center">
          <div className="glass-card py-20 px-8 rounded-[2.5rem] border-emerald-500/20 overflow-hidden relative shadow-2xl">
            <div className="absolute inset-0 mesh-gradient opacity-30 pointer-events-none"></div>
            <h2 className="font-display font-extrabold text-3xl md:text-5xl text-white mb-4 relative z-10">
              Never Miss a Lead Again
            </h2>
            <p className="font-sans text-[#94a3b8] text-base md:text-lg mb-10 max-w-xl mx-auto relative z-10">
              Verify signatures, automate reply channels, score lead lists, and connect voice outcomes instantly.
            </p>
            <div className="flex flex-col sm:flex-row justify-center items-center gap-4 relative z-10">
              <button
                onClick={() => router.push("/login")}
                className="w-full sm:w-auto px-8 py-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-base transition-all emerald-glow"
              >
                Sign In & Configure App
              </button>
              <button
                onClick={() => router.push("/login")}
                className="w-full sm:w-auto px-8 py-4 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white font-semibold text-base transition-all"
              >
                Access Dashboard
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="w-full bg-[#050505] border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-16 flex flex-col md:flex-row justify-between items-center gap-8">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-emerald-500 rounded-full"></div>
            <span className="font-display font-bold text-lg text-white">Aira AI</span>
          </div>
          <div className="flex gap-6 flex-wrap justify-center">
            <a href="#" className="font-sans text-xs text-[#64748b] hover:text-emerald-400 transition-colors">Privacy Policy</a>
            <a href="#" className="font-sans text-xs text-[#64748b] hover:text-emerald-400 transition-colors">Terms of Service</a>
            <a href="#" className="font-sans text-xs text-[#64748b] hover:text-emerald-400 transition-colors">Contact</a>
            <a href="#" className="font-sans text-xs text-[#64748b] hover:text-emerald-400 transition-colors">Documentation</a>
          </div>
          <div className="font-sans text-xs text-[#64748b]">
            © {new Date().getFullYear()} Aira AI. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
}
