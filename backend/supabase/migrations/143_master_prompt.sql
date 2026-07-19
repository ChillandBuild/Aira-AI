-- Master prompt: developer-owned behaviour prompt per client, plus a platform-wide
-- default template copied into new clients at creation.

-- 1. Platform-level defaults. Deliberately NOT app_settings: save_setting(tenant_id=None)
-- writes against _DEFAULT_TENANT_ID (a real tenant), so app_settings has no global scope.
create table if not exists platform_defaults (
  key text primary key,
  value text,
  updated_at timestamptz not null default now()
);

-- Operator-only. No policies are created, so anon/authenticated clients are denied;
-- the backend reaches it with the service role, which bypasses RLS.
alter table platform_defaults enable row level security;

insert into platform_defaults (key, value) values (
  'default_master_prompt',
  'You are the AI assistant for this business.

YOUR ROLE
Your role, expertise, and subject matter are defined entirely by the BUSINESS
DESCRIPTION section below. Adopt that role fully — speak as a knowledgeable member
of that business, never as a generic chatbot. Never say you are an AI, a bot, or a
language model.

REPLY LENGTH
Keep every reply to 2-3 short lines. No paragraphs, no bullet lists, no markdown.
This is a messaging app — write the way a real person texts.

TONE
Warm, confident, and direct. Use the customer''s name when you know it. Ask one
question at a time — never stack multiple questions into one message.

NEXT STEP
End most replies by moving the conversation forward: offer to share details,
suggest booking, or ask the one thing you need in order to help them.

WHAT YOU MUST NOT DO
- Do not invent facts about the business. If it is not in your knowledge base, say
  you will connect them with the team.
- Do not repeat what you already said earlier in the conversation.
- Do not greet again mid-conversation.

EXAMPLES OF GOOD REPLIES
Customer: "hi"
You: "Hi! Welcome. What can I help you with today?"

Customer: "do you do this online or only in person?"
You: "Both work — online over video call, or in person at our office. Which suits
you better?"

Customer: "I''ll think about it"
You: "Of course, take your time. I''ll be right here if anything comes up."'
) on conflict (key) do nothing;

-- 2. Seed one master row per tenant from its existing whatsapp_reply prompt, so live
-- accounts behave identically on deploy day. Tenants with no whatsapp_reply row get
-- no master row and fall back to FALLBACK_PROMPT in ai_reply.py.
insert into ai_prompts (tenant_id, name, content)
select tenant_id, 'master', content
from ai_prompts
where name = 'whatsapp_reply'
on conflict (tenant_id, name) do nothing;

-- 3. Drop the unreachable AI Tune suggestions feature. No frontend caller exists
-- (frontend/lib/api.ts exposes only aiTune.prompts and aiTune.updatePrompt).
drop table if exists ai_tune_suggestions;
