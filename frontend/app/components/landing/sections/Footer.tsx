"use client";

import {
  LinkedInIcon,
  FacebookIcon,
  InstagramIcon,
  YouTubeIcon,
} from "../icons";

export default function Footer() {
  return (
    <footer className="footer-dark relative z-[2]">
      <div className="max-w-7xl mx-auto px-6 md:px-10 py-16">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-8 mb-12">
          {/* Brand */}
          <div className="col-span-2">
            <div className="flex items-center gap-2.5 mb-4">
              <span className="nav-logo-text">Aira</span>
            </div>
            <p className="text-xs text-ink-secondary leading-relaxed max-w-xs mb-2">
              We help businesses automate conversations, qualify leads, evaluate telecallers and accelerate revenue.
            </p>
            <p className="text-[10px] text-ink-muted mb-5">A product of <span className="font-semibold">Bloom Matrix</span></p>
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
            © {new Date().getFullYear()} Bloom Matrix. All rights reserved.
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-ink-muted">Stay Updated</span>
            <div className="flex">
              <input
                type="email"
                placeholder="Enter your email"
                className="form-input-dark text-xs px-3 py-2 rounded-r-none w-48"
              />
              <button className="px-4 py-2 bg-gradient-to-r from-[#2e1065] to-[#5b21b6] text-white text-xs font-semibold rounded-r-lg rounded-l-none hover:opacity-90 transition-opacity">
                Subscribe
              </button>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
