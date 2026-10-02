(function () {
  const canvas = document.getElementById("crmMaterialStage");
  if (!canvas) return;

  const gl = canvas.getContext("webgl", {
    alpha: true,
    antialias: false,
    depth: false,
    stencil: false,
    premultipliedAlpha: true,
    preserveDrawingBuffer: false,
  });

  if (!gl) {
    canvas.hidden = true;
    return;
  }

  const maxRects = 160;
  const vertexSource = `
    attribute vec2 aPosition;
    void main() {
      gl_Position = vec4(aPosition, 0.0, 1.0);
    }
  `;

  const fragmentSource = `
    precision highp float;
    #define MAX_RECTS ${maxRects}

    uniform vec2 uResolution;
    uniform vec2 uPointer;
    uniform float uTime;
    uniform int uRectCount;
    uniform vec4 uRects[MAX_RECTS];
    uniform vec4 uMeta[MAX_RECTS];

    float hash(vec2 p) {
      p = fract(p * vec2(123.34, 456.21));
      p += dot(p, p + 45.32);
      return fract(p.x * p.y);
    }

    float noise(vec2 p) {
      vec2 i = floor(p);
      vec2 f = fract(p);
      float a = hash(i);
      float b = hash(i + vec2(1.0, 0.0));
      float c = hash(i + vec2(0.0, 1.0));
      float d = hash(i + vec2(1.0, 1.0));
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
    }

    float roundedRectSdf(vec2 p, vec2 center, vec2 halfSize, float radius) {
      vec2 q = abs(p - center) - halfSize + radius;
      return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
    }

    vec3 accentColor(float accent) {
      if (accent < 0.5) return vec3(0.98, 0.99, 1.0);
      if (accent < 1.5) return vec3(0.93, 0.96, 1.0);
      if (accent < 2.5) return vec3(0.91, 0.985, 0.97);
      if (accent < 3.5) return vec3(1.0, 0.955, 0.875);
      if (accent < 4.5) return vec3(1.0, 0.91, 0.91);
      if (accent < 5.5) return vec3(0.08, 0.095, 0.13);
      if (accent < 6.5) return vec3(0.86, 1.0, 0.20);
      if (accent < 7.5) return vec3(0.90, 1.0, 0.48);
      if (accent < 8.5) return vec3(0.14, 0.72, 0.64);
      if (accent < 9.5) return vec3(1.0, 0.84, 0.56);
      if (accent < 10.5) return vec3(1.0, 0.66, 0.66);
      if (accent < 11.5) return vec3(0.58, 0.78, 0.96);
      if (accent < 12.5) return vec3(0.99, 0.91, 0.72);
      if (accent < 13.5) return vec3(0.14, 0.70, 0.64);
      if (accent < 14.5) return vec3(0.84, 0.98, 0.93);
      return vec3(0.985, 0.992, 1.0);
    }

    void main() {
      vec2 frag = gl_FragCoord.xy;
      vec2 topSpace = vec2(frag.x, uResolution.y - frag.y);
      vec2 uv = topSpace / max(uResolution, vec2(1.0));
      vec2 pointer = uPointer / max(uResolution, vec2(1.0));

      float paperNoise = noise(topSpace * 0.82 + uTime * 10.0) - 0.5;
      float slowCloud = noise(uv * 3.3 + vec2(uTime * 0.018, -uTime * 0.015));
      float pointerGlow = 1.0 - smoothstep(0.0, 0.58, distance(uv, pointer));
      float upperGlow = 1.0 - smoothstep(0.0, 0.70, distance(uv, vec2(0.55, 0.04)));
      float limeField = 1.0 - smoothstep(0.0, 0.72, distance(uv, vec2(0.50, 0.16)));
      float warmField = 1.0 - smoothstep(0.0, 0.78, distance(uv, vec2(0.34, 0.76)));
      float mintField = 1.0 - smoothstep(0.0, 0.72, distance(uv, vec2(0.90, 0.63)));
      float leftWarm = 1.0 - smoothstep(0.0, 0.95, distance(uv, vec2(0.08, 0.22)));
      float rightCool = 1.0 - smoothstep(0.0, 0.90, distance(uv, vec2(0.92, 0.60)));

      vec3 color = vec3(0.650, 0.660, 0.675);
      color += vec3(0.110, 0.135, -0.020) * limeField;
      color += vec3(0.110, 0.030, 0.035) * warmField;
      color += vec3(-0.010, 0.105, 0.090) * mintField;
      color += vec3(0.030, 0.026, 0.022) * leftWarm;
      color += vec3(0.020, 0.032, 0.040) * rightCool;
      color += vec3(0.030, 0.040, 0.010) * upperGlow;
      color += vec3(0.030, 0.038, 0.052) * pointerGlow;
      color += (slowCloud - 0.5) * vec3(0.026, 0.024, 0.024);
      color += paperNoise * 0.010;

      for (int i = 0; i < MAX_RECTS; i++) {
        if (i < uRectCount) {
          vec4 rect = uRects[i];
          vec4 meta = uMeta[i];
          float kind = meta.x;
          float accent = meta.y;
          float alpha = meta.z;
          float selected = meta.w;

          vec2 center = rect.xy + rect.zw * 0.5;
          vec2 halfSize = max(rect.zw * 0.5, vec2(1.0));
          float baseRadius = mix(18.0, 40.0, clamp(rect.w / 250.0, 0.0, 1.0));
          if (kind > 3.5 && kind < 4.5) baseRadius = min(rect.w, rect.z) * 0.48;
          if (kind > 4.5 && kind < 5.5) baseRadius = min(rect.w, rect.z) * 0.48;
          if (kind > 5.5 && kind < 6.5) baseRadius = min(rect.w, rect.z) * 0.48;
          if (kind > 6.5 && kind < 7.5) baseRadius = 0.0;
          float d = roundedRectSdf(topSpace, center, halfSize, baseRadius);
          float inside = 1.0 - smoothstep(-1.1, 1.1, d);
          float edge = 1.0 - smoothstep(0.0, 1.65, abs(d));
          float softShadow = 1.0 - smoothstep(0.0, mix(22.0, 82.0, clamp(rect.w / 900.0, 0.0, 1.0)), max(d, 0.0));
          float contact = 1.0 - smoothstep(0.0, 18.0, max(d, 0.0));
          float innerTop = (1.0 - smoothstep(0.0, max(rect.w, 1.0) * 0.62, topSpace.y - rect.y)) * inside;
          float localNoise = noise((topSpace - rect.xy) * 0.34 + uTime * 4.0) - 0.5;

          vec3 fill = accentColor(accent);
          float fillMix = 0.0;
          float borderPower = 0.0;
          float shadowPower = 0.0;

          if (kind < 1.5) {
            fillMix = 0.72 * alpha;
            borderPower = 0.12;
            shadowPower = 0.030;
          } else if (kind < 2.5) {
            fillMix = 0.80 * alpha;
            borderPower = 0.18;
            shadowPower = 0.045;
          } else if (kind < 3.5) {
            fillMix = 0.92 * alpha;
            borderPower = 0.24;
            shadowPower = 0.055;
          } else if (kind < 4.5) {
            fillMix = 0.86 * alpha;
            borderPower = 0.18;
            shadowPower = 0.018;
          } else if (kind < 5.5) {
            fillMix = 0.96 * alpha;
            borderPower = 0.16;
            shadowPower = 0.020;
          } else if (kind < 6.5) {
            fillMix = 1.0;
            borderPower = 0.22;
            shadowPower = 0.055;
          } else if (kind < 6.5) {
            fillMix = 0.62 * alpha;
            borderPower = 0.10;
            shadowPower = 0.020;
          } else {
            fillMix = 0.28 * alpha;
            borderPower = 0.0;
            shadowPower = 0.0;
          }

          color -= vec3(0.16, 0.17, 0.19) * softShadow * shadowPower;
          color -= vec3(0.08, 0.09, 0.11) * contact * shadowPower;
          color = mix(color, fill + localNoise * 0.020, inside * fillMix);
          color += vec3(1.0) * edge * borderPower;
          color += vec3(1.0, 1.0, 1.0) * innerTop * 0.028;
          color += vec3(0.13, 0.32, 0.78) * selected * edge * 0.22;
          color += vec3(0.08, 0.18, 0.44) * selected * inside * 0.026;

          if (kind > 2.5 && kind < 3.5 && accent > 6.5) {
            float nodeLeft = 1.0 - smoothstep(5.0, 7.5, length(topSpace - vec2(rect.x, center.y)));
            float nodeRight = 1.0 - smoothstep(5.0, 7.5, length(topSpace - vec2(rect.x + rect.z, center.y)));
            float node = max(nodeLeft, nodeRight);
            color = mix(color, vec3(0.58, 0.70, 0.93), node * 0.72);
            color += vec3(1.0) * node * 0.18;
          }
        }
      }

      color = clamp(color, 0.0, 1.0);
      gl_FragColor = vec4(color, 1.0);
    }
  `;

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const message = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error(message || "Shader compile failed");
    }
    return shader;
  }

  function createProgram() {
    const program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "Program link failed");
    }
    return program;
  }

  let program;
  try {
    program = createProgram();
  } catch (error) {
    console.warn("CRM material WebGL disabled:", error);
    canvas.hidden = true;
    return;
  }

  const positionBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
    -1, -1,
     1, -1,
    -1,  1,
    -1,  1,
     1, -1,
     1,  1,
  ]), gl.STATIC_DRAW);

  const locations = {
    position: gl.getAttribLocation(program, "aPosition"),
    resolution: gl.getUniformLocation(program, "uResolution"),
    pointer: gl.getUniformLocation(program, "uPointer"),
    time: gl.getUniformLocation(program, "uTime"),
    rectCount: gl.getUniformLocation(program, "uRectCount"),
    rects: gl.getUniformLocation(program, "uRects[0]"),
    meta: gl.getUniformLocation(program, "uMeta[0]"),
  };

  const rectData = new Float32Array(maxRects * 4);
  const metaData = new Float32Array(maxRects * 4);
  const scaledRectData = new Float32Array(maxRects * 4);
  const pointer = { x: window.innerWidth * 0.62, y: window.innerHeight * 0.28 };
  let rectCount = 0;
  let lastRectScan = 0;
  let lastRender = 0;
  let interactionUntil = 0;
  let dirtyRects = true;
  let currentDpr = 1;

  const layerQueries = [
    [".workbench-shell", 1, 0, 0.98],
    [".topbar", 1, 0, 0.82],
    [".command-center.journey-board", 1, 0, 0.86],
    [".performance-strip", 1, 0, 0.78],
    [".performance-kpi", 3, 1, 0.86],
    [".performance-signed-item", 3, 0, 0.84],
    [".sales-flow-chip", 3, 0, 0.86],
    [".sales-flow-chip.teal", 3, 2, 0.88],
    [".sales-flow-chip.amber", 3, 3, 0.88],
    [".sales-flow-chip.danger", 3, 4, 0.88],
    [".panel", 1, 0, 0.78],
    [".panel-loop-empty", 1, 0, 0.80],
    [".panel-lifecycle", 1, 0, 0.80],
    [".queue-group", 2, 0, 0.82],
    [".queue-focus", 2, 1, 0.84],
    [".queue-todo", 2, 0, 0.84],
    [".queue-feedback", 2, 2, 0.84],
    [".queue-overdue", 2, 4, 0.84],
    [".queue-group-head em", 4, 0, 0.86],
    [".priority-card.sales-flow-row", 3, 7, 0.88],
    [".priority-card.sales-flow-row.is-selected", 3, 7, 0.94],
    [".queue-priority", 4, 0, 0.88],
    [".flow-row-state > span:not(.queue-priority)", 4, 0, 0.72],
    [".priority-p0", 4, 4, 0.90],
    [".priority-p1", 4, 3, 0.90],
    [".priority-p2", 4, 2, 0.90],
    [".priority-done", 4, 2, 0.90],
    [".flow-row-cta", 4, 1, 0.86],
    [".loop-empty-head", 2, 0, 0.82],
    [".loop-step", 3, 0, 0.84],
    [".lifecycle-empty", 2, 0, 0.82],
    [".lifecycle-current", 2, 1, 0.86],
    [".lifecycle-node", 3, 0, 0.84],
    [".mode-toggle", 4, 0, 0.70],
    [".mode-toggle-button.is-active", 5, 5, 1.0],
    [".topbar-tab", 4, 0, 0.42],
    [".topbar-tab.is-active", 5, 5, 1.0],
    [".global-workspace-head", 1, 14, 0.88],
    [".global-workspace-head > strong", 4, 7, 0.82],
    [".global-panel", 3, 0, 0.84],
    [".global-snapshot-hero", 3, 14, 0.86],
    [".global-record-card", 3, 0, 0.86],
    [".global-record-card:hover", 3, 7, 0.90],
    [".global-metric-grid .micro-row", 3, 0, 0.78],
    [".journey-status-tabs", 4, 0, 0.48],
    [".journey-status-tabs .is-active", 5, 5, 1.0],
    [".button-primary", 5, 5, 1.0],
    [".nav-item", 4, 0, 0.30],
    [".nav-item.is-active", 5, 6, 1.0],
    [".sidebar-panel", 1, 0, 0.55],
    [".active-customer", 4, 0, 0.56],
    [".stat-card", 3, 0, 0.84],
    [".quick-jumps", 1, 0, 0.68],
    [".focus-context", 2, 0, 0.78],
    [".evidence-form", 2, 0, 0.78],
    [".focus-section", 3, 0, 0.80],
    [".latest-receipt", 2, 2, 0.80],
    [".tool-window", 1, 0, 0.88],
    [".tool-head", 2, 0, 0.78],
    [".tool-card", 2, 0, 0.82],
    [".tool-metric-row div", 3, 0, 0.84],
    [".manual-target-row span", 4, 0, 0.68],
    [".manual-target-row input:checked + span", 5, 7, 0.92],
    [".tool-status-line span", 4, 0, 0.62],
    [".prospect-rule-row span", 4, 0, 0.62],
    [".prospect-step", 4, 0, 0.66],
    [".prospect-lead", 3, 7, 0.88],
    [".prospect-reasons span", 2, 0, 0.55],
    [".prospect-decision-button", 4, 0, 0.72],
    [".prospect-decision-button.primary", 4, 1, 0.82],
    [".prospect-decision-done", 4, 2, 0.76],
    [".news-customer-button", 4, 0, 0.62],
    [".news-customer-button.is-active", 5, 5, 1.0],
    [".news-signal", 3, 0, 0.82],
    [".tool-close", 4, 0, 0.62],
    [".tool-mini-button", 4, 1, 0.72],
    [".global-route-filter button", 4, 0, 0.62],
    [".global-route-filter button.is-active", 5, 14, 0.96],
    [".global-route-group", 3, 14, 0.82],
    [".global-route-meta .micro-row", 3, 0, 0.74],
    [".global-route-record", 3, 0, 0.78],
    [".global-route-signal-grid div", 2, 0, 0.60],
    [".accelerator-workbench", 1, 0, 0.72],
    [".accelerator-list", 1, 0, 0.86],
    [".accelerator-main", 1, 0, 0.76],
    [".accelerator-customer-head", 1, 7, 0.88],
    [".accelerator-workbench.is-customer-path-mode .accelerator-customer-head", 1, 14, 0.90],
    [".accelerator-workbench.is-customer-path-mode .accelerator-detail", 1, 14, 0.86],
    [".accelerator-workbench.is-readonly-mode .accelerator-customer-head", 1, 0, 0.82],
    [".accelerator-process", 2, 13, 0.76],
    [".accelerator-detail", 1, 14, 0.84],
    [".accelerator-panel-head", 2, 0, 0.70],
    [".accelerator-queue-item", 3, 0, 0.88],
    [".accelerator-queue-item.is-selected", 3, 7, 0.96],
    [".accelerator-avatar", 4, 6, 0.96],
    [".accelerator-state-dot", 4, 6, 0.92],
    [".accelerator-queue-score", 4, 9, 0.92],
    [".accelerator-queue-item.is-selected .accelerator-queue-score", 5, 5, 1.0],
    [".accelerator-filter", 4, 0, 0.58],
    [".accelerator-filter.is-active", 5, 5, 1.0],
    [".accelerator-add-todo", 4, 7, 0.78],
    [".accelerator-tab", 4, 0, 0.58],
    [".accelerator-tab.is-active", 5, 5, 1.0],
    [".accelerator-pill", 4, 0, 0.68],
    [".accelerator-pill.is-lime", 4, 6, 0.88],
    [".accelerator-process-pill", 4, 0, 0.76],
    [".accelerator-process-pill.is-label", 4, 8, 0.92],
    [".accelerator-process-pill.is-pending", 4, 0, 0.70],
    [".accelerator-process-pill.is-waiting", 4, 3, 0.88],
    [".accelerator-process-pill.is-done", 4, 8, 0.90],
    [".accelerator-process-pill.is-active", 4, 7, 0.94],
    [".accelerator-process-pill.is-readonly", 4, 14, 0.82],
    [".accelerator-process-pill em", 4, 0, 0.86],
    [".accelerator-capsule", 3, 0, 0.86],
    [".accelerator-capsule.is-state-neutral", 3, 0, 0.84],
    [".accelerator-capsule.is-state-readonly", 3, 14, 0.82],
    [".accelerator-capsule.is-state-waiting", 3, 3, 0.88],
    [".accelerator-capsule.is-state-current", 3, 7, 0.92],
    [".accelerator-capsule.is-state-done", 3, 8, 0.90],
    [".accelerator-capsule.is-active", 3, 0, 0.92],
    [".accelerator-capsule .accelerator-avatar", 4, 6, 0.92],
    [".accelerator-capsule.is-state-readonly .accelerator-avatar", 4, 14, 0.86],
    [".accelerator-capsule.is-state-waiting .accelerator-avatar", 4, 9, 0.90],
    [".accelerator-capsule.is-state-done .accelerator-avatar", 4, 8, 0.92],
    [".accelerator-drop", 2, 0, 0.80],
    [".accelerator-card", 3, 0, 0.84],
    [".accelerator-path-lane", 3, 0, 0.80],
    [".accelerator-path-workline", 3, 7, 0.82],
    [".accelerator-path-knowledge", 3, 14, 0.80],
    [".accelerator-workflow-line", 3, 0, 0.82],
    [".accelerator-workflow-line.is-current", 3, 7, 0.90],
    [".accelerator-workflow-line.is-waiting", 3, 9, 0.86],
    [".accelerator-workflow-line.is-done", 3, 14, 0.84],
    [".accelerator-workflow-line.is-overdue", 3, 4, 0.86],
    [".accelerator-route-filter button", 4, 0, 0.62],
    [".accelerator-route-filter button.is-active", 5, 5, 0.96],
    [".knowledge-direction-group", 3, 14, 0.84],
    [".knowledge-topic-record", 3, 0, 0.78],
    [".knowledge-topic-action", 3, 7, 0.72],
    [".accelerator-mini-card", 3, 0, 0.82],
    [".accelerator-status-chip", 4, 0, 0.70],
    [".accelerator-result-choice", 4, 0, 0.70],
    [".accelerator-result-choice.is-active", 5, 5, 1.0],
    [".accelerator-submit", 5, 5, 1.0],
    [".accelerator-dock-state span", 4, 7, 0.82],
  ];

  function materialDpr() {
    const raw = window.devicePixelRatio || 1;
    const area = window.innerWidth * window.innerHeight;
    const cap = area > 1600000 ? 1.1 : area > 1100000 ? 1.2 : 1.35;
    return Math.min(raw, cap);
  }

  function markDirty(activeMs = 700) {
    dirtyRects = true;
    interactionUntil = Math.max(interactionUntil, performance.now() + activeMs);
  }

  function resize(dpr = materialDpr()) {
    const width = Math.max(1, Math.floor(window.innerWidth * dpr));
    const height = Math.max(1, Math.floor(window.innerHeight * dpr));
    if (canvas.width !== width || canvas.height !== height || currentDpr !== dpr) {
      currentDpr = dpr;
      canvas.width = width;
      canvas.height = height;
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      gl.viewport(0, 0, width, height);
      dirtyRects = true;
    }
  }

  function visibleRect(rect) {
    if (rect.width < 14 || rect.height < 12) return null;
    if (rect.bottom < -80 || rect.top > window.innerHeight + 80) return null;
    if (rect.right < -80 || rect.left > window.innerWidth + 80) return null;
    const x = Math.max(-90, rect.left);
    const y = Math.max(-90, rect.top);
    const right = Math.min(window.innerWidth + 90, rect.right);
    const bottom = Math.min(window.innerHeight + 90, rect.bottom);
    return { x, y, w: right - x, h: bottom - y, area: rect.width * rect.height };
  }

  function clippedVisibleRect(element) {
    const source = element.getBoundingClientRect();
    let left = source.left;
    let top = source.top;
    let right = source.right;
    let bottom = source.bottom;
    let parent = element.parentElement;
    while (parent && parent !== document.documentElement) {
      const style = window.getComputedStyle(parent);
      const overflow = `${style.overflow}${style.overflowX}${style.overflowY}`;
      if (/(auto|scroll|hidden|clip)/.test(overflow)) {
        const clip = parent.getBoundingClientRect();
        left = Math.max(left, clip.left);
        top = Math.max(top, clip.top);
        right = Math.min(right, clip.right);
        bottom = Math.min(bottom, clip.bottom);
      }
      parent = parent.parentElement;
    }
    return visibleRect({
      left,
      top,
      right,
      bottom,
      width: Math.max(0, right - left),
      height: Math.max(0, bottom - top),
    });
  }

  function elementSelected(element) {
    return element.classList.contains("is-active") || element.classList.contains("is-selected") ? 1 : 0;
  }

  function scanRects(now) {
    if (!dirtyRects && now - lastRectScan < 260) return;
    lastRectScan = now;
    dirtyRects = false;

    const collected = [];
    const seen = new Map();
    layerQueries.forEach(([selector, kind, accent, alpha]) => {
      document.querySelectorAll(selector).forEach((element) => {
        if (element.hidden || element.getAttribute("aria-hidden") === "true") return;
        if (element.closest("[hidden], [aria-hidden='true'], .focus-tab-panel:not(.is-active)")) return;
        const style = window.getComputedStyle(element);
        if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return;
        const rect = clippedVisibleRect(element);
        if (!rect) return;
        const key = `${Math.round(rect.x)}:${Math.round(rect.y)}:${Math.round(rect.w)}:${Math.round(rect.h)}`;
        const selected = elementSelected(element);
        const priority = kind * 100 + accent * 10 + selected;
        const previous = seen.get(key);
        if (previous && previous.priority >= priority) return;
        const item = { ...rect, kind, accent, alpha, selected, priority };
        seen.set(key, item);
      });
    });
    seen.forEach((value) => collected.push(value));

    collected.sort((a, b) => {
      const selectedDiff = b.selected - a.selected;
      if (selectedDiff) return selectedDiff;
      return b.area - a.area;
    });

    rectCount = Math.min(maxRects, collected.length);
    rectData.fill(0);
    metaData.fill(0);
    for (let i = 0; i < rectCount; i += 1) {
      const rect = collected[i];
      const offset = i * 4;
      rectData[offset] = rect.x;
      rectData[offset + 1] = rect.y;
      rectData[offset + 2] = rect.w;
      rectData[offset + 3] = rect.h;
      metaData[offset] = rect.kind;
      metaData[offset + 1] = rect.accent;
      metaData[offset + 2] = rect.alpha;
      metaData[offset + 3] = rect.selected;
    }
  }

  function render(now) {
    window.requestAnimationFrame(render);

    const active = dirtyRects || now < interactionUntil;
    const targetInterval = active ? 33 : 120;
    if (now - lastRender < targetInterval && !dirtyRects) return;
    lastRender = now;

    const dpr = materialDpr();
    resize(dpr);
    scanRects(now);

    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.enableVertexAttribArray(locations.position);
    gl.vertexAttribPointer(locations.position, 2, gl.FLOAT, false, 0, 0);
    gl.uniform2f(locations.resolution, canvas.width, canvas.height);
    gl.uniform2f(locations.pointer, pointer.x * dpr, pointer.y * dpr);
    gl.uniform1f(locations.time, now * 0.001);
    gl.uniform1i(locations.rectCount, rectCount);

    for (let i = 0; i < rectCount; i += 1) {
      const offset = i * 4;
      scaledRectData[offset] = rectData[offset] * dpr;
      scaledRectData[offset + 1] = rectData[offset + 1] * dpr;
      scaledRectData[offset + 2] = rectData[offset + 2] * dpr;
      scaledRectData[offset + 3] = rectData[offset + 3] * dpr;
    }
    gl.uniform4fv(locations.rects, scaledRectData);
    gl.uniform4fv(locations.meta, metaData);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }

  window.addEventListener("resize", () => { markDirty(900); }, { passive: true });
  window.addEventListener("scroll", () => { markDirty(900); }, { passive: true });
  document.addEventListener("scroll", () => { markDirty(700); }, { passive: true, capture: true });
  window.addEventListener("pointermove", (event) => {
    pointer.x += (event.clientX - pointer.x) * 0.42;
    pointer.y += (event.clientY - pointer.y) * 0.42;
    interactionUntil = Math.max(interactionUntil, performance.now() + 450);
  }, { passive: true });

  const observer = new MutationObserver(() => { markDirty(700); });
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "hidden", "style"] });

  resize();
  gl.disable(gl.BLEND);
  window.requestAnimationFrame(render);
})();
