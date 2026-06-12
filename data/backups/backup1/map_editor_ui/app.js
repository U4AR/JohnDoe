const canvas = document.querySelector("#mapCanvas");
const ctx = canvas.getContext("2d");
const tabsEl = document.querySelector("#tabs");
const statusEl = document.querySelector("#status");
const saveEl = document.querySelector("#save");
const nodeCountEl = document.querySelector("#nodeCount");
const edgeCountEl = document.querySelector("#edgeCount");
const selectedEl = document.querySelector("#selected");
const modeLabelEl = document.querySelector("#modeLabel");

const ROW_TOLERANCE = 24;
const HIT_PAD = 10;

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
  nodeCountEl.textContent = state.nodes.length;
  edgeCountEl.textContent = currentEdges().length;
  selectedEl.textContent = selected ? `#${selected.id}` : "none";
}

function drawLine(edge, map) {
  const source = state.nodes.find((node) => node.uid === edge.source);
  const target = state.nodes.find((node) => node.uid === edge.target);
  if (!source || !target) return;
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = 7;
  ctx.strokeStyle = map.color;
  ctx.globalAlpha = 0.82;
  ctx.beginPath();
  ctx.moveTo(source.x, source.y);
  ctx.lineTo(target.x, target.y);
  ctx.stroke();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.stroke();
  ctx.restore();
}

function drawNode(node, map) {
  const selected = node.uid === state.selectedUid;
  const routeStart = node.uid === state.routeStartUid;
  const radius = Math.max(node.r + 4, String(node.id).length >= 3 ? 17 : 15);

  ctx.save();
  ctx.beginPath();
  ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
  ctx.fillStyle = selected || routeStart ? "#1f2b22" : "#f5e1a6";
  ctx.strokeStyle = routeStart ? map.color : "#2a2118";
  ctx.lineWidth = routeStart ? 5 : selected ? 4 : 2;
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = selected || routeStart ? "#fff8e7" : "#191713";
  ctx.font = `${String(node.id).length >= 3 ? 14 : 16}px Georgia, serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(node.id), node.x, node.y + 0.5);
  ctx.restore();
}

function render() {
  if (!state.image.complete || !state.image.naturalWidth) return;
  const map = currentMapInfo();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(state.image, 0, 0);
  currentEdges().forEach((edge) => drawLine(edge, map));
  state.nodes.forEach((node) => drawNode(node, map));
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
  loadImageForCurrentMap();
  setStatus("Ready. Changes are local until you save.");
}

boot().catch((error) => {
  setStatus(`Could not load editor: ${error.message}`);
});
