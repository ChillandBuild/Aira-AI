type MessageDisplayInput = {
  direction: "inbound" | "outbound";
  media_type?: string | null;
};

export function getMessageDisplayMeta(message: MessageDisplayInput) {
  const isVoiceNoteTranscript = message.direction === "inbound" && message.media_type === "audio";
  return {
    isVoiceNoteTranscript,
    label: isVoiceNoteTranscript ? "Voice note transcript" : null,
  };
}
