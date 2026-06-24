# Aira AI — Projects & Active Backlog

## Known Technical Debt
- **Orphaned Database Tables**: Bot Flow Builder tables (`automations`, `automation_flow_runs`, `bot_flows`) still exist in the Supabase schema, although the backend and frontend engine code has been deleted.
- **Stale Wiki References**: ✅ Cleared 2026-06-24. The graph carried 183 ghost nodes for deleted bot-flow modules because `graphify update` refuses to shrink the graph without `--force`. Ran `graphify update . --force` (4285 nodes, ghosts pruned) + `make wiki` (182 articles). `make wiki-refresh` now uses `--force` permanently, so deletions self-prune going forward.

## Active Backlog
*Currently empty. System architecture and features are fully stable and built as described in [stack-and-rules.md](file:///Users/prem/Documents/Aira%20AI/.agents/context/stack-and-rules.md).*

---

## Recently Completed Features
- **Security & Multi-Tenancy**: RLS launch blocker (Migration 114) + performance checks (Migration 115).
- **Shift Time Overrides**: Multi-tenant shift hour schedules per caller (Migration 112) + ShiftTimeline ranges.
- **Call Scripts Cockpit integration**: Segment-based routing, branch outcomes, and scripts cockpit panel (Migration 111).
- **Contact Recycling Engine**: Automatic APScheduler recycling job to re-queue unreachable voice leads (Migration 111).
