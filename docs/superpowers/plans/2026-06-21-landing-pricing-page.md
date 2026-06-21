# Landing Page: Pricing Section + Additions

## Global Constraints
- Design: "Warm Light Luxury" — cream surfaces, deep violet (#5b21b6) accent, warm ink
- Use existing CSS classes from landing.css (glass-dark, bento-card, section-eyebrow, section-title, etc.)
- No AI model names exposed (no Groq, no Llama, no model references)
- No fake social proof (no "500+ businesses" — AIRA hasn't launched yet)
- page.tsx must stay under 800 lines total
- All new sections use the `reveal` class for scroll-triggered animation
- Existing landing components: HeroRipple, RiverThread, RiverDelta, useRipple, useReducedMotion
- Lucide React for icons
- No trailing summaries, no inline comments unless WHY is non-obvious
- Bloom Matrix mentioned once (footer only), not prominently
- Pricing in INR (₹) — this is an India-focused B2B SaaS

## Task 1: Extract page.tsx into section components

Refactor the 887-line `frontend/app/page.tsx` into focused section components.

### Files to create:
- `frontend/app/components/landing/icons.tsx` — Move all 5 custom SVG icon components (WhatsAppIcon, InstagramIcon, FacebookIcon, LinkedInIcon, YouTubeIcon) here. Export each individually.
- `frontend/app/components/landing/sections/HeroSection.tsx` — Extract the hero section (id="hero"). Receives `scrollToSection` and `ripple` as props.
- `frontend/app/components/landing/sections/ProblemSection.tsx` — Extract the problem cards section (id="features"). No props needed (uses PROBLEMS data internally).
- `frontend/app/components/landing/sections/HowItWorksSection.tsx` — Extract "How Aira Works" section (id="how-it-works"). No props needed.
- `frontend/app/components/landing/sections/PlatformSection.tsx` — Extract platform features bento grid (id="platform"). Receives `scrollToSection` as prop.
- `frontend/app/components/landing/sections/DemoSection.tsx` — Extract the live demo chat simulator (id="demo"). This is the most complex — owns all chat state (chatMessages, currentStep, isTyping, chatEndRef, chatScrollRef). No props from parent.
- `frontend/app/components/landing/sections/IndustriesSection.tsx` — Extract industries grid (id="industries"). No props needed.
- `frontend/app/components/landing/sections/ContactSection.tsx` — Extract CTA + demo form (id="contact"). Owns form state internally.
- `frontend/app/components/landing/sections/Footer.tsx` — Extract footer. No props needed.

### Data to move into landing.data.ts:
Move these arrays from page.tsx into the existing `landing.data.ts`:
- `SIMULATED_MESSAGES`
- `PROBLEMS`
- `PLATFORM_FEATURES`
- `INDUSTRIES`

Export the TypeScript types for message sender, problem, platform feature, and industry.

### page.tsx becomes:
A thin orchestrator (~60-80 lines) that:
- Imports all section components
- Keeps only: nav scroll state, mobile menu state, scrollToSection function, ripple hook, IntersectionObserver effect
- Renders: noise overlay, fluid bg, RiverThread, nav, then all section components in order, then footer

### Acceptance criteria:
- Zero visual regression — the page looks identical before and after
- page.tsx is under 120 lines
- Each section component is self-contained with its own state where needed
- All imports resolve, no TypeScript errors
- `npm run build` passes

## Task 2: Add Capability Strip section

Create a new section component placed between Hero and Problem sections.

### File: `frontend/app/components/landing/sections/CapabilityStrip.tsx`

A compact horizontal bar showing 4 platform capabilities with icons:

| Icon | Label | Subtext |
|------|-------|---------|
| Layers (lucide) | 4 Channels | WhatsApp, Instagram, Telegram, Facebook |
| Zap (lucide) | 24/7 AI Response | Always-on automated replies |
| Timer (lucide) | < 2s Reply Time | Instant lead engagement |
| Headset (lucide) | Built-in Telecalling | Calls + AI coaching in one platform |

### Design:
- Full-width strip with `glass-dark` background
- Horizontal layout on desktop (4 columns), 2x2 grid on mobile
- Each item: icon (in primary-light circle) + label (bold, 14px) + subtext (muted, 12px)
- Compact — max 100px content height
- Uses `reveal` class for scroll animation
- No section eyebrow or title — this is a trust strip, not a section

### CSS: Add to landing.css
```css
.capability-strip { ... }
.capability-item { ... }
```

### Acceptance criteria:
- Strip renders between Hero and Problem sections in page.tsx
- Responsive: 4 columns desktop, 2x2 mobile
- Uses existing design tokens (no new colors)
- `npm run build` passes

## Task 3: Add Pricing Section with tiers, comparison, and FAQ

Create the pricing section — the core deliverable.

### File: `frontend/app/components/landing/sections/PricingSection.tsx`

### Data: Add to `landing.data.ts`:
```typescript
export interface PricingTier {
  name: string;
  monthlyPrice: number | null; // null = custom
  annualPrice: number | null;
  description: string;
  users: string;
  extraUserPrice: string;
  highlight: boolean; // true for Growth (recommended)
  badge?: string; // "Most Popular" for Growth
  features: { text: string; included: boolean }[];
  cta: string;
}
```

Pricing tiers data:

**Starter — ₹2,499/mo (₹1,999/mo annual)**
- 3 users, extra at ₹299/mo
- Features included: WhatsApp channel, AI conversations (500/mo), Lead management, Lead scoring (A/B/C/D), Broadcasts (1,000 contacts/mo), Basic analytics, Email support
- Features excluded: Telecalling, Bot flows, Knowledge base, Call recording & AI coaching, Bookings & payments, Revenue intelligence, Auto-failover
- CTA: "Start Free Trial"

**Growth — ₹5,999/mo (₹4,799/mo annual) — HIGHLIGHTED, badge "Most Popular"**
- 10 users, extra at ₹249/mo
- Features included: Everything in Starter, + 2 channels (WhatsApp + 1 more), AI conversations (3,000/mo), Broadcasts (10,000 contacts/mo), Telecalling (5 callers), Bot flows (3 flows), Knowledge base (50 docs), Full analytics, Priority support
- Features excluded: Call recording & AI coaching, Bookings & payments, Revenue intelligence, Auto-failover
- CTA: "Start Free Trial"

**Business — ₹11,999/mo (₹9,599/mo annual)**
- 25 users, extra at ₹199/mo
- Features included: Everything in Growth, + All 4 channels, Unlimited AI conversations, Unlimited broadcasts, Unlimited callers, Unlimited bot flows, Full knowledge base, Call recording & AI coaching, Bookings & payments, Revenue intelligence, Auto-failover, Dedicated support
- CTA: "Start Free Trial"

**Enterprise — Custom pricing**
- Unlimited users
- Features included: Everything in Business, + Custom integrations, White-label option, SLA guarantee, Dedicated account manager, On-premise option
- CTA: "Contact Sales"

### Section structure:
1. Section eyebrow: "SIMPLE, TRANSPARENT PRICING"
2. Title: "One Platform. One Price."
3. Subtitle: "Replace your WhatsApp tool, telecalling CRM, and analytics dashboard with AIRA."
4. Monthly/Annual toggle (pill switch, "Save 20%" badge on annual)
5. 4 pricing cards in responsive grid (1 col mobile, 2 col tablet, 4 col desktop)
6. Trust line below cards: "WhatsApp messages charged at Meta's cost — zero markup from AIRA"
7. "Replace 3 Tools" comparison box
8. FAQ accordion (5 items)

### Pricing card design:
- `glass-dark` base
- Growth card: violet gradient top border (2px), subtle violet glow shadow, "Most Popular" badge
- Price: large font, ₹ prefix, /mo suffix
- Annual price shown as strikethrough when monthly is selected, and vice versa
- User count + extra user price
- Feature list with CheckCircle2 (green) for included, X (muted) for excluded
- CTA button: btn-accent for Growth, btn-ghost-dark for others

### "Replace 3 Tools" comparison:
A card below the pricing grid showing:
- Left side: "Without AIRA" — 3 line items (WhatsApp Tool ₹3,000/mo + Telecalling CRM ₹5,000/mo + Analytics ₹3,000/mo = ₹11,000/mo)
- Right side: "With AIRA" — Growth plan at ₹5,999/mo
- Savings badge: "Save 45%"
- Use glass-dark styling with a violet accent border

### FAQ items (accordion):
1. "Do I pay extra for WhatsApp messages?" → "Yes — Meta charges per template message (₹1.09 for marketing, ₹0.15 for utility in India). AIRA passes these through at cost with zero markup."
2. "Is there a free trial?" → "Yes — 14-day free trial on the Growth plan. No credit card required."
3. "Can I switch plans anytime?" → "Yes — upgrade or downgrade anytime. Changes take effect on your next billing cycle."
4. "What about calling charges?" → "Voice calling minutes are billed separately through our telephony partner. Rates start at ₹1/minute."
5. "Do you offer annual billing?" → "Yes — save 20% with annual billing on any plan."

### CSS additions to landing.css:
- `.pricing-toggle` — pill-shaped monthly/annual switch
- `.pricing-card` — base card style
- `.pricing-card-highlight` — Growth card violet accent
- `.pricing-badge` — "Most Popular" badge
- `.pricing-price` — large price display
- `.pricing-feature` — feature list item
- `.pricing-comparison` — "Replace 3 Tools" box
- `.pricing-faq` — FAQ accordion styles
- `.faq-item` — individual FAQ item with expand/collapse

### Acceptance criteria:
- Section renders with id="pricing" between Platform Features and Live Demo
- Monthly/Annual toggle works and updates all prices
- Growth card is visually highlighted as recommended
- Comparison box shows savings math
- FAQ accordion expands/collapses items
- Responsive: stacks to 1 column on mobile
- Uses existing design tokens
- `npm run build` passes

## Task 4: Fix nav links + add Bloom Matrix to footer

### Nav fixes in page.tsx orchestrator:
- "Pricing" nav link → `scrollToSection("pricing")` (currently points to "platform")
- Remove "About Us" nav link (no dedicated section exists)
- Update mobile menu to match
- Keep: Home, Features, Industries, Pricing, Contact

### Footer update in Footer.tsx:
- Add below the brand description: "A product of **Bloom Matrix**" — small text, muted color, no logo
- Update copyright: "© 2024 Bloom Matrix. All rights reserved."
- Remove "Pricing" from Platform links column (it's now a section, not a page)

### Acceptance criteria:
- Nav "Pricing" scrolls to the pricing section
- "About Us" link removed from desktop nav and mobile menu
- Footer shows Bloom Matrix mention once
- `npm run build` passes
