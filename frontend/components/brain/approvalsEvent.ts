// Window event that says "something Aira was waiting on was just approved,
// discarded, fixed or re-sorted". The badge store refreshes its count on it and
// the hub reloads (then re-checks again a few seconds later). The Knowledge page
// dispatches it from its modal handlers, resort and delete (blueprint step 5).

export const APPROVALS_CHANGED_EVENT = "approvals:changed";

export function announceApprovalsChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(APPROVALS_CHANGED_EVENT));
}
