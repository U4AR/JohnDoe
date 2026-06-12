const DEFAULT_NOTICE = "Request high-confidence reports of a grey raincoat carrying a red folder at the selected junction.";
const DEFAULT_FOCUSED_JUNCTION = 100;

const els = {
  caseClock: document.querySelector("#caseClock strong"),
  caseStatus: document.querySelector("#caseStatus"),
  checksRemaining: document.querySelector("#checksRemaining"),
  soundToggle: document.querySelector("#soundToggle"),
  newCaseButton: document.querySelector("#newCaseButton"),
  checkButton: document.querySelector("#checkButton"),
  advanceButton: document.querySelector("#advanceButton"),
  layerTabs: document.querySelector("#layerTabs"),
  mapWrap: document.querySelector("#mapWrap"),
  mapImage: document.querySelector("#mapImage"),
  selectionLayer: document.querySelector("#selectionLayer"),
  witnessLayer: document.querySelector("#witnessLayer"),
  eventTicker: document.querySelector("#eventTicker"),
  blockadeTray: document.querySelector("#blockadeTray"),
  noticeText: document.querySelector("#noticeText"),
  raiseLookoutButton: document.querySelector("#raiseLookoutButton"),
  lookoutMeta: document.querySelector("#lookoutMeta"),
  witnessDrawer: document.querySelector("#witnessDrawer"),
  witnessCards: document.querySelector("#witnessCards"),
  closeWitnesses: document.querySelector("#closeWitnesses"),
  startScene: document.querySelector("#startScene"),
  gameScene: document.querySelector("#gameScene"),
  startBriefingButton: document.querySelector("#startBriefingButton"),
  briefingTitle: document.querySelector("#briefingTitle"),
  briefingBody: document.querySelector("#briefingBody"),
  briefingFacts: document.querySelector("#briefingFacts"),
  briefingBack: document.querySelector("#briefingBack"),
  briefingNext: document.querySelector("#briefingNext"),
  briefingProgress: document.querySelector("#briefingProgress"),
};

const state = {
  gameId: null,
  layer: "normal",
  map: { layers: [], junctions: [] },
  selected: [],
  focused: null,
  legalMoves: [],
  witnesses: [],
  witnessCards: [],
  sound: true,
  pointer: null,
  expandedWitnessJunction: null,
  briefingDeck: [],
  briefingIndex: 0,
};

const CASE_SEEDS = [
  {
    title: "The Aldgate Ledger",
    crime: "A courier carrying a sealed council ledger vanished after a staged street collision near Aldgate.",
    suspect: "Witnesses describe a slim figure in a grey raincoat, leather gloves, and a red document folder held flat against the ribs.",
    lastSeen: "The last reliable sighting places the runner beside Junction 100, turning away from a taxi rank as the rain thickened.",
    motive: "The ledger names payments routed through a false charity office.",
  },
  {
    title: "The Blackfriars Exchange",
    crime: "A safe-deposit key changed hands during a blackout, then the receiving clerk was found unconscious behind a shuttered kiosk.",
    suspect: "The robber kept their face low under a dark brim, but several reports agree on a grey raincoat and a red folder.",
    lastSeen: "A newspaper seller saw the suspect pause near Junction 100 before disappearing into the evening transport crowd.",
    motive: "The stolen key opens a box tied to a missing witness in a Commission inquiry.",
  },
  {
    title: "The Limehouse Packet",
    crime: "An evidence packet from the river-police archive was lifted during a diversion at a tram crossing.",
    suspect: "The culprit moved calmly, carrying a red folder and wearing a raincoat too clean for the weather.",
    lastSeen: "Two late commuters place the suspect near Junction 100, looking back once before choosing a route out.",
    motive: "The packet contains route notes for a paid escape network.",
  },
];

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
  const snapshot = await fetch("/api/snapshot").then((response) => response.json());
  applySnapshot(snapshot, false);
  bindEvents();
  if (!state.gameId) {
    showStartMenu();
  } else {
    showGameScene();
  }
}

function bindEvents() {
  els.newCaseButton.addEventListener("click", async () => {
    startBriefing();
  });

  els.startBriefingButton.addEventListener("click", () => {
    startBriefing();
  });

  els.briefingBack.addEventListener("click", () => {
    if (!state.briefingDeck.length || state.briefingIndex === 0) {
      showStartMenu();
      return;
    }
    state.briefingIndex -= 1;
    renderBriefing();
    playSound("map_select");
  });

  els.briefingNext.addEventListener("click", async () => {
    if (!state.briefingDeck.length) {
      startBriefing();
      return;
    }
    if (state.briefingIndex < state.briefingDeck.length - 1) {
      state.briefingIndex += 1;
      renderBriefing();
      playSound("witness_popup");
      return;
    }
    await openBriefedCase();
  });

  els.raiseLookoutButton.addEventListener("click", async () => {
    try {
      if (!state.gameId) {
        const opened = await api("new_case", {});
        applySnapshot(opened);
      }
      if (!state.focused) {
        state.focused = DEFAULT_FOCUSED_JUNCTION;
        state.selected = [DEFAULT_FOCUSED_JUNCTION];
        renderMapOverlays();
        renderTray();
      }
      const snapshot = await api("issue_notice", payload({ notice_text: els.noticeText.value || DEFAULT_NOTICE }));
      applySnapshot(snapshot);
      els.witnessDrawer.classList.remove("open");
    } catch (error) {
      flash(error.message || "Lookout failed.", "map_select");
    }
  });

  els.checkButton.addEventListener("click", async () => {
    if (!state.gameId) {
      return flash("Open a case first.", "map_select");
    }
    const snapshot = await api("check_junctions", payload());
    applySnapshot(snapshot);
  });

  els.advanceButton.addEventListener("click", async () => {
    if (!state.gameId) {
      return flash("Open a case first.", "map_select");
    }
    const snapshot = await api("advance_turn", payload());
    applySnapshot(snapshot);
  });

  els.soundToggle.addEventListener("click", () => {
    state.sound = !state.sound;
    els.soundToggle.textContent = state.sound ? "Sound" : "Muted";
    playSound("map_select");
  });

  els.closeWitnesses.addEventListener("click", () => {
    els.witnessDrawer.classList.remove("open");
  });

  els.mapWrap.addEventListener("pointerdown", startPointer);
  els.mapWrap.addEventListener("pointermove", movePointer);
  els.mapWrap.addEventListener("pointerup", endPointer);
  els.mapWrap.addEventListener("pointercancel", cancelPointer);
  els.witnessLayer.addEventListener("click", handleWitnessClick);
  els.witnessCards.addEventListener("click", handleWitnessClick);
  window.addEventListener("resize", renderMapOverlays);
  els.mapImage.addEventListener("load", renderMapOverlays);
}

function showStartMenu() {
  state.briefingDeck = [];
  state.briefingIndex = 0;
  els.startScene.classList.add("open");
  els.gameScene.classList.add("hidden");
  els.gameScene.setAttribute("aria-hidden", "true");
  els.briefingTitle.textContent = "Phantom Grid";
  els.briefingBody.textContent = "A new file has arrived from the Shadow Commission. The board is locked until the case is opened.";
  renderFacts([
    ["Role", "Commissioner"],
    ["City", "London"],
    ["Method", "Track witnesses, block routes, search junctions"],
  ]);
  els.briefingBack.disabled = true;
  els.briefingNext.textContent = "Open File";
  els.briefingProgress.textContent = "Awaiting case";
}

function startBriefing() {
  state.briefingDeck = buildCaseBriefing();
  state.briefingIndex = 0;
  els.startScene.classList.add("open");
  els.gameScene.classList.add("hidden");
  els.gameScene.setAttribute("aria-hidden", "true");
  renderBriefing();
  playSound("lookout_raise");
}

function showGameScene() {
  els.startScene.classList.remove("open");
  els.gameScene.classList.remove("hidden");
  els.gameScene.removeAttribute("aria-hidden");
  window.requestAnimationFrame(renderMapOverlays);
}

function buildCaseBriefing() {
  const caseData = CASE_SEEDS[Math.floor(Math.random() * CASE_SEEDS.length)];
  return [
    {
      title: caseData.title,
      body: caseData.crime,
      facts: [
        ["Crime", "Theft and flight"],
        ["Priority", "Recover evidence before turn 12"],
        ["Pressure", "Witness memory degrades each turn"],
      ],
    },
    {
      title: "Suspect Description",
      body: caseData.suspect,
      facts: [
        ["Garment", "Grey raincoat"],
        ["Object", "Red folder"],
        ["Behaviour", "Avoids direct lines and doubles back"],
      ],
    },
    {
      title: "Last Seen",
      body: caseData.lastSeen,
      facts: [
        ["Starting Lead", "Junction 100"],
        ["Likely Escape", "Taxi, bus, or subway route"],
        ["Notice Text", DEFAULT_NOTICE],
      ],
    },
    {
      title: "Commission Order",
      body: `${caseData.motive} Open the board and build a net before the trail cools.`,
      facts: [
        ["Open Actions", "Search, lookout, blockade"],
        ["Witness Cards", "Ask follow-up questions after reports arrive"],
        ["Board Status", "Ready"],
      ],
    },
  ];
}

function renderBriefing() {
  const card = state.briefingDeck[state.briefingIndex];
  if (!card) {
    showStartMenu();
    return;
  }
  els.briefingTitle.textContent = card.title;
  els.briefingBody.textContent = card.body;
  renderFacts(card.facts);
  els.briefingBack.disabled = false;
  els.briefingNext.textContent = state.briefingIndex === state.briefingDeck.length - 1 ? "Open Board" : "Next";
  els.briefingProgress.textContent = `Case file ${state.briefingIndex + 1}/${state.briefingDeck.length}`;
}

function renderFacts(facts) {
  els.briefingFacts.innerHTML = "";
  facts.forEach(([label, value]) => {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    els.briefingFacts.append(term, detail);
  });
}

async function openBriefedCase() {
  const snapshot = await api("new_case", {});
  els.noticeText.value = DEFAULT_NOTICE;
  applySnapshot(snapshot);
  state.selected = [DEFAULT_FOCUSED_JUNCTION];
  state.focused = DEFAULT_FOCUSED_JUNCTION;
  renderMapOverlays();
  renderTray();
  applySnapshot(await api("select_junctions", payload()));
  showGameScene();
  playSound("turn_advance");
}

function applySnapshot(snapshot, makeNoise = true) {
  if (!snapshot || !snapshot.ok) {
    return;
  }
  state.gameId = snapshot.game?.game_id || state.gameId;
  state.map = snapshot.map || state.map;
  state.selected = snapshot.selection?.junctions || state.selected;
  state.focused = snapshot.selection?.focused ?? null;
  state.legalMoves = snapshot.selection?.legal_moves || [];
  state.witnesses = snapshot.witness_locations || [];
  state.witnessCards = snapshot.witness_cards || [];
  if (state.expandedWitnessJunction && !state.witnesses.some((item) => item.junction_id === state.expandedWitnessJunction)) {
    state.expandedWitnessJunction = null;
  }

  renderLayers();
  renderGame(snapshot.game);
  renderMap();
  renderMapOverlays();
  renderTray();
  renderLookout(snapshot.lookout);
  renderWitnessCards();

  if (snapshot.event) {
    els.eventTicker.textContent = snapshot.event;
  }
  if (makeNoise && snapshot.sound) {
    playSound(snapshot.sound);
  }
}

function renderLayers() {
  if (els.layerTabs.dataset.ready === state.map.layers.join("|")) {
    return;
  }
  els.layerTabs.dataset.ready = state.map.layers.join("|");
  els.layerTabs.innerHTML = "";
  state.map.layers.forEach((layer) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = layer;
    button.addEventListener("click", () => {
      state.layer = layer;
      renderLayers();
      renderMap();
      playSound("map_select");
    });
    els.layerTabs.append(button);
  });
  updateLayerButtons();
}

function updateLayerButtons() {
  [...els.layerTabs.children].forEach((button) => {
    button.classList.toggle("active", button.textContent === state.layer);
  });
}

function renderGame(game) {
  if (!game) {
    els.caseClock.textContent = "-";
    els.caseStatus.textContent = "Ready";
    els.checksRemaining.textContent = "-";
    return;
  }
  els.caseClock.textContent = `${game.turn}/${game.max_turns}`;
  els.caseStatus.textContent = game.result ? game.result.replace("_", " ") : "In progress";
  els.checksRemaining.textContent = String(game.checks_remaining);
}

function renderMap() {
  updateLayerButtons();
  const nextSrc = `/assets/maps/${state.layer}`;
  if (!els.mapImage.src.endsWith(nextSrc)) {
    els.mapImage.src = nextSrc;
  }
}

function renderMapOverlays() {
  els.selectionLayer.innerHTML = "";
  els.witnessLayer.innerHTML = "";

  for (const junctionId of state.selected) {
    const junction = junctionById(junctionId);
    if (!junction) {
      continue;
    }
    const pin = document.createElement("div");
    pin.className = `junction-pin${junctionId === state.focused ? " focused" : ""}`;
    pin.textContent = junctionId;
    placeAtMapPoint(pin, junction.x, junction.y);
    els.selectionLayer.append(pin);
  }

  for (const witness of state.witnesses) {
    const junction = junctionById(witness.junction_id);
    if (!junction) {
      continue;
    }
    const pin = document.createElement("article");
    const card = cardById(witness.sample_witness_id);
    const data = card || {
      id: witness.sample_witness_id,
      junction_id: witness.junction_id,
      style: witness.sample_style,
      summary: witness.sample_summary,
      relevance: witness.sample_relevance,
      memory: null,
      reliability: null,
      questions: [],
    };
    const profile = witnessProfile(data.id || `j${witness.junction_id}`);
    pin.dataset.junctionId = String(witness.junction_id);

    if (state.expandedWitnessJunction === witness.junction_id) {
      pin.className = "witness-popup expanded";
      pin.innerHTML = witnessCardMarkup(data, witness, profile);
    } else {
      pin.className = "witness-pin";
      pin.innerHTML = `
        <span class="anon-avatar ${profile.gender}" aria-hidden="true"></span>
        <strong>${witness.count}</strong>
      `;
    }
    placeAtMapPoint(pin, junction.x, junction.y);
    els.witnessLayer.append(pin);
  }
}

function renderTray() {
  els.blockadeTray.innerHTML = "";
  els.blockadeTray.classList.toggle("open", Boolean(state.focused));
  if (!state.focused) {
    return;
  }

  const title = document.createElement("div");
  title.className = "tray-title";
  title.innerHTML = `<span>J${state.focused}</span><span>${state.selected.length} marked</span>`;
  els.blockadeTray.append(title);

  const modeGrid = document.createElement("div");
  modeGrid.className = "mode-grid";
  const lock = button("Lock junction", "danger", () => addBlock({ block_type: "junction_block" }));
  modeGrid.append(lock);
  ["taxi", "bus", "subway"].forEach((mode) => {
    modeGrid.append(button(`Jam ${mode}`, "", () => addBlock({ block_type: "mode_block", mode })));
  });
  els.blockadeTray.append(modeGrid);

  if (state.legalMoves.length) {
    const routes = document.createElement("div");
    routes.className = "route-grid";
    state.legalMoves.slice(0, 12).forEach((move) => {
      const label = `J${move.destination} ${move.mode}`;
      routes.append(button(label, move.blocked ? "" : "danger", () => {
        addBlock({ block_type: "edge_block", to_junction: move.destination, mode: move.mode });
      }));
    });
    els.blockadeTray.append(routes);
  }
}

function renderLookout(lookout) {
  if (!lookout || !lookout.raised) {
    els.lookoutMeta.textContent = "No witness pins yet.";
    return;
  }
  const review = lookout.review_allowed ? "cards open" : "crowd only";
  els.lookoutMeta.textContent = `${lookout.witness_count} witnesses, ${review}.`;
}

function renderWitnessCards(filterJunction = null) {
  els.witnessCards.innerHTML = "";
  const cards = filterJunction
    ? state.witnessCards.filter((card) => card.junction_id === filterJunction)
    : state.witnessCards;

  if (!cards.length) {
    const empty = document.createElement("div");
    empty.className = "witness-card";
    empty.innerHTML = "<strong>Map reports only</strong><p>Witness reports are pinned on the map.</p>";
    els.witnessCards.append(empty);
    return;
  }

  cards.forEach((card) => {
    const node = document.createElement("article");
    node.className = "witness-card";
    const profile = witnessProfile(card.id);
    node.innerHTML = `
      <div class="witness-id">
        <span class="anon-avatar ${profile.gender}" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(profile.label)}</strong>
          <span>J${card.junction_id} / ${escapeHtml(card.style)}</span>
        </div>
      </div>
      <p>${escapeHtml(profile.detail)}</p>
      <p>${escapeHtml(card.summary)}</p>
      <p>Rel ${card.relevance.toFixed(2)} / Mem ${card.memory.toFixed(2)}</p>
    `;
    if (card.questions?.length) {
      const latest = card.questions[card.questions.length - 1];
      const qa = document.createElement("div");
      qa.className = "witness-qa";
      qa.innerHTML = `
        <span>${escapeHtml(latest.question)}</span>
        <p>${escapeHtml(latest.answer)}</p>
      `;
      node.append(qa);
    }
    const ask = button("Ask", "", null);
    ask.dataset.action = "ask-witness";
    ask.dataset.witnessId = card.id;
    ask.dataset.junctionId = String(card.junction_id);
    node.append(ask);
    els.witnessCards.append(node);
  });
}

function handleWitnessClick(event) {
  const askButton = event.target.closest("[data-action='ask-witness']");
  if (askButton) {
    event.preventDefault();
    event.stopPropagation();
    askWitness(askButton.dataset.witnessId, Number(askButton.dataset.junctionId) || null);
    return;
  }

  const witnessNode = event.target.closest("[data-junction-id]");
  if (!witnessNode) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  expandWitnessLocation(Number(witnessNode.dataset.junctionId));
}

async function addBlock(detail) {
  if (!state.gameId) {
    return flash("Open a case first.", "map_select");
  }
  const snapshot = await api("add_block", payload(detail));
  applySnapshot(snapshot);
}

async function askWitness(witnessId, filterJunction = null) {
  const snapshot = await api("ask_witness", payload({ witness_id: witnessId, question: "Which direction were they moving?" }));
  if (filterJunction) {
    state.expandedWitnessJunction = filterJunction;
  }
  applySnapshot(snapshot);
  if (filterJunction) {
    expandWitnessLocation(filterJunction, false, true);
  }
}

function openWitnessDrawer(filterJunction = null) {
  els.witnessDrawer.classList.add("open");
  renderWitnessCards(filterJunction);
}

function focusWitnessLocation(junctionId) {
  expandWitnessLocation(junctionId);
  openWitnessDrawer(junctionId);
}

function expandWitnessLocation(junctionId, makeNoise = true, forceOpen = false) {
  state.focused = junctionId;
  state.expandedWitnessJunction = forceOpen || state.expandedWitnessJunction !== junctionId ? junctionId : null;
  renderMapOverlays();
  renderTray();
  if (makeNoise) {
    playSound("witness_popup");
  }
}

function startPointer(event) {
  if (shouldIgnoreMapPointer(event)) {
    return;
  }
  if (!els.mapImage.naturalWidth) {
    return;
  }
  els.mapWrap.setPointerCapture(event.pointerId);
  const point = naturalPointFromEvent(event);
  state.pointer = {
    id: event.pointerId,
    start: point,
    points: point ? [point] : [],
    moved: false,
  };
}

function movePointer(event) {
  if (shouldIgnoreMapPointer(event)) {
    return;
  }
  if (!state.pointer || state.pointer.id !== event.pointerId) {
    return;
  }
  const point = naturalPointFromEvent(event);
  if (!point) {
    return;
  }
  const distance = Math.hypot(point.x - state.pointer.start.x, point.y - state.pointer.start.y);
  if (distance > 16) {
    state.pointer.moved = true;
  }
  state.pointer.points.push(point);
}

async function endPointer(event) {
  if (shouldIgnoreMapPointer(event)) {
    state.pointer = null;
    return;
  }
  if (!state.pointer || state.pointer.id !== event.pointerId) {
    return;
  }
  const pointer = state.pointer;
  state.pointer = null;
  const point = naturalPointFromEvent(event);
  if (point) {
    pointer.points.push(point);
  }

  if (pointer.moved) {
    const dragged = junctionsNearPath(pointer.points);
    for (const junctionId of dragged) {
      if (!state.selected.includes(junctionId)) {
        state.selected.push(junctionId);
      }
    }
    if (dragged.length) {
      state.focused = dragged[dragged.length - 1];
    }
  } else if (point) {
    const junctionId = nearestJunction(point);
    if (junctionId) {
      if (state.selected.includes(junctionId)) {
        state.selected = state.selected.filter((item) => item !== junctionId);
      } else {
        state.selected = [...state.selected, junctionId];
      }
      state.focused = junctionId;
    }
  }

  renderMapOverlays();
  renderTray();
  const snapshot = await api("select_junctions", payload());
  applySnapshot(snapshot);
}

function cancelPointer() {
  state.pointer = null;
}

function shouldIgnoreMapPointer(event) {
  return Boolean(event.target.closest(".witness-pin, .witness-popup, .witness-drawer, button, textarea"));
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

function junctionsNearPath(points) {
  const found = [];
  for (const point of points) {
    for (const junction of state.map.junctions) {
      if (found.includes(junction.id)) {
        continue;
      }
      if (Math.hypot(point.x - junction.x, point.y - junction.y) <= 64) {
        found.push(junction.id);
      }
    }
  }
  return found;
}

function naturalPointFromEvent(event) {
  const rect = imageContentRect();
  if (!rect || event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) {
    return null;
  }
  return {
    x: ((event.clientX - rect.left) / rect.width) * els.mapImage.naturalWidth,
    y: ((event.clientY - rect.top) / rect.height) * els.mapImage.naturalHeight,
  };
}

function placeAtMapPoint(node, x, y) {
  const wrapRect = els.mapWrap.getBoundingClientRect();
  const rect = imageContentRect();
  if (!rect || !wrapRect.width || !wrapRect.height) {
    return;
  }
  const left = rect.left - wrapRect.left + (x / els.mapImage.naturalWidth) * rect.width;
  const top = rect.top - wrapRect.top + (y / els.mapImage.naturalHeight) * rect.height;
  node.style.left = `${left}px`;
  node.style.top = `${top}px`;
}

function imageContentRect() {
  const box = els.mapImage.getBoundingClientRect();
  if (!els.mapImage.naturalWidth || !els.mapImage.naturalHeight || !box.width || !box.height) {
    return null;
  }
  const imageRatio = els.mapImage.naturalWidth / els.mapImage.naturalHeight;
  const boxRatio = box.width / box.height;
  let width = box.width;
  let height = box.height;
  let left = box.left;
  let top = box.top;
  if (boxRatio > imageRatio) {
    width = height * imageRatio;
    left += (box.width - width) / 2;
  } else {
    height = width / imageRatio;
    top += (box.height - height) / 2;
  }
  return { left, top, width, height, right: left + width, bottom: top + height };
}

function junctionById(junctionId) {
  return state.map.junctions.find((junction) => junction.id === junctionId);
}

function button(label, className, onClick) {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = label;
  if (className) {
    node.className = className;
  }
  if (onClick) {
    node.addEventListener("click", onClick);
  }
  return node;
}

function witnessCardMarkup(card, witness, profile) {
  const latest = card.questions?.length ? card.questions[card.questions.length - 1] : null;
  const metrics = card.memory != null && card.reliability != null
    ? `Rel ${Number(card.relevance).toFixed(2)} / Mem ${Number(card.memory).toFixed(2)}`
    : `${witness.count} ${witness.count === 1 ? "report" : "reports"}`;
  const askMarkup = witness.inspectable && card.id
    ? `<button type="button" data-action="ask-witness" data-witness-id="${escapeHtml(card.id)}" data-junction-id="${witness.junction_id}">Ask</button>`
    : "";
  const answerMarkup = latest
    ? `<div class="witness-qa"><span>${escapeHtml(latest.question)}</span><p>${escapeHtml(latest.answer)}</p></div>`
    : "";
  return `
    <div class="witness-id">
      <span class="anon-avatar ${profile.gender}" aria-hidden="true"></span>
      <div>
        <strong>${escapeHtml(profile.label)}</strong>
        <span>ID J${witness.junction_id} / ${escapeHtml(card.style || "witness")}</span>
      </div>
    </div>
    <p>${escapeHtml(profile.detail)}</p>
    <p><b>Claims:</b> ${escapeHtml(shortSummary(card.summary))}</p>
    <span>${metrics}</span>
    ${answerMarkup}
    ${askMarkup}
  `;
}

function cardById(witnessId) {
  return state.witnessCards.find((card) => card.id === witnessId);
}

function witnessProfile(witnessId) {
  const hash = String(witnessId || "").split("").reduce((total, char) => total + char.charCodeAt(0), 0);
  const gender = hash % 2 === 0 ? "female" : "male";
  const labels = gender === "female"
    ? ["Anonymous woman", "Unknown commuter", "Street witness"]
    : ["Anonymous man", "Unknown passer-by", "Street witness"];
  const details = gender === "female"
    ? ["dark coat, pinned hair, steady voice", "market satchel, rain collar, watchful", "tram ticket stub, careful answers"]
    : ["flat cap, rain collar, ink-stained fingers", "work coat, tired eyes, quick answers", "paper folded in pocket, cautious"];
  return {
    gender,
    label: labels[hash % labels.length],
    detail: details[hash % details.length],
  };
}

function flash(message, sound) {
  els.eventTicker.textContent = message;
  playSound(sound);
}

let audioContext = null;

function playSound(name) {
  if (!state.sound) {
    return;
  }
  audioContext ||= new AudioContext();
  const now = audioContext.currentTime;
  const gain = audioContext.createGain();
  gain.connect(audioContext.destination);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);

  const tones = {
    map_select: [220, 0.12, "triangle"],
    blockade_set: [96, 0.2, "square"],
    lookout_raise: [330, 0.24, "sawtooth"],
    witness_popup: [520, 0.18, "sine"],
    turn_advance: [160, 0.3, "triangle"],
  };
  const [frequency, duration, type] = tones[name] || tones.map_select;
  const oscillator = audioContext.createOscillator();
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, now);
  oscillator.frequency.exponentialRampToValueAtTime(frequency * 1.35, now + duration);
  oscillator.connect(gain);
  oscillator.start(now);
  oscillator.stop(now + duration);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortSummary(value) {
  const clean = String(value || "Report received.").replace(/\s+/g, " ").trim();
  if (clean.length <= 126) {
    return clean;
  }
  return `${clean.slice(0, 123)}...`;
}

boot().catch((error) => {
  els.eventTicker.textContent = error.message;
});
