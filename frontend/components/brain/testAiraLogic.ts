/** Pure helpers for the Test Aira chat box. Limits mirror the backend (services/brain_sandbox.py). */

export const MAX_TURNS = 20;
export const MAX_MESSAGE_CHARS = 1000;
export const NEEDS_MANAGE_REASON = "Needs manage access: ask the owner to let you manage the Knowledge Base.";

export type SandboxRole = "user" | "assistant";

export interface SandboxTurn {
  role: SandboxRole;
  content: string;
  /** Only on assistant turns: whether Aira found matching knowledge for the question. */
  knowledgeUsed?: boolean;
}

export interface SandboxReply {
  reply: string;
  knowledgeUsed: boolean;
}

const STATUS_MESSAGES: Record<number, string> = {
  409: "Aira's reply model isn't set up for this business. Ask the Aira team to set it up.",
  429: "That's a lot of test messages. Please wait a few minutes and try again.",
  503: "Test Aira is switched off right now.",
  403: "You need manage access to the Knowledge Base to test Aira.",
  422: "That message can't be sent. Keep it under 1000 characters.",
};
const GENERIC_ERROR = "Aira couldn't answer just now. Please try again.";
const NETWORK_ERROR = "Couldn't reach the server. Please try again.";

export function messageForStatus(status: number | null): string {
  if (status === null) return NETWORK_ERROR;
  return STATUS_MESSAGES[status] ?? GENERIC_ERROR;
}

export function canSend(draft: string, isPending: boolean, canUse: boolean): boolean {
  return canUse && !isPending && draft.trim().length > 0 && draft.length <= MAX_MESSAGE_CHARS;
}

/** What goes to the server: the newest turns only (the server accepts at most MAX_TURNS), roles and text only. */
export function toRequestMessages(turns: readonly SandboxTurn[]): { role: SandboxRole; content: string }[] {
  return turns.slice(-MAX_TURNS).map(({ role, content }) => ({ role, content }));
}

export function isWindowed(turns: readonly SandboxTurn[]): boolean {
  return turns.length > MAX_TURNS;
}

export function parseSandboxReply(body: unknown): SandboxReply | null {
  if (typeof body !== "object" || body === null) return null;
  const b = body as Record<string, unknown>;
  if (typeof b.reply !== "string" || b.reply.trim() === "") return null;
  return { reply: b.reply, knowledgeUsed: b.knowledge_used === true };
}

export interface SandboxState {
  turns: SandboxTurn[];
  /** Bumps on every send and reset; a reply for an older value is dropped. */
  requestId: number;
}

export const INITIAL_SANDBOX_STATE: SandboxState = { turns: [], requestId: 0 };

export function withUserTurn(state: SandboxState, text: string): SandboxState {
  return { turns: [...state.turns, { role: "user", content: text }], requestId: state.requestId + 1 };
}

/** Adds Aira's reply only if no newer send or reset happened since `requestId` was issued. */
export function withReply(state: SandboxState, requestId: number, reply: SandboxReply): SandboxState {
  if (requestId !== state.requestId) return state;
  return { ...state, turns: [...state.turns, { role: "assistant", content: reply.reply, knowledgeUsed: reply.knowledgeUsed }] };
}

/** A failed send takes its user turn back off, so the person can edit and retry. */
export function withoutFailedTurn(state: SandboxState, requestId: number): SandboxState {
  if (requestId !== state.requestId) return state;
  return { ...state, turns: state.turns.slice(0, -1) };
}

export function resetState(state: SandboxState): SandboxState {
  return { turns: [], requestId: state.requestId + 1 };
}
