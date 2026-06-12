const canvas = document.querySelector("#mapCanvas");
const ctx = canvas.getContext("2d");
const previewCanvas = document.querySelector("#previewCanvas");
const previewCtx = previewCanvas.getContext("2d");
const tabsEl = document.querySelector("#tabs");
const statusEl = document.querySelector("#status");
const saveEl = document.querySelector("#save");
const savePreviewsEl = document.querySelector("#savePreviews");
const nodeCountEl = document.querySelector("#nodeCount");
const edgeCountEl = document.querySelector("#edgeCount");
const selectedEl = document.querySelector("#selected");
const modeLabelEl = document.querySelector("#modeLabel");
const editLabelEl = document.querySelector("#editLabel");
const previewLabelEl = document.querySelector("#previewLabel");

const ROW_TOLERANCE = 24;
const HIT_PAD = 10;
const PREVIEW_TITLE_HEIGHT = 86;

const state = {
  maps: [],
  currentMap: "map",
  nodes: [],
  edges: {},
  mode: "move",
  selectedUid: null,
  routeStartUid: null,
  draggingUid: null,
  dragMoved: false,
  dirty: false,
  image: new Image(),
  baseMapImage: new Image(),
};

function setStatus(message) {
  statusEl.textContent = `${state.dirty ? "Unsaved changes. " : ""}${message}`;
}

function currentMapInfo() {
  return state.maps.find((map) => map.key === state.currentMap);
}

function currentEdges() {
  state.edges[state.currentMap] ||= [];
  return state.edges[state.currentMap];
}

function uidNumber(uid) {
  const match = String(uid).match(/\d+/);
  return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER;
}

function edgeKey(source, target) {
  return [source, target].sort((a, b) => uidNumber(a) - uidNumber(b) || String(a).localeCompare(String(b))).join("--");
}

function markDirty(message = "Edited locally.") {
  state.dirty = true;
  setStatus(message);
}

function renumberNodes() {
  const ordered = [...state.nodes].sort((a, b) => {
    const ay = Math.round(a.y / ROW_TOLERANCE);
    const by = Math.round(b.y / ROW_TOLERANCE);
    return ay - by || a.x - b.x || uidNumber(a.uid) - uidNumber(b.uid);
  });

  ordered.forEach((node, index) => {
    node.id = index + 1;
  });
  state.nodes.sort((a, b) => a.id - b.id);
}

function makeNode(x, y) {
  return {
    uid: `u${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
    id: state.nodes.length + 1,
    x: Math.round(x),
    y: Math.round(y),
    r: 12,
  };
}

function loadImageForCurrentMap() {
  const map = currentMapInfo();
  if (!map) return;
  state.image = new Image();
  state.image.onload = () => {
    canvas.width = state.image.naturalWidth;
    canvas.height = state.image.naturalHeight;
    render();
  };
  state.image.src = map.imageUrl;
}

function loadBaseMapImage() {
  const map = state.maps.find((item) => item.key === "map");
  if (!map) return;
  state.baseMapImage = new Image();
  state.baseMapImage.onload = () => {
    previewCanvas.width = state.baseMapImage.naturalWidth;
    previewCanvas.height = state.baseMapImage.naturalHeight + PREVIEW_TITLE_HEIGHT;
    renderPreview();
  };
  state.baseMapImage.src = map.imageUrl;
}

function renderTabs() {
  tabsEl.innerHTML = "";
  for (const map of state.maps) {
    const button = document.createElement("button");
    button.textContent = `${map.label}`;
    button.style.borderLeft = `0.45rem solid ${map.color}`;
    button.classList.toggle("active", map.key === state.currentMap);
    button.addEventListener("click", () => {
      state.currentMap = map.key;
      state.routeStartUid = null;
      renderTabs();
      loadImageForCurrentMap();
      renderPreview();
      updateFacts();
      setStatus(`Showing ${map.label}.`);
    });
    tabsEl.append(button);
  }
}

function renderModeButtons() {
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      state.routeStartUid = null;
      document.querySelectorAll("[data-mode]").forEach((item) => item.classList.toggle("active", item === button));
      modeLabelEl.textContent = button.textContent;
      render();
      setStatus(`${button.textContent} mode.`);
    });
  });
}

function updateFacts() {
  const selected = state.nodes.find((node) => node.uid === state.selectedUid);
  const map = currentMapInfo();
  nodeCountEl.textContent = state.nodes.length;
  edgeCountEl.textContent = currentEdges().length;
  selectedEl.textContent = selected ? `#${selected.id}` : "none";
  editLabelEl.textContent = map ? map.label : "current map";
  previewLabelEl.textContent = map ? `${map.label} on Map.png` : "transport routes";
}

function drawLine(targetCtx, edge, map, yOffset = 0, options = {}) {
  const source = state.nodes.find((node) => node.uid === edge.source);
  const target = state.nodes.find((node) => node.uid === edge.target);
  if (!source || !target) return;
  targetCtx.save();
  targetCtx.lineCap = "round";
  targetCtx.lineJoin = "round";
  targetCtx.lineWidth = options.width || 7;
  targetCtx.strokeStyle = map.color;
  targetCtx.globalAlpha = options.alpha || 0.82;
  targetCtx.beginPath();
  targetCtx.moveTo(source.x, source.y + yOffset);
  targetCtx.lineTo(target.x, target.y + yOffset);
  targetCtx.stroke();
  targetCtx.globalAlpha = options.innerAlpha || 0.85;
  targetCtx.lineWidth = options.innerWidth || 2;
  targetCtx.strokeStyle = "rgba(255,255,255,0.85)";
  targetCtx.stroke();
  targetCtx.restore();
}

function drawNode(targetCtx, node, map, yOffset = 0, options = {}) {
  const selected = node.uid === state.selectedUid;
  const routeStart = node.uid === state.routeStartUid;
  const radius = Math.max(node.r + 4, String(node.id).length >= 3 ? 17 : 15);
  const x = node.x;
  const y = node.y + yOffset;

  targetCtx.save();
  targetCtx.beginPath();
  targetCtx.arc(x, y, options.radius || radius, 0, Math.PI * 2);
  targetCtx.fillStyle = options.simple ? "#f5e1a6" : selected || routeStart ? "#1f2b22" : "#f5e1a6";
  targetCtx.strokeStyle = options.simple ? "#2a2118" : routeStart ? map.color : "#2a2118";
  targetCtx.lineWidth = options.simple ? 2 : routeStart ? 5 : selected ? 4 : 2;
  targetCtx.fill();
  targetCtx.stroke();

  targetCtx.fillStyle = options.simple || !(selected || routeStart) ? "#191713" : "#fff8e7";
  targetCtx.font = `${String(node.id).length >= 3 ? 14 : 16}px Georgia, serif`;
  targetCtx.textAlign = "center";
  targetCtx.textBaseline = "middle";
  targetCtx.fillText(String(node.id), x, y + 0.5);
  targetCtx.restore();
}

function render() {
  if (!state.image.complete || !state.image.naturalWidth) return;
  const map = currentMapInfo();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(state.image, 0, 0);
  currentEdges().forEach((edge) => drawLine(ctx, edge, map));
  state.nodes.forEach((node) => drawNode(ctx, node, map));
  updateFacts();
  renderPreview();
}

function renderPreview() {
  if (!state.baseMapImage.complete || !state.baseMapImage.naturalWidth) return;
  const map = currentMapInfo();
  if (!map) return;

  previewCanvas.width = state.baseMapImage.naturalWidth;
  previewCanvas.height = state.baseMapImage.naturalHeight + PREVIEW_TITLE_HEIGHT;
  previewCtx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
  previewCtx.fillStyle = "#f2e7ce";
  previewCtx.fillRect(0, 0, previewCanvas.width, PREVIEW_TITLE_HEIGHT);
  previewCtx.drawImage(state.baseMapImage, 0, PREVIEW_TITLE_HEIGHT);

  currentEdges().forEach((edge) =>
    drawLine(previewCtx, edge, map, PREVIEW_TITLE_HEIGHT, {
      width: 9,
      innerWidth: 2,
      alpha: 0.78,
      innerAlpha: 0.9,
    }),
  );
  state.nodes.forEach((node) =>
    drawNode(previewCtx, node, map, PREVIEW_TITLE_HEIGHT, {
      simple: true,
      radius: Math.max(node.r + 2, 13),
    }),
  );

  previewCtx.fillStyle = "#f2e7ce";
  previewCtx.fillRect(0, 0, previewCanvas.width, PREVIEW_TITLE_HEIGHT);
  previewCtx.strokeStyle = map.color;
  previewCtx.lineWidth = 5;
  previewCtx.beginPath();
  previewCtx.moveTo(0, PREVIEW_TITLE_HEIGHT - 2);
  previewCtx.lineTo(previewCanvas.width, PREVIEW_TITLE_HEIGHT - 2);
  previewCtx.stroke();

  previewCtx.fillStyle = "#1e1c17";
  previewCtx.font = "700 36px Georgia, serif";
  previewCtx.textAlign = "left";
  previewCtx.textBaseline = "alphabetic";
  previewCtx.fillText(`${map.label} Routes`, 34, 45);
  previewCtx.fillStyle = "#5c584a";
  previewCtx.font = "17px Georgia, serif";
  previewCtx.fillText("       ", 36, 69);
  updateFacts();
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) * canvas.width) / rect.width,
    y: ((event.clientY - rect.top) * canvas.height) / rect.height,
  };
}

function findNode(point) {
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const node of state.nodes) {
    const distance = Math.hypot(point.x - node.x, point.y - node.y);
    const hitRadius = Math.max(node.r + HIT_PAD, 18);
    if (distance <= hitRadius && distance < bestDistance) {
      best = node;
      bestDistance = distance;
    }
  }
  return best;
}

function pointToSegmentDistance(point, a, b) {
  const vx = b.x - a.x;
  const vy = b.y - a.y;
  const wx = point.x - a.x;
  const wy = point.y - a.y;
  const lengthSquared = vx * vx + vy * vy;
  if (lengthSquared === 0) return Math.hypot(point.x - a.x, point.y - a.y);
  const t = Math.max(0, Math.min(1, (wx * vx + wy * vy) / lengthSquared));
  return Math.hypot(point.x - (a.x + t * vx), point.y - (a.y + t * vy));
}

function findEdge(point) {
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const edge of currentEdges()) {
    const source = state.nodes.find((node) => node.uid === edge.source);
    const target = state.nodes.find((node) => node.uid === edge.target);
    if (!source || !target) continue;
    const distance = pointToSegmentDistance(point, source, target);
    if (distance < 10 && distance < bestDistance) {
      best = edge;
      bestDistance = distance;
    }
  }
  return best;
}

function addRoute(sourceUid, targetUid) {
  if (!sourceUid || !targetUid || sourceUid === targetUid) return false;
  const key = edgeKey(sourceUid, targetUid);
  if (currentEdges().some((edge) => edgeKey(edge.source, edge.target) === key)) return false;
  const [source, target] = [sourceUid, targetUid].sort((a, b) => uidNumber(a) - uidNumber(b) || String(a).localeCompare(String(b)));
  currentEdges().push({ source, target });
  return true;
}

function removeEdge(edgeToRemove) {
  state.edges[state.currentMap] = currentEdges().filter((edge) => edge !== edgeToRemove);
}

function removeNode(uid) {
  state.nodes = state.nodes.filter((node) => node.uid !== uid);
  for (const key of Object.keys(state.edges)) {
    state.edges[key] = state.edges[key].filter((edge) => edge.source !== uid && edge.target !== uid);
  }
  if (state.selectedUid === uid) state.selectedUid = null;
  if (state.routeStartUid === uid) state.routeStartUid = null;
}

canvas.addEventListener("pointerdown", (event) => {
  const point = canvasPoint(event);
  const node = findNode(point);

  if (state.mode === "add") {
    const added = makeNode(point.x, point.y);
    state.nodes.push(added);
    state.selectedUid = added.uid;
    renumberNodes();
    markDirty(`Added junction #${added.id}.`);
    render();
    return;
  }

  if (state.mode === "route") {
    if (!node) {
      setStatus("Route mode needs a junction click.");
      return;
    }
    state.selectedUid = node.uid;
    if (!state.routeStartUid) {
      state.routeStartUid = node.uid;
      setStatus(`Route start set to #${node.id}. Click the destination junction.`);
    } else if (addRoute(state.routeStartUid, node.uid)) {
      const start = state.nodes.find((item) => item.uid === state.routeStartUid);
      state.routeStartUid = null;
      markDirty(`Added route ${start ? `#${start.id}` : ""} to #${node.id}.`);
    } else {
      state.routeStartUid = null;
      setStatus("That route already exists.");
    }
    render();
    return;
  }

  if (state.mode === "delete") {
    const edge = findEdge(point);
    if (edge) {
      removeEdge(edge);
      markDirty("Deleted route from current map.");
      render();
      return;
    }
    if (node && window.confirm(`Delete junction #${node.id} from all maps? Routes connected to it will also be removed.`)) {
      removeNode(node.uid);
      renumberNodes();
      markDirty("Deleted junction and renumbered.");
      render();
    }
    return;
  }

  if (node) {
    state.selectedUid = node.uid;
    state.draggingUid = node.uid;
    state.dragMoved = false;
    canvas.setPointerCapture(event.pointerId);
    render();
  } else {
    state.selectedUid = null;
    render();
  }
});

canvas.addEventListener("pointermove", (event) => {
  if (!state.draggingUid || state.mode !== "move") return;
  const node = state.nodes.find((item) => item.uid === state.draggingUid);
  if (!node) return;
  const point = canvasPoint(event);
  node.x = Math.round(point.x);
  node.y = Math.round(point.y);
  state.dragMoved = true;
  state.dirty = true;
  render();
});

canvas.addEventListener("pointerup", (event) => {
  if (!state.draggingUid) return;
  const movedUid = state.draggingUid;
  state.draggingUid = null;
  try {
    canvas.releasePointerCapture(event.pointerId);
  } catch {
    // Pointer capture may already be gone if the pointer left the canvas.
  }
  if (state.dragMoved) {
    renumberNodes();
    const moved = state.nodes.find((node) => node.uid === movedUid);
    state.selectedUid = movedUid;
    markDirty(`Moved junction${moved ? ` #${moved.id}` : ""} across all maps.`);
    render();
  }
});

saveEl.addEventListener("click", async () => {
  saveEl.disabled = true;
  setStatus("Saving graph files and labelled images...");
  try {
    renumberNodes();
    const response = await fetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nodes: state.nodes,
        edges: state.edges,
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || "Save failed.");
    }
    state.dirty = false;
    setStatus(`Saved ${result.nodeCount} junctions. Backup: ${result.backup}`);
  } catch (error) {
    setStatus(`Save failed: ${error.message}`);
  } finally {
    saveEl.disabled = false;
    render();
  }
});

savePreviewsEl.addEventListener("click", async () => {
  savePreviewsEl.disabled = true;
  setStatus("Saving bus, taxi, and subway preview images...");
  try {
    renumberNodes();
    const response = await fetch("/api/save-previews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nodes: state.nodes,
        edges: state.edges,
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || "Preview save failed.");
    }
    const files = Object.values(result.saved).join(", ");
    setStatus(`Saved preview images: ${files}. Backup: ${result.backup}`);
  } catch (error) {
    setStatus(`Preview save failed: ${error.message}`);
  } finally {
    savePreviewsEl.disabled = false;
    render();
  }
});

window.addEventListener("beforeunload", (event) => {
  if (!state.dirty) return;
  event.preventDefault();
  event.returnValue = "";
});

async function boot() {
  const response = await fetch("/api/state");
  const data = await response.json();
  state.maps = data.maps;
  state.currentMap = data.master || state.maps[0]?.key || "map";
  state.nodes = data.nodes;
  state.edges = data.edges;
  renumberNodes();
  renderTabs();
  renderModeButtons();
  loadBaseMapImage();
  loadImageForCurrentMap();
  setStatus("Ready. Changes are local until you save.");
}

boot().catch((error) => {
  setStatus(`Could not load editor: ${error.message}`);
});
