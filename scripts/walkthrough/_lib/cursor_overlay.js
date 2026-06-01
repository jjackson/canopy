// Synthetic cursor + click feedback. Playwright headless doesn't draw the
// OS cursor, so this stands in for it during recordings — and it makes clicks
// UNMISTAKABLE on screen (a recording where you can't tell what was clicked is
// useless). On mousedown we fire three things at the click point: a press-pulse
// on the cursor, an expanding ring, and a bright filled dot that lingers ~600ms.
//
// Injected via add_init_script, which runs at document creation time — before
// any markup is parsed. We defer DOM work to DOMContentLoaded and re-pin the
// cursor if React/other scripts tear it out.

(function () {
  if (window.__synthCursorReady) return;
  window.__synthCursorReady = true;

  let lastX = 200,
    lastY = 100;

  function ensure() {
    let cursor = document.getElementById('__synthCursor');
    if (!cursor) {
      cursor = document.createElement('div');
      cursor.id = '__synthCursor';
      // Larger arrow (32px) with a heavy outline + shadow so it reads against
      // busy/light backgrounds.
      cursor.innerHTML =
        '<svg width="32" height="32" viewBox="0 0 22 22" style="display:block">' +
        '<path d="M2 2 L2 18 L7 13 L10 19 L13 17 L10 11 L17 11 Z" ' +
        'fill="#ffffff" stroke="#111827" stroke-width="1.6" stroke-linejoin="round"/>' +
        '</svg>';
      const s = cursor.style;
      s.position = 'fixed';
      s.top = '0';
      s.left = '0';
      s.width = '32px';
      s.height = '32px';
      s.pointerEvents = 'none';
      s.zIndex = '2147483647';
      s.transformOrigin = '2px 2px'; // pin scaling to the arrow tip
      s.transform = 'translate(' + (lastX - 2) + 'px,' + (lastY - 2) + 'px)';
      s.transition = 'transform 120ms linear';
      s.filter = 'drop-shadow(0 2px 4px rgba(0,0,0,0.5))';
      (document.body || document.documentElement).appendChild(cursor);
    }
    return cursor;
  }

  function place(x, y) {
    lastX = x;
    lastY = y;
    const cursor = ensure();
    cursor.style.transform = 'translate(' + (x - 2) + 'px,' + (y - 2) + 'px)';
  }

  function pressPulse() {
    // Briefly shrink the cursor so the click reads as a physical press.
    const cursor = ensure();
    const base = 'translate(' + (lastX - 2) + 'px,' + (lastY - 2) + 'px)';
    cursor.style.transform = base + ' scale(0.7)';
    setTimeout(() => {
      cursor.style.transform = base;
    }, 130);
  }

  function spawnRing(x, y) {
    const ring = document.createElement('div');
    const s = ring.style;
    s.position = 'fixed';
    s.left = x - 16 + 'px';
    s.top = y - 16 + 'px';
    s.width = '32px';
    s.height = '32px';
    s.borderRadius = '50%';
    s.border = '3px solid #4f46e5';
    s.background = 'rgba(79,70,229,0.20)';
    s.pointerEvents = 'none';
    s.zIndex = '2147483646';
    s.transition = 'transform 520ms ease-out, opacity 520ms ease-out';
    s.transform = 'scale(0.4)';
    s.opacity = '1';
    (document.body || document.documentElement).appendChild(ring);
    requestAnimationFrame(() => {
      s.transform = 'scale(3.6)';
      s.opacity = '0';
    });
    setTimeout(() => ring.remove(), 560);
  }

  function spawnDot(x, y) {
    // A bright, opaque dot that snaps in and lingers ~600ms so a viewer (and a
    // single freeze-frame) can see EXACTLY where the click landed.
    const dot = document.createElement('div');
    const s = dot.style;
    s.position = 'fixed';
    s.left = x - 11 + 'px';
    s.top = y - 11 + 'px';
    s.width = '22px';
    s.height = '22px';
    s.borderRadius = '50%';
    s.background = 'rgba(79,70,229,0.55)';
    s.border = '2px solid #ffffff';
    s.boxShadow = '0 0 0 2px rgba(79,70,229,0.9), 0 1px 4px rgba(0,0,0,0.4)';
    s.pointerEvents = 'none';
    s.zIndex = '2147483646';
    s.transition = 'transform 160ms ease-out, opacity 380ms ease-in 360ms';
    s.transform = 'scale(0.3)';
    s.opacity = '1';
    (document.body || document.documentElement).appendChild(dot);
    requestAnimationFrame(() => {
      s.transform = 'scale(1)';
    });
    // fade out after a beat (the opacity transition has a 360ms delay baked in)
    requestAnimationFrame(() => {
      s.opacity = '0';
    });
    setTimeout(() => dot.remove(), 800);
  }

  function clickFx(x, y) {
    pressPulse();
    spawnRing(x, y);
    spawnDot(x, y);
  }

  function attach() {
    ensure();
    document.addEventListener(
      'mousemove',
      (e) => place(e.clientX, e.clientY),
      true,
    );
    document.addEventListener(
      'mousedown',
      (e) => clickFx(e.clientX, e.clientY),
      true,
    );

    // Self-heal: if anything detaches the cursor, recreate it.
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
