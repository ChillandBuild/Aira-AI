"use client";
import { useEffect, useState } from "react";

interface AiraLoaderProps {
  showRetryAfterMs?: number;
  onRetry?: () => void;
}

export function AiraLoader({ showRetryAfterMs, onRetry }: AiraLoaderProps) {
  const [showRetry, setShowRetry] = useState(false);

  useEffect(() => {
    if (!showRetryAfterMs) return;
    const t = setTimeout(() => {
      setShowRetry(true);
    }, showRetryAfterMs);
    return () => clearTimeout(t);
  }, [showRetryAfterMs]);

  return (
    <div className="fixed inset-0 z-dialog flex flex-col items-center justify-center bg-[#f1f5f9] p-4 text-center">
      <div className="flex flex-col items-center gap-4">
        {!showRetry && (
          <div
            className="h-10 w-10 rounded-full border-[3px] border-[#e2e8f0] border-t-[#0A1528]"
            style={{ animation: "spin 0.75s linear infinite" }}
          />
        )}
        <span className="text-xs font-medium tracking-widest text-[#475569] uppercase">
          Anril
        </span>
        {showRetry && (
          <div className="mt-4 max-w-sm animate-in fade-in duration-300">
            <p className="font-body text-sm text-[#475569] mb-3">
              Couldn&apos;t reach the server. The backend may be waking up — this can take 30–60 seconds.
            </p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="btn-primary text-sm px-6 py-2"
              >
                Retry
              </button>
            )}
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
