const state = {
  demo: null,
  strategy: "fix",
  selected: 1,
  view: "usage",
  customAnalysis: null,
};

const staticDataUrl = document.querySelector('meta[name="sensor-demo-data"]')?.content;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function element(name, attributes = {}, text = "") {
  const node = document.createElement(name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  node.textContent = text;
  return node;
}

function currentRevision() {
  return state.demo.revisions[state.selected];
}

function currentScore() {
  const suffix = state.strategy === "stable" ? "stable_score" : "fix_score";
  return currentRevision()[suffix];
}

function currentPatterns() {
  return state.demo.patterns[state.strategy];
}

function patternKey(pattern) {
  return pattern.kind === "required-guard" ? `guard:${pattern.label}` : `${pattern.from}:${pattern.to}`;
}

function renderTimeline() {
  const timeline = $("#timeline");
  timeline.replaceChildren();
  timeline.style.gridTemplateColumns = `repeat(${state.demo.revisions.length}, 1fr)`;
  state.demo.revisions.forEach((revision, index) => {
    const button = element("button", {
      class: `commit ${index === state.selected ? "active" : ""} ${revision.role === "fix" ? "fixed" : ""}`,
      "aria-label": `Select commit ${revision.id}: ${revision.message}`,
    });
    button.append(
      element("span", { class: "commit-dot" }),
      element("span", { class: "commit-id" }, revision.id),
      element("span", { class: "commit-message" }, revision.message),
      element("span", { class: "commit-date" }, revision.date),
    );
    button.addEventListener("click", () => {
      state.selected = index;
      state.customAnalysis = null;
      $("#source-editor").value = revision.source;
      render();
    });
    timeline.append(button);
  });
}

function renderSummary() {
  const revision = currentRevision();
  const analysis = state.customAnalysis?.analysis || revision.analysis;
  const score = state.customAnalysis?.score || currentScore();
  const riskCard = $("#risk-card");
  riskCard.classList.toggle("safe", score.risk === 0);
  $("#risk-score").textContent = score.risk;
  $("#risk-label").textContent = score.risk >= 70 ? "Required guard missing" : score.risk > 0 ? "Pattern mismatch" : "No missing patterns";
  $("#risk-dial").style.setProperty("--risk-angle", `${score.risk * 3.6}deg`);
  $("#call-count").textContent = analysis.calls.length;
  $("#pattern-count").textContent = currentPatterns().length;
  $("#graph-count").textContent = analysis.graph.nodes.length + analysis.graph.edges.length;
}

function nodePosition(node, index, total) {
  if (node.kind === "data") {
    return { x: 125 + (index * 650) / Math.max(total - 1, 1), y: 285 };
  }
  const y = node.kind === "guard" ? 180 : 92;
  return { x: 95 + (index * 710) / Math.max(total - 1, 1), y };
}

function svgNode(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function renderGraph() {
  const revision = currentRevision();
  const analysis = state.customAnalysis?.analysis || revision.analysis;
  const isChange = state.view === "change";
  const graph = isChange ? state.demo.change_graph : analysis.graph;
  const nodes = graph.nodes;
  const eventNodes = nodes.filter((node) => node.kind !== "data");
  const dataNodes = nodes.filter((node) => node.kind === "data");
  const positions = new Map();
  eventNodes.forEach((node, index) => positions.set(node.id, nodePosition(node, index, eventNodes.length)));
  dataNodes.forEach((node, index) => positions.set(node.id, nodePosition(node, index, dataNodes.length)));

  const svg = $("#graph-svg");
  svg.replaceChildren();
  const defs = svgNode("defs");
  const marker = svgNode("marker", { id: "arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse" });
  marker.append(svgNode("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#9aa9a4" }));
  defs.append(marker);
  svg.append(defs);

  graph.edges.forEach((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return;
    const path = svgNode("path", {
      d: `M ${from.x} ${from.y + 18} C ${from.x} ${from.y + 80}, ${to.x} ${to.y - 80}, ${to.x} ${to.y - 18}`,
      class: `graph-edge ${edge.kind !== "control" ? "data-edge" : ""}`,
      "marker-end": "url(#arrow)",
    });
    svg.append(path);
  });

  nodes.forEach((node) => {
    const position = positions.get(node.id);
    const group = svgNode("g", { class: `graph-node ${node.kind} ${node.status || ""}` });
    if (node.kind === "data") {
      group.append(svgNode("circle", { cx: position.x, cy: position.y, r: "24" }));
    } else {
      group.append(svgNode("rect", { x: position.x - 56, y: position.y - 22, width: "112", height: "44", rx: "5" }));
    }
    const label = svgNode("text", { x: position.x, y: position.y + 3, class: "graph-label" });
    label.textContent = node.label.length > 15 ? `${node.label.slice(0, 13)}…` : node.label;
    const type = svgNode("text", { x: position.x, y: position.y + (node.kind === "data" ? 40 : 38), class: "graph-type" });
    type.textContent = node.status && node.status !== "unchanged" ? `${node.kind} · ${node.status}` : node.kind;
    group.append(label, type);
    svg.append(group);
  });

  $("#graph-kicker").textContent = isChange ? "Change graph · fe8f65b → e9ea0b3" : "API usage graph";
  $("#graph-title").textContent = isChange ? "+ range guard prevents overflow" : "gnttab_dma_alloc_pages()";
}

function renderFinding() {
  const score = state.customAnalysis?.score || currentScore();
  const body = $("#finding-body");
  body.replaceChildren();
  const finding = score.findings[0];
  const safe = !finding;
  $("#severity").textContent = safe ? "Clear" : finding.severity;
  $("#severity").classList.toggle("none", safe);
  $("#finding-heading").textContent = safe ? "Assessment" : "Finding";
  body.append(
    element("div", { class: `finding-icon ${safe ? "safe" : ""}` }, safe ? "✓" : "!"),
    element("h4", {}, safe ? "Usage matches history" : finding.title),
    element("p", {}, safe ? "No mined regularity is missing from this revision. The result is evidence of consistency, not proof of correctness." : finding.detail),
    element("div", { class: "evidence" }, safe ? "0 missing patterns" : `Expected: ${finding.expected} · support ${Math.round(finding.support * 100)}%`),
  );

  const list = $("#patterns");
  list.replaceChildren();
  const missing = new Set(score.missing_patterns.map(patternKey));
  currentPatterns().forEach((pattern) => {
    const row = element("div", { class: `pattern ${missing.has(patternKey(pattern)) ? "missing" : ""}` });
    const label = pattern.kind === "required-guard" ? pattern.label : `${pattern.from} → ${pattern.to}`;
    row.append(element("code", {}, label), element("b", {}, `${Math.round(pattern.support * 100)}%`));
    list.append(row);
  });
}

function renderView() {
  const sourceMode = state.view === "source";
  $("#graph-stage").hidden = sourceMode;
  $("#source-panel").hidden = !sourceMode;
  $(".legend").hidden = sourceMode;
  if (sourceMode) {
    const revision = currentRevision();
    $("#graph-kicker").textContent = `Pinned kernel source · ${revision.id}`;
    $("#graph-title").textContent = revision.message;
  } else {
    renderGraph();
  }
}

function render() {
  renderTimeline();
  renderSummary();
  renderView();
  renderFinding();
}

async function runCustomAnalysis() {
  const button = $("#run-analysis");
  const error = $("#editor-error");
  button.disabled = true;
  button.textContent = "Analyzing…";
  error.hidden = true;
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: $("#source-editor").value,
        patterns: currentPatterns(),
        profile: state.demo.profile,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Analysis failed");
    state.customAnalysis = payload;
    renderSummary();
    renderFinding();
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.innerHTML = "Run analysis <kbd>⌘↵</kbd>";
  }
}

function bindControls() {
  $$("[data-strategy]").forEach((button) => {
    button.addEventListener("click", () => {
      state.strategy = button.dataset.strategy;
      state.customAnalysis = null;
      $$("[data-strategy]").forEach((item) => item.classList.toggle("active", item === button));
      $("#strategy-help").textContent = state.strategy === "stable"
        ? "Compare ordered API calls with the earlier revisions."
        : "Require the validation guard added by the upstream fix.";
      render();
    });
  });
  $$("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      $$("[data-view]").forEach((item) => item.classList.toggle("active", item === button));
      renderView();
    });
  });
  const runButton = $("#run-analysis");
  if (staticDataUrl) {
    runButton.disabled = true;
    runButton.textContent = "Local server required";
    runButton.title = "Run uv run sensor-lite to analyze edited source.";
    $("#runtime-mode").textContent = "Static dataset";
  } else {
    runButton.addEventListener("click", runCustomAnalysis);
  }
  $("#source-editor").addEventListener("keydown", (event) => {
    if (!staticDataUrl && (event.metaKey || event.ctrlKey) && event.key === "Enter") {
      runCustomAnalysis();
    }
  });
}

async function initialize() {
  bindControls();
  try {
    const response = await fetch(staticDataUrl || "/api/demo");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Unable to load demo");
    state.demo = payload;
    $("#project-name").textContent = payload.project.name;
    $("#window-count").textContent = payload.project.commits;
    $("#source-editor").value = payload.revisions[state.selected].source;
    render();
  } catch (caught) {
    $("#project-name").textContent = "Analysis unavailable";
    $("#finding-body").textContent = caught.message;
  }
}

initialize();
