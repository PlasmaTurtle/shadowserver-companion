/** Spatial instrument. Geometry and all interactive marks come from source records. */
import {
  LENSES,
  clamp,
  seeded,
  mercatorPoint,
  geographicStates,
  jurisdictionBounds,
  endpointKey,
  densityBand,
  densityStats,
  fieldBodyScale,
} from './eclipse_model.js';
import {
  createLocationClusterer,
  semanticLevel,
  membershipForObservation,
} from './eclipse_space.js';
export function createScene(canvas, hooks = {}) {
  const ctx = canvas.getContext('2d'),
    root = canvas.closest('#eclipse'),
    controller = new AbortController(),
    signal = controller.signal;
  const on = (target, event, fn, options = {}) =>
    target.addEventListener(event, fn, { ...options, signal });
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let width = 0,
    height = 0,
    dpr = 1,
    mode = 'field',
    lens = 'vulnerability',
    data = { nodes: [], edges: [] },
    geo = null,
    jurisdiction = [],
    regionBounds = null,
    camera = { x: 0, y: 0, k: 1 },
    fitScale = 1,
    fitMode = null,
    selected = null,
    selectedObservation = null,
    hover = null,
    drag = null,
    alive = true,
    raf = 0,
    transition = null,
    reveal = null,
    focused = null,
    motion = !reduced.matches,
    hitItems = [],
    fieldPaintOrder = [],
    expanded = null,
    atmosphereCache = null,
    locationClusters = createLocationClusterer([]),
    keyboardIndex = -1;
  const cameras = new Map(),
    shadowContours = new WeakMap(),
    viewKey = () => mode + ':' + lens;
  const screen = (n) => ({ x: n.x * camera.k + camera.x, y: n.y * camera.k + camera.y });
  const world = (x, y) => ({ x: (x - camera.x) / camera.k, y: (y - camera.y) / camera.k });
  const color = () => LENSES[lens]?.color || '#7cffff';
  const isBody = (node) => node.field_object === true || node.type !== 'asset';
  const nodeDepth = (node) => (Number.isFinite(node.depth) ? clamp(node.depth, 0, 1) : 0.5);
  // A fetched constellation has a new local fitScale. Its inspection meaning
  // must survive that coordinate reset instead of returning to overview glyphs.
  const detailRatio = () =>
    Math.max(camera.k / fitScale, mode === 'field' && data.focused === true ? 1.8 : 0);
  function invalidate() {
    if (alive && !raf && !document.hidden) raf = requestAnimationFrame(draw);
  }
  function report() {
    const level = semanticLevel(detailRatio());
    root.dataset.semanticLevel = level;
    root.dataset.animating = String(!!transition || !!reveal);
    cameras.set(viewKey(), { camera: { ...camera }, fitScale, fitMode });
    hooks.camera?.(Math.round((camera.k / fitScale) * 100));
    hooks.level?.(level);
    invalidate();
  }
  function finishTransition(completed, reason) {
    const previous = transition;
    transition = null;
    if (!previous) return;
    previous.onSettled?.({ completed, reason });
    if (completed) previous.onComplete?.();
  }
  function go(
    target,
    animate = true,
    { duration = 460, onComplete = null, onSettled = null } = {},
  ) {
    finishTransition(false, 'superseded');
    transition =
      animate && motion && !reduced.matches && !document.hidden
        ? {
            from: { ...camera },
            to: target,
            start: performance.now(),
            duration,
            onComplete,
            onSettled,
          }
        : null;
    if (!transition) camera = { ...target };
    report();
    if (!transition) {
      onSettled?.({ completed: true, reason: 'immediate' });
      onComplete?.();
    }
  }
  function fit(region = false, animate = false) {
    focused = null;
    fitMode = region ? 'region' : 'data';
    const b = (region && regionBounds) ||
      data.bounds || { minX: 0, minY: 0, maxX: 1200, maxY: 760 };
    const view = mode === 'atlas' ? viewport() : { left: 0, right: width, top: 0, bottom: height },
      pad = mode === 'atlas' ? 24 : mode === 'pulse' ? 25 : 65;
    const k = clamp(
      Math.min(
        (view.right - view.left - pad * 2) / Math.max(1, b.maxX - b.minX),
        (view.bottom - view.top - pad * 2) / Math.max(1, b.maxY - b.minY),
      ),
      mode === 'atlas' ? 0.005 : 0.035,
      mode === 'atlas' ? 12 : 2,
    );
    fitScale = k;
    expanded = null;
    go(
      {
        k,
        x: (view.left + view.right - (b.maxX + b.minX) * k) / 2,
        y: mode === 'pulse' ? 105 - 105 * k : (view.top + view.bottom - (b.maxY + b.minY) * k) / 2,
      },
      animate,
    );
  }
  function zoom(factor, x = width / 2, y = height / 2, animate = false) {
    focused = null;
    fitMode = null;
    const anchor = world(x, y),
      k = clamp(camera.k * factor, fitScale * 0.3, Math.max(12, fitScale * 12));
    go({ k, x: x - anchor.x * k, y: y - anchor.y * k }, animate);
  }
  function viewport() {
    const inspectorWidth =
      typeof getComputedStyle === 'function'
        ? parseFloat(getComputedStyle(root).getPropertyValue('--ec-inspector-width')) || 340
        : 340;
    const rightInset =
      root.dataset.inspectorOpen === 'true' && !matchMedia('(max-width:1050px)').matches
        ? Math.min(inspectorWidth + 48, width * 0.45)
        : 0;
    return {
      left: Math.min(42, width * 0.07),
      right: width - rightInset - Math.min(34, width * 0.05),
      top: Math.min(124, height * 0.19),
      bottom: height - Math.min(88, height * 0.14),
      rightInset,
    };
  }
  function focusedCamera(n, ratio, { sources = false } = {}) {
    const view = viewport();
    if (mode !== 'field') {
      const k = ratio ? fitScale * ratio : Math.max(camera.k, fitScale * 1.7);
      return { k, x: (width - view.rightInset) / 2 - n.x * k, y: height * 0.46 - n.y * k };
    }
    // A local constellation supplies its own inspection distance. Multiplying
    // the full-field fit makes a selection microscopic in a large universe.
    const members = [n, ...(sources ? [] : data.neighbors?.get(n.id) || [])].filter(
      (item) => Number.isFinite(item.x) && Number.isFinite(item.y),
    );
    // Some callers provide only edges, rather than the model's neighbor index.
    if (!sources && !data.neighbors?.has(n.id))
      for (const edge of data.edges || []) {
        const other = edge.source === n.id ? edge.to : edge.target === n.id ? edge.from : null;
        if (other && Number.isFinite(other.x) && Number.isFinite(other.y)) members.push(other);
      }
    const xs = members.map((item) => item.x),
      ys = members.map((item) => item.y),
      minX = Math.min(...xs),
      maxX = Math.max(...xs),
      minY = Math.min(...ys),
      maxY = Math.max(...ys),
      usableWidth = Math.max(100, view.right - view.left),
      usableHeight = Math.max(100, view.bottom - view.top),
      labelRoom = Math.min(150, usableWidth * 0.25),
      k = sources
        ? Math.max(fitScale * 3.05, 1.5)
        : clamp(
            Math.min(
              Math.max(80, usableWidth - labelRoom - 80) / Math.max(260, maxX - minX),
              Math.max(80, usableHeight - 90) / Math.max(210, maxY - minY),
            ),
            0.035,
            3,
          );
    return {
      k,
      x: (view.left + view.right - labelRoom) / 2 - ((minX + maxX) / 2) * k,
      y: (view.top + view.bottom) / 2 - ((minY + maxY) / 2) * k,
    };
  }
  function focus(id, ratio, options = {}) {
    const n = data.nodes.find((item) => item.id === id);
    if (!n || !Number.isFinite(n.x) || !Number.isFinite(n.y)) return false;
    fitMode = null;
    focused = { id, ratio, sources: !!options.sources };
    go(focusedCamera(n, ratio, options), true, {
      duration: mode === 'field' ? 720 : 460,
      ...options,
    });
    return true;
  }
  function setLevel(level) {
    if (mode !== 'field') return;
    if (level === 'overview') {
      fit(false, true);
      return;
    }
    const ratio = { overview: 1, endpoints: 1.8, sources: 3.05 }[level] || 1;
    let target = data.nodes.find((n) => n.id === selected);
    if (level === 'sources' && target?.type !== 'asset') {
      const candidates = data.nodes.filter(
        (n) =>
          n.type === 'asset' && (!target || (data.neighbors?.get(target.id) || []).includes(n)),
      );
      target = candidates.sort(
        (a, b) =>
          (b.observation_count || 0) - (a.observation_count || 0) || a.id.localeCompare(b.id),
      )[0];
      if (target) selected = target.id;
    }
    if (target) focus(target.id, ratio, { sources: level === 'sources' });
    else {
      const anchor = world(width / 2, height / 2),
        k = fitScale * ratio;
      go({ k, x: width / 2 - anchor.x * k, y: height / 2 - anchor.y * k });
    }
  }
  function resize() {
    if (!alive) return;
    const r = canvas.getBoundingClientRect(),
      old = width,
      oldHeight = height;
    // Hidden traditional views must not replace the saved field camera with a 1px fit.
    if (r.width <= 0 || r.height <= 0) return;
    width = Math.max(1, r.width);
    height = Math.max(1, r.height);
    dpr = Math.min(2, devicePixelRatio || 1);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const focusNode = focused && data.nodes.find((item) => item.id === focused.id);
    if (old && focusNode) {
      const target = focusedCamera(focusNode, focused.ratio, focused);
      if (transition) transition.to = target;
      else camera = target;
      report();
    } else if (fitMode && (width !== old || height !== oldHeight)) fit(fitMode === 'region');
    else if (!old || width / old < 0.75 || width / old > 1.3) fit();
    else {
      camera.x += (width - old) / 2;
      camera.y += (height - oldHeight) / 2;
      report();
    }
    invalidate();
  }
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  function rectangle(x, y, w, h, r = 3) {
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);
  }
  function label(
    text,
    x,
    y,
    { size = 12, fill = '#d5e9ff', align = 'left', weight = 400, mono = false, max = 0 } = {},
  ) {
    ctx.fillStyle = fill;
    ctx.font = `${weight} ${size}px ${mono ? 'Consolas,monospace' : 'Inter,Segoe UI,sans-serif'}`;
    ctx.textAlign = align;
    const raw = String(text || '');
    let value = raw;
    if (max && ctx.measureText(value).width > max) {
      while (value.length && ctx.measureText(value + '…').width > max) value = value.slice(0, -1);
      value += '…';
    }
    ctx.fillText(value, x, y);
    return ctx.measureText(value).width;
  }
  function atmosphere() {
    // Decorative light has no data meaning. Cache its low-frequency texture so
    // panning only paints one image; no idle animation or filter pass is needed.
    const key = `${Math.ceil(width)}:${Math.ceil(height)}:${mode}`;
    if (atmosphereCache?.key === key) return atmosphereCache.canvas;
    const surface = document.createElement('canvas');
    surface.width = Math.ceil(width);
    surface.height = Math.ceil(height);
    const paint = surface.getContext('2d'),
      wash = paint.createLinearGradient(0, 0, width * 0.8, height);
    // Keep the shared cosmic artwork visible through the scientific layer.
    // Its decorative depth is CSS-composited independently of the data canvas.
    wash.addColorStop(0, '#111e3114');
    wash.addColorStop(0.5, '#0e192a0f');
    wash.addColorStop(1, '#1a20381c');
    paint.fillStyle = wash;
    paint.fillRect(0, 0, width, height);
    const strength = mode === 'field' ? 0.65 : 0.4;
    for (const [cx, cy, radius, rgb, opacity] of [
      [0.92, 0.08, 0.67, '116,70,163', 0.25],
      [0.69, 0.18, 0.36, '106,85,163', 0.17],
      [0.02, 0.95, 0.61, '28,137,153', 0.24],
      [0.2, 0.78, 0.3, '47,105,137', 0.16],
      [0.72, 1.05, 0.52, '97,64,136', 0.17],
    ]) {
      const x = width * cx,
        y = height * cy,
        mist = paint.createRadialGradient(x, y, 0, x, y, Math.max(width, height) * radius);
      mist.addColorStop(0, `rgba(${rgb},${opacity * strength})`);
      mist.addColorStop(0.45, `rgba(${rgb},${opacity * strength * 0.45})`);
      mist.addColorStop(1, `rgba(${rgb},0)`);
      paint.fillStyle = mist;
      paint.fillRect(0, 0, width, height);
    }
    // Sparse curved filaments stay at the edge of the field, behind all marks.
    if (mode === 'field') {
      const filament = paint.createLinearGradient(width * 0.35, height, width, 0);
      filament.addColorStop(0, '#b7a7ed00');
      filament.addColorStop(0.6, '#b7a7ed14');
      filament.addColorStop(1, '#a2dce300');
      paint.strokeStyle = filament;
      paint.lineWidth = 0.8;
      for (let i = 0; i < 3; i++) {
        paint.beginPath();
        paint.moveTo(width * 0.32, height * (1.1 + i * 0.04));
        paint.bezierCurveTo(
          width * 0.95,
          height * (0.82 + i * 0.04),
          width * (0.7 + i * 0.04),
          -height * 0.1,
          width * 1.2,
          -height * 0.15,
        );
        paint.stroke();
      }
    }
    atmosphereCache = { key, canvas: surface };
    return surface;
  }
  function densityHalo(x, y, node, radius = 12) {
    const count = node.density_count ?? node.observation_count ?? 0;
    const band = densityBand(count);
    if (band.id === 'normal') return;
    const outer = radius + (band.id === 'purple' ? 38 : band.id === 'red' ? 26 : 18);
    const glow = ctx.createRadialGradient(x, y, radius * 0.6, x, y, outer);
    glow.addColorStop(0, band.color + '07');
    glow.addColorStop(0.4, band.color + (band.id === 'purple' ? '69' : '43'));
    glow.addColorStop(1, band.color + '00');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(x, y, outer, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = band.color + (band.id === 'purple' ? 'e3' : band.id === 'red' ? 'cc' : 'b5');
    ctx.lineWidth = band.id === 'purple' ? 3 : band.id === 'red' ? 2 : 1;
    ctx.beginPath();
    ctx.arc(x, y, radius + 4, 0, Math.PI * 2);
    ctx.stroke();
    if (band.id === 'purple') {
      ctx.strokeStyle = band.color + '4d';
      ctx.beginPath();
      ctx.ellipse(x, y, radius + 18, radius + 9, -0.4, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  function darkMatterHalo(x, y, node, radius, onlyDark) {
    const count = node.dark_matter_density ?? node.dark_matter_observations ?? 0;
    if (!(count > 0)) return;
    // This shadow is retained, unadmitted evidence, not an inferred connection.
    // Bound both geometry and work: more observations deepen a local envelope
    // without covering the whole field or creating more particles/animation.
    let points = shadowContours.get(node);
    if (!points) {
      points = Array.from({ length: 24 }, (_, index) => {
        const angle = (index / 24) * Math.PI * 2,
          reach = 0.82 + seeded(node.id + ':shadow:' + index) * 0.18;
        return { x: Math.cos(angle) * reach, y: Math.sin(angle) * reach * 0.78 };
      });
      shadowContours.set(node, points);
    }
    const mass = clamp(Math.log2(1 + count) / 12, 0, 1),
      outer = radius + 20 + mass * 28,
      traceCloud = (scale) => {
        scale *= outer;
        ctx.beginPath();
        const first = points[0],
          last = points[points.length - 1];
        ctx.moveTo(x + ((last.x + first.x) / 2) * scale, y + ((last.y + first.y) / 2) * scale);
        points.forEach((point, index) => {
          const next = points[(index + 1) % points.length];
          ctx.quadraticCurveTo(
            x + point.x * scale,
            y + point.y * scale,
            x + ((point.x + next.x) / 2) * scale,
            y + ((point.y + next.y) / 2) * scale,
          );
        });
        ctx.closePath();
      },
      shadow = ctx.createRadialGradient(x, y, radius * 0.35, x, y, outer);
    shadow.addColorStop(0, onlyDark ? '#01040af2' : '#02060de0');
    shadow.addColorStop(0.65, '#02060dba');
    shadow.addColorStop(1, '#02060d15');
    ctx.fillStyle = shadow;
    traceCloud(1);
    ctx.fill();
    ctx.lineWidth = onlyDark ? 1.3 : 1;
    ctx.strokeStyle = onlyDark ? '#a8b9cf9c' : '#91a5bd78';
    ctx.stroke();
    ctx.lineWidth = 0.7;
    ctx.strokeStyle = '#7895b14d';
    traceCloud(0.78);
    ctx.stroke();
    // Bent, broken light at the boundary is a visual metaphor only. These arcs
    // terminate around this one object and cannot be mistaken for graph edges.
    for (let index = 0; index < 3; index++) {
      ctx.strokeStyle = index === 1 ? '#aac5d87a' : '#789bb861';
      ctx.lineWidth = index === 1 ? 1.1 : 0.7;
      ctx.beginPath();
      ctx.ellipse(
        x,
        y,
        outer + 5 + index * 5,
        outer * (0.52 + index * 0.08),
        -0.42,
        Math.PI * (0.13 + index * 0.67),
        Math.PI * (0.57 + index * 0.67),
      );
      ctx.stroke();
    }
  }
  function background() {
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(atmosphere(), 0, 0);
    const grid = 80 * Math.pow(2, Math.floor(Math.log2(Math.max(0.05, camera.k)))),
      step = clamp((grid / camera.k) * camera.k, 30, 140);
    ctx.strokeStyle = '#6ba0b00c';
    ctx.lineWidth = 0.7;
    for (let x = ((camera.x % step) + step) % step; x < width; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = ((camera.y % step) + step) % step; y < height; y += step) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    const grain = Math.min(200, Math.floor((width * height) / 3500));
    for (let i = 0; i < grain; i++) {
      ctx.fillStyle = i % 11 === 0 ? '#acbfd049' : '#8fb7d322';
      const x = (((seeded('fieldx' + i) * width + camera.x * 0.08) % width) + width) % width,
        y = (((seeded('fieldy' + i) * height + camera.y * 0.08) % height) + height) % height;
      ctx.fillRect(x, y, i % 11 === 0 ? 1 : 0.6, i % 11 === 0 ? 1 : 0.6);
    }
  }
  function revealOpacity(node, now) {
    if (!reveal || node.id === selected || node.id === hover?.id) return 1;
    const rank = Number.isFinite(node.revealRank)
        ? node.revealRank
        : reveal.ranks.get(node.id) || 0,
      delay = (rank / reveal.maximum) * 0.65,
      progress = clamp(((now - reveal.start) / reveal.duration - delay) / 0.35, 0, 1);
    // Every mark stays present and selectable from the first frame. Arrival is
    // a brightness reveal, never a delayed admission of data or hit targets.
    return 0.18 + 0.82 * progress * progress * (3 - 2 * progress);
  }
  function scan(now) {
    if (!reveal) return;
    const progress = clamp((now - reveal.start) / reveal.duration, 0, 1),
      x = width * (0.08 + 0.84 * (0.5 - 0.5 * Math.cos(progress * Math.PI * 2))),
      half = Math.min(100, width * 0.12),
      wash = ctx.createLinearGradient(x - half, 0, x + half, 0);
    wash.addColorStop(0, '#8dcfe300');
    wash.addColorStop(0.5, '#9cdae31c');
    wash.addColorStop(1, '#8dcfe300');
    ctx.globalAlpha = Math.sin(progress * Math.PI) * 0.8;
    ctx.fillStyle = wash;
    ctx.fillRect(x - half, 0, half * 2, height);
    ctx.globalAlpha = 1;
  }
  function field(now) {
    const level = semanticLevel(detailRatio()),
      approachScale = fieldBodyScale(detailRatio()),
      active = selected || hover?.id,
      neighbors = new Set(active ? [active] : []),
      sources = selectedObservation
        ? new Set(membershipForObservation(data, selectedObservation).map((n) => n.id))
        : null;
    for (const edge of data.edges || []) {
      if (edge.source === active) neighbors.add(edge.target);
      if (edge.target === active) neighbors.add(edge.source);
    }
    // Real relationships are quiet until focus makes them relevant. Curvature
    // is a drawing convention, never traffic or inferred ownership.
    for (const edge of data.edges || []) {
      const a = screen(edge.from),
        b = screen(edge.to),
        chosen = neighbors.has(edge.source) && neighbors.has(edge.target);
      ctx.strokeStyle = chosen ? '#beeef2' : '#7196a6';
      ctx.globalAlpha =
        (active ? (chosen ? 0.62 : 0.045) : 0.15) *
        Math.min(revealOpacity(edge.from, now), revealOpacity(edge.to, now));
      ctx.lineWidth = chosen ? 1.3 : 0.7;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.bezierCurveTo(a.x + (b.x - a.x) * 0.2, b.y, a.x + (b.x - a.x) * 0.8, a.y, b.x, b.y);
      ctx.stroke();
    }
    const names = [],
      bodyRects = [],
      temperatures = { cool: '#81dce2', warm: '#e6ca79', hot: '#f3a476', blazing: '#f18fa8' };
    // Depth sorting is cached at set(), not repeated on every animation frame.
    // Chosen objects are the explicit foreground exception. Reverse hit order
    // then agrees with the visible body at overlapping coordinates.
    const chosenNode = (n) => n.id === active || sources?.has(n.id),
      paintOrder =
        active || sources
          ? [
              ...fieldPaintOrder.filter((n) => !chosenNode(n)),
              ...fieldPaintOrder.filter(chosenNode),
            ]
          : fieldPaintOrder;
    for (const n of paintOrder) {
      const p = screen(n);
      if (p.x < -130 || p.y < -100 || p.x > width + 130 || p.y > height + 100) continue;
      const hub = isBody(n),
        chosen = n.id === active || sources?.has(n.id),
        related = neighbors.has(n.id),
        dim = active && !related && !chosen,
        appearance = revealOpacity(n, now),
        depth = nodeDepth(n),
        admitted = n.admitted_density ?? n.admitted_observations ?? 0,
        dark = n.dark_matter_density ?? n.dark_matter_observations ?? 0,
        onlyDark = dark > 0 && admitted === 0,
        radius = hub
          ? clamp(11 + Math.log2(1 + (n.asset_count || 1)) * 2, 13, 25) * approachScale
          : chosen
            ? 7
            : level === 'overview'
              ? 3
              : 5;
      ctx.globalAlpha = (dim ? 0.18 : chosen ? 1 : 0.86 + depth * 0.14) * appearance;
      if (dark > 0 && (hub || chosen)) darkMatterHalo(p.x, p.y, n, radius, onlyDark);
      if (hub || level !== 'overview' || chosen) densityHalo(p.x, p.y, n, radius);
      // The halo distorts decorative filament light, never data positions.
      const density = n.density_count ?? n.observation_count ?? 0;
      if (hub && density > 50 && !dim) {
        const band = densityBand(density),
          warp = radius + (band.id === 'purple' ? 57 : 36);
        ctx.strokeStyle = band.color + '38';
        ctx.lineWidth = 0.7;
        for (let i = 0; i < 3; i++) {
          ctx.beginPath();
          ctx.ellipse(
            p.x,
            p.y,
            warp + i * 9,
            warp * (0.42 + i * 0.06),
            -0.45,
            Math.PI * 0.1,
            Math.PI * 1.68,
          );
          ctx.stroke();
        }
      }
      ctx.fillStyle = onlyDark ? '#111b2a' : '#091521';
      ctx.strokeStyle = chosen ? '#e4ffff' : onlyDark ? '#8795b1' : '#8bc5ce';
      ctx.lineWidth = chosen ? 1.8 : 1;
      if (onlyDark) ctx.setLineDash([3, 4]);
      ctx.beginPath();
      if (!hub) ctx.roundRect(p.x - radius, p.y - radius, radius * 2, radius * 2, 1);
      else if (['cve', 'finding'].includes(n.type)) {
        ctx.moveTo(p.x, p.y - radius);
        ctx.lineTo(p.x + radius * 0.85, p.y);
        ctx.lineTo(p.x, p.y + radius);
        ctx.lineTo(p.x - radius * 0.85, p.y);
        ctx.closePath();
      } else ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.setLineDash([]);
      if (hub && !onlyDark) {
        const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius * 2);
        glow.addColorStop(0, chosen ? '#b5ffff65' : '#8bdce23a');
        glow.addColorStop(1, '#8bdce200');
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius * 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#d3ffff';
        ctx.beginPath();
        ctx.arc(p.x, p.y, (n.type === 'entity' ? 3.1 : 2) * approachScale, 0, Math.PI * 2);
        ctx.fill();
      }
      if (chosen) {
        ctx.strokeStyle = '#c9ffff80';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + 7, Math.PI * 0.1, Math.PI * 0.88);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + 7, Math.PI * 1.1, Math.PI * 1.88);
        ctx.stroke();
      }
      if (temperatures[n.temperature] && (hub || chosen || level !== 'overview')) {
        ctx.fillStyle = temperatures[n.temperature];
        ctx.beginPath();
        ctx.arc(p.x + radius + 5, p.y - radius - 4, 3, 0, Math.PI * 2);
        ctx.fill();
      }
      if (n.risk_changed && (hub || chosen))
        label('△', p.x - radius - 15, p.y - radius, { size: 13, fill: '#e8cd91' });
      hitItems.push({
        node: n,
        x: p.x - Math.max(22, radius),
        y: p.y - Math.max(22, radius),
        w: Math.max(44, radius * 2),
        h: Math.max(44, radius * 2),
      });
      bodyRects.push({
        id: n.id,
        x: p.x - radius - 6,
        y: p.y - radius - 6,
        w: (radius + 6) * 2,
        h: (radius + 6) * 2,
      });
      if (hub || chosen || (level !== 'overview' && (!active || related)))
        names.push({
          n,
          p,
          hub,
          chosen,
          dim,
          appearance,
          radius,
          rank: (chosen ? 100 : 0) + (related ? 20 : 0) + depth,
        });
    }
    // Labels do not compete with each other. Identity is always readable at
    // inspection distance; quiet peripheral bodies remain directly selectable.
    const occupied = [
        { x: 16, y: 12, w: Math.min(420, width * 0.55), h: 105 },
        { x: 16, y: height - 80, w: Math.min(440, width * 0.65), h: 70 },
      ],
      maxNames = level === 'overview' ? 24 : 45;
    if (root.dataset.inspectorOpen === 'true' && !matchMedia('(max-width:1050px)').matches)
      occupied.push({ x: width - 390, y: 15, w: 390, h: height - 90 });
    names.sort((a, b) => b.rank - a.rank || a.n.id.localeCompare(b.n.id));
    let placedNames = 0;
    for (const item of names) {
      if (placedNames >= maxNames) break;
      const { n, p, hub, chosen, dim, radius, appearance } = item,
        title = n.displayLabel || n.label,
        size = hub ? (chosen ? 19 : 15) : 12,
        assetCount = n.total_assets ?? n.asset_count,
        observationCount = n.density_count ?? n.observation_count ?? 0,
        caption = hub
          ? `${n.type !== 'asset' && assetCount !== undefined && assetCount !== 1 ? `${Number(assetCount).toLocaleString('en-US')} assets · ` : ''}${Number(observationCount).toLocaleString('en-US')} observations`
          : '',
        h = hub ? 43 : 20;
      ctx.font = `${hub ? 500 : 400} ${size}px ${hub ? 'Inter,Segoe UI,sans-serif' : 'Consolas,monospace'}`;
      const titleWidth = ctx.measureText(String(title || '')).width;
      ctx.font = '400 11px Inter,Segoe UI,sans-serif';
      const w = Math.min(
          hub ? 220 : 190,
          Math.ceil(Math.max(titleWidth, ctx.measureText(caption).width)) + 4,
        ),
        lineY = p.y - (hub ? 7 : -4),
        aboveY = p.y - radius - (hub ? 38 : 15),
        belowY = p.y + radius + 29,
        candidates = [
          { x: p.x + radius + 13, y: lineY },
          { x: p.x - radius - 13 - w, y: lineY },
          { x: p.x - w / 2, y: aboveY },
          { x: p.x - w / 2, y: belowY },
        ];
      if (chosen) {
        candidates.push(
          { x: p.x + radius + 13, y: aboveY },
          { x: p.x - radius - 13 - w, y: aboveY },
          { x: p.x + radius + 13, y: belowY },
          { x: p.x - radius - 13 - w, y: belowY },
        );
        const view = viewport();
        candidates.push(
          { x: view.left + 12, y: view.top + 18 },
          { x: view.right - w - 8, y: 42 },
          { x: view.left + 12, y: view.bottom - 30 },
          { x: view.right - w - 8, y: view.bottom - 30 },
        );
      }
      const placement = candidates.find(({ x, y }) => {
        if (x < 12 || x + w > width - 12 || y < 22 || y + h > height - 35) return false;
        const rect = { x: x - 3, y: y - 17, w: w + 6, h },
          intersects = (r) =>
            r.x < rect.x + rect.w &&
            r.x + r.w > rect.x &&
            r.y < rect.y + rect.h &&
            r.y + r.h > rect.y;
        return !bodyRects.some((r) => r.id !== n.id && intersects(r)) && !occupied.some(intersects);
      });
      if (!placement) continue;
      const { x, y } = placement,
        rect = { x: x - 3, y: y - 17, w: w + 6, h };
      occupied.push(rect);
      ctx.globalAlpha = (dim ? 0.34 : 1) * appearance;
      label(title, x, y, {
        size,
        weight: hub ? 500 : 400,
        fill: chosen ? '#efffff' : '#d2e5ee',
        max: w,
        mono: !hub,
      });
      if (hub) {
        label(caption, x, y + 19, { size: 11, fill: '#9bb3c4', max: w });
      }
      hitItems.push({ node: n, ...rect });
      placedNames++;
    }
    ctx.globalAlpha = 1;
    if (level === 'sources') {
      const n = (data.nodes || []).find((n) => n.id === selected && n.type === 'asset');
      if (n?.rows?.length) {
        const p = screen(n),
          rows = n.rows.slice(0, 4),
          left = clamp(p.x + 22, 15, width - 225),
          top = clamp(p.y + 38, 80, height - rows.length * 36 - 45);
        rows.forEach((row, i) => {
          const y = top + i * 36,
            chosen = row.id === selectedObservation;
          ctx.fillStyle = chosen ? '#21454f' : '#0a1826';
          ctx.strokeStyle = chosen ? '#a6eae8' : '#304a5c';
          ctx.lineWidth = 1;
          rectangle(left, y, 204, 31, 2);
          ctx.fill();
          ctx.stroke();
          label(row.observed_day || 'Undated', left + 9, y + 20, {
            size: 12,
            mono: true,
            fill: '#d6e8ef',
          });
          label('Evidence', left + 194, y + 20, { size: 11, align: 'right', fill: '#9fb7c4' });
          hitItems.push({
            node: {
              id: 'source:' + row.id,
              type: 'source',
              label: row.hostname || row.ip,
              rows: [row],
              row,
              observation_count: 1,
            },
            x: left,
            y,
            w: 204,
            h: 31,
          });
        });
      }
    }
  }
  function trace(geometry) {
    const polys =
      geometry?.type === 'Polygon'
        ? [geometry.coordinates]
        : geometry?.type === 'MultiPolygon'
          ? geometry.coordinates
          : [];
    for (const polygon of polys)
      for (const ring of polygon) {
        ring.forEach(([lon, lat], i) => {
          const p = screen(mercatorPoint(lon, lat));
          if (!i) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });
        ctx.closePath();
      }
  }
  function atlas() {
    if (geo) {
      for (const region of geo.states || []) {
        const b = region.bounds;
        if (
          b.maxX * camera.k + camera.x < 0 ||
          b.minX * camera.k + camera.x > width ||
          b.maxY * camera.k + camera.y < 0 ||
          b.minY * camera.k + camera.y > height
        )
          continue;
        const selected = jurisdiction.includes(region.properties?.postal);
        ctx.beginPath();
        trace(region.geometry);
        ctx.fillStyle = selected ? '#0c263880' : '#0b1a292e';
        ctx.fill();
        ctx.strokeStyle = selected ? '#487a9e' : '#264057';
        ctx.lineWidth = 0.8;
        ctx.stroke();
      }
      if (camera.k > 0.5) {
        ctx.strokeStyle = '#66a4c528';
        ctx.lineWidth = 0.5;
        for (const county of geo.counties || []) {
          ctx.beginPath();
          trace(county.geometry);
          ctx.stroke();
        }
      }
      for (const region of geo.states || []) {
        if (!jurisdiction.includes(region.properties?.postal)) continue;
        const b = region.bounds,
          span = (b.maxX - b.minX) * camera.k;
        if (span < 35) continue;
        const p = screen({ x: (b.minX + b.maxX) / 2, y: (b.minY + b.maxY) / 2 });
        const text =
          span > region.properties.name.length * 8
            ? region.properties.name.toUpperCase()
            : region.properties.postal;
        label(text, p.x, p.y, { size: 11, mono: true, fill: '#7299b8', align: 'center' });
      }
    }
    const clusters = locationClusters(camera, 56),
      mapLabels = [],
      markerCount = (c) =>
        c.entity_map ? c.entity_count : (c.finding_count ?? c.observation_count ?? 0),
      markerRadius = (c) => clamp(13 + Math.log2(1 + markerCount(c)) * 3, 16, 27);
    const mapBodies = clusters.map((c) => {
      const r = markerRadius(c);
      return { id: c.id, x: c.sx - r - 4, y: c.sy - r - 4, w: (r + 4) * 2, h: (r + 4) * 2 };
    });
    root.dataset.clusterCount = String(clusters.length);
    for (const c of clusters) {
      const p = { x: c.sx, y: c.sy },
        contains = c.rows.some((r) => r.id === selectedObservation),
        chosen = c.id === selected || c.members.some((n) => n.id === selected) || contains,
        r = markerRadius(c);
      if (p.x < -80 || p.y < -80 || p.x > width + 80 || p.y > height + 80) continue;
      densityHalo(p.x, p.y, c.entity_map ? { density_count: c.entity_count } : c, r);
      if (c.risk_changed) label('△', p.x + r + 5, p.y - r, { size: 17, fill: '#e8cd91' });
      ctx.strokeStyle = chosen
        ? '#fff'
        : c.entity_map || c.admitted_density
          ? '#7cffff'
          : '#8d91aa';
      ctx.lineWidth = chosen ? 2.5 : 1.3;
      ctx.fillStyle = chosen ? '#214a5b' : '#0b2639';
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fill();
      if (c.approximate) ctx.setLineDash([3, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      label(markerCount(c), p.x, p.y + 5, {
        size: 15,
        fill: '#e3ffff',
        weight: 600,
        align: 'center',
      });
      mapLabels.push({ c, p, r, chosen });
      hitItems.push({
        node: {
          ...c,
          basis:
            c.basis ||
            'Clustered reported locations. Click to expand; source coordinates are unchanged.',
        },
        x: p.x - r,
        y: p.y - r,
        w: r * 2,
        h: r * 2,
      });
      if (expanded === c.id && c.members.length === 1 && !c.summary) {
        const endpoints = new Map();
        for (const row of c.rows) {
          const key = endpointKey(row);
          if (!endpoints.has(key)) endpoints.set(key, []);
          endpoints.get(key).push(row);
        }
        const children = [...endpoints.values()].slice(0, 12);
        children.forEach((rows, i) => {
          const angle = -Math.PI / 2 + (i * Math.PI * 2) / children.length,
            radius = 85 + Math.floor(i / 8) * 35,
            x = p.x + Math.cos(angle) * radius,
            y = p.y + Math.sin(angle) * radius;
          ctx.strokeStyle = '#8fced66e';
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(x, y);
          ctx.stroke();
          ctx.fillStyle = '#7cffff';
          ctx.fillRect(x - 5, y - 5, 10, 10);
          label(rows[0].hostname || rows[0].ip, x + 10, y + 4, { size: 11, mono: true, max: 165 });
          hitItems.push({
            node: {
              id: 'map-endpoint:' + endpointKey(rows[0]),
              type: 'map-endpoint',
              label: rows[0].hostname || rows[0].ip,
              rows,
              ...densityStats(rows),
              basis:
                'Expanded endpoint labels share this reported location. Their offset is for readability, not a distinct position.',
            },
            x: x - 8,
            y: y - 10,
            w: 180,
            h: 25,
          });
        });
      }
    }
    const occupied = [{ x: 16, y: 12, w: Math.min(420, width * 0.55), h: 105 }];
    if (root.dataset.inspectorOpen === 'true' && !matchMedia('(max-width:1050px)').matches)
      occupied.push({ x: width - 390, y: 15, w: 390, h: height - 90 });
    const overlaps = (a, b) =>
      a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    mapLabels.sort((a, b) => Number(b.chosen) - Number(a.chosen) || a.c.id.localeCompare(b.c.id));
    for (const { c, p, r, chosen } of mapLabels) {
      ctx.font = '12px Inter,Segoe UI,sans-serif';
      const textWidth = Math.min(170, ctx.measureText(c.label).width),
        rect = { x: p.x - textWidth / 2 - 3, y: p.y - r - 25, w: textWidth + 6, h: 19 };
      if (
        !chosen &&
        (occupied.some((o) => overlaps(o, rect)) ||
          mapBodies.some((o) => o.id !== c.id && overlaps(o, rect)))
      )
        continue;
      occupied.push(rect);
      label(c.label, p.x, p.y - r - 10, { size: 12, fill: '#cbe8f4', align: 'center', max: 170 });
      if (chosen && c.members.length > 1)
        label(
          c.entity_map
            ? `${c.entity_count} entities · select an entity in Details`
            : `${c.members.length} assets · select to expand`,
          p.x,
          p.y + r + 17,
          {
            size: 11,
            fill: '#b1c9d9',
            align: 'center',
            max: 220,
          },
        );
    }
  }
  function pulse() {
    const lanes = data.lanes || [],
      days = data.days || [],
      span = Math.max(86400000, data.end - data.start);
    const chartLeft = screen({ x: 300, y: 0 }).x,
      chartRight = screen({ x: 1000, y: 0 }).x;
    const dayIndices =
      days.length <= 10
        ? days.map((_, i) => i)
        : [
            ...new Set(
              Array.from({ length: 8 }, (_, i) => Math.round((i * (days.length - 1)) / 7)),
            ),
          ];
    for (const i of dayIndices) {
      const day = days[i],
        x = screen({
          x: 300 + (days.length === 1 ? 0.5 : (Date.parse(day) - data.start) / span) * 700,
          y: 0,
        }).x;
      ctx.strokeStyle = '#577b9d30';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, 60);
      ctx.lineTo(x, height - 62);
      ctx.stroke();
      label(day, x, 44, { size: 12, mono: true, align: 'center', fill: '#aec9e5' });
    }
    label('OBSERVATIONS / REPORTED DATE', 20, 25, { size: 11, mono: true, fill: '#7fb4d1' });
    const largest = Math.max(1, ...(data.nodes || []).map((n) => n.observation_count));
    lanes.forEach((lane, i) => {
      const y = screen({ x: 0, y: 105 + i * 62 }).y,
        daysSeen =
          lane.day_count ?? new Set(lane.rows.map((r) => r.observed_day).filter(Boolean)).size,
        active = lane.rows.some((r) => r.id === selectedObservation);
      ctx.fillStyle = active ? '#173c4a80' : i % 2 ? '#101b2a55' : '#0a121d55';
      ctx.fillRect(0, y - 26, width, 53);
      label(lane.label, Math.max(10, chartLeft - 49), y - 2, {
        size: 13,
        mono: lens === 'ip',
        align: 'right',
        fill: active ? '#e8ffff' : '#d1e4fa',
        max: Math.max(120, chartLeft - 65),
      });
      label(
        `${daysSeen} days · ${lane.observation_count ?? lane.rows.length} observations`,
        Math.max(10, chartLeft - 49),
        y + 17,
        {
          size: 11,
          align: 'right',
          fill: '#a3bddb',
        },
      );
    });
    const spacing =
        days.length > 1
          ? Math.abs(screen({ x: 300 + 700 / Math.max(1, days.length - 1), y: 0 }).x - chartLeft)
          : 100,
      cw = clamp(spacing * 0.55, 24, 68),
      ch = clamp((35 * camera.k) / fitScale, 26, 42);
    for (const n of data.nodes || []) {
      const p = screen(n);
      if (p.x < chartLeft - 40 || p.y < 60 || p.y > height - 50 || p.x > width + 40) continue;
      const chosen = n.id === selected || n.rows.some((r) => r.id === selectedObservation),
        intensity = 0.18 + 0.72 * Math.sqrt(n.observation_count / largest);
      ctx.fillStyle = chosen ? '#7cffff' : `rgba(142,174,255,${intensity})`;
      ctx.strokeStyle = chosen ? '#ffffff' : '#8aabff80';
      ctx.lineWidth = chosen ? 2.5 : 1;
      rectangle(p.x - cw / 2, p.y - ch / 2, cw, ch, 3);
      ctx.fill();
      ctx.stroke();
      label(n.observation_count, p.x, p.y + 5, {
        size: 14,
        weight: 600,
        align: 'center',
        fill: chosen ? '#05212c' : '#edf5ff',
      });
      hitItems.push({ node: n, x: p.x - cw / 2, y: p.y - ch / 2, w: cw, h: ch });
    }
  }
  function draw(now = performance.now()) {
    let completed = null;
    raf = 0;
    if (!alive || document.hidden) return;
    if (reveal && now - reveal.start >= reveal.duration) reveal = null;
    if (transition) {
      const t = clamp((now - transition.start) / transition.duration, 0, 1),
        ease = 1 - (1 - t) ** 3;
      for (const key of ['x', 'y', 'k'])
        camera[key] = transition.from[key] + (transition.to[key] - transition.from[key]) * ease;
      if (t === 1) {
        const settled = transition;
        completed = () => {
          settled.onSettled?.({ completed: true, reason: 'arrived' });
          settled.onComplete?.();
        };
        transition = null;
        cameras.set(viewKey(), { camera: { ...camera }, fitScale, fitMode });
      }
      hooks.camera?.(Math.round((camera.k / fitScale) * 100));
      hooks.level?.(semanticLevel(detailRatio()));
      root.dataset.semanticLevel = semanticLevel(detailRatio());
    }
    root.dataset.animating = String(!!transition || !!reveal);
    root.dataset.revealing = String(!!reveal);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    hitItems = [];
    background();
    scan(now);
    if (mode === 'field') field(now);
    else if (mode === 'atlas') atlas();
    else pulse();
    const outside =
      selectedObservation &&
      data.selectedRow &&
      !membershipForObservation(data, selectedObservation).length;
    if (outside) {
      const row = data.selectedRow,
        x = 20,
        y = height - 125,
        w = Math.min(350, width - 40);
      ctx.fillStyle = '#0b2335';
      ctx.strokeStyle = '#70cbd8';
      rectangle(x, y, w, 62, 3);
      ctx.fill();
      ctx.stroke();
      label(
        mode === 'atlas' ? 'NO USABLE LOCATION' : 'NO DATED CELL IN THIS LENS',
        x + 12,
        y + 20,
        { size: 11, fill: '#7cffff' },
      );
      label(row.hostname || row.ip || 'Selected source', x + 12, y + 44, { size: 13, max: w - 24 });
      hitItems.push({
        node: {
          id: 'source:' + row.id,
          type: 'source',
          row,
          rows: [row],
          label: row.hostname || row.ip,
          observation_count: 1,
        },
        x,
        y,
        w,
        h: 62,
      });
    }
    root.dataset.selectedUnplaced = String(!!outside);
    const selectedNodes = selectedObservation
      ? membershipForObservation(data, selectedObservation)
      : mode === 'atlas' && selected
        ? locationClusters(camera, 56)
            .filter((c) => c.id === selected || c.members.some((n) => n.id === selected))
            .flatMap((c) => c.members)
        : (data.nodes || []).filter((n) => n.id === selected);
    const present = outside || selectedNodes.length > 0;
    root.dataset.selectedPresent = String(present);
    root.dataset.renderedCount = String(hitItems.length);
    root.dataset.sourceCards = String(hitItems.filter((h) => h.node.type === 'source').length);
    root.dataset.selectedVisible = String(
      !!outside ||
        selectedNodes.some((n) => {
          const p = screen(n);
          return p.x > 0 && p.x < width && p.y > 0 && p.y < height - 45;
        }),
    );
    if (transition || reveal) raf = requestAnimationFrame(draw);
    completed?.();
  }
  function hit(x, y) {
    for (let i = hitItems.length - 1; i >= 0; i--) {
      const h = hitItems[i];
      if (x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) return h.node;
    }
    return null;
  }
  function pick(node) {
    fitMode = null;
    selected = node.id;
    if (node.type === 'source') {
      selectedObservation = node.row.id;
      hooks.select?.(node);
      invalidate();
      return;
    }
    selectedObservation = null;
    hooks.select?.(node);
    if (mode === 'atlas' && node.type === 'cluster') {
      if (node.members.length > 1 && new Set(node.members.map((n) => `${n.x}|${n.y}`)).size > 1) {
        const xs = node.members.map((n) => n.x),
          ys = node.members.map((n) => n.y),
          k = Math.min(Math.max(camera.k * 2.2, 1.5), 12);
        go({ k, x: width / 2 - node.x * k, y: height * 0.45 - node.y * k });
      } else {
        expanded = expanded === node.id ? null : node.id;
        invalidate();
      }
      return;
    }
    // Selection hooks own Field navigation. Starting another focus here would
    // overwrite the controller's inspector-aware journey and its completion.
    invalidate();
  }
  on(canvas, 'pointerdown', (e) => {
    if (e.button !== 0) return;
    focused = null;
    fitMode = null;
    finishTransition(false, 'input');
    canvas.focus({ preventScroll: true });
    canvas.setPointerCapture(e.pointerId);
    drag = { x: e.clientX, y: e.clientY, lastX: e.clientX, lastY: e.clientY, moved: false };
  });
  on(canvas, 'pointermove', (e) => {
    const rect = canvas.getBoundingClientRect(),
      x = e.clientX - rect.left,
      y = e.clientY - rect.top;
    if (drag) {
      const dx = e.clientX - drag.lastX,
        dy = e.clientY - drag.lastY;
      drag.moved ||= Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 4;
      drag.lastX = e.clientX;
      drag.lastY = e.clientY;
      if (drag.moved) {
        focused = null;
        camera.x += dx;
        camera.y += dy;
        report();
        hooks.hover?.(null);
        return;
      }
    }
    hover = hit(x, y);
    canvas.style.cursor = hover ? 'pointer' : 'grab';
    hooks.hover?.(hover, x, y);
    invalidate();
  });
  on(canvas, 'pointerup', (e) => {
    if (!drag) return;
    const moved = drag.moved;
    drag = null;
    if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    if (!moved) {
      const rect = canvas.getBoundingClientRect(),
        node = hit(e.clientX - rect.left, e.clientY - rect.top);
      if (node) pick(node);
      else {
        hover = null;
        hooks.hover?.(null);
        invalidate();
      }
    }
  });
  on(canvas, 'pointercancel', () => {
    drag = null;
  });
  on(canvas, 'pointerleave', () => {
    if (!drag) {
      hover = null;
      hooks.hover?.(null);
      invalidate();
    }
  });
  on(
    canvas,
    'wheel',
    (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      zoom(
        Math.exp(-clamp(e.deltaY, -180, 180) * 0.0025),
        e.clientX - rect.left,
        e.clientY - rect.top,
      );
    },
    { passive: false },
  );
  on(canvas, 'keydown', (e) => {
    if (
      [
        '+',
        '=',
        '-',
        '0',
        '[',
        ']',
        'Enter',
        'ArrowLeft',
        'ArrowRight',
        'ArrowUp',
        'ArrowDown',
        'Escape',
      ].includes(e.key)
    )
      e.preventDefault();
    if (['[', ']'].includes(e.key)) {
      const bodies = data.nodes || [];
      if (bodies.length) {
        keyboardIndex = (keyboardIndex + (e.key === ']' ? 1 : -1) + bodies.length) % bodies.length;
        pick(bodies[keyboardIndex]);
        canvas.setAttribute(
          'aria-label',
          `${bodies[keyboardIndex].label}. Use brackets to select another object, Enter to focus, arrows to pan.`,
        );
      }
    } else if (e.key === 'Enter') {
      const n = (data.nodes || []).find((n) => n.id === selected);
      if (n) pick(n);
    } else if (['+', '='].includes(e.key)) zoom(1.25, width / 2, height / 2, true);
    else if (e.key === '-') zoom(0.8, width / 2, height / 2, true);
    else if (e.key === '0') fit(false, true);
    else if (e.key === 'Escape') {
      finishTransition(false, 'input');
      selected = null;
      focused = null;
      selectedObservation = null;
      hooks.clear?.();
      invalidate();
    } else if (e.key.startsWith('Arrow')) {
      focused = null;
      fitMode = null;
      finishTransition(false, 'input');
      const d = e.shiftKey ? 100 : 40;
      camera.x += e.key === 'ArrowLeft' ? d : e.key === 'ArrowRight' ? -d : 0;
      camera.y += e.key === 'ArrowUp' ? d : e.key === 'ArrowDown' ? -d : 0;
      report();
    }
  });
  on(document, 'visibilitychange', () => {
    if (document.hidden) {
      reveal = null;
      cancelAnimationFrame(raf);
      raf = 0;
      if (transition) {
        camera = { ...transition.to };
        finishTransition(true, 'immediate');
      }
    } else invalidate();
  });
  on(reduced, 'change', () => {
    if (reduced.matches) {
      motion = false;
      reveal = null;
      if (transition) {
        camera = { ...transition.to };
        finishTransition(true, 'immediate');
      }
    }
    hooks.motion?.(motion, reduced.matches);
    report();
  });
  resize();
  return {
    set(next, newMode, newLens, { reset = false, reveal: shouldReveal = false } = {}) {
      cameras.set(viewKey(), { camera: { ...camera }, fitScale, fitMode });
      const changed = mode !== newMode || lens !== newLens;
      mode = newMode;
      lens = newLens;
      data = next;
      fieldPaintOrder = [...(data.nodes || [])].sort(
        (a, b) => nodeDepth(a) - nodeDepth(b) || a.id.localeCompare(b.id),
      );
      reveal = null;
      focused = null;
      if (shouldReveal && mode === 'field' && motion && !reduced.matches && !document.hidden) {
        const ordered = [...(data.nodes || [])].sort((a, b) => a.id.localeCompare(b.id));
        if (ordered.length)
          reveal = {
            start: performance.now(),
            duration: 1350,
            ranks: new Map(ordered.map((node, rank) => [node.id, rank])),
            maximum: ordered.reduce(
              (largest, node) =>
                Math.max(largest, Number.isFinite(node.revealRank) ? node.revealRank : 0),
              Math.max(1, ordered.length - 1),
            ),
          };
      }
      locationClusters = createLocationClusterer(data.nodes || []);
      finishTransition(false, 'view-changed');
      hover = null;
      expanded = null;
      if (reset || !cameras.has(viewKey())) fit(mode === 'atlas' && jurisdiction.length > 0);
      else if (changed) {
        const saved = cameras.get(viewKey());
        camera = { ...saved.camera };
        fitScale = saved.fitScale;
        fitMode = saved.fitMode || null;
      }
      report();
    },
    geometry(value) {
      geo = { ...value, states: geographicStates(value) };
      regionBounds = jurisdictionBounds(geo.states, jurisdiction);
      if (mode === 'atlas' && fitMode === 'region') fit(true);
      invalidate();
    },
    jurisdiction(value) {
      const codes = [...new Set(value?.states || [])].sort();
      if (codes.join('|') === jurisdiction.join('|')) return;
      jurisdiction = codes;
      regionBounds = jurisdictionBounds(geo?.states || [], jurisdiction);
      for (const key of cameras.keys()) if (key.startsWith('atlas:')) cameras.delete(key);
      if (mode === 'atlas') fit(jurisdiction.length > 0);
      invalidate();
    },
    select(id) {
      selected = id;
      if (!id) {
        selectedObservation = null;
        focused = null;
      }
      invalidate();
    },
    selectObservation(id, { focus: shouldFocus = false } = {}) {
      selectedObservation = id;
      const nodes = membershipForObservation(data, id),
        n = nodes.find((n) => n.type === 'asset') || nodes[0];
      selected = n?.id || null;
      if (shouldFocus && n) {
        if (mode === 'field') focus(n.id, 3.05, { sources: true });
        else if (mode === 'atlas') {
          fitMode = null;
          const k = Math.max(camera.k, fitScale * 1.7);
          go({ k, x: width / 2 - n.x * k, y: height * 0.45 - n.y * k });
        } else invalidate();
      }
      root.dataset.selectedSource = id || '';
      invalidate();
      return !!n;
    },
    focus,
    position(id) {
      const node = (data.nodes || []).find((item) => item.id === id);
      if (!node || !width || !height || !Number.isFinite(node.x) || !Number.isFinite(node.y))
        return null;
      const p = screen(node);
      return { x: clamp((p.x / width) * 2 - 1, -1, 1), y: clamp((p.y / height) * 2 - 1, -1, 1) };
    },
    captureView() {
      return {
        mode,
        lens,
        camera: { ...camera },
        fitScale,
        fitMode,
        selected,
        selectedObservation,
        width,
        height,
      };
    },
    restoreView(value) {
      if (
        !value ||
        value.mode !== mode ||
        value.lens !== lens ||
        !['x', 'y', 'k'].every((k) => Number.isFinite(value.camera?.[k])) ||
        value.camera.k <= 0
      )
        return false;
      finishTransition(false, 'restored');
      focused = null;
      camera = {
        ...value.camera,
        x: value.camera.x + (width - (value.width || width)) / 2,
        y: value.camera.y + (height - (value.height || height)) / 2,
      };
      fitScale = value.fitScale > 0 ? value.fitScale : fitScale;
      fitMode = ['data', 'region'].includes(value.fitMode) ? value.fitMode : null;
      selected = value.selected || null;
      selectedObservation = value.selectedObservation || null;
      report();
      return true;
    },
    approach(id, { onComplete } = {}) {
      if (!alive || !(data.nodes || []).some((n) => n.id === id))
        return Promise.resolve({ completed: false, reason: 'unavailable' });
      selected = id;
      return new Promise((resolve) => {
        focus(id, Math.max(2.75, camera.k / fitScale), {
          duration: mode === 'field' ? 720 : 420,
          onComplete,
          onSettled: resolve,
        });
      });
    },
    cancelApproach() {
      focused = null;
      finishTransition(false, 'cancelled');
      report();
    },
    fit: (region = false) => fit(region, true),
    zoom: (factor) => zoom(factor, width / 2, height / 2, true),
    level: setLevel,
    motion(value) {
      motion = !!value && !reduced.matches;
      if (!motion) reveal = null;
      if (!motion && transition) {
        camera = { ...transition.to };
        finishTransition(true, 'immediate');
        report();
      }
      hooks.motion?.(motion, reduced.matches);
      invalidate();
      return motion;
    },
    destroy() {
      alive = false;
      reveal = null;
      focused = null;
      if (atmosphereCache) {
        atmosphereCache.canvas.width = 0;
        atmosphereCache.canvas.height = 0;
        atmosphereCache = null;
      }
      controller.abort();
      observer.disconnect();
      cancelAnimationFrame(raf);
      locationClusters = createLocationClusterer([]);
      finishTransition(false, 'destroyed');
    },
    snapshot() {
      return {
        mode,
        lens,
        nodes: data.nodes.length,
        level: semanticLevel(detailRatio()),
        motion,
        animated: !!transition || !!reveal,
        revealing: !!reveal,
      };
    },
  };
}
