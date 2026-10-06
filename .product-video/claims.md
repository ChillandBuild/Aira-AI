# Aira AI: claims ledger (web-product-video)

Rules: ~/.claude/skills/web-product-video/references/claims-ledger.md. Only `ok` / `approved-by-user` rows may appear on screen.
Numbers visible INSIDE the captured screens are seeded demo data (tenant SMTesting). Captions never quote them as results.

| # | claim (as shown) | source type | source | status |
|---|---|---|---|---|
| 1 | Turn every enquiry into revenue | published | public site hero h1 "Turn Every Enquiry Into Revenue" | ok |
| 2 | Instant AI replies, 24/7 | published + screen | site "Instant, human-like AI conversations 24/7"; inbox.png (AI-labelled replies) | ok |
| 3 | WhatsApp, Instagram and Facebook in one inbox | screen + code | inbox.png channel icons; leads.png channel column | ok |
| 4 | Answers from your own knowledge base | code | backend knowledge RAG replies (messages.reply_source='knowledge', 2,275 live rows); frontend/components/chat-thread.tsx | ok |
| 5 | Every lead sorted Hot, Warm or Cold | screen + code | leads.png segment column; backend/app/services/segmentation.py | ok |
| 6 | Hands off to a human when it matters | screen + code | dashboard.png "Escalations"; backend/app/routes/chat_handovers.py | ok |
| 7 | Every recorded call scored out of 100 | screen + code | call-review.png "91.8 /100"; backend/app/services/call_marking.py (10 checks, 100 marks) | ok |
| 8 | Coaching tips after each call | screen + code | call-review.png tips + "Top things to improve"; backend/app/services/call_ai_pipeline.py | ok |
| 9 | Your telecallers' lead queue, ready to dial | screen | calls.png "Lead Queue" | ok |
| 10 | Every sale from quote to paid | screen | deals.png subtitle "Every sale in one place … from quote to paid" | ok |
| 11 | See what the AI did with your leads | screen | analytics.png "What the AI did with your leads" | ok |
| 12 | Book a Demo | published | public site CTA button | ok |
| 13 | AI makes / places phone calls | none | calls are human telecallers over TeleCMI; AI only scores (profile banned_claims) | BLOCKED |
| 14 | Any price or plan cost | none | profile banned_claims | BLOCKED |
| 15 | Customer counts, revenue or conversion uplift (e.g. "+24%", "16.8% conversion") | none | landing-page mock numbers are illustrative, not measured | BLOCKED |
| 16 | Seeded on-screen figures as results (e.g. "91% AI share", "6 new leads") | none | demo data, not customer results | BLOCKED |
