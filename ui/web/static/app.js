const DEFAULT_NOTICE = "Request high-confidence reports of a grey raincoat carrying a red folder at the selected junction.";
const DEFAULT_FOCUSED_JUNCTION = 100;

const ASSET = "/static/assets/reference/";

const TACTICS = {
  roadblock: {
    label: "Roadblock",
    countLabel: "3 units",
    icon: "icon_roadblock.png",
    pin: "pin_roadblock.png",
    preview: "Blocks one road route from this junction. Best for cutting off a known escape path.",
    details: "Blocks one open route leaving this junction for two turns.",
  },
  junction_lockdown: {
    label: "Junction Lockdown",
    countLabel: "3 units",
    icon: "icon_junction_lockdown.png",
    pin: "pin_junction_lockdown.png",
    preview: "Locks down movement through this junction for a short time. Best at chokepoints.",
    details: "Blocks movement through this junction for two turns.",
  },
  patrol_unit: {
    label: "Patrol Unit",
    countLabel: "2 units",
    icon: "icon_patrol_unit.png",
    pin: "pin_patrol_unit.png",
    preview: "Watches this junction and raises pressure nearby. Best where the suspect may pass through.",
    details: "Marks a watched junction for visible patrol pressure.",
  },
  search_team: {
    label: "Search Team",
    countLabel: "2 units",
    icon: "icon_search_team.png",
    pin: "pin_search_team.png",
    preview: "Investigates this junction for stronger confirmation. Best for checking promising witness clusters.",
    details: "Marks this junction as under focused investigation.",
  },
  lookout_board: {
    label: "Lookout Board",
    countLabel: "2 units",
    icon: "icon_lookout_board.png",
    pin: "pin_lookout_board.png",
    preview: "Posts a public notice here. People nearby are more likely to report sightings after seeing it.",
    details: "Increases nearby witness response when a lookout notice is raised.",
  },
};

const LAYER_LABELS = {
  normal: "Normal",
  taxi: "Taxi",
  bus: "Bus",
  subway: "Subway",
};

const els = {
  caseClock: document.querySelector("#caseClock"),
  turnPhase: document.querySelector("#turnPhase"),
  settingsButton: document.querySelector("#settingsButton"),
  newCaseButton: document.querySelector("#newCaseButton"),
  advanceButton: document.querySelector("#advanceButton"),
  activeUnitsText: document.querySelector("#activeUnitsText"),
  unitIcons: document.querySelector("#unitIcons"),
  tacticTray: document.querySelector("#tacticTray"),
  layerTabs: document.querySelector("#layerTabs"),
  mapWrap: document.querySelector("#mapWrap"),
  mapCanvas: document.querySelector("#mapCanvas"),
  mapImage: document.querySelector("#mapImage"),
  selectionLayer: document.querySelector("#selectionLayer"),
  witnessLayer: document.querySelector("#witnessLayer"),
  tacticLayer: document.querySelector("#tacticLayer"),
  mapMessage: document.querySelector("#mapMessage"),
  legendStrip: document.querySelector("#legendStrip"),
  noticeText: document.querySelector("#noticeText"),
  raiseLookoutButton: document.querySelector("#raiseLookoutButton"),
  lookoutMeta: document.querySelector("#lookoutMeta"),
  statementList: document.querySelector("#statementList"),
  eventTicker: document.querySelector("#eventTicker"),
  detailPopup: document.querySelector("#detailPopup"),
  wantedDescription: document.querySelector("#wantedDescription"),
  gameTitle: document.querySelector("#gameTitle"),
  gameSubtitle: document.querySelector("#gameSubtitle"),
  zoomOutButton: document.querySelector("#zoomOutButton"),
  zoomInButton: document.querySelector("#zoomInButton"),
  zoomResetButton: document.querySelector("#zoomResetButton"),
  zoomValue: document.querySelector("#zoomValue"),
  settingsDialog: document.querySelector("#settingsDialog"),
  settingsCloseButton: document.querySelector("#settingsCloseButton"),
  soundSetting: document.querySelector("#soundSetting"),
  difficultySetting: document.querySelector("#difficultySetting"),
  modelNameSetting: document.querySelector("#modelNameSetting"),
  modelPathSetting: document.querySelector("#modelPathSetting"),
  serverBinSetting: document.querySelector("#serverBinSetting"),
  baseUrlSetting: document.querySelector("#baseUrlSetting"),
  llamaStatusText: document.querySelector("#llamaStatusText"),
  settingsSaveButton: document.querySelector("#settingsSaveButton"),
  llamaStartButton: document.querySelector("#llamaStartButton"),
  llamaRestartButton: document.querySelector("#llamaRestartButton"),
  llamaStopButton: document.querySelector("#llamaStopButton"),
};

const state = {
  gameId: null,
  layer: "normal",
  map: { layers: [], junctions: [] },
  selected: [],
  focused: null,
  witnesses: [],
  witnessCards: [],
  previousStatements: [],
  placedTactics: [],
  tacticCounts: emptyCounts(),
  sound: true,
  popup: null,
  pointerDrag: null,
  mapView: { zoom: 1.45, x: 0, y: 0, initialized: false },
  mapPan: null,
  suppressMapClick: false,
  settings: null,
  appScale: 1,
};

function emptyCounts() {
  const limits = Object.fromEntries(Object.keys(TACTICS).map((key) => [key, 0]));
  return {
    limits,
    placed: { ...limits },
    remaining: { ...limits },
    total_limit: 12,
    total_remaining: 12,
  };
}

function api(path, payload = {}) {
  return fetch(`/api/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(async (response) => {
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || response.statusText);
    }
    return response.json();
  });
}

function payload(extra = {}) {
  return {
    game_id: state.gameId,
    selected_junctions: state.selected,
    focused_junction: state.focused,
    ...extra,
  };
}

async function boot() {
  adjustAppScale();
  restoreEditableTitle();
  bindEvents();
  const snapshot = await fetch("/api/snapshot").then((response) => response.json());
  applySnapshot(snapshot, false);
  if (!state.gameId) {
    await openNewCase(false);
  }
  renderLegend();
}

function adjustAppScale() {
  const designWidth = 1672;
  const designHeight = 940;
  state.appScale = Math.min(window.innerWidth / designWidth, window.innerHeight / designHeight);
  document.documentElement.style.setProperty("--app-scale", String(state.appScale));
}

function bindEvents() {
  bindEditableTitle(els.gameTitle, "phantomGridTitle");
  bindEditableTitle(els.gameSubtitle, "phantomGridSubtitle");
  els.newCaseButton.addEventListener("click", () => openNewCase(true));
  els.settingsButton.addEventListener("click", openSettings);
  els.advanceButton.addEventListener("click", async () => {
    if (!state.gameId) return openNewCase(true);
    applySnapshot(await api("advance_turn", payload()));
  });
  els.raiseLookoutButton.addEventListener("click", async () => {
    if (!state.gameId) await openNewCase(false);
    if (!state.focused) {
      state.focused = DEFAULT_FOCUSED_JUNCTION;
      state.selected = [DEFAULT_FOCUSED_JUNCTION];
    }
    applySnapshot(await api("issue_notice", payload({ notice_text: els.noticeText.value || DEFAULT_NOTICE })));
  });

  els.mapWrap.addEventListener("click", handleMapClick);
  els.mapWrap.addEventListener("pointerdown", startMapPan);
  els.mapWrap.addEventListener("dragover", (event) => event.preventDefault());
  els.mapWrap.addEventListener("drop", handleMapDrop);
  els.mapWrap.addEventListener("wheel", handleMapWheel, { passive: false });
  els.zoomOutButton.addEventListener("click", () => zoomBy(0.86));
  els.zoomInButton.addEventListener("click", () => zoomBy(1.16));
  els.zoomResetButton.addEventListener("click", () => resetMapView(true));
  els.tacticTray.addEventListener("pointerdown", startTrayPointerDrag);
  els.tacticLayer.addEventListener("pointerdown", startPlacedPointerDrag);
  els.witnessLayer.addEventListener("click", handleWitnessClick);
  els.tacticLayer.addEventListener("click", handleTacticClick);
  els.detailPopup.addEventListener("click", handlePopupClick);
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".detail-popup, .map-token, .witness-token")) {
      closePopup();
    }
  });
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", handleDocumentDrop);
  window.addEventListener("pointermove", movePointerDrag);
  window.addEventListener("pointerup", endPointerDrag);
  window.addEventListener("pointercancel", cancelPointerDrag);
  window.addEventListener("pointermove", moveMapPan);
  window.addEventListener("pointerup", endMapPan);
  window.addEventListener("pointercancel", cancelMapPan);
  window.addEventListener("resize", () => {
    adjustAppScale();
    clampMapView();
    renderMapView();
    renderMapOverlays();
  });
  els.mapImage.addEventListener("load", () => resetMapView(false));
  els.settingsCloseButton.addEventListener("click", () => els.settingsDialog.close());
  els.settingsSaveButton.addEventListener("click", saveSettings);
  els.llamaStartButton.addEventListener("click", () => runLlamaAction("start"));
  els.llamaRestartButton.addEventListener("click", () => runLlamaAction("restart"));
  els.llamaStopButton.addEventListener("click", () => runLlamaAction("stop"));
}

function restoreEditableTitle() {
  const savedTitle = localStorage.getItem("phantomGridTitle");
  const savedSubtitle = localStorage.getItem("phantomGridSubtitle");
  if (savedTitle) els.gameTitle.textContent = savedTitle;
  if (savedSubtitle) els.gameSubtitle.textContent = savedSubtitle;
}

function bindEditableTitle(element, storageKey) {
  element.addEventListener("input", () => {
    localStorage.setItem(storageKey, element.textContent.trim());
  });
  element.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      element.blur();
    }
  });
  element.addEventListener("blur", () => {
    if (!element.textContent.trim()) {
      element.textContent = storageKey === "phantomGridTitle" ? "Phantom Grid" : "Catch John Doe before he vanishes again!";
    }
    localStorage.setItem(storageKey, element.textContent.trim());
  });
}

async function openSettings() {
  try {
    const data = await fetch("/api/settings").then((response) => response.json());
    state.settings = data.settings;
    populateSettings(data);
    if (!els.settingsDialog.open) {
      els.settingsDialog.showModal();
    }
  } catch (error) {
    flash(error.message || "Could not load settings.", "map_select");
  }
}

function populateSettings(data) {
  const settings = data.settings || {};
  els.soundSetting.value = state.sound ? "on" : "off";
  els.difficultySetting.value = settings.difficulty || "normal";
  els.modelNameSetting.value = settings.llm_model || "";
  els.modelPathSetting.value = settings.llamacpp_model_path || "";
  els.serverBinSetting.value = settings.llamacpp_server_bin || "";
  els.baseUrlSetting.value = settings.llamacpp_base_url || "http://127.0.0.1:8080/v1";
  renderLlamaStatus(data.llama, settings);
}

function settingsPayload() {
  return {
    difficulty: els.difficultySetting.value,
    llm_model: els.modelNameSetting.value,
    llamacpp_model_path: els.modelPathSetting.value,
    llamacpp_server_bin: els.serverBinSetting.value,
    llamacpp_base_url: els.baseUrlSetting.value,
  };
}

async function saveSettings() {
  try {
    state.sound = els.soundSetting.value === "on";
    const data = await api("settings", settingsPayload());
    state.settings = data.settings;
    populateSettings(data);
    flash("Settings saved. Difficulty applies to new cases.", "map_select");
  } catch (error) {
    flash(error.message || "Could not save settings.", "map_select");
  }
}

async function runLlamaAction(action) {
  try {
    state.sound = els.soundSetting.value === "on";
    const response = await fetch(`/api/llama/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settingsPayload()),
    });
    const data = await response.json();
    if (data.settings) {
      state.settings = data.settings;
    }
    renderLlamaStatus(data.llama, data.settings || state.settings || {});
    flash(data.event || "llama-server status updated.", data.ok ? "blockade_set" : "map_select");
  } catch (error) {
    flash(error.message || "Could not control llama-server.", "map_select");
  }
}

function renderLlamaStatus(llama, settings) {
  const server = settings.llamacpp_server_bin_exists ? "server path ok" : "server path missing";
  const model = settings.llamacpp_model_exists ? "model path ok" : "model path missing";
  const reach = llama?.reachable ? "reachable" : "not reachable";
  const pid = llama?.pid ? ` PID ${llama.pid}` : "";
  els.llamaStatusText.textContent = `llama-server: ${reach}${pid}. ${server}; ${model}. ${llama?.detail || ""}`;
}

async function openNewCase(makeNoise) {
  closePopup();
  els.noticeText.value = DEFAULT_NOTICE;
  const snapshot = await api("new_case", {});
  applySnapshot(snapshot, makeNoise);
  state.selected = [DEFAULT_FOCUSED_JUNCTION];
  state.focused = DEFAULT_FOCUSED_JUNCTION;
  applySnapshot(await api("select_junctions", payload()), makeNoise);
}

function applySnapshot(snapshot, makeNoise = true) {
  if (!snapshot || !snapshot.ok) return;
  state.gameId = snapshot.game?.game_id || state.gameId;
  state.map = snapshot.map || state.map;
  state.selected = snapshot.selection?.junctions || state.selected;
  state.focused = snapshot.selection?.focused ?? state.focused;
  state.witnesses = snapshot.witness_locations || [];
  state.witnessCards = snapshot.witness_cards || [];
  state.previousStatements = snapshot.previous_statements || [];
  state.placedTactics = snapshot.placed_tactics || [];
  state.tacticCounts = snapshot.tactic_counts || state.tacticCounts;

  renderGame(snapshot.game);
  renderTacticTray();
  renderLayers();
  renderMap();
  renderMapOverlays();
  renderLookout(snapshot.lookout);
  renderStatements();
  renderActiveUnits();

  if (snapshot.event) {
    flash(snapshot.event, snapshot.sound, makeNoise);
  }
}

function renderGame(game) {
  if (!game) {
    els.caseClock.textContent = "-";
    els.turnPhase.textContent = "Evening";
    return;
  }
  els.caseClock.textContent = `${game.turn} / ${game.max_turns}`;
  els.turnPhase.textContent = turnPhase(game.turn);
  els.wantedDescription.textContent = game.initial_description || els.wantedDescription.textContent;
}

function renderTacticTray() {
  els.tacticTray.innerHTML = "";
  for (const [type, tactic] of Object.entries(TACTICS)) {
    const remaining = state.tacticCounts.remaining?.[type] ?? 0;
    const limit = state.tacticCounts.limits?.[type] ?? 0;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "tactic-card";
    card.draggable = remaining > 0;
    card.disabled = remaining <= 0;
    card.dataset.tacticType = type;
    card.setAttribute("aria-label", `${tactic.label}, ${remaining} of ${limit} remaining. ${tactic.preview}`);
    card.innerHTML = `
      <img src="${ASSET}${tactic.icon}" alt="" />
      <span>${escapeHtml(tactic.label)}</span>
      <strong>${remaining} / ${limit}</strong>
      <em class="tactic-preview">${escapeHtml(tactic.preview)}<br><b>${remaining} left</b></em>
    `;
    card.addEventListener("dragstart", (event) => {
      if (remaining <= 0) {
        event.preventDefault();
        return;
      }
      event.dataTransfer.setData("application/x-tactic-type", type);
      event.dataTransfer.effectAllowed = "copy";
    });
    els.tacticTray.append(card);
  }
}

function renderLayers() {
  const ordered = ["normal", "taxi", "bus", "subway"].filter((layer) => state.map.layers.includes(layer));
  const key = ordered.join("|");
  if (els.layerTabs.dataset.ready !== key) {
    els.layerTabs.dataset.ready = key;
    els.layerTabs.innerHTML = "";
    ordered.forEach((layer) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = LAYER_LABELS[layer] || layer;
      button.dataset.layer = layer;
      button.addEventListener("click", () => {
        state.layer = layer;
        renderLayers();
        renderMap();
        playSound("map_select");
      });
      els.layerTabs.append(button);
    });
  }
  [...els.layerTabs.children].forEach((button) => {
    button.classList.toggle("active", button.dataset.layer === state.layer);
  });
}

function renderMap() {
  const nextSrc = `/assets/maps/${state.layer}`;
  if (!els.mapImage.src.endsWith(nextSrc)) {
    els.mapImage.src = nextSrc;
  }
}

function renderMapView() {
  els.mapCanvas.style.transform = `translate(${state.mapView.x}px, ${state.mapView.y}px) scale(${state.mapView.zoom})`;
  els.zoomValue.textContent = `${Math.round(state.mapView.zoom * 100)}%`;
}

function resetMapView(force) {
  if (!els.mapImage.naturalWidth) return;
  if (!force && state.mapView.initialized) {
    renderMapView();
    renderMapOverlays();
    return;
  }
  state.mapView.zoom = 1.45;
  const wrap = { width: els.mapWrap.clientWidth, height: els.mapWrap.clientHeight };
  const base = imageBaseRect();
  const focus = junctionById(state.focused || DEFAULT_FOCUSED_JUNCTION);
  const targetX = base.left + ((focus?.x || els.mapImage.naturalWidth / 2) / els.mapImage.naturalWidth) * base.width;
  const targetY = base.top + ((focus?.y || els.mapImage.naturalHeight / 2) / els.mapImage.naturalHeight) * base.height;
  state.mapView.x = wrap.width / 2 - targetX * state.mapView.zoom;
  state.mapView.y = wrap.height / 2 - targetY * state.mapView.zoom;
  state.mapView.initialized = true;
  clampMapView();
  renderMapView();
  renderMapOverlays();
}

function zoomBy(factor, clientX = null, clientY = null) {
  const wrap = els.mapWrap.getBoundingClientRect();
  const anchorX = clientX == null ? els.mapWrap.clientWidth / 2 : (clientX - wrap.left) / state.appScale;
  const anchorY = clientY == null ? els.mapWrap.clientHeight / 2 : (clientY - wrap.top) / state.appScale;
  const oldZoom = state.mapView.zoom;
  const nextZoom = Math.min(Math.max(oldZoom * factor, 0.85), 2.4);
  const worldX = (anchorX - state.mapView.x) / oldZoom;
  const worldY = (anchorY - state.mapView.y) / oldZoom;
  state.mapView.zoom = nextZoom;
  state.mapView.x = anchorX - worldX * nextZoom;
  state.mapView.y = anchorY - worldY * nextZoom;
  clampMapView();
  renderMapView();
}

function clampMapView() {
  const wrap = { width: els.mapWrap.clientWidth, height: els.mapWrap.clientHeight };
  if (!wrap.width || !wrap.height) return;
  const zoom = state.mapView.zoom;
  const scaledWidth = wrap.width * zoom;
  const scaledHeight = wrap.height * zoom;
  const minX = Math.min(0, wrap.width - scaledWidth);
  const minY = Math.min(0, wrap.height - scaledHeight);
  state.mapView.x = Math.min(Math.max(state.mapView.x, minX), 0);
  state.mapView.y = Math.min(Math.max(state.mapView.y, minY), 0);
}

function renderMapOverlays() {
  els.selectionLayer.innerHTML = "";
  els.witnessLayer.innerHTML = "";
  els.tacticLayer.innerHTML = "";

  const focused = junctionById(state.focused);
  if (focused) {
    const marker = document.createElement("div");
    marker.className = "focus-marker";
    placeAtMapPoint(marker, focused.x, focused.y);
    els.selectionLayer.append(marker);
  }

  state.witnesses.forEach((witness) => {
    const junction = junctionById(witness.junction_id);
    if (!junction) return;
    const token = document.createElement("button");
    token.type = "button";
    token.className = `witness-token ${witness.viewed ? "viewed" : "unviewed"}`;
    token.dataset.junctionId = String(witness.junction_id);
    token.dataset.witnessId = witness.sample_witness_id || "";
    token.innerHTML = `
      <img src="${ASSET}${witness.viewed ? "pin_viewed_witness.png" : "pin_unviewed_witness.png"}" alt="" />
      <strong>${witness.count}</strong>
    `;
    placeAtMapPoint(token, junction.x, junction.y);
    els.witnessLayer.append(token);
  });

  state.placedTactics.forEach((placed) => {
    const tactic = TACTICS[placed.tactic_type];
    if (!tactic) return;
    const token = document.createElement("button");
    token.type = "button";
    token.className = `map-token ${placed.tactic_type}`;
    token.draggable = true;
    token.dataset.tacticId = placed.tactic_id;
    token.innerHTML = `<img src="${ASSET}${tactic.pin}" alt="${escapeHtml(tactic.label)}" />`;
    token.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("application/x-placed-tactic-id", placed.tactic_id);
      event.dataTransfer.effectAllowed = "move";
    });
    placeAtMapPoint(token, placed.x, placed.y);
    els.tacticLayer.append(token);
  });
}

function renderLookout(lookout) {
  if (!lookout || !lookout.raised) {
    els.lookoutMeta.textContent = "No witness pins yet.";
    return;
  }
  const review = lookout.review_allowed ? "statements available" : "crowd reports only";
  els.lookoutMeta.textContent = `${lookout.witness_count} potential witnesses, ${review}.`;
}

function renderStatements() {
  els.statementList.innerHTML = "";
  if (!state.previousStatements.length) {
    const empty = document.createElement("article");
    empty.className = "statement-card empty";
    empty.innerHTML = "<strong>No statements yet</strong><p>Ask a witness statement to pin it here.</p>";
    els.statementList.append(empty);
    return;
  }
  state.previousStatements.slice().reverse().forEach((statement) => {
    const card = document.createElement("article");
    card.className = "statement-card";
    card.innerHTML = `
      <div>
        <strong>${String(statement.junction_id).padStart(2, "0")} Junction ${statement.junction_id}</strong>
        <span>${escapeHtml(statement.time_label || "")}</span>
      </div>
      <p>${escapeHtml(shortSummary(statement.answer || statement.summary, 118))}</p>
      <mark aria-label="Viewed">✓</mark>
    `;
    els.statementList.append(card);
  });
}

function renderActiveUnits() {
  const total = state.tacticCounts.total_limit ?? 12;
  const remaining = state.tacticCounts.total_remaining ?? total;
  els.activeUnitsText.textContent = `${remaining} / ${total} left`;
  els.unitIcons.innerHTML = "";
  for (let index = 0; index < total; index += 1) {
    const dot = document.createElement("span");
    dot.className = index < remaining ? "unit-dot ready" : "unit-dot used";
    els.unitIcons.append(dot);
  }
}

function renderLegend() {
  const items = [
    ["pin_unviewed_witness.png", "Unviewed Witness", "Lead"],
    ["pin_viewed_witness.png", "Viewed Witness", "Cleared"],
    ["pin_roadblock.png", "Roadblock", "Blocks Road"],
    ["pin_junction_lockdown.png", "Junction Lockdown", "Blocks Area"],
    ["pin_patrol_unit.png", "Patrol Unit", "Patrolling"],
    ["pin_search_team.png", "Search Team", "Investigating"],
    ["pin_lookout_board.png", "Lookout Board", "Alerts"],
  ];
  els.legendStrip.innerHTML = "";
  items.forEach(([icon, label, detail]) => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `<img src="${ASSET}${icon}" alt="" /><strong>${label}</strong><span>${detail}</span>`;
    els.legendStrip.append(item);
  });
}

async function handleMapClick(event) {
  if (state.suppressMapClick) {
    state.suppressMapClick = false;
    return;
  }
  if (event.target.closest(".map-token, .witness-token")) return;
  const point = naturalPointFromEvent(event);
  if (!point) return;
  const junctionId = nearestJunction(point);
  if (!junctionId) return;
  state.focused = junctionId;
  state.selected = [junctionId];
  renderMapOverlays();
  applySnapshot(await api("select_junctions", payload()));
}

function startMapPan(event) {
  if (event.button !== 0) return;
  if (event.target.closest(".map-token, .witness-token, .map-controls, .detail-popup")) return;
  state.mapPan = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: state.mapView.x,
    originY: state.mapView.y,
    moved: false,
  };
}

function moveMapPan(event) {
  const pan = state.mapPan;
  if (!pan || pan.pointerId !== event.pointerId || state.pointerDrag) return;
  const dx = (event.clientX - pan.startX) / state.appScale;
  const dy = (event.clientY - pan.startY) / state.appScale;
  if (Math.hypot(dx, dy) > 6) {
    pan.moved = true;
  }
  state.mapView.x = pan.originX + dx;
  state.mapView.y = pan.originY + dy;
  clampMapView();
  renderMapView();
}

function endMapPan(event) {
  const pan = state.mapPan;
  if (!pan || pan.pointerId !== event.pointerId) return;
  if (pan.moved) {
    state.suppressMapClick = true;
  }
  state.mapPan = null;
}

function cancelMapPan() {
  state.mapPan = null;
}

function handleMapWheel(event) {
  if (!event.target.closest("#mapWrap")) return;
  event.preventDefault();
  zoomBy(event.deltaY < 0 ? 1.12 : 0.89, event.clientX, event.clientY);
}

async function handleMapDrop(event) {
  event.preventDefault();
  event.stopPropagation();
  const tacticType = event.dataTransfer.getData("application/x-tactic-type");
  const movedTactic = event.dataTransfer.getData("application/x-placed-tactic-id");
  if (movedTactic) return;
  if (!tacticType) return;
  const point = naturalPointFromEvent(event);
  const junctionId = point ? nearestJunction(point) : null;
  if (!junctionId) {
    flash("Drop the tactic closer to a junction.", "map_select");
    return;
  }
  if ((state.tacticCounts.remaining?.[tacticType] ?? 0) <= 0) {
    flash(`No ${TACTICS[tacticType].label} units remain.`, "map_select");
    return;
  }
  await placeTacticAt(tacticType, junctionId);
}

async function handleDocumentDrop(event) {
  const tacticId = event.dataTransfer.getData("application/x-placed-tactic-id");
  if (!tacticId || event.target.closest("#mapWrap")) return;
  event.preventDefault();
  closePopup();
  applySnapshot(await api("remove_tactic", payload({ tactic_id: tacticId })));
}

function startTrayPointerDrag(event) {
  const card = event.target.closest(".tactic-card");
  if (!card || card.disabled) return;
  const tacticType = card.dataset.tacticType;
  if (!tacticType || (state.tacticCounts.remaining?.[tacticType] ?? 0) <= 0) return;
  event.preventDefault();
  beginPointerDrag(event, {
    kind: "new",
    tacticType,
    label: TACTICS[tacticType].label,
    icon: TACTICS[tacticType].icon,
  });
}

function startPlacedPointerDrag(event) {
  const token = event.target.closest(".map-token");
  if (!token) return;
  const placed = state.placedTactics.find((item) => item.tactic_id === token.dataset.tacticId);
  if (!placed) return;
  const tactic = TACTICS[placed.tactic_type];
  if (!tactic) return;
  event.preventDefault();
  beginPointerDrag(event, {
    kind: "placed",
    tacticId: placed.tactic_id,
    label: tactic.label,
    icon: tactic.pin,
  });
}

function beginPointerDrag(event, detail) {
  closePopup();
  const ghost = document.createElement("div");
  ghost.className = "drag-ghost";
  ghost.innerHTML = `<img src="${ASSET}${detail.icon}" alt="" /><span>${escapeHtml(detail.label)}</span>`;
  document.body.append(ghost);
  state.pointerDrag = {
    ...detail,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    moved: false,
    ghost,
  };
  positionDragGhost(event.clientX, event.clientY);
}

function movePointerDrag(event) {
  const drag = state.pointerDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 8) {
    drag.moved = true;
  }
  positionDragGhost(event.clientX, event.clientY);
}

async function endPointerDrag(event) {
  const drag = state.pointerDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  state.pointerDrag = null;
  drag.ghost.remove();

  const point = naturalPointFromClient(event.clientX, event.clientY);
  if (drag.kind === "new") {
    if (!drag.moved) return;
    const junctionId = point ? nearestJunction(point) : null;
    if (!junctionId) {
      flash("Drop the tactic closer to a junction.", "map_select");
      return;
    }
    await placeTacticAt(drag.tacticType, junctionId);
    return;
  }

  if (drag.kind === "placed" && drag.moved && !point) {
    applySnapshot(await api("remove_tactic", payload({ tactic_id: drag.tacticId })));
  }
}

function cancelPointerDrag() {
  if (state.pointerDrag?.ghost) {
    state.pointerDrag.ghost.remove();
  }
  state.pointerDrag = null;
}

function positionDragGhost(x, y) {
  const ghost = state.pointerDrag?.ghost;
  if (!ghost) return;
  ghost.style.left = `${x + 12}px`;
  ghost.style.top = `${y + 12}px`;
}

async function placeTacticAt(tacticType, junctionId) {
  state.focused = junctionId;
  state.selected = [junctionId];
  optimisticCount(tacticType, -1);
  renderTacticTray();
  renderActiveUnits();
  try {
    applySnapshot(await api("place_tactic", payload({ tactic_type: tacticType, junction_id: junctionId })));
  } catch (error) {
    optimisticCount(tacticType, 1);
    renderTacticTray();
    renderActiveUnits();
    flash(error.message || "Could not place tactic.", "map_select");
  }
}

function handleTacticClick(event) {
  const token = event.target.closest("[data-tactic-id]");
  if (!token) return;
  event.preventDefault();
  event.stopPropagation();
  const placed = state.placedTactics.find((item) => item.tactic_id === token.dataset.tacticId);
  if (!placed) return;
  showTacticPopup(placed, event.clientX, event.clientY);
}

function handleWitnessClick(event) {
  const token = event.target.closest("[data-witness-id]");
  if (!token) return;
  event.preventDefault();
  event.stopPropagation();
  const witnessId = token.dataset.witnessId;
  const junctionId = Number(token.dataset.junctionId);
  const location = state.witnesses.find((item) => item.junction_id === junctionId);
  const card = state.witnessCards.find((item) => item.id === witnessId);
  showWitnessPopup(location, card, event.clientX, event.clientY);
}

function handlePopupClick(event) {
  const close = event.target.closest("[data-action='close-popup']");
  if (close) {
    closePopup();
    return;
  }
  const remove = event.target.closest("[data-action='remove-tactic']");
  if (remove) {
    api("remove_tactic", payload({ tactic_id: remove.dataset.tacticId }))
      .then((snapshot) => {
        closePopup();
        applySnapshot(snapshot);
      })
      .catch((error) => flash(error.message || "Could not remove tactic.", "map_select"));
    return;
  }
  const ask = event.target.closest("[data-action='ask-witness']");
  if (ask) {
    askWitness(ask.dataset.witnessId);
  }
}

function showTacticPopup(placed, x, y) {
  const tactic = TACTICS[placed.tactic_type];
  if (!tactic) return;
  state.focused = placed.junction_id;
  state.selected = [placed.junction_id];
  renderMapOverlays();
  els.detailPopup.innerHTML = `
    <button class="popup-close" type="button" data-action="close-popup" aria-label="Close">×</button>
    <img src="${ASSET}${tactic.pin}" alt="" />
    <h3>${escapeHtml(tactic.label)}</h3>
    <p>${escapeHtml(tactic.details)}</p>
    <dl>
      <dt>Junction</dt><dd>${placed.junction_id}</dd>
      <dt>Turn Placed</dt><dd>${placed.turn_created}</dd>
    </dl>
    <button class="remove-button" type="button" data-action="remove-tactic" data-tactic-id="${escapeHtml(placed.tactic_id)}">Remove</button>
  `;
  placePopup(x, y);
}

function showWitnessPopup(location, card, x, y) {
  if (!location) return;
  const witnessId = card?.id || location.sample_witness_id;
  const canAsk = Boolean(witnessId);
  state.focused = location.junction_id;
  state.selected = [location.junction_id];
  renderMapOverlays();
  els.detailPopup.innerHTML = `
    <button class="popup-close" type="button" data-action="close-popup" aria-label="Close">×</button>
    <img src="${ASSET}${location.viewed ? "pin_viewed_witness.png" : "pin_unviewed_witness.png"}" alt="" />
    <h3>${location.viewed ? "Viewed Witness" : "Unviewed Witness"}</h3>
    <p>${escapeHtml(shortSummary(card?.summary || location.sample_summary || "Potential witness report.", 160))}</p>
    <dl>
      <dt>Junction</dt><dd>${location.junction_id}</dd>
      <dt>Reports</dt><dd>${location.count}</dd>
    </dl>
    ${canAsk ? `<button class="ask-button" type="button" data-action="ask-witness" data-witness-id="${escapeHtml(witnessId)}">Ask Statement</button>` : ""}
  `;
  placePopup(x, y);
}

async function askWitness(witnessId) {
  if (!witnessId) return;
  try {
    applySnapshot(await api("ask_witness", payload({ witness_id: witnessId, question: "Which direction were they moving?" })));
    closePopup();
  } catch (error) {
    flash(error.message || "Could not ask witness.", "map_select");
  }
}

function placePopup(x, y) {
  const margin = 18;
  els.detailPopup.hidden = false;
  const width = 280;
  const left = Math.min(Math.max(x + 14, margin), window.innerWidth - width - margin);
  const top = Math.min(Math.max(y + 14, margin), window.innerHeight - 320);
  els.detailPopup.style.left = `${left}px`;
  els.detailPopup.style.top = `${Math.max(top, margin)}px`;
}

function closePopup() {
  els.detailPopup.hidden = true;
  els.detailPopup.innerHTML = "";
}

function optimisticCount(tacticType, delta) {
  if (!state.tacticCounts.remaining || !(tacticType in state.tacticCounts.remaining)) return;
  state.tacticCounts.remaining[tacticType] = Math.max(0, state.tacticCounts.remaining[tacticType] + delta);
  state.tacticCounts.total_remaining = Math.max(0, state.tacticCounts.total_remaining + delta);
}

function nearestJunction(point) {
  let best = null;
  let bestDistance = 64;
  for (const junction of state.map.junctions) {
    const distance = Math.hypot(point.x - junction.x, point.y - junction.y);
    if (distance <= bestDistance) {
      best = junction.id;
      bestDistance = distance;
    }
  }
  return best;
}

function naturalPointFromEvent(event) {
  return naturalPointFromClient(event.clientX, event.clientY);
}

function naturalPointFromClient(clientX, clientY) {
  const wrap = els.mapWrap.getBoundingClientRect();
  const base = imageBaseRect();
  if (!wrap.width || !base) {
    return null;
  }
  const localX = (clientX - wrap.left) / state.appScale;
  const localY = (clientY - wrap.top) / state.appScale;
  const canvasX = (localX - state.mapView.x) / state.mapView.zoom;
  const canvasY = (localY - state.mapView.y) / state.mapView.zoom;
  if (canvasX < base.left || canvasX > base.right || canvasY < base.top || canvasY > base.bottom) return null;
  return {
    x: ((canvasX - base.left) / base.width) * els.mapImage.naturalWidth,
    y: ((canvasY - base.top) / base.height) * els.mapImage.naturalHeight,
  };
}

function placeAtMapPoint(node, x, y) {
  const rect = imageBaseRect();
  if (!rect) return;
  const left = rect.left + (x / els.mapImage.naturalWidth) * rect.width;
  const top = rect.top + (y / els.mapImage.naturalHeight) * rect.height;
  node.style.left = `${left}px`;
  node.style.top = `${top}px`;
}

function imageBaseRect() {
  const widthBox = els.mapWrap.clientWidth;
  const heightBox = els.mapWrap.clientHeight;
  if (!els.mapImage.naturalWidth || !els.mapImage.naturalHeight || !widthBox || !heightBox) return null;
  const imageRatio = els.mapImage.naturalWidth / els.mapImage.naturalHeight;
  const boxRatio = widthBox / heightBox;
  let width = widthBox;
  let height = heightBox;
  let left = 0;
  let top = 0;
  if (boxRatio > imageRatio) {
    width = height * imageRatio;
    left += (widthBox - width) / 2;
  } else {
    height = width / imageRatio;
    top += (heightBox - height) / 2;
  }
  return { left, top, width, height, right: left + width, bottom: top + height };
}

function junctionById(junctionId) {
  return state.map.junctions.find((junction) => junction.id === junctionId);
}

function turnPhase(turn) {
  return ["Morning", "Midday", "Afternoon", "Evening", "Night"][(Number(turn || 1) - 1) % 5];
}

function flash(message, sound, makeNoise = true) {
  els.eventTicker.textContent = message;
  els.mapMessage.textContent = message;
  if (makeNoise && sound) playSound(sound);
}

let audioContext = null;

function playSound(name) {
  if (!state.sound) return;
  audioContext ||= new AudioContext();
  const now = audioContext.currentTime;
  const gain = audioContext.createGain();
  gain.connect(audioContext.destination);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.07, now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.2);
  const tones = {
    map_select: [220, 0.12, "triangle"],
    blockade_set: [110, 0.2, "square"],
    lookout_raise: [330, 0.24, "sawtooth"],
    witness_popup: [520, 0.18, "sine"],
    turn_advance: [160, 0.3, "triangle"],
  };
  const [frequency, duration, type] = tones[name] || tones.map_select;
  const oscillator = audioContext.createOscillator();
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, now);
  oscillator.frequency.exponentialRampToValueAtTime(frequency * 1.28, now + duration);
  oscillator.connect(gain);
  oscillator.start(now);
  oscillator.stop(now + duration);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortSummary(value, limit = 126) {
  const clean = String(value || "Report received.").replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, limit - 3)}...`;
}

boot().catch((error) => {
  flash(error.message || "The board failed to open.", "map_select", false);
});
