"use client";

import { useState, useEffect, useRef } from "react";
import { Activity, CheckCircle2 } from "lucide-react";
import { WhatsAppIcon } from "../icons";
import { SIMULATED_MESSAGES, type SimulatedMessage } from "../landing.data";

export default function DemoSection() {
  const [chatMessages, setChatMessages] = useState<SimulatedMessage[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

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
    const el = chatScrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [chatMessages, isTyping]);

  return (
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
  );
}
