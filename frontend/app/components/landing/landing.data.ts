import {
  MessageSquare,
  Bot,
  Star,
  PhoneCall,
  BarChart3,
  TrendingUp,
  MessageCircle,
  Clock,
  Target,
  Landmark,
  Send,
  Headset,
  GraduationCap,
  Building2,
  Heart,
  Car,
  Factory,
  type LucideIcon,
} from "lucide-react";

export interface FlowStep {
  icon: LucideIcon;
  title: string;
  desc: string;
}

/** The "enquiry → revenue" pipeline, rendered as a river delta. */
export const FLOW_STEPS: FlowStep[] = [
  { icon: MessageSquare, title: "Enquiry", desc: "Customer reaches out on WhatsApp, Website or Ads" },
  { icon: Bot, title: "AI Conversation", desc: "Instant, human-like AI conversations 24/7" },
  { icon: Star, title: "Lead Qualification", desc: "AI identifies intent and scores the lead" },
  { icon: PhoneCall, title: "Telecaller Assignment", desc: "Smart assignment to the right team member" },
  { icon: BarChart3, title: "AI Evaluation", desc: "Calls are tracked and performance is evaluated" },
  { icon: TrendingUp, title: "Revenue", desc: "Timely follow-ups close deals and drive growth" },
];

export interface SimulatedMessage {
  sender: "customer" | "aira" | "system";
  text: string;
  time: string;
}

export const SIMULATED_MESSAGES: SimulatedMessage[] = [
  { sender: "customer", text: "Hi! I'm interested in the Enterprise plan for my 20-person agency.", time: "14:02" },
  { sender: "aira", text: "Great! I can help with that. Based on your team size, you'd qualify for our Priority Onboarding. Would you like to see a custom demo?", time: "14:02" },
  { sender: "customer", text: "Yes, Thursday at 10 AM works.", time: "14:03" },
  { sender: "aira", text: "Perfect. Appointment confirmed. I've sent a calendar invite and a brief prep doc to your email. See you then!", time: "14:03" },
  { sender: "system", text: "Lead Scored: 9.8/10 (Hot) • Routed to priority telecaller queue", time: "14:03" },
];

export interface Problem {
  icon: LucideIcon;
  title: string;
  desc: string;
}

export const PROBLEMS: Problem[] = [
  { icon: MessageCircle, title: "Enquiries go unanswered", desc: "Leads slip through WhatsApp, web, and social channels without any response." },
  { icon: Clock, title: "Follow-ups get missed", desc: "Manual tracking leads to forgotten callbacks and cold prospects." },
  { icon: TrendingUp, title: "Hot leads turn cold", desc: "Without instant AI response, high-intent leads lose interest quickly." },
  { icon: Target, title: "Telecaller performance is hard to measure", desc: "No visibility into call quality, outcomes, or team performance." },
  { icon: Landmark, title: "Revenue opportunities are lost", desc: "Disjointed systems mean you can't optimize the full enquiry-to-revenue pipeline." },
];

export interface PlatformFeature {
  icon: LucideIcon;
  title: string;
  desc: string;
  tags: string[];
}

export const PLATFORM_FEATURES: PlatformFeature[] = [
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

export interface Industry {
  icon: LucideIcon;
  name: string;
}

export const INDUSTRIES: Industry[] = [
  { icon: GraduationCap, name: "Education" },
  { icon: Building2, name: "Real Estate" },
  { icon: Heart, name: "Healthcare" },
  { icon: Car, name: "Automotive" },
  { icon: Factory, name: "Manufacturing" },
  { icon: Landmark, name: "Financial Services" },
];

/* ── Pricing ────────────────────────────────────────────── */

export interface PricingTier {
  name: string;
  monthlyPrice: number | null;
  annualPrice: number | null;
  description: string;
  users: string;
  extraUserPrice: string;
  highlight: boolean;
  badge?: string;
  features: { text: string; included: boolean }[];
  cta: string;
}

export const PRICING_TIERS: PricingTier[] = [
  {
    name: "Starter",
    monthlyPrice: 2499,
    annualPrice: 1999,
    description: "For small teams getting started with WhatsApp lead-gen.",
    users: "3 users included",
    extraUserPrice: "₹299/user extra",
    highlight: false,
    features: [
      { text: "WhatsApp channel", included: true },
      { text: "AI conversations (500/mo)", included: true },
      { text: "Lead management", included: true },
      { text: "Lead scoring (A/B/C/D)", included: true },
      { text: "Broadcasts (1,000 contacts/mo)", included: true },
      { text: "Basic analytics", included: true },
      { text: "Email support", included: true },
      { text: "Telecalling", included: false },
      { text: "Bot flows", included: false },
      { text: "Knowledge base", included: false },
      { text: "Call recording & AI coaching", included: false },
      { text: "Bookings & payments", included: false },
      { text: "Revenue intelligence", included: false },
      { text: "Auto-failover", included: false },
    ],
    cta: "Start Free Trial",
  },
  {
    name: "Growth",
    monthlyPrice: 5999,
    annualPrice: 4799,
    description: "For growing teams that need multichannel + telecalling.",
    users: "10 users included",
    extraUserPrice: "₹249/user extra",
    highlight: true,
    badge: "Most Popular",
    features: [
      { text: "Everything in Starter +", included: true },
      { text: "2 channels (WhatsApp + 1 more)", included: true },
      { text: "AI conversations (3,000/mo)", included: true },
      { text: "Broadcasts (10,000 contacts/mo)", included: true },
      { text: "Telecalling (5 callers)", included: true },
      { text: "Bot flows (3 flows)", included: true },
      { text: "Knowledge base (50 docs)", included: true },
      { text: "Full analytics", included: true },
      { text: "Priority support", included: true },
      { text: "Call recording & AI coaching", included: false },
      { text: "Bookings & payments", included: false },
      { text: "Revenue intelligence", included: false },
      { text: "Auto-failover", included: false },
    ],
    cta: "Start Free Trial",
  },
  {
    name: "Business",
    monthlyPrice: 11999,
    annualPrice: 9599,
    description: "For established teams that need the full platform.",
    users: "25 users included",
    extraUserPrice: "₹199/user extra",
    highlight: false,
    features: [
      { text: "Everything in Growth +", included: true },
      { text: "All 4 channels", included: true },
      { text: "Unlimited AI conversations", included: true },
      { text: "Unlimited broadcasts", included: true },
      { text: "Unlimited callers", included: true },
      { text: "Unlimited bot flows", included: true },
      { text: "Full knowledge base", included: true },
      { text: "Call recording & AI coaching", included: true },
      { text: "Bookings & payments", included: true },
      { text: "Revenue intelligence", included: true },
      { text: "Auto-failover", included: true },
      { text: "Dedicated support", included: true },
    ],
    cta: "Start Free Trial",
  },
  {
    name: "Enterprise",
    monthlyPrice: null,
    annualPrice: null,
    description: "For large organizations with custom requirements.",
    users: "Unlimited users",
    extraUserPrice: "",
    highlight: false,
    features: [
      { text: "Everything in Business +", included: true },
      { text: "Custom integrations", included: true },
      { text: "White-label option", included: true },
      { text: "SLA guarantee", included: true },
      { text: "Dedicated account manager", included: true },
      { text: "On-premise option", included: true },
    ],
    cta: "Contact Sales",
  },
];

export interface FaqItem {
  question: string;
  answer: string;
}

export const FAQ_ITEMS: FaqItem[] = [
  {
    question: "Do I pay extra for WhatsApp messages?",
    answer:
      "Yes — Meta charges per template message (₹1.09 for marketing, ₹0.15 for utility in India). AIRA passes these through at cost with zero markup.",
  },
  {
    question: "Is there a free trial?",
    answer:
      "Yes — 14-day free trial on the Growth plan. No credit card required.",
  },
  {
    question: "Can I switch plans anytime?",
    answer:
      "Yes — upgrade or downgrade anytime. Changes take effect on your next billing cycle.",
  },
  {
    question: "What about calling charges?",
    answer:
      "Voice calling minutes are billed separately through our telephony partner. Rates start at ₹1/minute.",
  },
  {
    question: "Do you offer annual billing?",
    answer: "Yes — save 20% with annual billing on any plan.",
  },
];
