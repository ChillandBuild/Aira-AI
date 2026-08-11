"use client";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Clock, Phone } from "lucide-react";
import { api, ExpertHandoffSession } from "@/lib/api";
import { ConsultationDetails } from "./ConsultationDetails";
import { usePolling } from "@/hooks/usePolling";

type Bucket = "awaiting_payment" | "paid";

export default function ConsultationsPage() {
  const [bucket, setBucket] = useState<Bucket>("awaiting_payment");
  const [sessions, setSessions] = useState<ExpertHandoffSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState<ExpertHandoffSession | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.expertHandoff.listSessions(bucket);
      setSessions(data);
    } catch {
      /* non-critical, list stays as-is */
    } finally {
      setLoading(false);
    }
  }, [bucket]);

  useEffect(() => {
    setLoading(true);
    setSelectedSession(null);
    load();
  }, [bucket, load]);

  usePolling(load, 30000);

  function handleResolved() {
    setSelectedSession(null);
    load();
  }

  return (
    <div className="flex h-full">
      <div className="w-[340px] flex-shrink-0 border-r border-border flex flex-col">
        <div className="p-4 border-b border-border">
          <h1 className="font-display text-lg font-bold text-ink mb-3">Consultations</h1>
          <div className="flex gap-2 p-1 bg-surface-subtle border border-border rounded-xl">
            <button
              type="button"
              onClick={() => setBucket("awaiting_payment")}
              className={`flex-1 px-3 py-1.5 rounded-lg font-label text-xs font-bold transition-all ${
                bucket === "awaiting_payment" ? "bg-white text-ink shadow-sm" : "text-ink-muted"
              }`}
            >
              Awaiting Payment
            </button>
            <button
              type="button"
              onClick={() => setBucket("paid")}
              className={`flex-1 px-3 py-1.5 rounded-lg font-label text-xs font-bold transition-all ${
                bucket === "paid" ? "bg-white text-ink shadow-sm" : "text-ink-muted"
              }`}
            >
              Paid
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-16 rounded-xl bg-border-subtle animate-pulse" />
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <p className="p-6 text-center font-body text-sm text-ink-muted">
              {bucket === "awaiting_payment" ? "No leads waiting on payment." : "No paid consultations yet."}
            </p>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => setSelectedSession(session)}
                className={`w-full text-left p-4 border-b border-border-subtle hover:bg-surface-subtle transition-colors ${
                  selectedSession?.id === session.id ? "bg-primary-light/40" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-label text-sm font-semibold text-ink">
                    {session.leads?.name || "Unknown lead"}
                  </span>
                  {session.status === "paid" ? (
                    <CheckCircle2 size={14} className="text-emerald-600" />
                  ) : (
                    <Clock size={14} className="text-amber-600" />
                  )}
                </div>
                <div className="flex items-center gap-1 mt-1 text-xs text-ink-muted font-body">
                  <Phone size={11} />
                  {session.leads?.phone || "—"}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {!selectedSession ? (
          <div className="h-full flex items-center justify-center">
            <p className="font-body text-sm text-ink-muted">Select a lead to view consultation details.</p>
          </div>
        ) : (
          <ConsultationDetails session={selectedSession} onResolved={handleResolved} />
        )}
      </div>
    </div>
  );
}
