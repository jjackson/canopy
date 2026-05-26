// Synthetic cursor + click-ripple overlay for canopy:walkthrough video recording.
//
// Playwright headless does not render the OS cursor. Without this overlay,
// the recorded walkthrough video has no signal for how the user navigated
// between screens — every click looks like a teleport. With it, viewers see
// a visible pointer move across the page and a brief indigo ring on each
// click, restoring the "I'm watching a person use this product" feel.
//
// Injected via ctx.add_init_script — runs at document creation on every
// navigation. Defers DOM work to DOMContentLoaded (documentElement isn't
// guaranteed at init-script time) and self-heals via MutationObserver if
// the page tears out the cursor element.

(function () {
  if (window.__synthCursorReady) return;
  window.__synthCursorReady = true;

  let lastX = 200, lastY = 100;

  function ensure() {
    let cursor = document.getElementById('__synthCursor');
    if (!cursor) {
      cursor = document.createElement('div');
      cursor.id = '__synthCursor';
      cursor.innerHTML =
        '<svg width="26" height="26" viewBox="0 0 22 22" style="display:block">' +
        '<path d="M2 2 L2 18 L7 13 L10 19 L13 17 L10 11 L17 11 Z" ' +
        'fill="#ffffff" stroke="#111827" stroke-width="1.4" stroke-linejoin="round"/>' +
        '</svg>';
      const s = cursor.style;
      s.position = 'fixed';
      s.top = '0';
      s.left = '0';
      s.width = '26px';
      s.height = '26px';
      s.pointerEvents = 'none';
      s.zIndex = '2147483647';
      s.transform = 'translate(' + (lastX - 2) + 'px,' + (lastY - 2) + 'px)';
      s.transition = 'transform 90ms linear';
      s.filter = 'drop-shadow(0 2px 3px rgba(0,0,0,0.35))';
      (document.body || document.documentElement).appendChild(cursor);
    }
    return cursor;
  }

  function place(x, y) {
    lastX = x; lastY = y;
    const cursor = ensure();
    cursor.style.transform = 'translate(' + (x - 2) + 'px,' + (y - 2) + 'px)';
  }

  function spawnRipple(x, y) {
    const ring = document.createElement('div');
    const s = ring.style;
    s.position = 'fixed';
    s.left = (x - 10) + 'px';
    s.top = (y - 10) + 'px';
    s.width = '20px';
    s.height = '20px';
    s.borderRadius = '50%';
    s.border = '2.5px solid #4f46e5';
    s.background = 'rgba(79,70,229,0.22)';
    s.pointerEvents = 'none';
    s.zIndex = '2147483646';
    s.transition = 'transform 420ms ease-out, opacity 420ms ease-out';
    s.transform = 'scale(1)';
    s.opacity = '1';
    (document.body || document.documentElement).appendChild(ring);
    requestAnimationFrame(() => {
      s.transform = 'scale(4.5)';
      s.opacity = '0';
    });
    setTimeout(() => ring.remove(), 500);
  }

  function attach() {
    ensure();
    document.addEventListener('mousemove', e => place(e.clientX, e.clientY), true);
    document.addEventListener('mousedown', e => spawnRipple(e.clientX, e.clientY), true);

    // Self-heal: if the page wipes the cursor (React mount, route change),
    // restore it on the next mutation.
    const obs = new MutationObserver(() => {
      if (!document.getElementById('__synthCursor')) {
        ensure();
      }
    });
    obs.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach, { once: true });
  } else {
    attach();
  }
})();
