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
