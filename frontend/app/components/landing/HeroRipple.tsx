"use client";

import { useEffect, useRef } from "react";
import { useReducedMotion } from "./useReducedMotion";

interface Ripple {
  x: number;
  y: number;
  radius: number;
  maxRadius: number;
  delay: number; // ms before this ring starts (creates the "reverb")
  life: number; // 0..1 remaining
  decay: number;
  width: number;
  deep: boolean;
}

interface Mote {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  base: number; // base alpha
  phase: number; // twinkle phase
}

const RING_VIOLET = "124, 58, 237"; // #7c3aed
const RING_DEEP = "91, 33, 182"; // #5b21b6

/**
 * The hero's living atmosphere. Slow violet light-motes drift like wind/breath,
 * and a triple-ring "reverb" radiates from the pointer / on click. The breathing
 * aurora, crescent moonlight and warm tint are CSS layers (.hero-pool) beneath
 * this canvas. Paused offscreen via IntersectionObserver. Renders nothing for
 * reduced-motion — the static CSS wash is the fallback.
 */
export default function HeroRipple() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { reducedMotion, coarsePointer } = useReducedMotion();

  useEffect(() => {
    if (reducedMotion) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    let width = 0;
    let height = 0;
    const ripples: Ripple[] = [];
    let motes: Mote[] = [];
    let running = true;
    let rafId = 0;
    let lastAmbient = 0;
    let pointerQueued: { x: number; y: number } | null = null;

    const seedMotes = () => {
      const count = Math.round((width * height) / 42000);
      motes = Array.from({ length: Math.min(Math.max(count, 10), 26) }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.12,
        vy: -0.06 - Math.random() * 0.1,
        r: 0.8 + Math.random() * 1.8,
        base: 0.08 + Math.random() * 0.14,
        phase: Math.random() * Math.PI * 2,
      }));
    };

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seedMotes();
    };

    // A "reverb" = three concentric rings staggered in time.
    const spawn = (x: number, y: number, strength: number) => {
      const maxRadius = Math.min(width, height) * (0.32 + strength * 0.28);
      for (let i = 0; i < 3; i++) {
        ripples.push({
          x,
          y,
          radius: 0,
          maxRadius,
          delay: i * 170,
          life: 1,
          decay: 0.006 + Math.random() * 0.004,
          width: 1.6 - i * 0.35,
          deep: i % 2 === 1,
        });
      }
    };

    const onPointerMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointerQueued = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    };
    const onPointerDown = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      spawn(e.clientX - rect.left, e.clientY - rect.top, 1);
    };

    let prev = performance.now();
    const frame = (now: number) => {
      if (!running) return;
      const dt = Math.min(now - prev, 48);
      prev = now;
      const step = dt / 16;

      if (width === 0 || height === 0) {
        rafId = requestAnimationFrame(frame);
        return;
      }

      if (pointerQueued) {
        if (Math.random() > 0.45) spawn(pointerQueued.x, pointerQueued.y, 0.22);
        pointerQueued = null;
      }
      if (now - lastAmbient > 2000) {
        lastAmbient = now;
        spawn(width * (0.2 + Math.random() * 0.6), height * (0.25 + Math.random() * 0.5), 0.5);
      }

      ctx.clearRect(0, 0, width, height);

      // Drifting motes (wind / breath)
      for (const m of motes) {
        m.x += m.vx * step;
        m.y += m.vy * step;
        m.phase += 0.02 * step;
        if (m.y < -10) m.y = height + 10;
        if (m.x < -10) m.x = width + 10;
        else if (m.x > width + 10) m.x = -10;
        const a = m.base * (0.6 + 0.4 * Math.sin(m.phase));
        ctx.beginPath();
        ctx.arc(m.x, m.y, Math.max(0.1, m.r), 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${RING_VIOLET}, ${a})`;
        ctx.fill();
      }

      // Reverb rings
      for (let i = ripples.length - 1; i >= 0; i--) {
        const r = ripples[i];
        if (r.delay > 0) {
          r.delay -= dt;
          continue;
        }
        r.radius += (r.maxRadius - r.radius) * 0.018 * step;
        r.life -= r.decay * step;
        if (r.life <= 0) {
          ripples.splice(i, 1);
          continue;
        }
        const eased = r.life * r.life;
        ctx.beginPath();
        ctx.arc(r.x, r.y, Math.max(0.1, r.radius), 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${r.deep ? RING_DEEP : RING_VIOLET}, ${0.16 * eased})`;
        ctx.lineWidth = Math.max(0.1, r.width);
        ctx.stroke();
      }
      rafId = requestAnimationFrame(frame);
    };

    resize();
    window.addEventListener("resize", resize);
    if (!coarsePointer) {
      window.addEventListener("pointermove", onPointerMove, { passive: true });
      window.addEventListener("pointerdown", onPointerDown, { passive: true });
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !running) {
          running = true;
          prev = performance.now();
          rafId = requestAnimationFrame(frame);
        } else if (!entry.isIntersecting && running) {
          running = false;
          cancelAnimationFrame(rafId);
        }
      },
      { threshold: 0 }
    );
    io.observe(canvas);
    rafId = requestAnimationFrame(frame);

    return () => {
      running = false;
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerdown", onPointerDown);
      io.disconnect();
    };
  }, [reducedMotion, coarsePointer]);

  return (
    <div className="hero-pool" aria-hidden="true">
      <div className="hero-aurora" />
      <div className="hero-curtains">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="hero-moon" />
      {!reducedMotion && <canvas ref={canvasRef} className="hero-pool-canvas" />}
    </div>
  );
}
