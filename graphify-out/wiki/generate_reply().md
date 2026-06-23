# generate_reply()

> God node · 36 connections · `backend/app/services/ai_reply.py`

**Community:** [[Ai Reply Service]]

## Connections by Relation

### calls
- [[get_supabase()]] `INFERRED`
- [[get_setting()]] `INFERRED`
- [[get_telecalling_config()]] `INFERRED`
- [[whatsapp_webhook()]] `INFERRED`
- [[auto_assign_lead()]] `INFERRED`
- [[compute_score()]] `INFERRED`
- [[send_whatsapp()]] `EXTRACTED`
- [[maybe_assign_lead()]] `INFERRED`
- [[record_stage_event()]] `INFERRED`
- [[sync_follow_up_jobs()]] `INFERRED`
- [[get_knowledge_context()]] `INFERRED`
- [[get_inbox_config()]] `INFERRED`
- [[send_instagram()]] `EXTRACTED`
- [[send_telegram()]] `EXTRACTED`
- [[send_facebook()]] `EXTRACTED`
- [[_is_similar()]] `EXTRACTED`
- [[_trigger_chat_escalation()]] `EXTRACTED`
- [[should_assign_to_telecalling()]] `INFERRED`
- [[should_escalate_hot_lead()]] `INFERRED`
- [[should_escalate_to_inbox()]] `INFERRED`

### contains
- [[ai_reply.py]] `EXTRACTED`

### rationale_for
- [[Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply]] `EXTRACTED`
- [[Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply]] `EXTRACTED`
- [[Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply]] `EXTRACTED`
- [[Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply]] `EXTRACTED`
- [[Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply]] `EXTRACTED`

### references
- [[str]] `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*