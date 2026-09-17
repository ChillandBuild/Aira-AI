"use client";
import { useEffect, useState } from "react";
import { Fingerprint, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { createClient } from "@/lib/supabase/client";

interface Passkey {
  id: string;
  friendly_name?: string;
  created_at: string;
}

export function PasskeySettings() {
  const [passkeys, setPasskeys] = useState<Passkey[]>([]);
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);

  async function loadPasskeys() {
    const supabase = createClient();
    const { data, error } = await supabase.auth.passkey.list();
    if (!error && data) {
      setPasskeys(data);
    }
    setLoading(false);
  }

  useEffect(() => {
    loadPasskeys();
  }, []);

  async function handleRegister() {
    setRegistering(true);
    const supabase = createClient();
    const { error } = await supabase.auth.registerPasskey();
    if (error) {
      toast.error(error.message);
    } else {
      toast.success("Passkey registered");
      await loadPasskeys();
    }
    setRegistering(false);
  }

  async function handleDelete(passkeyId: string) {
    const supabase = createClient();
    const { error } = await supabase.auth.passkey.delete({ passkeyId });
    if (error) {
      toast.error(error.message);
    } else {
      toast.success("Passkey removed");
      setPasskeys((prev) => prev.filter((p) => p.id !== passkeyId));
    }
  }

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-display text-base font-bold text-primary flex items-center gap-2">
          <Fingerprint size={16} className="text-secondary" /> Passkeys
        </h2>
        <button
          onClick={handleRegister}
          disabled={registering}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary font-label text-xs font-semibold hover:bg-primary/20 transition-colors disabled:opacity-60"
        >
          <Plus size={14} />
          {registering ? "Registering…" : "Add passkey"}
        </button>
      </div>

      {loading ? (
        <p className="font-body text-sm text-on-surface-muted">Loading…</p>
      ) : passkeys.length === 0 ? (
        <p className="font-body text-sm text-on-surface-muted">
          No passkeys yet. Add one to sign in with Face ID, Touch ID, or Windows Hello instead of a password.
        </p>
      ) : (
        <ul className="divide-y divide-surface-low">
          {passkeys.map((pk) => (
            <li key={pk.id} className="flex items-center justify-between py-3">
              <div>
                <p className="font-body text-sm font-medium text-on-surface">
                  {pk.friendly_name || "Passkey"}
                </p>
                <p className="font-label text-xs text-on-surface-muted">
                  Added {new Date(pk.created_at).toLocaleDateString()}
                </p>
              </div>
              <button
                onClick={() => handleDelete(pk.id)}
                className="text-on-surface-muted hover:text-red-500 transition-colors"
                aria-label="Remove passkey"
              >
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
