/**
 * BetLab AI — Trust-Building Animation Library
 * ─────────────────────────────────────────────
 * Drop-in React components and hooks that add conversion-focused
 * micro-animations to the BetLab app. All components inherit the
 * app's existing CSS variables (--gold, --win, --loss, etc.).
 *
 * IMPORTS
 * ───────
 * import {
 *   LivePickCounter,
 *   usePickCardStagger,
 *   ResultBadge,
 *   useCountUp,
 *   AnimatedStat,
 *   StatsStrip,
 *   AIThinking,
 *   ConfidenceBar,
 *   HeroScanLine,
 * } from './BetLabTrustAnimations';
 *
 * USAGE EXAMPLES — see JSDoc above each export below.
 */

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import './betlab-trust-animations.css';

/* ═══════════════════════════════════════════════════════════
   HOOK: useCountUp
   ─────────────────────────────────────────────────────────
   Counts a number from 0 to `target` with cubic ease-out.
   When triggerOnMount is false, counting begins the first time
   the returned `ref` element scrolls into the viewport (30% visible).

   Usage:
     const { displayValue, isComplete, ref } = useCountUp(27, {
       suffix: 'W',
       triggerOnMount: false,
     });
     return <span ref={ref}>{displayValue}</span>;
═══════════════════════════════════════════════════════════ */
export function useCountUp(target, {
  duration       = 1200,
  overshoot      = true,
  prefix         = '',
  suffix         = '',
  decimals       = 0,
  triggerOnMount = true,
} = {}) {
  const [value,      setValue]      = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const ref        = useRef(null);
  const rafRef     = useRef(null);
  const startRef   = useRef(null);
  const triggered  = useRef(false);

  const format = useCallback((v) => {
    const abs = Math.abs(v);
    const formatted = decimals > 0 ? abs.toFixed(decimals) : Math.round(abs).toString();
    return `${prefix}${v < 0 ? '-' : ''}${formatted}${suffix}`;
  }, [prefix, suffix, decimals]);

  const startCounting = useCallback(() => {
    if (triggered.current) return;
    triggered.current = true;

    startRef.current = null;
    const dir = target >= 0 ? 1 : -1;
    const absTarget = Math.abs(target);

    function tick(timestamp) {
      if (!startRef.current) startRef.current = timestamp;
      const elapsed  = timestamp - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // Cubic ease-out
      const eased    = 1 - Math.pow(1 - progress, 3);
      const current  = dir * eased * absTarget;

      setValue(current);

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setValue(target);
        setIsComplete(true);
      }
    }

    rafRef.current = requestAnimationFrame(tick);
  }, [target, duration]);

  // Trigger on mount or via IntersectionObserver
  useEffect(() => {
    if (triggerOnMount) {
      startCounting();
      return () => cancelAnimationFrame(rafRef.current);
    }

    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          observer.disconnect();
          startCounting();
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(el);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(rafRef.current);
    };
  }, [triggerOnMount, startCounting]);

  // Overshoot: brief scale-up CSS class at completion
  useEffect(() => {
    if (!isComplete || !overshoot || !ref.current) return;
    const el = ref.current;
    el.classList.add('blt-stat-overshoot');
    const id = setTimeout(() => el.classList.remove('blt-stat-overshoot'), 220);
    return () => clearTimeout(id);
  }, [isComplete, overshoot]);

  const displayValue = format(value);
  return { value, displayValue, isComplete, ref };
}

/* ═══════════════════════════════════════════════════════════
   HOOK: usePickCardStagger
   ─────────────────────────────────────────────────────────
   Returns an array of { cardStyle, badgeStyle } objects.
   Apply cardStyle to each pick card wrapper and badgeStyle
   to the premium badge inside it.

   Usage:
     const stagger = usePickCardStagger(picks.length);
     picks.map((p, i) => (
       <div
         key={p.id}
         className="blt-card-enter your-card-class"
         style={stagger[i].cardStyle}
       >
         <span className="blt-badge-premium" style={stagger[i].badgeStyle}>
           PREMIUM
         </span>
       </div>
     ))
═══════════════════════════════════════════════════════════ */
export function usePickCardStagger(count) {
  return useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      // Card enter delay: 80ms × index
      cardStyle: { '--blt-stagger-i': i },
      // Badge shimmer: card animate (0.4s) + settle buffer (300ms) + 80ms×i stagger
      badgeStyle: { animationDelay: `${i * 80 + 700}ms` },
    }));
  }, [count]);
}

/* ═══════════════════════════════════════════════════════════
   COMPONENT: LivePickCounter
   ─────────────────────────────────────────────────────────
   A persistently-ticking number in DM Mono gold that counts
   up on load, slows to a crawl, and settles with a glow flash.
   Gives visitors the impression the AI is always working.

   Usage:
     <LivePickCounter value={12847} label="picks analyzed today" />
     <LivePickCounter value={3291}  label="games scanned" size="2xl" />
═══════════════════════════════════════════════════════════ */
export function LivePickCounter({
  value = 0,
  label = 'picks analyzed today',
  size  = '3xl',         // Tailwind size token passed as class suffix
  className = '',
}) {
  const { value: animVal, isComplete, ref } = useCountUp(value, {
    duration: 1200,
    triggerOnMount: true,
    overshoot: false,
  });
  const spanRef = useRef(null);

  // Merge the IntersectionObserver ref from hook with our local spanRef
  // (hook ref is only for IO; here triggerOnMount=true so we just need spanRef)
  useEffect(() => {
    if (!isComplete || !spanRef.current) return;
    const el = spanRef.current;
    el.classList.add('blt-counter-landed');
    const id = setTimeout(() => el.classList.remove('blt-counter-landed'), 800);
    return () => clearTimeout(id);
  }, [isComplete]);

  const formatted = Math.round(Math.abs(animVal)).toLocaleString('en-US');

  return (
    <div className={`blt-counter-wrap ${className}`}>
      <span
        ref={spanRef}
        className={`blt-counter-number text-${size}`}
        style={{ fontFamily: "'DM Mono', monospace", color: 'var(--gold, #c9a227)' }}
      >
        {formatted}
      </span>
      {label && <span className="blt-counter-label">{label}</span>}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENT: ResultBadge
   ─────────────────────────────────────────────────────────
   WIN  → scale pulse (1→1.15→1) + expanding green ring
   LOSS → lateral shake + red tint flash

   Usage:
     <ResultBadge type="WIN"  className="px-3 py-1 rounded-full text-sm font-bold bg-green-900/30 text-green-400" />
     <ResultBadge type="LOSS" className="px-3 py-1 rounded-full text-sm font-bold bg-red-900/30 text-red-400" />
═══════════════════════════════════════════════════════════ */
export function ResultBadge({ type = 'WIN', children, className = '' }) {
  const [animated, setAnimated] = useState(false);
  const isWin = type === 'WIN';

  // Trigger animation after first paint so CSS transition fires
  useEffect(() => {
    const id = requestAnimationFrame(() => setAnimated(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div
      className={`blt-result-badge ${animated ? (isWin ? 'blt-result-win' : 'blt-result-loss') : ''} ${className}`}
    >
      {/* WIN: expanding ring sibling */}
      {isWin && animated && <div className="blt-result-win-ring" />}

      {/* LOSS: red flash overlay */}
      {!isWin && animated && <div className="blt-result-loss-flash" />}

      {children ?? type}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENT: AnimatedStat
   ─────────────────────────────────────────────────────────
   A single statistic that counts up from zero when it enters
   the viewport. Win rate numbers are rendered in gold.

   Usage:
     <AnimatedStat value={27}   suffix="W"  label="Wins" />
     <AnimatedStat value={44}   suffix="%"  label="Win Rate" isWinRate />
     <AnimatedStat value={-8.4} suffix="u"  label="Units"    decimals={1} />
═══════════════════════════════════════════════════════════ */
export function AnimatedStat({
  value     = 0,
  prefix    = '',
  suffix    = '',
  decimals  = 0,
  label     = '',
  isWinRate = false,
  size      = '2xl',
  className = '',
}) {
  const { displayValue, ref } = useCountUp(value, {
    triggerOnMount: false,
    overshoot: true,
    prefix,
    suffix,
    decimals,
  });

  return (
    <div className={`blt-animated-stat ${className}`} ref={ref}>
      <span
        className={`blt-stat-number text-${size}`}
        style={isWinRate ? { color: 'var(--gold, #c9a227)' } : {}}
      >
        {displayValue}
      </span>
      {label && <span className="blt-stat-label">{label}</span>}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENT: StatsStrip
   ─────────────────────────────────────────────────────────
   A horizontal strip of animated stats — the highest-trust
   element. Numbers populate as the user scrolls past.

   Usage:
     <StatsStrip stats={[
       { value: 27,   suffix: 'W',  label: 'Wins' },
       { value: 44,   suffix: '%',  label: 'Win Rate', isWinRate: true },
       { value: -8.4, suffix: 'u',  label: 'Units',    decimals: 1 },
     ]} />
═══════════════════════════════════════════════════════════ */
export function StatsStrip({ stats = [], className = '' }) {
  return (
    <div className={`flex items-center justify-around gap-6 ${className}`}>
      {stats.map((s, i) => (
        <AnimatedStat key={i} {...s} />
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENT: AIThinking
   ─────────────────────────────────────────────────────────
   Three pulsing gold dots (200ms stagger) with label text
   and a subtle gold particle field drifting upward behind.
   Implies serious computation is happening.

   Usage:
     <AIThinking label="AI is generating picks" active={true} />
     <AIThinking label="Analyzing odds..."       active={isGenerating} />
═══════════════════════════════════════════════════════════ */
export function AIThinking({ label = 'AI is thinking', active = true, className = '' }) {
  const canvasRef   = useRef(null);
  const rafRef      = useRef(null);
  const mountedRef  = useRef(true);
  const particleRef = useRef([]);

  // Particle class — identical pattern to betlab_loading.html
  const buildParticles = useCallback((W, H) => {
    const GOLDS = [
      'rgba(201,162,39,',
      'rgba(240,192,64,',
      'rgba(160,120,16,',
    ];
    const count = Math.min(60, Math.max(8, Math.floor((W * H) / 1800)));
    particleRef.current = Array.from({ length: count }, () => {
      const c = GOLDS[Math.floor(Math.random() * GOLDS.length)];
      return {
        x:  Math.random() * W,
        y:  Math.random() * H,
        r:  Math.random() * 1.3 + 0.3,
        vy: -(Math.random() * 0.35 + 0.12),
        vx: (Math.random() - 0.5) * 0.12,
        a:  Math.random() * 0.35 + 0.07,
        c,
        reset(iW, iH) {
          this.x = Math.random() * iW;
          this.y = iH + 4;
          this.r  = Math.random() * 1.3 + 0.3;
          this.vy = -(Math.random() * 0.35 + 0.12);
          this.vx = (Math.random() - 0.5) * 0.12;
          this.a  = Math.random() * 0.35 + 0.07;
        },
        update(iW, iH) {
          this.y += this.vy; this.x += this.vx;
          if (this.y < -6) this.reset(iW, iH);
        },
        draw(ctx) {
          ctx.save();
          ctx.globalAlpha = this.a;
          ctx.fillStyle   = this.c + '1)';
          ctx.shadowBlur  = 4;
          ctx.shadowColor = this.c + '0.8)';
          ctx.beginPath();
          ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        },
      };
    });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let W = 0, H = 0;

    const sizeCanvas = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      W = canvas.width  = parent.offsetWidth;
      H = canvas.height = parent.offsetHeight;
      buildParticles(W, H);
    };

    sizeCanvas();

    const ro = new ResizeObserver(sizeCanvas);
    ro.observe(canvas.parentElement);

    const loop = () => {
      if (!mountedRef.current) return;
      ctx.clearRect(0, 0, W, H);
      particleRef.current.forEach(p => { p.update(W, H); p.draw(ctx); });
      rafRef.current = requestAnimationFrame(loop);
    };

    if (active) {
      rafRef.current = requestAnimationFrame(loop);
    }

    return () => {
      ro.disconnect();
      cancelAnimationFrame(rafRef.current);
      ctx.clearRect(0, 0, W, H);
    };
  }, [active, buildParticles]);

  if (!active) return null;

  return (
    <div className={`blt-ai-thinking ${className}`} style={{ minHeight: 32 }}>
      <canvas ref={canvasRef} className="blt-ai-canvas" />
      <div className="blt-ai-content">
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className="blt-ai-dot"
            style={{ '--blt-dot-i': i }}
          />
        ))}
        {label && <span className="blt-ai-label">{label}</span>}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENT: ConfidenceBar
   ─────────────────────────────────────────────────────────
   Confidence percentage fills from 0 on card entrance.
   > 75%  → gold fill + pulsing glow (high conviction)
   50–75% → standard gold fill, no glow
   < 50%  → muted blue fill (#6ba3ff), no glow

   Usage:
     <ConfidenceBar value={82} title="Model Confidence" />
     <ConfidenceBar value={61} />
     <ConfidenceBar value={38} title="Edge Rating" />
═══════════════════════════════════════════════════════════ */
export function ConfidenceBar({ value = 0, title = 'Confidence', className = '' }) {
  const [animatedWidth, setAnimatedWidth] = useState(0);
  const clampedValue = Math.max(0, Math.min(100, value));

  const isHigh = clampedValue > 75;
  const isLow  = clampedValue < 50;

  // Animate from 0 → value after first paint
  useEffect(() => {
    const id = requestAnimationFrame(() => setAnimatedWidth(clampedValue));
    return () => cancelAnimationFrame(id);
  }, [clampedValue]);

  const fillClass = [
    'blt-bar-fill',
    isHigh ? 'blt-bar-fill--glow' : '',
    isLow  ? 'blt-bar-fill--muted' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={`blt-confidence-bar ${className}`}>
      <div className="blt-bar-header">
        <span className="blt-bar-title">{title}</span>
        <span className={`blt-bar-value ${isLow ? 'blt-bar-value--muted' : ''}`}>
          {clampedValue}%
        </span>
      </div>
      <div className="blt-bar-track">
        <div
          className={fillClass}
          style={{ width: `${animatedWidth}%` }}
        />
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENT: HeroScanLine
   ─────────────────────────────────────────────────────────
   A 1px gold horizontal line that sweeps down the hero section
   once on load. As it passes each stat element, `onStatReveal`
   fires for that index — use it to trigger StatsStrip count-ups.

   IMPORTANT: The parent wrapper must have:
     position: relative;
     overflow: hidden;

   Usage:
     const [revealed, setRevealed] = useState([]);
     <div style={{ position: 'relative', overflow: 'hidden' }}>
       <HeroScanLine
         statPositions={[0.35, 0.6, 0.8]}
         onStatReveal={(i) => setRevealed(prev => [...prev, i])}
         duration={1800}
       />
       <StatsStrip stats={stats} />
     </div>

   statPositions: array of 0–1 fractional positions (top of parent = 0,
   bottom = 1). Each position maps to that fraction of `duration` ms.
═══════════════════════════════════════════════════════════ */
export function HeroScanLine({
  statPositions = [],
  onStatReveal,
  duration = 1800,
  className = '',
}) {
  const mountedRef = useRef(true);
  const timersRef  = useRef([]);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    mountedRef.current = true;

    // Sort positions ascending so callbacks fire in visual order
    const sorted = [...statPositions].sort((a, b) => a - b);

    timersRef.current = sorted.map((pos, i) => {
      return setTimeout(() => {
        if (mountedRef.current) onStatReveal?.(i);
      }, pos * duration);
    });

    // Remove the element after animation finishes
    const exitTimer = setTimeout(() => {
      if (mountedRef.current) setVisible(false);
    }, duration + 100);

    timersRef.current.push(exitTimer);

    return () => {
      mountedRef.current = false;
      timersRef.current.forEach(clearTimeout);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!visible) return null;

  return (
    <div
      className={`blt-hero-scan-line ${className}`}
      style={{ '--blt-scan-duration': `${duration}ms` }}
    />
  );
}
