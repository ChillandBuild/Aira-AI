// "standard" runs the full Nira config (WhatsApp + Page + Instagram + ads).
// "whatsapp_only" runs the WhatsApp-only config, so Meta asks for nothing else.
// "coexistence" runs that same WhatsApp-only config with Meta's connect-without-
// switching feature turned on for a number already live on the mobile app.
export type MetaSignupMode = "standard" | "whatsapp_only" | "coexistence";
export type MetaSignupFinishEvent = "FINISH" | "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING";

type MetaSignupMessage = {
  type: "WA_EMBEDDED_SIGNUP";
  event: MetaSignupFinishEvent;
  data: {
    waba_id: string;
    phone_number_id: string;
    business_id?: string;
  };
};

export type ReadyMetaSignup = {
  code: string;
  session: {
    waba_id: string;
    phone_number_id: string;
    business_id?: string;
    is_coexistence: boolean;
  };
};

export type MetaLoginOptions = {
  config_id: string;
  response_type: "code";
  override_default_response_type: true;
  extras?: {
    setup: Record<string, never>;
    featureType: "whatsapp_business_app_onboarding";
    sessionInfoVersion: "3";
  };
};

export function buildMetaLoginOptions(configId: string, mode: MetaSignupMode): MetaLoginOptions {
  return {
    config_id: configId,
    response_type: "code",
    override_default_response_type: true,
    ...(mode === "coexistence"
      ? {
          extras: {
            setup: {},
            featureType: "whatsapp_business_app_onboarding" as const,
            sessionInfoVersion: "3" as const,
          },
        }
      : {}),
  };
}

export function resolveMetaSignupCompletion(
  requestedMode: MetaSignupMode,
  event: MetaSignupFinishEvent
): boolean {
  // Only coexistence has its own finish event. Every other mode ends on FINISH,
  // so the check is "did Meta open the flow we asked for", not a mode equality.
  const wantedCoexistence = requestedMode === "coexistence";
  const gotCoexistence = event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING";
  if (gotCoexistence !== wantedCoexistence) {
    if (wantedCoexistence) {
      throw new Error(
        "Meta did not open the connect-without-switching flow. Check WhatsApp coexistence eligibility and try again."
      );
    }
    throw new Error("Meta returned a different signup flow. Start the connection again.");
  }
  return gotCoexistence;
}

function parseMetaSignupMessage(value: unknown): MetaSignupMessage | null {
  if (typeof value === "string") {
    try {
      return parseMetaSignupMessage(JSON.parse(value) as unknown);
    } catch {
      return null;
    }
  }
  if (!value || typeof value !== "object") return null;
  const message = value as Record<string, unknown>;
  if (message.type !== "WA_EMBEDDED_SIGNUP") return null;
  if (message.event !== "FINISH" && message.event !== "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING") return null;
  if (!message.data || typeof message.data !== "object") return null;
  const data = message.data as Record<string, unknown>;
  if (typeof data.waba_id !== "string" || !data.waba_id) return null;
  if (typeof data.phone_number_id !== "string" || !data.phone_number_id) return null;
  if (data.business_id !== undefined && typeof data.business_id !== "string") return null;
  return {
    type: "WA_EMBEDDED_SIGNUP",
    event: message.event,
    data: {
      waba_id: data.waba_id,
      phone_number_id: data.phone_number_id,
      business_id: data.business_id,
    },
  };
}

export class MetaSignupCoordinator {
  private nextAttemptId = 0;
  private retiredSources = new WeakSet<object>();
  private active: {
    id: number;
    mode: MetaSignupMode;
    code?: string;
    session?: ReadyMetaSignup["session"];
  } | null = null;

  begin(mode: MetaSignupMode): number | null {
    if (this.active) return null;
    const id = ++this.nextAttemptId;
    this.active = { id, mode };
    return id;
  }

  isActive(attemptId: number): boolean {
    return this.active?.id === attemptId;
  }

  cancel(attemptId: number): void {
    if (this.active?.id === attemptId) this.active = null;
  }

  receiveCode(attemptId: number, code: string): ReadyMetaSignup | null {
    if (!this.active || this.active.id !== attemptId || !code) return null;
    this.active.code = code;
    return this.takeReady();
  }

  receiveMessage(value: unknown, source: object): ReadyMetaSignup | null {
    if (this.retiredSources.has(source)) return null;
    const message = parseMetaSignupMessage(value);
    if (!message || !this.active) return null;
    let isCoexistence: boolean;
    try {
      isCoexistence = resolveMetaSignupCompletion(this.active.mode, message.event);
    } catch (error) {
      this.retiredSources.add(source);
      this.active = null;
      throw error;
    }
    this.active.session = {
      waba_id: message.data.waba_id,
      phone_number_id: message.data.phone_number_id,
      business_id: message.data.business_id,
      is_coexistence: isCoexistence,
    };
    return this.takeReady();
  }

  private takeReady(): ReadyMetaSignup | null {
    if (!this.active?.code || !this.active.session) return null;
    const ready = { code: this.active.code, session: this.active.session };
    this.active = null;
    return ready;
  }
}
