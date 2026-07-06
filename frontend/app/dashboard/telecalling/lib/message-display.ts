type MessageDisplayInput = {
  direction: "inbound" | "outbound";
  media_type?: string | null;
};

export function getMessageDisplayMeta(message: MessageDisplayInput) {
  const isVoiceNoteTranscript = message.direction === "inbound" && message.media_type === "audio";
  const isAiVoiceReply = message.direction === "outbound" && message.media_type === "audio";
  return {
    isVoiceNoteTranscript,
    isAiVoiceReply,
    label: isVoiceNoteTranscript ? "Voice note transcript" : isAiVoiceReply ? "AI voice reply" : null,
  };
}
