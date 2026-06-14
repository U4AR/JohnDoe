const DEFAULT_NOTICE = "Request high-confidence reports of a grey raincoat carrying a red folder at the selected junction.";
const DEFAULT_FOCUSED_JUNCTION = 100;

const ASSET = "/static/assets/reference/";
const ASSET_VERSION = "20260614-complete-icons-v3";

function assetUrl(filename) {
  return `${ASSET}${filename}?v=${ASSET_VERSION}`;
}

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
    preview: "Deters the suspect AND files a high-reliability sighting if they pass through or near this junction.",
    details: "The culprit avoids this junction. If they still pass through or next to it, the patrol officer files a witness report.",
  },
  search_team: {
    label: "Search Team",
    countLabel: "2 units",
    icon: "icon_search_team.png",
    pin: "pin_search_team.png",
    preview: "Stakes out this junction. If the suspect passes through, the case ends instantly.",
    details: "Wins the case if the culprit is at this junction at any point during the next turn.",
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

const LAYER_Y_OFFSET = {
  normal: 0,
  taxi: 86,
  bus: 86,
  subway: 86,
};

const LAYER_MODE = {
  taxi: "taxi",
  bus: "bus",
  subway: "subway",
};

function currentLayerYOffset() {
  return LAYER_Y_OFFSET[state.layer] || 0;
}

const els = {
  caseClock: document.querySelector("#caseClock"),
  turnPhase: document.querySelector("#turnPhase"),
  settingsButton: document.querySelector("#settingsButton"),
  newCaseButton: document.querySelector("#newCaseButton"),
  stopGameButton: document.querySelector("#stopGameButton"),
  restartGameButton: document.querySelector("#restartGameButton"),
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
  notesText: document.querySelector("#notesText"),
  notesStatus: document.querySelector("#notesStatus"),
  statementList: document.querySelector("#statementList"),
  eventTicker: document.querySelector("#eventTicker"),
  detailPopup: document.querySelector("#detailPopup"),
  wantedDescription: document.querySelector("#wantedDescription"),
  wantedLastSeen: document.querySelector("#wantedLastSeen"),
  wantedAlias: document.querySelector("#wantedAlias"),
  gameTitle: document.querySelector("#gameTitle"),
  gameSubtitle: document.querySelector("#gameSubtitle"),
  zoomOutButton: document.querySelector("#zoomOutButton"),
  zoomInButton: document.querySelector("#zoomInButton"),
  zoomResetButton: document.querySelector("#zoomResetButton"),
  zoomValue: document.querySelector("#zoomValue"),
  toggleWitnessesButton: document.querySelector("#toggleWitnessesButton"),
  toggleTacticsButton: document.querySelector("#toggleTacticsButton"),
  toggleFocusButton: document.querySelector("#toggleFocusButton"),
  witnessModeButton: document.querySelector("#witnessModeButton"),
  settingsDialog: document.querySelector("#settingsDialog"),
  settingsCloseButton: document.querySelector("#settingsCloseButton"),
  soundSetting: document.querySelector("#soundSetting"),
  difficultySetting: document.querySelector("#difficultySetting"),
  providerSetting: document.querySelector("#providerSetting"),
  customModelSettings: document.querySelector("#customModelSettings"),
  llamaConnectionSettings: document.querySelector("#llamaConnectionSettings"),
  externalServerHint: document.querySelector("#externalServerHint"),
  modelPathSetting: document.querySelector("#modelPathSetting"),
  serverBinSetting: document.querySelector("#serverBinSetting"),
  baseUrlSetting: document.querySelector("#baseUrlSetting"),
  llmModelSetting: document.querySelector("#llmModelSetting"),
  gatewayUrlSetting: document.querySelector("#gatewayUrlSetting"),
  launcherPathSetting: document.querySelector("#launcherPathSetting"),
  comniCheckoutSetting: document.querySelector("#comniCheckoutSetting"),
  omniRootSetting: document.querySelector("#omniRootSetting"),
  modelDirSetting: document.querySelector("#modelDirSetting"),
  quantizationSetting: document.querySelector("#quantizationSetting"),
  contextLengthSetting: document.querySelector("#contextLengthSetting"),
  gpuLayersSetting: document.querySelector("#gpuLayersSetting"),
  voiceDirSetting: document.querySelector("#voiceDirSetting"),
  llamaStatusText: document.querySelector("#llamaStatusText"),
  settingsSaveButton: document.querySelector("#settingsSaveButton"),
  llamaStartButton: document.querySelector("#llamaStartButton"),
  llamaRestartButton: document.querySelector("#llamaRestartButton"),
  llamaStopButton: document.querySelector("#llamaStopButton"),
  noticeDialog: document.querySelector("#noticeDialog"),
  noticeCloseButton: document.querySelector("#noticeCloseButton"),
  noticeCancelButton: document.querySelector("#noticeCancelButton"),
  noticeJunctionLabel: document.querySelector("#noticeJunctionLabel"),
  noticeText: document.querySelector("#noticeText"),
  raiseLookoutButton: document.querySelector("#raiseLookoutButton"),
  lookoutMeta: document.querySelector("#lookoutMeta"),
  witnessDialog: document.querySelector("#witnessDialog"),
  witnessCloseButton: document.querySelector("#witnessCloseButton"),
  witnessName: document.querySelector("#witnessName"),
  witnessProfile: document.querySelector("#witnessProfile"),
  witnessSummary: document.querySelector("#witnessSummary"),
  witnessTranscript: document.querySelector("#witnessTranscript"),
  witnessConnection: document.querySelector("#witnessConnection"),
  witnessMessage: document.querySelector("#witnessMessage"),
  sendWitnessMessage: document.querySelector("#sendWitnessMessage"),
  autoSpeechButton: document.querySelector("#autoSpeechButton"),
  pushToTalkButton: document.querySelector("#pushToTalkButton"),
  stopAudioButton: document.querySelector("#stopAudioButton"),
  micLevel: document.querySelector("#micLevel"),
  storyDialog: document.querySelector("#storyDialog"),
  storyCloseButton: document.querySelector("#storyCloseButton"),
  storyTimeline: document.querySelector("#storyTimeline"),
  storyFooter: document.querySelector("#storyFooter"),
  caseIntroDialog: document.querySelector("#caseIntroDialog"),
  caseIntroTitle: document.querySelector("#caseIntroTitle"),
  caseIntroKicker: document.querySelector("#caseIntroKicker"),
  caseIntroCrime: document.querySelector("#caseIntroCrime"),
  caseIntroNarrative: document.querySelector("#caseIntroNarrative"),
  caseIntroStolen: document.querySelector("#caseIntroStolen"),
  caseIntroVictim: document.querySelector("#caseIntroVictim"),
  caseIntroAlias: document.querySelector("#caseIntroAlias"),
  caseIntroDescription: document.querySelector("#caseIntroDescription"),
  caseIntroSightings: document.querySelector("#caseIntroSightings"),
  beginInvestigationButton: document.querySelector("#beginInvestigationButton"),
  setupOverlay: document.querySelector("#setupOverlay"),
  setupTitle: document.querySelector("#setupTitle"),
  setupMessage: document.querySelector("#setupMessage"),
  setupProgress: document.querySelector("#setupProgress"),
  setupProgressText: document.querySelector("#setupProgressText"),
  setupStartButton: document.querySelector("#setupStartButton"),
  setupSettingsButton: document.querySelector("#setupSettingsButton"),
  setupPicker: document.querySelector("#setupPicker"),
  pickerQuantization: document.querySelector("#pickerQuantization"),
  pickerDevice: document.querySelector("#pickerDevice"),
  pickerGpuLayers: document.querySelector("#pickerGpuLayers"),
  pickerContext: document.querySelector("#pickerContext"),
  pickerDeviceHint: document.querySelector("#pickerDeviceHint"),
  pickerQuantHint: document.querySelector("#pickerQuantHint"),
  gpuDeviceSetting: document.querySelector("#gpuDeviceSetting"),
  witnessChatTtsSetting: document.querySelector("#witnessChatTtsSetting"),
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
  game: null,
  notesDirty: false,
  notesTimer: null,
  activeWitness: null,
  witnessSocket: null,
  mediaStream: null,
  captureContext: null,
  captureNode: null,
  speechMode: null,
  pushRecording: false,
  pushDrainUntil: 0,
  playbackContext: null,
  playbackSources: [],
  playbackTime: 0,
  setup: null,
  setupTimer: null,
  runtimeOptions: null,
  pickerHydrated: false,
  activeIntroGameId: null,
  mapVisibility: { witnesses: true, tactics: true, focus: true },
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
  const requestedGameId = new URLSearchParams(window.location.search).get("game_id");
  const snapshotUrl = requestedGameId
    ? `/api/snapshot?game_id=${encodeURIComponent(requestedGameId)}`
    : "/api/snapshot";
  const snapshot = await fetch(snapshotUrl).then((response) => response.json());
  applySnapshot(snapshot, false);
  showOpeningForFreshCase(snapshot);
  if (!state.gameId) flash("Preparing the local AI runtime...", "map_select", false);
  renderLegend();
  ensureLocalAI();
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
  els.stopGameButton.addEventListener("click", () => finishGame("stopped"));
  els.restartGameButton.addEventListener("click", () => restartGame());
  els.settingsButton.addEventListener("click", openSettings);
  els.advanceButton.addEventListener("click", async () => {
    if (!state.gameId) return openNewCase(true);
    beginTurnProcessing();
    try {
      const snapshot = await api("advance_turn", payload());
      playSound("turn_advance");
      if (snapshot?.sound && snapshot.sound !== "turn_advance") playSound(snapshot.sound);
      applySnapshot(snapshot, false);
    } finally {
      endTurnProcessing();
    }
  });
  els.raiseLookoutButton.addEventListener("click", publishNotice);
  els.noticeCloseButton.addEventListener("click", () => els.noticeDialog.close());
  els.noticeCancelButton.addEventListener("click", () => els.noticeDialog.close());
  els.notesText.addEventListener("input", scheduleNotesSave);

  els.mapWrap.addEventListener("click", handleMapClick);
  els.mapWrap.addEventListener("pointerdown", startMapPan);
  els.mapWrap.addEventListener("dragover", (event) => event.preventDefault());
  els.mapWrap.addEventListener("drop", handleMapDrop);
  els.mapWrap.addEventListener("wheel", handleMapWheel, { passive: false });
  els.zoomOutButton.addEventListener("click", () => zoomBy(0.86));
  els.zoomInButton.addEventListener("click", () => zoomBy(1.16));
  els.zoomResetButton.addEventListener("click", () => resetMapView(true));
  els.toggleWitnessesButton.addEventListener("click", () => toggleMapVisibility("witnesses"));
  els.toggleTacticsButton.addEventListener("click", () => toggleMapVisibility("tactics"));
  els.toggleFocusButton.addEventListener("click", () => toggleMapVisibility("focus"));
  els.witnessModeButton.addEventListener("click", enableWitnessMode);
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
  els.providerSetting.addEventListener("change", renderBackendFields);
  els.llamaStartButton.addEventListener("click", () => runLlamaAction("start"));
  els.llamaRestartButton.addEventListener("click", () => runLlamaAction("restart"));
  els.llamaStopButton.addEventListener("click", () => runLlamaAction("stop"));
  els.setupStartButton.addEventListener("click", handleSetupStart);
  els.setupSettingsButton.addEventListener("click", openSettings);
  els.witnessCloseButton.addEventListener("click", closeWitnessInterview);
  els.sendWitnessMessage.addEventListener("click", sendWitnessText);
  els.witnessMessage.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendWitnessText(); }
  });
  els.autoSpeechButton.addEventListener("click", toggleAutoSpeech);
  els.pushToTalkButton.addEventListener("pointerdown", startPushToTalk);
  els.pushToTalkButton.addEventListener("pointerup", stopPushToTalk);
  els.pushToTalkButton.addEventListener("pointercancel", stopPushToTalk);
  window.addEventListener("pointerup", () => { if (state.pushRecording) stopPushToTalk(); });
  els.stopAudioButton.addEventListener("click", stopPlayback);
  els.storyCloseButton.addEventListener("click", () => els.storyDialog.close());
  els.beginInvestigationButton.addEventListener("click", dismissCaseIntroduction);
}

async function ensureLocalAI() {
  clearTimeout(state.setupTimer);
  try {
    const setup = await fetch("/api/setup/status").then((response) => response.json());
    if (!state.runtimeOptions) await loadRuntimeOptions();
    renderSetup(setup);
    if (setup.service_ready) return;
    // Files-ready but service not running: bring it up automatically with the
    // settings the user already picked. We do NOT auto-start the heavy download
    // — that waits for the user to confirm picker choices.
    if (setup.files_ready && !setup.installing) {
      const restarted = await fetch("/api/setup/start", { method: "POST" }).then((response) => response.json());
      renderSetup(restarted);
    }
    const next = setup.installing || setup.files_ready ? 2000 : 4000;
    state.setupTimer = setTimeout(ensureLocalAI, next);
  } catch (error) {
    renderSetup({ state: "error", message: error.message || "Setup status could not be read.", progress: 0 });
  }
}

async function loadRuntimeOptions() {
  try {
    const data = await fetch("/api/runtime/options").then((response) => response.json());
    state.runtimeOptions = data;
    populatePicker(data);
  } catch (error) {
    els.pickerDeviceHint.textContent = error.message || "Could not detect runtime options; using defaults.";
  }
}

function populatePicker(options) {
  if (!options || state.pickerHydrated) return;
  const current = options.current || {};
  fillSelect(els.pickerQuantization, options.quantizations || [], (item) => ({
    value: item.id, label: item.label, selected: item.id === current.minicpm_quantization,
  }));
  fillSelect(els.pickerDevice, options.devices || [], (item) => ({
    value: item.id, label: item.label, selected: item.id === current.minicpm_gpu_device,
  }));
  fillSelect(els.pickerGpuLayers, options.gpu_layer_presets || [], (item) => ({
    value: item.id, label: item.label, selected: String(item.id) === String(current.llamacpp_gpu_layers),
  }));
  fillSelect(els.pickerContext, options.context_length_presets || [], (item) => ({
    value: String(item.id), label: item.label, selected: Number(item.id) === Number(current.llamacpp_context_length),
  }));
  // Mirror the GPU-device dropdown in the settings dialog using the same list.
  fillSelect(els.gpuDeviceSetting, options.devices || [], (item) => ({
    value: item.id, label: item.label, selected: item.id === current.minicpm_gpu_device,
  }));
  state.pickerHydrated = true;
}

function fillSelect(select, items, mapper) {
  if (!select) return;
  select.innerHTML = "";
  items.forEach((item) => {
    const { value, label, selected } = mapper(item);
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = label;
    if (selected) option.selected = true;
    select.append(option);
  });
}

function renderSetup(setup) {
  state.setup = setup;
  const ready = Boolean(setup.service_ready);
  const installing = Boolean(setup.installing) || (setup.files_ready && !setup.service_ready) || setup.state === "running";
  const errored = setup.state === "error";
  // Show the picker only at the moment when nothing is downloading or running.
  // Once setup is in flight, hide it so the progress UI takes over.
  const showPicker = !ready && !installing && !errored && Boolean(state.runtimeOptions);

  els.setupOverlay.classList.toggle("ready", ready);
  els.setupOverlay.hidden = Boolean(state.gameId);
  els.setupPicker.hidden = !showPicker;
  els.setupProgress.hidden = showPicker;
  els.setupProgressText.hidden = showPicker;
  els.setupProgress.value = Number(setup.progress || 0);
  els.setupMessage.textContent = setup.message || "Preparing the local AI runtime...";
  els.setupProgressText.textContent = ready ? "Everything is ready" : `${Math.round(setup.progress || 0)}% - ${setup.stage || "setup"}`;

  if (ready) {
    els.setupTitle.textContent = "The Investigation Desk Is Ready";
    els.setupStartButton.textContent = "Start Game";
    els.setupStartButton.disabled = false;
    return;
  }
  if (errored) {
    els.setupTitle.textContent = "Local AI Setup Needs Attention";
    els.setupStartButton.textContent = "Retry Setup";
    els.setupStartButton.disabled = false;
    return;
  }
  if (showPicker) {
    els.setupTitle.textContent = "Set Up Your Local AI";
    els.setupStartButton.textContent = "Download & Install With These Settings";
    els.setupStartButton.disabled = false;
    return;
  }
  els.setupTitle.textContent = setup.files_ready ? "Starting Local AI" : "Preparing Your Investigation Desk";
  els.setupStartButton.textContent = setup.files_ready ? "Loading Model..." : "Downloading and Installing...";
  els.setupStartButton.disabled = true;
}

function pickerPayload() {
  return {
    minicpm_quantization: els.pickerQuantization?.value || undefined,
    minicpm_gpu_device: els.pickerDevice?.value || undefined,
    llamacpp_gpu_layers: els.pickerGpuLayers?.value || undefined,
    llamacpp_context_length: els.pickerContext?.value ? Number(els.pickerContext.value) : undefined,
  };
}

async function handleSetupStart() {
  if (state.setup?.service_ready) {
    els.setupStartButton.disabled = true;
    els.setupStartButton.textContent = "Opening Case...";
    await openNewCase(true);
    if (state.gameId) els.setupOverlay.hidden = true;
    return;
  }
  els.setupStartButton.disabled = true;
  els.setupStartButton.textContent = "Starting...";
  // If the picker is visible, post the chosen options. Otherwise this is a
  // retry or service-restart — backend uses whatever's already in .env.
  const payload = els.setupPicker.hidden ? {} : pickerPayload();
  try {
    await fetch("/api/setup/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    flash(error.message || "Could not start setup.", "map_select");
  }
  ensureLocalAI();
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
  els.providerSetting.value = settings.llm_provider || "minicpm_omni";
  els.modelPathSetting.value = settings.llamacpp_model_path || "";
  els.serverBinSetting.value = settings.llamacpp_server_bin || "";
  els.baseUrlSetting.value = settings.llamacpp_base_url || "http://127.0.0.1:8080/v1";
  els.llmModelSetting.value = settings.llm_model || "";
  renderBackendFields();
  els.gatewayUrlSetting.value = settings.omni_gateway_url || "http://127.0.0.1:8006";
  els.launcherPathSetting.value = settings.omni_launcher_path || "";
  els.comniCheckoutSetting.value = settings.comni_checkout_path || "";
  els.omniRootSetting.value = settings.llamacpp_omni_root || "";
  els.modelDirSetting.value = settings.minicpm_model_dir || "";
  els.contextLengthSetting.value = String(settings.llamacpp_context_length || 8192);
  els.gpuLayersSetting.value = settings.llamacpp_gpu_layers || "auto";
  els.voiceDirSetting.value = settings.witness_voice_dir || "";
  if (state.runtimeOptions?.devices && !els.gpuDeviceSetting.options.length) {
    fillSelect(els.gpuDeviceSetting, state.runtimeOptions.devices, (item) => ({
      value: item.id, label: item.label, selected: item.id === (settings.minicpm_gpu_device || "auto"),
    }));
  } else {
    els.gpuDeviceSetting.value = settings.minicpm_gpu_device || "auto";
  }
  els.witnessChatTtsSetting.value = settings.witness_chat_tts === false ? "0" : "1";
  const models = data.model_scan?.models || [];
  els.quantizationSetting.innerHTML = models.length ? "" : '<option value="">No compatible models found</option>';
  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.filename;
    option.textContent = `${model.quantization} (${formatBytes(model.size_bytes)})`;
    option.selected = model.filename === settings.minicpm_quantization;
    els.quantizationSetting.append(option);
  });
  renderLlamaStatus(data.llama || data.omni, settings);
}

function settingsPayload() {
  return {
    llm_provider: els.providerSetting.value,
    llamacpp_model_path: els.modelPathSetting.value,
    llamacpp_server_bin: els.serverBinSetting.value,
    llamacpp_base_url: els.baseUrlSetting.value,
    llm_model: els.llmModelSetting.value,
    difficulty: els.difficultySetting.value,
    omni_gateway_url: els.gatewayUrlSetting.value,
    omni_launcher_path: els.launcherPathSetting.value,
    comni_checkout_path: els.comniCheckoutSetting.value,
    llamacpp_omni_root: els.omniRootSetting.value,
    minicpm_model_dir: els.modelDirSetting.value,
    minicpm_quantization: els.quantizationSetting.value,
    llamacpp_context_length: Number(els.contextLengthSetting.value),
    llamacpp_gpu_layers: els.gpuLayersSetting.value,
    minicpm_gpu_device: els.gpuDeviceSetting.value,
    witness_chat_tts: els.witnessChatTtsSetting.value === "1",
    witness_voice_dir: els.voiceDirSetting.value,
  };
}

function renderBackendFields() {
  const managed = els.providerSetting.value === "llama_cpp_server";
  const external = els.providerSetting.value === "external_llama_cpp_server";
  els.customModelSettings.hidden = !managed;
  els.llamaConnectionSettings.hidden = !(managed || external);
  els.externalServerHint.hidden = !external;
  els.llmModelSetting.disabled = managed;
  els.llamaStartButton.disabled = external;
  els.llamaRestartButton.disabled = external;
  els.llamaStopButton.disabled = external;
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
    renderLlamaStatus(data.llama || data.omni, data.settings || state.settings || {});
    flash(data.event || "AI backend status updated.", data.ok ? "blockade_set" : "map_select");
  } catch (error) {
    flash(error.message || "Could not control the AI backend.", "map_select");
  }
}

function renderLlamaStatus(llama, settings) {
  const custom = settings.llm_provider === "llama_cpp_server";
  const external = settings.llm_provider === "external_llama_cpp_server";
  const backend = custom || external ? (settings.llm_model || "llama.cpp") : "OpenBMB MiniCPM-o";
  const launcher = external
    ? "user-managed server"
    : custom
    ? (settings.llamacpp_model_exists && settings.llamacpp_server_bin_exists ? "model and server paths ok" : "model or server path missing")
    : (settings.omni_launcher_exists ? "launcher path ok" : "launcher path missing");
  const reach = llama?.ready ? "ready" : llama?.reachable ? "reachable, not ready" : "not reachable";
  const pid = llama?.pid ? ` PID ${llama.pid}` : "";
  let detail = typeof llama?.detail === "string" ? llama.detail : "";
  if (!detail && (custom || external) && Array.isArray(llama?.detail?.data)) {
    detail = `${llama.detail.data.length} model${llama.detail.data.length === 1 ? "" : "s"} loaded`;
  } else if (!detail && llama?.detail?.workers) {
    const workers = llama.detail.workers;
    detail = `${workers.idle_workers || 0} of ${workers.total_workers || 0} workers idle`;
  }
  els.llamaStatusText.textContent = `${backend}: ${reach}${pid}. ${launcher}. Context ${settings.llamacpp_context_length || 8192}; GPU layers ${settings.llamacpp_gpu_layers || "auto"}. ${detail}`;
}

async function openNewCase(makeNoise) {
  closePopup();
  try {
    const snapshot = await api("new_case", {});
    applySnapshot(snapshot, makeNoise);
    state.selected = [DEFAULT_FOCUSED_JUNCTION];
    state.focused = DEFAULT_FOCUSED_JUNCTION;
    applySnapshot(await api("select_junctions", payload()), makeNoise);
    showCaseIntroduction(snapshot.case_introduction, snapshot.game?.initial_description, snapshot.game?.game_id, true);
  } catch (error) {
    flash(error.message || "MiniCPM-o must be ready before a case can start.", "map_select");
    await openSettings();
  }
}

function showOpeningForFreshCase(snapshot) {
  if (!snapshot?.game || snapshot.game.turn !== 1 || snapshot.game.result || snapshot.game.phase === "complete") return;
  showCaseIntroduction(
    snapshot.case_introduction,
    snapshot.game.initial_description,
    snapshot.game.game_id,
  );
}

function introSeenKey(gameId) {
  return `phantomGridIntroSeen:${gameId}`;
}

function showCaseIntroduction(intro, description, gameId, force = false) {
  if (!intro || !els.caseIntroDialog) return;
  if (!force && gameId && sessionStorage.getItem(introSeenKey(gameId)) === "1") return;
  state.activeIntroGameId = gameId || state.gameId;
  els.caseIntroTitle.textContent = intro.case_title || "A New Case";
  els.caseIntroKicker.textContent = intro.kicker || "A thief has vanished into London.";
  els.caseIntroCrime.textContent = titleCase(intro.crime || "A daring theft");
  els.caseIntroNarrative.textContent = intro.narrative || "The trail is already growing cold.";
  els.caseIntroStolen.textContent = intro.stolen_item || "Unknown valuables";
  els.caseIntroVictim.textContent = intro.victim || "Name withheld";
  els.caseIntroAlias.textContent = intro.culprit_alias || "John Doe";
  els.caseIntroDescription.textContent = description || "Description unavailable.";
  els.caseIntroSightings.innerHTML = (intro.last_seen || []).map((sighting, index) => `
    <li class="sighting-${escapeHtml(sighting.confidence || "unconfirmed")}">
      <span>${String(index + 1).padStart(2, "0")}</span>
      <div><small>${escapeHtml(sighting.label || "Report")}</small><strong>${escapeHtml(sighting.location || `Junction ${sighting.junction_id}`)}</strong><p>${escapeHtml(sighting.detail || "")}</p></div>
    </li>
  `).join("");
  if (!els.caseIntroDialog.open) els.caseIntroDialog.showModal();
  const shell = els.caseIntroDialog.querySelector(".case-intro-shell");
  shell.scrollTop = 0;
  shell.focus({ preventScroll: true });
}

function dismissCaseIntroduction() {
  if (state.activeIntroGameId) sessionStorage.setItem(introSeenKey(state.activeIntroGameId), "1");
  state.activeIntroGameId = null;
  els.caseIntroDialog.close();
}

function titleCase(value) {
  return String(value).replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function applySnapshot(snapshot, makeNoise = true) {
  if (!snapshot || !snapshot.ok) return;
  state.gameId = snapshot.game?.game_id || state.gameId;
  if (state.gameId) {
    const url = new URL(window.location.href);
    if (url.searchParams.get("game_id") !== state.gameId) {
      url.searchParams.set("game_id", state.gameId);
      window.history.replaceState({}, "", url);
    }
  }
  state.map = snapshot.map || state.map;
  state.selected = snapshot.selection?.junctions || state.selected;
  state.focused = snapshot.selection?.focused ?? state.focused;
  state.witnesses = snapshot.witness_locations || [];
  state.witnessCards = snapshot.witness_cards || [];
  state.previousStatements = snapshot.previous_statements || [];
  state.placedTactics = snapshot.placed_tactics || [];
  state.tacticCounts = snapshot.tactic_counts || state.tacticCounts;
  state.game = snapshot.game || state.game;
  if (snapshot.case_introduction?.culprit_alias) els.wantedAlias.textContent = snapshot.case_introduction.culprit_alias;
  if (!state.notesDirty && typeof snapshot.notes === "string") els.notesText.value = snapshot.notes;

  renderGame(snapshot.game);
  renderTacticTray();
  renderLayers();
  renderMap();
  renderMapOverlays();
  renderLookout(snapshot.lookout);
  renderStatements();
  renderActiveUnits();

  if (snapshot.notice_prompt?.open) openNoticeDialog(snapshot.notice_prompt);
  if (snapshot.game?.result && snapshot.story_available) loadStoryReveal();

  if (snapshot.event) {
    flash(snapshot.event, snapshot.sound, makeNoise);
  }
}

function renderGame(game) {
  if (!game) {
    els.caseClock.textContent = "-";
    els.turnPhase.textContent = "Evening";
    els.advanceButton.disabled = true;
    els.stopGameButton.disabled = true;
    return;
  }
  const complete = Boolean(game.result || game.phase === "complete");
  els.caseClock.textContent = `${game.turn} / ${game.max_turns}`;
  els.turnPhase.textContent = turnPhase(game.turn);
  els.wantedDescription.textContent = game.initial_description || els.wantedDescription.textContent;
  els.wantedLastSeen.textContent = game.last_seen?.location || (game.last_seen?.junction_id ? `Junction ${game.last_seen.junction_id}` : "Awaiting confirmed location");
  els.advanceButton.disabled = complete;
  els.stopGameButton.disabled = complete;
}

function renderTacticTray() {
  els.tacticTray.innerHTML = "";
  const complete = Boolean(state.game?.result || state.game?.phase === "complete");
  for (const [type, tactic] of Object.entries(TACTICS)) {
    const remaining = complete ? 0 : (state.tacticCounts.remaining?.[type] ?? 0);
    const limit = state.tacticCounts.limits?.[type] ?? 0;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "tactic-card";
    card.draggable = remaining > 0;
    card.disabled = remaining <= 0;
    card.dataset.tacticType = type;
    card.setAttribute("aria-label", `${tactic.label}, ${remaining} of ${limit} remaining. ${tactic.preview}`);
    card.innerHTML = `
      <img src="${assetUrl(tactic.icon)}" alt="" />
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
        state.mapView.initialized = false;
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
  const offset = currentLayerYOffset();
  const focus = junctionById(state.focused || DEFAULT_FOCUSED_JUNCTION);
  const targetX = base.left + ((focus?.x || els.mapImage.naturalWidth / 2) / els.mapImage.naturalWidth) * base.width;
  const focusY = focus?.y != null ? focus.y + offset : els.mapImage.naturalHeight / 2;
  const targetY = base.top + (focusY / els.mapImage.naturalHeight) * base.height;
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
  const nextZoom = Math.min(Math.max(oldZoom * factor, 0.85), 6);
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
  const tacticCountsByJunction = new Map();
  state.placedTactics.forEach((placed) => {
    tacticCountsByJunction.set(placed.junction_id, (tacticCountsByJunction.get(placed.junction_id) || 0) + 1);
  });
  const witnessJunctions = new Set(
    state.mapVisibility.witnesses ? state.witnesses.map((witness) => witness.junction_id) : [],
  );

  const focused = junctionById(state.focused);
  if (focused && state.mapVisibility.focus) {
    const marker = document.createElement("div");
    marker.className = "focus-marker";
    placeAtMapPoint(marker, focused.x, focused.y);
    els.selectionLayer.append(marker);
  }

  if (state.mapVisibility.witnesses) state.witnesses.forEach((witness) => {
    const junction = junctionById(witness.junction_id);
    if (!junction) return;
    const reports = witness.reports?.length ? witness.reports : [{
      id: witness.sample_witness_id,
      viewed: witness.viewed,
      summary: witness.sample_summary,
    }];
    if (reports.length > 1) {
      const cluster = document.createElement("button");
      cluster.type = "button";
      cluster.className = "witness-token witness-cluster-token";
      cluster.dataset.witnessClusterJunction = String(witness.junction_id);
      cluster.setAttribute("aria-label", `${reports.length} separate witness reports at Junction ${witness.junction_id}. Open report list.`);
      cluster.innerHTML = `
        <img src="${assetUrl(reports.some((report) => !report.viewed) ? "pin_unviewed_witness.png" : "pin_viewed_witness.png")}" alt="" />
        <strong>${reports.length}</strong>
      `;
      placeAtMapPoint(cluster, junction.x, junction.y);
      els.witnessLayer.append(cluster);
    }
    reports.forEach((report, reportIndex) => {
      const token = document.createElement("button");
      const offset = witnessReportOffset(reportIndex, reports.length, tacticCountsByJunction.has(witness.junction_id));
      token.type = "button";
      token.className = `witness-token witness-cluster-member ${report.viewed ? "viewed" : "unviewed"}`;
      token.dataset.junctionId = String(witness.junction_id);
      token.dataset.witnessId = report.id || "";
      token.style.setProperty("--token-offset-x", `${offset.x}px`);
      token.style.setProperty("--token-offset-y", `${offset.y}px`);
      if (reports.length > 1 || tacticCountsByJunction.has(witness.junction_id)) token.classList.add("co-located");
      token.setAttribute("aria-label", `${report.viewed ? "Viewed" : "Unviewed"} witness ${reportIndex + 1} of ${reports.length} at Junction ${witness.junction_id}`);
      token.innerHTML = `
        <img src="${assetUrl(report.viewed ? "pin_viewed_witness.png" : "pin_unviewed_witness.png")}" alt="" />
        ${reports.length > 1 ? `<strong>${reportIndex + 1}</strong>` : ""}
      `;
      placeAtMapPoint(token, junction.x, junction.y);
      els.witnessLayer.append(token);
    });
  });

  const renderedTacticsByJunction = new Map();
  if (state.mapVisibility.tactics) state.placedTactics.forEach((placed) => {
    const tactic = TACTICS[placed.tactic_type];
    if (!tactic) return;
    const token = document.createElement("button");
    token.type = "button";
    token.className = `map-token ${placed.tactic_type}`;
    token.draggable = true;
    token.dataset.tacticId = placed.tactic_id;
    const tacticIndex = renderedTacticsByJunction.get(placed.junction_id) || 0;
    renderedTacticsByJunction.set(placed.junction_id, tacticIndex + 1);
    const colocatedWithWitness = witnessJunctions.has(placed.junction_id);
    const tacticCount = tacticCountsByJunction.get(placed.junction_id) || 1;
    if (colocatedWithWitness || tacticCount > 1) {
      token.classList.add("co-located");
      const offset = tacticStackOffset(tacticIndex, tacticCount);
      token.style.setProperty("--token-offset-x", `${offset.x}px`);
      token.style.setProperty("--token-offset-y", `${offset.y}px`);
    }
    token.innerHTML = `<img src="${assetUrl(tactic.pin)}" alt="${escapeHtml(tactic.label)}" />`;
    token.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("application/x-placed-tactic-id", placed.tactic_id);
      event.dataTransfer.effectAllowed = "move";
    });
    placeAtMapPoint(token, placed.x, placed.y);
    els.tacticLayer.append(token);
  });
}

function tacticStackOffset(index, total) {
  if (total <= 1) return { x: 0, y: 0 };
  if (total === 2) {
    const spread = 44;
    return { x: index === 0 ? -spread : spread, y: 0 };
  }
  const radius = 46;
  const angle = (-Math.PI / 2) + (index * Math.PI * 2) / total;
  return { x: Math.round(Math.cos(angle) * radius), y: Math.round(Math.sin(angle) * radius) };
}

function witnessReportOffset(index, total, colocatedWithTactic) {
  if (total === 1) return { x: colocatedWithTactic ? -28 : 0, y: 0 };
  const ringIndex = Math.floor(index / 8);
  const position = index % 8;
  const itemsInRing = Math.min(8, total - ringIndex * 8);
  const radius = 26 + ringIndex * 18 + (colocatedWithTactic ? 8 : 0);
  const angle = (-Math.PI / 2) + (position * Math.PI * 2) / itemsInRing;
  return { x: Math.round(Math.cos(angle) * radius), y: Math.round(Math.sin(angle) * radius) };
}

function toggleMapVisibility(category) {
  state.mapVisibility[category] = !state.mapVisibility[category];
  renderMapVisibilityControls();
  renderMapOverlays();
}

function enableWitnessMode() {
  state.mapVisibility.witnesses = true;
  state.mapVisibility.tactics = false;
  state.mapVisibility.focus = false;
  renderMapVisibilityControls();
  renderMapOverlays();
}

function renderMapVisibilityControls() {
  const controls = [
    [els.toggleWitnessesButton, "witnesses"],
    [els.toggleTacticsButton, "tactics"],
    [els.toggleFocusButton, "focus"],
  ];
  controls.forEach(([button, category]) => {
    const visible = state.mapVisibility[category];
    button.classList.toggle("active", visible);
    button.setAttribute("aria-pressed", String(visible));
  });
  els.witnessModeButton.classList.toggle(
    "active",
    state.mapVisibility.witnesses && !state.mapVisibility.tactics && !state.mapVisibility.focus,
  );
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
      <mark aria-label="Viewed">OK</mark>
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
    item.innerHTML = `<img src="${assetUrl(icon)}" alt="" /><strong>${label}</strong><span>${detail}</span>`;
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
  ghost.innerHTML = `<img src="${assetUrl(detail.icon)}" alt="" /><span>${escapeHtml(detail.label)}</span>`;
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
    applySnapshot(await api("place_tactic", payload({
      tactic_type: tacticType,
      junction_id: junctionId,
      layer: state.layer,
    })));
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
  const cluster = event.target.closest("[data-witness-cluster-junction]");
  if (cluster) {
    event.preventDefault();
    event.stopPropagation();
    const junctionId = Number(cluster.dataset.witnessClusterJunction);
    const location = state.witnesses.find((item) => item.junction_id === junctionId);
    showWitnessClusterPopup(location, event.clientX, event.clientY);
    return;
  }
  const token = event.target.closest("[data-witness-id]");
  if (!token) return;
  event.preventDefault();
  event.stopPropagation();
  const witnessId = token.dataset.witnessId;
  openWitnessInterview(witnessId);
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
    return;
  }
  const openWitness = event.target.closest("[data-action='open-witness']");
  if (openWitness) {
    openWitnessInterview(openWitness.dataset.witnessId);
  }
}

function showTacticPopup(placed, x, y) {
  const tactic = TACTICS[placed.tactic_type];
  if (!tactic) return;
  state.focused = placed.junction_id;
  state.selected = [placed.junction_id];
  renderMapOverlays();
  els.detailPopup.innerHTML = `
    <button class="popup-close" type="button" data-action="close-popup" aria-label="Close">X</button>
    <img src="${assetUrl(tactic.pin)}" alt="" />
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
    <button class="popup-close" type="button" data-action="close-popup" aria-label="Close">X</button>
    <img src="${assetUrl(location.viewed ? "pin_viewed_witness.png" : "pin_unviewed_witness.png")}" alt="" />
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

function showWitnessClusterPopup(location, x, y) {
  if (!location?.reports?.length) return;
  state.focused = location.junction_id;
  state.selected = [location.junction_id];
  renderMapOverlays();
  const reportButtons = location.reports.map((report, index) => `
    <button class="cluster-report-button ${report.viewed ? "viewed" : "unviewed"}" type="button" data-action="open-witness" data-witness-id="${escapeHtml(report.id)}">
      <strong>Report ${index + 1}: ${escapeHtml(report.name || report.style || "Witness")}</strong>
      <span>${escapeHtml(shortSummary(report.summary || "Potential witness report.", 92))}</span>
    </button>
  `).join("");
  els.detailPopup.innerHTML = `
    <button class="popup-close" type="button" data-action="close-popup" aria-label="Close">X</button>
    <h3>${location.reports.length} Witness Reports</h3>
    <p>Junction ${location.junction_id}. Select a report to interview that witness.</p>
    <div class="cluster-report-list">${reportButtons}</div>
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
    y: ((canvasY - base.top) / base.height) * els.mapImage.naturalHeight - currentLayerYOffset(),
  };
}

function placeAtMapPoint(node, x, y) {
  const rect = imageBaseRect();
  if (!rect) return;
  const offset = currentLayerYOffset();
  const left = rect.left + (x / els.mapImage.naturalWidth) * rect.width;
  const top = rect.top + ((y + offset) / els.mapImage.naturalHeight) * rect.height;
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

function beginTurnProcessing() {
  state.turnProcessing = true;
  state.advanceButtonLabel = els.advanceButton.textContent;
  els.advanceButton.classList.add("processing");
  els.advanceButton.disabled = true;
  els.advanceButton.textContent = "Processing Turn...";
  els.eventTicker.textContent = "Generating the next turn... this can take a while.";
  els.mapMessage.textContent = "Generating the next turn... this can take a while.";
  playSound("blockade_set");
}

function endTurnProcessing() {
  state.turnProcessing = false;
  els.advanceButton.classList.remove("processing");
  els.advanceButton.textContent = state.advanceButtonLabel || "Advance Turn";
  const complete = Boolean(state.game?.result || state.game?.phase === "complete");
  els.advanceButton.disabled = complete;
}

let audioContext = null;

function playSound(name) {
  if (!state.sound) return;
  audioContext ||= new AudioContext();
  const now = audioContext.currentTime;
  if (name === "turn_advance") {
    playChime([523.25, 783.99, 1046.5], 0.7, "sine", 0.32);
    return;
  }
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

function playChime(frequencies, duration, type, peak) {
  if (!audioContext) return;
  const now = audioContext.currentTime;
  frequencies.forEach((frequency, index) => {
    const start = now + index * 0.12;
    const gain = audioContext.createGain();
    gain.connect(audioContext.destination);
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(peak, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    const oscillator = audioContext.createOscillator();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, start);
    oscillator.connect(gain);
    oscillator.start(start);
    oscillator.stop(start + duration);
  });
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

function openNoticeDialog(prompt) {
  els.noticeJunctionLabel.textContent = `Junction ${prompt.junction_id}`;
  els.noticeText.value = prompt.prefill || DEFAULT_NOTICE;
  els.lookoutMeta.textContent = "The wording controls which existing witnesses recognize the appeal.";
  if (!els.noticeDialog.open) els.noticeDialog.showModal();
  els.noticeText.focus();
}

async function publishNotice() {
  if (!state.gameId) return;
  try {
    const snapshot = await api("issue_notice", payload({ notice_text: els.noticeText.value || DEFAULT_NOTICE }));
    els.noticeDialog.close();
    applySnapshot(snapshot);
  } catch (error) {
    els.lookoutMeta.textContent = error.message || "Could not publish this notice.";
  }
}

function scheduleNotesSave() {
  state.notesDirty = true;
  els.notesStatus.textContent = "Saving...";
  clearTimeout(state.notesTimer);
  state.notesTimer = setTimeout(saveNotes, 500);
}

async function saveNotes() {
  if (!state.gameId) return;
  try {
    const response = await fetch(`/api/game/${encodeURIComponent(state.gameId)}/notes`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notes: els.notesText.value }),
    });
    if (!response.ok) throw new Error("Could not save notes");
    state.notesDirty = false;
    els.notesStatus.textContent = "Saved with this case.";
  } catch (error) {
    els.notesStatus.textContent = error.message || "Notes not saved.";
  }
}

async function openWitnessInterview(witnessId) {
  if (!witnessId || !state.gameId) return;
  closePopup();
  try {
    const response = await fetch(`/api/witness/${encodeURIComponent(state.gameId)}/${encodeURIComponent(witnessId)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not open witness.");
    state.activeWitness = data.witness;
    els.witnessName.textContent = data.witness.name;
    els.witnessProfile.textContent = `${data.witness.occupation} | Junction ${data.witness.junction_id} | ${data.witness.personality.style || "measured"}`;
    els.witnessSummary.textContent = data.witness.summary;
    els.witnessConnection.textContent = "Text ready | speech disconnected";
    els.witnessTranscript.innerHTML = "";
    data.witness.transcript.forEach((turn) => {
      appendChatMessage("user", turn.question);
      appendChatMessage("witness", turn.answer);
    });
    if (!els.witnessDialog.open) els.witnessDialog.showModal();
    els.witnessMessage.focus();
  } catch (error) {
    flash(error.message || "Could not open witness.", "map_select");
  }
}

async function sendWitnessText() {
  const witness = state.activeWitness;
  const message = els.witnessMessage.value.trim();
  if (!witness || !message) return;
  els.witnessMessage.value = "";
  appendChatMessage("user", message);
  els.sendWitnessMessage.disabled = true;
  els.witnessConnection.textContent = "Witness is answering...";
  try {
    const response = await fetch(`/api/witness/${encodeURIComponent(state.gameId)}/${encodeURIComponent(witness.id)}/message`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Witness response failed.");
    appendChatMessage("witness", data.answer);
    if (data.audio_data) playFloat32Audio(data.audio_data, data.audio_sample_rate || 24000);
    if (data.snapshot) applySnapshot(data.snapshot, false);
    els.witnessConnection.textContent = "Text ready";
  } catch (error) {
    appendChatMessage("witness", `[Connection error: ${error.message}]`);
    els.witnessConnection.textContent = "MiniCPM-o unavailable";
  } finally {
    els.sendWitnessMessage.disabled = false;
  }
}

function appendChatMessage(role, text) {
  const bubble = document.createElement("article");
  bubble.className = `chat-message ${role}`;
  bubble.textContent = text;
  els.witnessTranscript.append(bubble);
  els.witnessTranscript.scrollTop = els.witnessTranscript.scrollHeight;
  return bubble;
}

async function finishGame(reason) {
  if (!state.gameId) return;
  try {
    const response = await fetch(`/api/game/${encodeURIComponent(state.gameId)}/stop`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not finish case.");
    if (data.snapshot) applySnapshot(data.snapshot, false);
    if (els.noticeDialog.open) els.noticeDialog.close();
    if (els.witnessDialog.open) closeWitnessInterview();
    showStoryReveal(data.story, reason === "restarted");
  } catch (error) {
    flash(error.message || "Could not finish case.", "map_select");
  }
}

async function restartGame() {
  if (!state.gameId) return openNewCase(true);
  await finishGame("restarted");
}

async function loadStoryReveal() {
  if (!state.gameId || els.storyDialog.open) return;
  const response = await fetch(`/api/game/${encodeURIComponent(state.gameId)}/story`);
  if (!response.ok) return;
  const data = await response.json();
  showStoryReveal(data.story, false);
}

function showStoryReveal(story, offerRestart) {
  els.storyTimeline.innerHTML = "";
  (story.segments || []).forEach((segment) => {
    const card = document.createElement("article");
    card.className = "story-card";
    const facts = (segment.observable_facts || []).map((fact) => `<li>${escapeHtml(fact.text)}</li>`).join("");
    card.innerHTML = `<h3>Turn ${segment.turn_number}: Junction ${segment.from_junction} to ${segment.to_junction}</h3><p><strong>${escapeHtml(segment.mode)}</strong> | ${segment.changed_disguise ? "disguise changed" : "same disguise"}</p><p>${escapeHtml(segment.narrative)}</p>${facts ? `<ul class="story-facts">${facts}</ul>` : ""}`;
    els.storyTimeline.append(card);
  });
  els.storyFooter.innerHTML = offerRestart ? '<button id="confirmRestartButton" type="button">Confirm New Case</button>' : `<p>Case result: ${escapeHtml(story.result || story.finalized_reason || "complete")}</p>`;
  if (offerRestart) document.querySelector("#confirmRestartButton").addEventListener("click", async () => {
    els.storyDialog.close(); state.gameId = null; state.game = null; await openNewCase(true);
  });
  if (!els.storyDialog.open) els.storyDialog.showModal();
}

function formatBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / (1024 ** index)).toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}

async function toggleAutoSpeech() {
  if (state.speechMode === "auto") return stopSpeechSession();
  state.speechMode = "auto";
  els.autoSpeechButton.classList.add("active");
  els.autoSpeechButton.textContent = "Stop Auto Speech";
  await startSpeechSession();
}

async function startPushToTalk(event) {
  event.preventDefault();
  state.speechMode = "push";
  state.pushRecording = true;
  state.pushDrainUntil = 0;
  els.pushToTalkButton.classList.add("recording");
  els.pushToTalkButton.textContent = "Listening...";
  if (!state.witnessSocket || state.witnessSocket.readyState > 1) await startSpeechSession();
}

function stopPushToTalk() {
  state.pushRecording = false;
  state.pushDrainUntil = Date.now() + 1000;
  els.pushToTalkButton.classList.remove("recording");
  els.pushToTalkButton.textContent = "Hold to Talk";
}

async function startSpeechSession() {
  if (!state.activeWitness || !state.gameId) return;
  try {
    if (!state.mediaStream) {
      state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/ws/witness/${encodeURIComponent(state.gameId)}/${encodeURIComponent(state.activeWitness.id)}`;
    const socket = new WebSocket(url);
    state.witnessSocket = socket;
    els.witnessConnection.textContent = "Connecting speech...";
    socket.onopen = () => socket.send(JSON.stringify({ type: "prepare", config: {} }));
    socket.onmessage = (event) => handleSpeechMessage(JSON.parse(event.data));
    socket.onclose = () => {
      els.witnessConnection.textContent = "Speech disconnected | text ready";
      stopCapture();
      state.witnessSocket = null;
      state.speechMode = null;
      els.autoSpeechButton.classList.remove("active");
      els.autoSpeechButton.textContent = "Start Auto Speech";
    };
    socket.onerror = () => { els.witnessConnection.textContent = "Speech connection failed"; };
  } catch (error) {
    els.witnessConnection.textContent = error.message || "Microphone permission failed";
    state.speechMode = null;
  }
}

async function handleSpeechMessage(message) {
  if (message.type === "queued" || message.type === "queue_update") {
    els.witnessConnection.textContent = `Speech queued #${message.position}`;
  } else if (message.type === "prepared") {
    els.witnessConnection.textContent = state.speechMode === "auto" ? "Listening automatically" : "Push to talk ready";
    await startCapture();
  } else if (message.type === "vad_state") {
    els.witnessConnection.textContent = message.speaking ? "Listening..." : "Waiting for speech";
  } else if (message.type === "generating") {
    appendChatMessage("user", "[Spoken question]");
    state.currentAssistantBubble = appendChatMessage("witness", "");
    els.witnessConnection.textContent = "Witness is answering...";
  } else if (message.type === "chunk") {
    if (message.text_delta) {
      if (!state.currentAssistantBubble) state.currentAssistantBubble = appendChatMessage("witness", "");
      state.currentAssistantBubble.textContent += message.text_delta;
      els.witnessTranscript.scrollTop = els.witnessTranscript.scrollHeight;
    }
    if (message.audio_data) playFloat32Audio(message.audio_data, message.audio_sample_rate || 24000);
  } else if (message.type === "turn_done") {
    state.currentAssistantBubble = null;
    els.witnessConnection.textContent = state.speechMode === "auto" ? "Listening automatically" : "Push to talk ready";
  } else if (message.type === "error") {
    els.witnessConnection.textContent = message.error || "Speech error";
  }
}

async function startCapture() {
  if (state.captureContext || !state.mediaStream) return;
  const context = new AudioContext();
  const source = context.createMediaStreamSource(state.mediaStream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  const silent = context.createGain();
  silent.gain.value = 0;
  processor.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    let sum = 0;
    for (const value of input) sum += value * value;
    els.micLevel.value = Math.min(Math.sqrt(sum / input.length) * 8, 1);
    const shouldSend = state.speechMode === "auto" || (
      state.speechMode === "push" && (state.pushRecording || Date.now() < state.pushDrainUntil)
    );
    if (!shouldSend || state.witnessSocket?.readyState !== WebSocket.OPEN) return;
    const audio = resampleAudio(input, context.sampleRate, 16000);
    state.witnessSocket.send(JSON.stringify({ type: "audio_chunk", audio_base64: float32ToBase64(audio) }));
  };
  source.connect(processor); processor.connect(silent); silent.connect(context.destination);
  state.captureContext = context; state.captureNode = processor;
}

function resampleAudio(input, sourceRate, targetRate) {
  if (sourceRate === targetRate) return new Float32Array(input);
  const ratio = sourceRate / targetRate;
  const output = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < output.length; i += 1) {
    const start = Math.floor(i * ratio); const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0; for (let j = start; j < end; j += 1) sum += input[j];
    output[i] = sum / Math.max(end - start, 1);
  }
  return output;
}

function float32ToBase64(floatArray) {
  const bytes = new Uint8Array(floatArray.buffer); let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function playFloat32Audio(base64Data, sampleRate) {
  const binary = atob(base64Data); const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const usable = bytes.byteLength - (bytes.byteLength % 4);
  const floats = new Float32Array(bytes.buffer.slice(0, usable));
  if (!state.playbackContext) state.playbackContext = new AudioContext({ sampleRate });
  const context = state.playbackContext; const buffer = context.createBuffer(1, floats.length, sampleRate);
  buffer.copyToChannel(floats, 0);
  const source = context.createBufferSource(); source.buffer = buffer; source.connect(context.destination);
  const start = Math.max(context.currentTime + 0.03, state.playbackTime || 0);
  source.start(start); state.playbackTime = start + buffer.duration; state.playbackSources.push(source);
  source.onended = () => { state.playbackSources = state.playbackSources.filter((item) => item !== source); };
}

function stopPlayback() {
  state.playbackSources.forEach((source) => { try { source.stop(); } catch (_) {} });
  state.playbackSources = []; state.playbackTime = 0;
}

function stopCapture() {
  if (state.captureNode) state.captureNode.disconnect();
  if (state.captureContext) state.captureContext.close();
  state.captureNode = null; state.captureContext = null; els.micLevel.value = 0;
}

function stopSpeechSession() {
  if (state.witnessSocket?.readyState === WebSocket.OPEN) state.witnessSocket.send(JSON.stringify({ type: "stop" }));
  if (state.witnessSocket) state.witnessSocket.close();
  stopCapture(); state.speechMode = null; state.pushRecording = false; state.pushDrainUntil = 0;
  els.autoSpeechButton.classList.remove("active"); els.autoSpeechButton.textContent = "Start Auto Speech";
  els.pushToTalkButton.classList.remove("recording"); els.pushToTalkButton.textContent = "Hold to Talk";
}

function closeWitnessInterview() {
  stopSpeechSession(); stopPlayback();
  if (state.mediaStream) state.mediaStream.getTracks().forEach((track) => track.stop());
  state.mediaStream = null; state.activeWitness = null; els.witnessDialog.close();
}

boot().catch((error) => {
  flash(error.message || "The board failed to open.", "map_select", false);
});
