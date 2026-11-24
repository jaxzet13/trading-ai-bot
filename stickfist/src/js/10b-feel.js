/* ============================================================================
   10b. FEEL. The small things that make the page behave like an app on a phone: a light tap under every press, sheets you can flick away,
   numbers that flash when they move, and coins that fly to your balance when you sell. None of it changes what anything is worth.
   ========================================================================== */
// a light tap for every button, tab and row you press
document.addEventListener("click", e => { const t = e.target.closest && e.target.closest("button, .btabs a, .ptab, .crow, .mrow, .ctile, a.btn, .mover"); if (t && !t.disabled) buzz(8); }, true);

// tapping the tab you are already on goes back to the top, as it does in any phone app
document.addEventListener("click", e => { const a = e.target.closest && e.target.closest(".btabs a.on"); if (a && scrollY > 0) scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" }); });

// the card window is a sheet on a phone: drag it down from its top to put it away
(() => {
  const box = $("mbox"), modal = $("modal"); let y0 = null, dy = 0, t0 = 0;
  const phone = () => matchMedia("(max-width: 760px)").matches;
  box.addEventListener("touchstart", e => { if (!phone() || box.classList.contains("ec") || box.scrollTop > 0 || e.touches.length !== 1) { y0 = null; return; } const r = box.getBoundingClientRect(); if (e.touches[0].clientY - r.top > 70) { y0 = null; return; } y0 = e.touches[0].clientY; dy = 0; t0 = performance.now(); box.style.transition = "none"; }, { passive: true });
  box.addEventListener("touchmove", e => { if (y0 == null) return; dy = Math.max(0, e.touches[0].clientY - y0); box.style.transform = `translateY(${dy}px)`; modal.style.background = `rgba(5,5,6,${Math.max(.3, .92 - dy / 600)})`; }, { passive: true });
  const end = () => {
    if (y0 == null) return; const fast = dy > 40 && dy / Math.max(1, performance.now() - t0) > .55; y0 = null; box.style.transition = "transform .22s cubic-bezier(.2,.8,.2,1)";
    if (dy > 120 || fast) { box.style.transform = "translateY(105%)"; setTimeout(() => { closeModal(); box.style.transform = ""; box.style.transition = ""; modal.style.background = ""; }, 200); buzz(8); }
    else { box.style.transform = ""; modal.style.background = ""; setTimeout(() => { box.style.transition = ""; }, 240); }
  };
  box.addEventListener("touchend", end); box.addEventListener("touchcancel", end);
})();

// a number that just moved flashes green or red for a moment, like a ticker
const Tick = (() => {
  const seen = new Map();
  function scan() {
    if (reduced) return; const live = new Set();
    document.querySelectorAll("[data-tick]").forEach(el => {
      const k = el.dataset.tick, v = +el.dataset.v; live.add(k); if (!isFinite(v)) return; const was = seen.get(k); seen.set(k, v);
      if (was == null || was === v || Math.abs(v - was) / Math.max(1, Math.abs(was)) < .0005) return;
      el.classList.remove("tk-up", "tk-dn"); void el.offsetWidth; el.classList.add(v > was ? "tk-up" : "tk-dn");
    });
    for (const k of seen.keys()) if (!live.has(k)) seen.delete(k);
  }
  return { scan };
})();

let lastTap = null; addEventListener("pointerdown", e => { lastTap = { left: e.clientX, top: e.clientY, width: 0, height: 0 }; }, true);
// selling: a few coins fly from where you tapped up to your balance
function coinBurst(from, n) {
  const bal = $("bal"); if (reduced || !bal || !from) return; const a = from.getBoundingClientRect ? from.getBoundingClientRect() : from, b = bal.getBoundingClientRect(); if (!b.width) return;
  const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2, x1 = b.left + b.width / 2, y1 = b.top + b.height / 2; n = Math.max(3, Math.min(9, n || 5));
  for (let i = 0; i < n; i++) {
    const c = document.createElement("span"); c.className = "coin"; c.textContent = "$"; c.setAttribute("aria-hidden", "true"); document.body.appendChild(c);
    const sx = (Math.random() - .5) * 70, sy = -20 - Math.random() * 50, d = 420 + i * 45 + Math.random() * 80;
    c.animate([{ transform: `translate(${x0}px, ${y0}px) scale(.6)`, opacity: 0 }, { transform: `translate(${x0 + sx}px, ${y0 + sy}px) scale(1.15)`, opacity: 1, offset: .25 }, { transform: `translate(${x1}px, ${y1}px) scale(.5)`, opacity: .9 }], { duration: d, easing: "cubic-bezier(.5,0,.3,1)", fill: "forwards" }).onfinish = () => c.remove();
  }
  setTimeout(() => { bal.classList.remove("bump"); void bal.offsetWidth; bal.classList.add("bump"); }, 430);
}
