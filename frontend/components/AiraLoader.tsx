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
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#f0ece4] p-4 text-center">
      <div className="flex flex-col items-center gap-4">
        {!showRetry && (
          <div
            className="h-10 w-10 rounded-full border-[3px] border-[#e8e3db] border-t-[#1c1917]"
            style={{ animation: "spin 0.75s linear infinite" }}
          />
        )}
        <span className="text-xs font-medium tracking-widest text-[#78716c] uppercase">
          Aira
        </span>
        {showRetry && (
          <div className="mt-4 max-w-sm animate-in fade-in duration-300">
            <p className="font-body text-sm text-[#78716c] mb-3">
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
