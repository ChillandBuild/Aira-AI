import Link from "next/link";
import { WifiOff } from "lucide-react";
import { AiraLogo } from "@/components/logo";

export default function OfflinePage() {
  return (
    <main className="min-h-screen bg-background px-6 py-10 text-ink">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-lg flex-col justify-center">
        <AiraLogo height={34} className="mb-12 text-ink" aria-label="Aira AI" />

        <div className="rounded-2xl border border-border bg-white p-8 shadow-card">
          <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-primary-light text-primary">
            <WifiOff aria-hidden="true" size={24} strokeWidth={2.2} />
          </div>

          <h1 className="text-2xl font-extrabold tracking-tight text-ink">You are offline</h1>
          <p className="mt-3 text-sm leading-6 text-ink-secondary">
            Aira needs a connection for live leads, conversations, and team updates. Reconnect and continue from the dashboard.
          </p>

          <Link href="/dashboard" className="btn-primary mt-7">
            Return to dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}
