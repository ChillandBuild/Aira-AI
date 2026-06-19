# Landing Page Redesign — "Aira: The River of Meaning"

**Date:** 2026-06-19
**Status:** Revision 2 (2026-06-19) — see "Revision 2" below. v1 implemented then redirected by user.

---

## Revision 2 — "Symbolic, not literal" (supersedes the meanings section)

**User feedback:** v1 *named* the meanings (a "River / Noble / Moon" word list + an "Aira means river…" cycling hero line). The user wants the name's story told **symbolically through animation only — never as text**. References they love: arcade.software, sarvam.ai (clean, airy, premium, one immersive atmospheric gradient motif, generous whitespace).

**Changes:**
1. **Delete** `MeaningsRiver` section/component and its usage. Delete the hero cycling sub-line and `HERO_CYCLE` usage. No on-page text ever names a meaning.
2. **Hero = one immersive atmospheric moment** (Arcade/Sarvam-grade), keeping the headline + dashboard mockup. Built from layered, *breathing* violet aurora-mesh gradients plus:
   - **Breath of life** → the whole atmosphere slowly breathes (scale/opacity pulse).
   - **Descended from the moon** → a soft crescent of violet moonlight glow, high in the hero.
   - **Of the wind** → slow-drifting light motes on the hero canvas.
   - **River** → the existing flowing current/thread.
   - **Love** → a faint warm rose-violet tint in the wash.
   None labeled. The motifs are ambient and concentrated in the hero (premium > scattered effects).
3. **Keep:** `RiverThread`, `RiverDelta` (flow is symbolic, not naming), chat simulator, all other sections, palette, fonts. Remove now-unused `.meaning-*` and `.hero-cycle` CSS.
4. Maintain all per-element reduced-motion / mobile fallbacks from §7; the aurora freezes to a static wash, motes and breathing stop.

**Net effect:** the page reads premium and calm like the references; the name's meaning is felt in light and motion, not spelled out.
**Scope:** Full creative redesign of the marketing landing page (`frontend/app/page.tsx` + `frontend/app/landing.css`). Dashboard/app untouched.

---

## 1. Why

The current landing page is visually polished but says nothing about what **Aira** means or what the product *is* beyond generic SaaS copy. It is static. The name "Aira" carries rich multicultural meaning and — most usefully — descends from the Sanskrit root *Ira* (water / Earth), making **"river"** a perfect organizing metaphor: scattered enquiries flow in from many channels and converge into one stream of revenue.

This redesign gives the page one spine — a flowing river — and weaves the name's meanings into it as the emotional centerpiece. Palette, copy, and all existing sections are preserved; only the *presentation and motion* change.

## 2. Locked decisions (from brainstorm)

| Decision | Choice |
|---|---|
| Ambition | **Full river spine** — rework the whole page around the metaphor |
| Hero voice | **Value-first, river underneath** — keep selling H1, add poetic cycling sub-line over rippling water |
| Meanings count | **All eight** — full reference card incl. moon + noble, plus the "river" anchor (§5) |
| Meanings placement | **Right after hero** |
| Palette | **Unchanged** — violet `#5b21b6` / `#7c3aed`, warm cream `#faf8f5`, Dancing Script wordmark |

## 3. Non-negotiable constraints

1. Palette and Dancing Script wordmark stay exactly as in `landing.css` today.
2. All current sections and copy are preserved (problem, how-it-works, platform bento, chat simulator, industries, CTA form, footer).
3. **No new animation library.** Hero water is hand-written Canvas 2D; river-thread and delta are SVG + CSS. Keeps JS within the < 150 kb landing budget (`web/performance.md`).
4. Motion stays on compositor-friendly properties (`transform`, `opacity`, `filter`); never animate layout-bound props.
5. `prefers-reduced-motion` honored **per element** (see §7), not just one global block.
6. **Preserve the recent chat-scroll fix** (commit e424e96): the simulator scrolls only its own container via `chatScrollRef.scrollTo` ([page.tsx:213-217](../../../frontend/app/page.tsx#L213)). Decomposition must not regress this.
7. Etymology framed **poetically, not as a hard claim** — e.g. "*Ira* — the ancient root for water," never "Aira literally means river."

## 4. Component breakdown

`page.tsx` is 902 lines and growing. Decompose into focused, independently-understandable pieces under `frontend/app/components/landing/`:

| File | Responsibility | Depends on |
|---|---|---|
| `HeroRipple.tsx` | Canvas-2D violet water surface behind hero; breathes on load, ripples on pointer-move/click. Self-contained, exposes nothing. | canvas, `useReducedMotion` |
| `RiverThread.tsx` | The vertical animated SVG river-path spine between sections. Absolutely/fixed positioned — cannot cause layout shift. | — |
| `MeaningsRiver.tsx` | New "What Aira Means" section; six meanings drift in on scroll. | meanings content table (§5), IntersectionObserver |
| `RiverDelta.tsx` | "How Aira Works" re-rendered as tributaries→delta with particle flow. **Prototype first** (§8). | SVG, `FLOW_STEPS` data |
| `useRipple.ts` | Hook: button ripple emanating from click point. | — |
| `useReducedMotion.ts` | Shared reduced-motion + coarse-pointer (mobile) detector. | — |
| `page.tsx` | Composition only — imports the above, keeps existing sections, shrinks well under 800 lines. | all of the above |

Existing inline data arrays (`SIMULATED_MESSAGES`, `PROBLEMS`, `FLOW_STEPS`, etc.) move to `frontend/app/components/landing/landing.data.ts`.

CSS extensions live in `landing.css` (existing tokens reused; no new color tokens).

## 5. "What Aira Means" — content table (now all eight)

> **Updated:** You said "match everything / there are so many meanings / it should mention everything." So the default is now **all eight** meanings from your reference card (including the two I'd dropped — *descended from the moon* and *noble*), with "river" added as the metaphor anchor. The moon meaning lands beautifully on the violet/celestial palette. Locked microcopy below; edit any line you want.

| # | Meaning (origin) | Product line |
|---|---|---|
| 1 | River — *Sanskrit, from the root Ira (water)* | Many channels, one flow. |
| 2 | Descended from the moon — *Sanskrit* | Always on, through the night. |
| 3 | Noble / honourable — *Sanskrit* | Every lead treated with care. |
| 4 | Breath of life — *Arabic* | Your pipeline, always moving. |
| 5 | The beginning — *Arabic* | Every enquiry, a new source. |
| 6 | Of the wind / free spirit — *English* | Reaches leads wherever they are. |
| 7 | Messenger — *Finnish* | Every conversation, carried. |
| 8 | Love / affection — *Japanese* | Conversations that feel human. |

If eight feels long in-scroll, the section can show all eight on desktop and auto-condense to a swipeable set of cards on mobile (no content cut).

Visual treatment: each row fades/drifts in on the current as it enters viewport (translateX + opacity, staggered). The origin label is a small monospace eyebrow; the meaning is the large display word; the product line is the warm-ink subtitle. A faint reflection of each word sits beneath it on the "water."

**Hero cycling sub-line** (the poetic line under the H1) draws from the same set, locked as:
`river · descended from the moon · breath of life · messenger · of the wind · flow`

## 6. Section-by-section plan

1. **Hero** — full-bleed `HeroRipple` canvas behind the existing two-column layout. Left: badge, H1 "Turn Every Enquiry Into Revenue", **new cycling sub-line** (`river · descended from the moon · breath of life · messenger · of the wind · flow`, typewriter/fade cycle — see §5), CTAs, trust row — all unchanged copy, now sitting "on water." Right: existing dashboard mockup, floated above the water with a soft caustic glow. Reduced-motion / mobile → static violet gradient "pool," no canvas, sub-line shows one static value.
2. **What Aira Means** (`MeaningsRiver`) — new, right after hero. §5 content.
3. **Problem** — unchanged content; cards re-themed to sit on the river thread.
4. **How Aira Works** (`RiverDelta`) — same `FLOW_STEPS`, delta presentation. Static fallback = current step row.
5. **Platform bento**, **Live demo simulator**, **Industries**, **CTA + form**, **Footer** — content unchanged; `.river-separator` lines give way to the continuous `RiverThread`; buttons gain `useRipple`; cards gain hover caustic shimmer.

## 7. Per-element motion & performance spec

| Element | Full motion | Mobile (coarse pointer) | `prefers-reduced-motion` |
|---|---|---|---|
| Hero ripple canvas | rAF loop; pointer handler **rAF-throttled**; DPR capped ~1.5; **paused via IntersectionObserver** when hero scrolls offscreen | gentle auto-ripple only, no pointer tracking | no canvas — static gradient pool |
| River thread | animated stroke gradient/dash | same, slower | static thin gradient line |
| Meanings drift-in | translateX + opacity stagger | same | appear in place, no transform |
| River delta particles | particles along SVG paths | reduce particle count | **static** delta, no particles |
| Orb scroll-parallax | transform on scroll, throttled | disabled | disabled |
| Button/card ripple+caustic | on interaction | on tap | disabled |

Targets unchanged from `web/performance.md`: LCP < 2.5s, INP < 200ms, CLS < 0.1. River-thread and canvas are positioned so they contribute **zero** layout shift.

## 8. Build order (de-risked)

1. **`RiverDelta` prototype first** — it is the highest-risk/highest-effort piece (particles on paths that stay smooth + accessible on mid-range devices). If it doesn't land cleanly, ship its static fallback and move on; the rest of the page is independent of it.
2. `useReducedMotion` + `HeroRipple` (the hero is the first-look wow — second priority).
3. `RiverThread` spine + CSS section re-theming.
4. `MeaningsRiver` section.
5. `useRipple` + card caustic + orb parallax polish.
6. Decompose `page.tsx`, move data file, verify chat-scroll behavior intact, full responsive + reduced-motion pass.

## 9. Testing

- Visual regression screenshots at 320 / 375 / 768 / 1024 / 1440 (per `web/testing.md`).
- Reduced-motion pass: every animated element has a verified still state.
- Keyboard nav + focus states unaffected; contrast unchanged (palette reused).
- Lighthouse on `/` — confirm CWV targets and JS budget hold after canvas added.
- Manual: chat simulator still scrolls only its container, not the page.

## 10. Out of scope

- No backend/form-submission change (demo form stays simulated as today).
- No copy rewrite beyond the new cycling sub-line and the six meaning lines.
- No palette or font change.
- Dashboard and all `/dashboard/*` pages untouched.
