"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Menu, X } from "lucide-react";
import "./landing.css";
import RiverThread from "./components/landing/RiverThread";
import { useRipple } from "./components/landing/useRipple";
import HeroSection from "./components/landing/sections/HeroSection";
import ProblemSection from "./components/landing/sections/ProblemSection";
import HowItWorksSection from "./components/landing/sections/HowItWorksSection";
import PlatformSection from "./components/landing/sections/PlatformSection";
import DemoSection from "./components/landing/sections/DemoSection";
import IndustriesSection from "./components/landing/sections/IndustriesSection";
import ContactSection from "./components/landing/sections/ContactSection";
import Footer from "./components/landing/sections/Footer";

const NAV_LINKS = [
  { id: "hero", label: "Home" }, { id: "features", label: "Features" },
  { id: "industries", label: "Industries" }, { id: "platform", label: "Pricing" },
  { id: "contact", label: "Contact" },
];

export default function LandingPage() {
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [navScrolled, setNavScrolled] = useState(false);
  const ripple = useRipple();

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) e.target.classList.add("visible"); }),
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );
    document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const h = () => setNavScrolled(window.scrollY > 40);
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);

  const scrollTo = (id: string) => { setMobileMenuOpen(false); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); };

  return (
    <div className="landing-page">
      <div className="noise-overlay" aria-hidden="true" />
      <div className="fluid-bg" aria-hidden="true">
        <div className="fluid-orb fluid-orb-1" /><div className="fluid-orb fluid-orb-2" />
        <div className="fluid-orb fluid-orb-3" /><div className="fluid-orb fluid-orb-4" />
      </div>
      <RiverThread />

      <nav className={`nav-landing ${navScrolled ? "scrolled" : ""}`} id="nav-main">
        <div className="max-w-7xl mx-auto px-6 md:px-10 flex justify-between items-center h-[72px]">
          <button onClick={() => scrollTo("hero")} className="flex items-center gap-2.5 group">
            <span className="nav-logo-text">Aira</span>
            <span className="text-ink-muted text-xs font-medium hidden sm:inline ml-1 border-l border-border pl-2.5">AI Revenue Acceleration</span>
          </button>
          <div className="hidden md:flex items-center gap-8">
            {NAV_LINKS.map((l) => <button key={l.label} onClick={() => scrollTo(l.id)} className="nav-link">{l.label}</button>)}
          </div>
          <div className="hidden md:flex items-center gap-3">
            <button onClick={() => router.push("/login")} className="btn-login">Login</button>
            <button onClick={() => scrollTo("contact")} onPointerDown={ripple} className="btn-accent text-sm py-2 px-5 ripple-host">Book a Demo <ArrowRight size={14} /></button>
          </div>
          <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="md:hidden text-ink-secondary hover:text-ink transition-colors" aria-label="Toggle Menu">
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
        {mobileMenuOpen && (
          <div className="mobile-menu-overlay md:hidden">
            <div className="pt-24 px-8 flex flex-col gap-6">
              {NAV_LINKS.map((l) => <button key={l.label} onClick={() => scrollTo(l.id)} className="text-left text-lg font-medium text-ink-secondary hover:text-ink transition-colors">{l.label}</button>)}
              <div className="river-separator my-4" />
              <button onClick={() => { setMobileMenuOpen(false); router.push("/login"); }} className="btn-login w-full justify-center">Login</button>
              <button onClick={() => { setMobileMenuOpen(false); scrollTo("contact"); }} className="btn-accent w-full justify-center">Book a Demo <ArrowRight size={16} /></button>
            </div>
          </div>
        )}
      </nav>

      <main className="relative z-[2]">
        <HeroSection scrollToSection={scrollTo} ripple={ripple} />
        <ProblemSection />
        <HowItWorksSection />
        <PlatformSection scrollToSection={scrollTo} />
        <DemoSection />
        <IndustriesSection />
        <ContactSection />
      </main>
      <Footer />
    </div>
  );
}
