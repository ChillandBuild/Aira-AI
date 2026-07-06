import { describe, expect, it } from "vitest";

import { getMessageDisplayMeta } from "./message-display";

describe("getMessageDisplayMeta", () => {
  it("labels inbound audio messages as voice note transcripts", () => {
    expect(getMessageDisplayMeta({ direction: "inbound", media_type: "audio" })).toEqual({
      isVoiceNoteTranscript: true,
      isAiVoiceReply: false,
      label: "Voice note transcript",
    });
  });

  it("does not label typed WhatsApp text as a voice note transcript", () => {
    expect(getMessageDisplayMeta({ direction: "inbound", media_type: null })).toEqual({
      isVoiceNoteTranscript: false,
      isAiVoiceReply: false,
      label: null,
    });
  });

  it("labels outbound audio messages as AI voice replies", () => {
    expect(getMessageDisplayMeta({ direction: "outbound", media_type: "audio" })).toEqual({
      isVoiceNoteTranscript: false,
      isAiVoiceReply: true,
      label: "AI voice reply",
    });
  });
});
