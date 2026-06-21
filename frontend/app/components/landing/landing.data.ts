import {
  MessageSquare,
  Bot,
  Star,
  PhoneCall,
  BarChart3,
  TrendingUp,
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
