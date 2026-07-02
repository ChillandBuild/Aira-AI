import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * `lib/impersonation.ts` guards every DOM access with `typeof window ===
 * "undefined"` (it runs in both server and client contexts), so exercising
 * the real storage/event logic here requires a minimal window-shaped stub —
 * the vitest environment for this repo is plain "node", not jsdom.
 */
class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  setItem(key: string, value: string) {
    this.store.set(key, value);
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
}

function installWindowStub() {
  const listeners = new Map<string, Set<() => void>>();
  const win = {
    sessionStorage: new MemoryStorage(),
    addEventListener(name: string, cb: () => void) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name)!.add(cb);
    },
    removeEventListener(name: string, cb: () => void) {
      listeners.get(name)?.delete(cb);
    },
    dispatchEvent(evt: { type: string }) {
      listeners.get(evt.type)?.forEach((cb) => cb());
      return true;
    },
  };
  // @ts-expect-error -- minimal test stub, not a full Window
  globalThis.window = win;
  // Event constructor isn't available in the plain node test environment.
  // @ts-expect-error -- minimal test stub
  globalThis.Event = class {
    type: string;
    constructor(type: string) {
      this.type = type;
    }
  };
  return win;
}

const STORAGE_KEY = "aira_operator_impersonation";

describe("impersonation session storage", () => {
  beforeEach(() => {
    vi.resetModules();
    installWindowStub();
  });

  afterEach(() => {
    // @ts-expect-error -- cleanup test stub
    delete globalThis.window;
    // @ts-expect-error -- cleanup test stub
    delete globalThis.Event;
  });

  it("returns the stored session while unexpired", async () => {
    const { getImpersonationSession } = await import("./impersonation");
    const session = {
      tenantId: "t-1",
      tenantName: "Acme",
      startedAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));

    expect(getImpersonationSession()).toEqual(session);
  });

  it("clearImpersonationSession removes the stored session and notifies listeners (B2)", async () => {
    const { clearImpersonationSession, getImpersonationSession, subscribeImpersonation } =
      await import("./impersonation");
    const session = {
      tenantId: "t-1",
      tenantName: "Acme",
      startedAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));

    const listener = vi.fn();
    const unsubscribe = subscribeImpersonation(listener);

    clearImpersonationSession();

    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(getImpersonationSession()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
  });

  it("getImpersonationSession on an expired session clears storage and notifies listeners (B2 regression)", async () => {
    // This is the exact desync the impersonation banner used to cause: on
    // TTL expiry the getter must clear the stored session AND emit the
    // change event so every listener (sidebars, client-detail header)
    // re-syncs, instead of leaving stale storage other tabs/components can
    // still read as "active".
    const { getImpersonationSession, subscribeImpersonation } = await import("./impersonation");
    const expiredSession = {
      tenantId: "t-2",
      tenantName: "Beta",
      startedAt: new Date(Date.now() - 120_000).toISOString(),
      expiresAt: new Date(Date.now() - 1_000).toISOString(),
    };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(expiredSession));

    const listener = vi.fn();
    const unsubscribe = subscribeImpersonation(listener);

    expect(getImpersonationSession()).toBeNull();
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
  });

  it("subscribeImpersonation unsubscribe stops future notifications", async () => {
    const { clearImpersonationSession, subscribeImpersonation } = await import("./impersonation");
    const listener = vi.fn();
    const unsubscribe = subscribeImpersonation(listener);
    unsubscribe();

    clearImpersonationSession();

    expect(listener).not.toHaveBeenCalled();
  });
});
