export function mountCosmicBackground() {
  'use strict';
  if (!document.getElementById?.('background-motion')) return null;
  const host = document.createElement('div');
  host.innerHTML = `<div id="dm-viewport" aria-hidden="true"><div id="dm-approach"><div id="dm-camera"><img id="dm-art" src="/static/cosmic-data-field.png" alt=""><svg id="dm-field" viewBox="0 0 1672 941" xmlns="http://www.w3.org/2000/svg"><defs>
<linearGradient id="dm-spectrum" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#aa8df0"/><stop offset=".43" stop-color="#829edb"/><stop offset=".64" stop-color="#40bde8"/><stop offset="1" stop-color="#68d8ff"/></linearGradient>
<linearGradient id="dm-flow-spectrum" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="941"><stop stop-color="#bea5ff"/><stop offset=".42" stop-color="#a8b4fa"/><stop offset=".62" stop-color="#8bd5ff"/><stop offset="1" stop-color="#63cbe8"/></linearGradient>
<filter id="dm-halo" filterUnits="userSpaceOnUse" x="770" y="-30" width="430" height="1000"><feGaussianBlur stdDeviation="4"/></filter>
<filter id="dm-soft" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="1.7"/></filter>
<radialGradient id="dm-massshade" cx="0" cy=".5" r="1"><stop stop-color="#02040a" stop-opacity=".1"/><stop offset=".7" stop-color="#02040a" stop-opacity=".7"/></radialGradient>
<clipPath id="dm-exterior"><path d="M-200 -200H1450L1118.500 0C905.203 156.667 845.711 313.333 831.100 470C842.243 627 883.152 784 1100.000 941L1450 1141H-200Z"/></clipPath>
</defs><g clip-path="url(#dm-exterior)"><g id="dm-far-stars"></g></g><g id="dm-trajectories" fill="none" stroke="url(#dm-spectrum)" clip-path="url(#dm-exterior)"></g><g id="dm-mesh" clip-path="url(#dm-exterior)" fill="none" stroke="url(#dm-spectrum)"></g><g id="dm-halo-paths" fill="none" filter="url(#dm-halo)"></g><g id="dm-corona" fill="none"></g><g id="dm-packets" clip-path="url(#dm-exterior)"><!-- Decorative packets carry no observation meaning. --></g><g clip-path="url(#dm-exterior)"><g id="dm-near-stars"></g></g></svg></div></div><div class="dm-veil"></div></div>`;
  const viewport = host.firstElementChild;
  document.body.prepend(viewport);
  const NS = 'http://www.w3.org/2000/svg',
    $ = (id) => viewport.querySelector('#dm-' + id),
    tau = Math.PI * 2;
  let seed = 491;
  function rand() {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  }
  function svg(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) $(parent).append(e);
    return e;
  }
  function bez(a, b, c, d, t) {
    return (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d;
  }
  function limb(t) {
    return t < 0.5
      ? { x: bez(1118.5, 905.203, 845.711, 831.1, t * 2), y: 470 * t * 2 }
      : { x: bez(831.1, 842.243, 883.152, 1100.0, (t - 0.5) * 2), y: 470 + 471 * (t - 0.5) * 2 };
  }
  function pathPoints(start, end, offset = 0, wiggle = 0) {
    let d = '';
    for (let i = 0; i <= 18; i++) {
      const t = start + ((end - start) * i) / 18,
        p = limb(t);
      p.x -= offset + Math.sin(t * 95 + offset) * wiggle;
      d += (i ? 'L' : 'M') + p.x.toFixed(2) + ' ' + p.y.toFixed(2);
    }
    return d;
  }
  // Deliberately sparse: no visible particles within the silhouette.
  for (let i = 0; i < 165; i++) {
    const x = rand() * 1180,
      y = rand() * 941,
      r = 0.25 + rand() * 0.6;
    svg(
      'circle',
      { cx: x, cy: y, r, fill: i % 3 ? '#a8c7ea' : '#80d5ff', opacity: 0.12 + rand() * 0.4 },
      'far-stars',
    );
  }
  for (let i = 0; i < 19; i++) {
    const x = rand() * 1070,
      y = rand() * 941,
      r = 0.45 + rand() * 0.55;
    const g = svg('g', { opacity: 0.22 + rand() * 0.35 }, 'near-stars');
    g.append(svg('circle', { cx: x, cy: y, r, fill: '#c7e6ff' }));
    if (i % 4 === 0) {
      g.append(
        svg('path', {
          d: `M${x - 3} ${y}h6M${x} ${y - 3}v6`,
          stroke: '#80cdff',
          'stroke-width': 0.35,
          opacity: 0.4,
        }),
      );
    }
  }
  const routeDs = [
    'M737 -20C484 135 352 309 379 518C405 730 574 825 806 959',
    'M1044 -20C864 92 680 221 665 419C647 615 795 734 1005 826',
    'M1001 -30C859 99 770 248 772 398C773 619 896 824 1100 941',
    'M330 88C527 176 678 194 883 260',
    'M545 794C682 867 854 881 1069 911',
    'M1201 -20C1028 92 867 193 831 407C806 619 939 828 1132 971',
  ];
  const routes = routeDs.map((d, i) =>
    svg(
      'path',
      { d, 'stroke-width': i < 2 ? 0.65 : 0.45, opacity: i < 2 ? 0.36 : 0.14 },
      'trajectories',
    ),
  );
  // Sample each trajectory once. Animation frames only interpolate this lookup,
  // avoiding repeated geometry queries while the data streams are moving.
  const motionPaths = routes.slice(0, 3).map((p) => {
    const len = p.getTotalLength(),
      points = [];
    for (let i = 0; i <= 512; i++) {
      const a = p.getPointAtLength((i / 512) * len);
      points.push({ x: a.x, y: a.y });
    }
    return { p, len, points };
  });
  function along(route, distance) {
    const at = Math.max(0, Math.min(512, (distance / route.len) * 512)),
      i = Math.min(511, Math.floor(at)),
      f = at - i,
      a = route.points[i],
      b = route.points[i + 1];
    return {
      x: a.x + (b.x - a.x) * f,
      y: a.y + (b.y - a.y) * f,
      angle: (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI,
    };
  }
  function flowColor(y) {
    const f = Math.max(0, Math.min(1, (y - 120) / 650));
    return `rgb(${Math.round(190 + (139 - 190) * f)},${Math.round(165 + (213 - 165) * f)},255)`;
  }
  for (let i = 0; i < 20; i++) {
    const t = 0.08 + rand() * 0.84,
      a = limb(t),
      b = limb(Math.min(0.99, t + 0.06 + rand() * 0.12)),
      c = limb(Math.max(0.01, t - 0.07));
    const ox = 18 + rand() * 80;
    svg(
      'path',
      {
        d: `M${c.x} ${c.y}L${a.x - ox} ${a.y + 12}L${b.x} ${b.y}L${a.x} ${a.y}`,
        opacity: 0.07 + rand() * 0.12,
        'stroke-width': 0.5,
      },
      'mesh',
    );
    svg(
      'circle',
      {
        cx: a.x - ox,
        cy: a.y + 12,
        r: 0.7,
        fill: t < 0.45 ? '#b6a0ef' : '#55d0ff',
        stroke: 'none',
        opacity: 0.4,
      },
      'mesh',
    );
  }
  const segments = [];
  for (let i = 0; i < 64; i++) {
    const t = i / 64,
      end = (i + 0.88) / 64,
      c = t < 0.4 ? '#b89aff' : t < 0.55 ? '#93b5ff' : '#65d9ff';
    const d = pathPoints(t, end, 1, 1.1);
    const glow = svg('path', { d, stroke: c, 'stroke-width': 6, opacity: 0 }, 'halo-paths');
    const core = svg(
      'path',
      { d, stroke: c, 'stroke-width': 0.7 + (i % 7 === 0 ? 0.45 : 0), opacity: 0.2 },
      'corona',
    );
    segments.push({ t, glow, core, grain: 0.5 + rand() * 0.5 });
  }
  // Tiny angular secondary strands imply stress rather than a decorative neon ring.
  for (let i = 0; i < 10; i++) {
    const t = 0.03 + i * 0.094;
    svg(
      'path',
      {
        d: pathPoints(t, Math.min(t + 0.042, 0.99), 3 + rand() * 7, 1.3),
        stroke: i < 4 ? '#ae92ee' : '#4bc6ef',
        'stroke-width': 0.4,
        opacity: 0.22,
      },
      'corona',
    );
  }
  // Flowing trains, rather than isolated dots: a curved taper and a few sharp
  // packet marks share the same fixed trajectory. Only phase and light change.
  const packets = [];
  for (let i = 0; i < 6; i++) {
    const lane = i % 3,
      route = motionPaths[lane],
      g = svg('g', {}, 'packets');
    const tailLength = [152, 126, 102][lane],
      bands = [];
    for (let j = 0; j < 6; j++) {
      const band = svg('path', {
        d: route.p.getAttribute('d'),
        fill: 'none',
        stroke: 'url(#dm-flow-spectrum)',
        'stroke-width': (1.25 - j * 0.15).toFixed(2),
        'stroke-linecap': 'round',
        'stroke-dasharray': `${(tailLength / 6 + 0.7).toFixed(2)} ${(route.len * 3).toFixed(2)}`,
        opacity: (0.58 * (1 - j / 6) ** 1.35).toFixed(3),
      });
      g.append(band);
      bands.push(band);
    }
    const marks = [];
    for (let j = 0; j < 4; j++) {
      const mark = svg('g', {});
      mark.append(
        svg('rect', { x: -2.6, y: -0.65, width: 5.2, height: 1.3, rx: 0.35, fill: 'currentColor' }),
      );
      g.append(mark);
      marks.push(mark);
    }
    packets.push({
      g,
      route,
      bands,
      marks,
      tailLength,
      phase: (lane * 0.19 + (i >= 3 ? 0.51 : 0.07)) % 1,
      speed: [3, 4, 6][lane],
    });
  }
  const camera = $('camera'),
    approachPlane = $('approach'),
    far = $('far-stars'),
    near = $('near-stars');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let time = 0,
    last = 0,
    raf = 0,
    brightness = 0.68,
    frames = 0,
    destroyed = false;
  let preference = 'auto';
  try {
    preference = localStorage.getItem('companion-background-motion') || 'auto';
  } catch {}
  const isPaused = () =>
    preference === 'paused' ||
    reduced.matches ||
    document.hidden ||
    (document.documentElement.dataset.theme === 'light' &&
      !document.body.classList.contains('eclipse-view'));
  const motionEnabled = () => preference !== 'paused' && !reduced.matches;
  let notifiedMotion = null;
  let approachTarget = { depth: 0, x: 0, y: 0 };
  const bounded = (value, low, high) =>
    Number.isFinite(value) ? Math.max(low, Math.min(high, value)) : 0;
  function approach({ depth = 0, x = 0, y = 0, immediate = false } = {}) {
    if (destroyed) return { ...approachTarget };
    approachTarget = {
      depth: bounded(depth, 0, 1),
      x: bounded(x, -1, 1),
      y: bounded(y, -1, 1),
    };
    const target = approachTarget;
    // Object approach is a separate compositor transform: pausing drift or
    // steering toward a selection never resets the ambient 144-second orbit.
    approachPlane.style.transitionDuration = immediate || isPaused() ? '0ms' : '650ms';
    approachPlane.style.transform = `translate3d(${(-target.x * target.depth * 2).toFixed(6)}%,${(-target.y * target.depth * 2).toFixed(6)}%,0) scale(${(1 + target.depth * 0.12).toFixed(6)})`;
    return { ...target };
  }
  function resetApproach({ immediate = false } = {}) {
    return approach({ immediate });
  }
  function cameraAt(t) {
    const p = (tau * t) / 144;
    return {
      x: 3.2 * Math.sin(p + 0.25) + 0.6 * Math.sin(2 * p - 0.4),
      y: 1.25 * Math.sin(p - 0.9) + 0.35 * Math.sin(2 * p + 0.2),
      scale: 1.1 + 0.08 * Math.sin(p - 0.2),
      roll: 0.55 * Math.sin(p + 0.6),
    };
  }
  function draw(t) {
    const phase = (tau * t) / 144;
    // Closed flight path: the entire exterior shares a camera transform.
    // Percentage steering reads consistently across display sizes. Asynchronous
    // push-in, steering and roll avoid a synchronized inflating/deflating effect.
    const flight = cameraAt(t),
      { x, y, scale, roll } = flight;
    camera.style.transform = `translate3d(${x.toFixed(6)}%,${y.toFixed(6)}%,0) rotate(${roll.toFixed(6)}deg) scale(${scale.toFixed(6)})`;
    const sx = x * 16.72,
      sy = y * 9.41,
      z = scale - 1.1;
    // Fixed outer clipping keeps these independently moving star planes outside
    // the eclipse silhouette even at the extremes of the parallax movement.
    far.setAttribute(
      'transform',
      `translate(${(-sx * 0.65).toFixed(3)} ${(-sy * 0.55).toFixed(3)}) translate(835 470) scale(${(1 - z * 0.3).toFixed(6)}) translate(-835 -470)`,
    );
    near.setAttribute(
      'transform',
      `translate(${(sx * 0.8).toFixed(3)} ${(sy * 0.7).toFixed(3)}) translate(835 470) scale(${(1 + z * 1.3).toFixed(6)}) translate(-835 -470)`,
    );
    const crest = 0.5 + 0.39 * Math.sin(phase * 2 - 0.8),
      echo = 0.5 + 0.42 * Math.sin(phase * 3 + 2);
    for (const s of segments) {
      const dist = (s.t - crest) / 0.12,
        dist2 = (s.t - echo) / 0.065;
      const wave =
        Math.exp(-dist * dist) * (0.65 + 0.17 * Math.sin(phase * 12 + s.t * 38)) +
        Math.exp(-dist2 * dist2) * 0.22;
      const power = (0.08 + wave * s.grain) * brightness;
      s.core.setAttribute('opacity', (0.14 + power * 0.85).toFixed(3));
      s.glow.setAttribute('opacity', (power * 0.48).toFixed(3));
    }
    for (const p of packets) {
      const u = ((((t / 144) * p.speed + p.phase) % 1) + 1) % 1;
      // Slight acceleration through the bend suggests gravitational deflection.
      const progress = u - 0.065 * Math.sin(tau * u),
        at = progress * p.route.len;
      const fade =
        Math.max(0, Math.min(1, progress * 20, (1 - progress) * 20)) * (0.42 + brightness * 0.5);
      p.g.setAttribute('opacity', fade.toFixed(3));
      for (let j = 0; j < p.bands.length; j++)
        p.bands[j].setAttribute(
          'stroke-dashoffset',
          (-(at - ((j + 1) * p.tailLength) / 6)).toFixed(2),
        );
      for (let j = 0; j < p.marks.length; j++) {
        const distance = at - j * p.tailLength * 0.22,
          a = along(p.route, distance),
          mark = p.marks[j];
        mark.setAttribute(
          'transform',
          `translate(${a.x.toFixed(2)} ${a.y.toFixed(2)}) rotate(${a.angle.toFixed(2)})`,
        );
        mark.setAttribute('color', flowColor(a.y));
        mark.setAttribute('opacity', (distance < 0 ? 0 : 1 - j * 0.22).toFixed(3));
      }
    }
    frames++;
  }
  function frame(now) {
    raf = 0;
    if (destroyed || isPaused()) {
      last = 0;
      return;
    }
    if (!last) last = now;
    const elapsed = now - last;
    if (elapsed >= 1000 / 30) {
      time = (time + Math.min(elapsed / 1000, 0.1)) % 144;
      last = now;
      draw(time);
    }
    raf = requestAnimationFrame(frame);
  }
  const button = document.getElementById?.('background-motion');
  function sync() {
    cancelAnimationFrame(raf);
    raf = 0;
    last = 0;
    const paused = isPaused();
    viewport.dataset.paused = String(paused);
    if (!document.body.classList.contains('eclipse-view') && approachTarget.depth)
      resetApproach({ immediate: true });
    else if (paused) approach({ ...approachTarget, immediate: true });
    if (button) {
      button.textContent = paused ? 'Drift off' : 'Drift on';
      button.setAttribute('aria-pressed', String(!paused));
      button.title = reduced.matches
        ? 'Background motion follows your reduced-motion preference'
        : 'Toggle background drift';
    }
    const enabled = motionEnabled();
    if (notifiedMotion !== enabled) {
      notifiedMotion = enabled;
      if (typeof CustomEvent === 'function' && typeof window.dispatchEvent === 'function')
        window.dispatchEvent(new CustomEvent('companion:motion', { detail: { enabled } }));
    }
    if (!destroyed && !paused) raf = requestAnimationFrame(frame);
  }
  function setMotion(enabled) {
    if (destroyed) return false;
    preference = enabled ? 'auto' : 'paused';
    try {
      localStorage.setItem('companion-background-motion', preference);
    } catch {}
    sync();
    return motionEnabled();
  }
  function toggle() {
    setMotion(preference === 'paused');
  }
  button?.addEventListener('click', toggle);
  document.addEventListener('visibilitychange', sync);
  window.addEventListener('companion:presentation', sync);
  reduced.addEventListener('change', sync);
  const observer = new MutationObserver(sync);
  observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  draw(0);
  resetApproach({ immediate: true });
  sync();
  const api = {
    approach,
    resetApproach,
    setMotion,
    motionEnabled,
    destroy() {
      destroyed = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
      button?.removeEventListener('click', toggle);
      document.removeEventListener('visibilitychange', sync);
      window.removeEventListener('companion:presentation', sync);
      reduced.removeEventListener('change', sync);
      viewport.remove();
      if (window.CosmicBackground === api) delete window.CosmicBackground;
    },
    getState() {
      return { time, frames, paused: isPaused(), approach: { ...approachTarget } };
    },
  };
  window.CosmicBackground = api;
  return api;
}
