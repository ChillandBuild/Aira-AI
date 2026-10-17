import { CallCard, ChatCard, RouteCard, ScoreCard } from "./FeatureCards";
import type { Feature } from "./FeatureRow";

// Kicker, title and body are the approved mockup copy. `points` are plain
// descriptions of what the product does today (see .agents/context/subsystem-notes.md:
// knowledge base, chat escalation, hot/warm/cold scoring, assignment, call review).
export const FEATURES: readonly Feature[] = [
  {
    id: "replies",
    kicker: "01 Answer",
    title: "Every enquiry gets a reply",
    body: "Anril AI answers on WhatsApp, web chat and phone, using what you have told it about your business.",
    wash: "teal",
    visual: <ChatCard />,
    points: [
      "Answers from the information you give it about your business.",
      "Hands the conversation to your team when a person is needed.",
    ],
  },
  {
    id: "scoring",
    kicker: "02 Score",
    title: "Know who to call first",
    body: "Each lead gets a score built from what they asked and how they answered, so your team starts with the people most likely to buy.",
    wash: "blue",
    visual: <ScoreCard />,
    points: [
      "Every lead is marked hot, warm or cold.",
      "The mark updates when the lead sends a new message.",
      "You describe what a buying step looks like in your business.",
    ],
  },
  {
    id: "routing",
    kicker: "03 Route",
    title: "Hot leads go straight to a telecaller",
    body: "The telecaller sees what the lead asked and what was said, before they pick up the phone.",
    wash: "beige",
    visual: <RouteCard />,
    points: ["Hot leads are assigned to a telecaller automatically.", "The conversation so far is on screen before the call."],
  },
  {
    id: "call-scoring",
    kicker: "04 Measure",
    title: "Know which calls were good",
    body: "Every telecaller call is scored, so you can see who is closing and who needs help.",
    wash: "teal",
    visual: <CallCard />,
    points: ["Owners and managers review scored calls in one place."],
  },
];
