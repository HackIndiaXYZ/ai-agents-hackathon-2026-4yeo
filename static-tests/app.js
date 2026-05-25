const state = {
  qaSessionId: "",
  qaResult: null,
  voiceSessionId: "",
  livekitToken: "",
  livekitUrl: "",
  livekitRoom: null,
  latestArtifactId: "",
  adaptionRunRecordId: "",
  latestScenario: null,
};

const $ = (id) => document.getElementById(id);

function apiBase() {
  return $("apiBase").value.replace(/\/$/, "");
}

function write(id, payload) {
  $(id).textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

function setStatus(status) {
  $("stateStatus").textContent = status;
}

function syncState() {
  $("stateQaSession").textContent = state.qaSessionId || "None";
  $("stateVoiceSession").textContent = state.voiceSessionId || "None";
  $("stateArtifact").textContent = state.latestArtifactId || "None";
}

function log(message, payload) {
  const stamp = new Date().toLocaleTimeString();
  const suffix = payload ? `\n${JSON.stringify(payload, null, 2)}` : "";
  $("logOut").textContent = `[${stamp}] ${message}${suffix}\n\n${$("logOut").textContent}`;
}

async function request(method, path, body) {
  const url = `${apiBase()}${path}`;
  setStatus(`${method} ${path}`);
  const init = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }
  const response = await fetch(url, init);
  const text = await response.text();
  let payload = text;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = text;
  }
  if (!response.ok) {
    log(`FAIL ${method} ${path}`, payload);
    throw new Error(typeof payload === "object" ? JSON.stringify(payload) : payload);
  }
  log(`OK ${method} ${path}`, payload);
  setStatus("Ready");
  return payload;
}

async function health() {
  const payload = await request("GET", "/health");
  write("systemOut", payload);
}

async function readiness() {
  const payload = await request("GET", "/health/readiness");
  write("systemOut", payload);
  return payload;
}

async function analytics() {
  const payload = await request("GET", "/analytics/summary");
  write("systemOut", payload);
}

async function loadScenarios() {
  const scenarios = await request("GET", "/demo/scenarios");
  const select = $("scenarioId");
  select.innerHTML = "";
  for (const scenario of scenarios) {
    const option = document.createElement("option");
    option.value = scenario.id;
    option.textContent = scenario.id;
    select.appendChild(option);
  }
  write("demoOut", scenarios);
}

async function runScenario() {
  const scenarioId = $("scenarioId").value;
  const payload = await request("POST", `/demo/scenarios/${encodeURIComponent(scenarioId)}/run`);
  state.latestScenario = payload.scenario;
  state.qaSessionId = payload.session.id;
  state.qaResult = payload.result;
  syncState();
  write("demoOut", payload);
}

async function createQaSession() {
  const payload = await request("POST", "/qa/sessions", {
    language: $("qaLanguage").value,
    domain: $("qaDomain").value,
    is_demo: true,
  });
  state.qaSessionId = payload.id;
  syncState();
  write("qaOut", payload);
}

async function ensureQaSession() {
  if (!state.qaSessionId) {
    await createQaSession();
  }
}

async function submitTranscript() {
  await ensureQaSession();
  const payload = await request("POST", `/qa/sessions/${state.qaSessionId}/transcript`, {
    transcript: $("qaTranscript").value,
    source: "static_test",
    language: $("qaLanguage").value,
  });
  state.qaResult = payload;
  write("qaOut", payload);
}

async function createCorrection() {
  await ensureQaSession();
  if (!state.qaResult) {
    await submitTranscript();
  }
  const payload = await request("POST", `/qa/sessions/${state.qaSessionId}/corrections`, {
    corrected_score: state.qaResult.final_score,
    corrected_violation_label: state.qaResult.violation_label,
    corrected_escalation_required: state.qaResult.escalation_required,
    corrected_coaching_note: state.qaResult.coaching_note,
    reviewer_note: $("reviewerNote").value,
  });
  write("qaOut", payload);
}

async function connectVoice() {
  const payload = await request("POST", "/voice/connect", {
    qa_session_id: state.qaSessionId || null,
    language: $("qaLanguage").value,
    domain: $("qaDomain").value,
    participant_identity: $("participantIdentity").value,
  });
  state.voiceSessionId = payload.voice_session_id;
  state.qaSessionId = payload.qa_session_id;
  state.livekitToken = payload.token;
  state.livekitUrl = payload.livekit_url;
  syncState();
  write("voiceOut", payload);
}

async function ensureVoiceSession() {
  if (!state.voiceSessionId) {
    await connectVoice();
  }
}

async function sendVoiceEvent(eventType, extra = {}) {
  await ensureVoiceSession();
  const body = {
    voice_session_id: state.voiceSessionId,
    event_type: eventType,
    ...extra,
  };
  const payload = await request("POST", "/voice/events", body);
  if (payload.qa_result) {
    state.qaResult = payload.qa_result;
  }
  write("voiceOut", payload);
}

async function sendPartialVoice() {
  await sendVoiceEvent("partial_transcript", {
    transcript: $("voiceTranscript").value.slice(0, 38),
    confidence: 0.72,
    turn_index: 1,
  });
}

async function sendFinalVoice() {
  await sendVoiceEvent("final_transcript", {
    transcript: $("voiceTranscript").value,
    confidence: 0.93,
    turn_index: 1,
    provider_metadata: { source: "static-tests" },
  });
}

async function sendInterruption() {
  await sendVoiceEvent("interruption", {
    provider_metadata: { reason: "barge_in" },
  });
}

async function sendMetrics() {
  await sendVoiceEvent("metrics", {
    metrics: {
      transcription_delay: 0.18,
      total_latency: 0.94,
      turn_end_delay: 0.31,
    },
  });
}

async function loadVoiceTimeline() {
  await ensureVoiceSession();
  const payload = await request("GET", `/voice/sessions/${state.voiceSessionId}/timeline`);
  write("voiceOut", payload);
}

async function joinLiveKitRoom() {
  await ensureVoiceSession();
  if (state.livekitRoom) {
    await leaveLiveKitRoom();
  }
  const sdk = await import($("livekitSdkUrl").value);
  const room = new sdk.Room();
  const audioSink = $("remoteAudio");
  audioSink.innerHTML = "";
  room.on(sdk.RoomEvent.TrackSubscribed, (track) => {
    if (track.kind === "audio") {
      const element = track.attach();
      element.autoplay = true;
      audioSink.appendChild(element);
    }
  });
  room.on(sdk.RoomEvent.Disconnected, () => {
    log("LiveKit room disconnected");
  });
  await room.connect(state.livekitUrl, state.livekitToken);
  if (typeof room.startAudio === "function") {
    await room.startAudio();
  }
  if (typeof room.localParticipant.setMicrophoneEnabled === "function") {
    await room.localParticipant.setMicrophoneEnabled(true);
  } else if (typeof sdk.createLocalTracks === "function") {
    const tracks = await sdk.createLocalTracks({ audio: true, video: false });
    for (const track of tracks) {
      await room.localParticipant.publishTrack(track);
    }
  }
  state.livekitRoom = room;
  write("voiceOut", {
    connected: true,
    roomName: room.name,
    localParticipant: room.localParticipant.identity,
    livekitUrl: state.livekitUrl,
  });
}

async function leaveLiveKitRoom() {
  if (state.livekitRoom) {
    state.livekitRoom.disconnect();
    state.livekitRoom = null;
  }
  $("remoteAudio").innerHTML = "";
  write("voiceOut", { connected: false });
}

async function loadTools() {
  const payload = await request("GET", "/agent-tools");
  write("toolsOut", payload);
}

async function runTool(toolName, input) {
  return request("POST", "/agent-tools/run", { tool_name: toolName, input });
}

async function runRiskScan() {
  const payload = await runTool("risk_scan", {
    domain: $("qaDomain").value,
    language: $("qaLanguage").value,
    transcript: $("qaTranscript").value,
  });
  write("toolsOut", payload);
}

async function runEscalationPlan() {
  if (!state.qaResult) {
    await submitTranscript();
  }
  const payload = await runTool("escalation_plan", {
    domain: $("qaDomain").value,
    violation_label: state.qaResult.violation_label,
    urgency: state.qaResult.urgency,
    final_score: state.qaResult.final_score,
    transcript: $("qaTranscript").value,
  });
  write("toolsOut", payload);
}

async function runSessionSummary() {
  await ensureQaSession();
  const payload = await runTool("session_summary", { qa_session_id: state.qaSessionId });
  write("toolsOut", payload);
}

async function loadSeed() {
  const payload = await request("POST", "/datasets/seed/load");
  write("datasetOut", payload);
}

async function listRows() {
  const payload = await request("GET", "/datasets/rows");
  write("datasetOut", { count: payload.length, rows: payload.slice(0, 8) });
}

async function listArtifacts() {
  const payload = await request("GET", "/datasets/artifacts");
  state.latestArtifactId = payload[0]?.id || state.latestArtifactId;
  syncState();
  write("datasetOut", { count: payload.length, artifacts: payload });
}

async function exportDataset() {
  const payload = await request("POST", "/datasets/export", { format: "all" });
  const jsonl = payload.artifacts.find((artifact) => artifact.artifact_type === "jsonl");
  state.latestArtifactId = jsonl ? jsonl.id : payload.artifacts[0]?.id || "";
  syncState();
  write("datasetOut", payload);
}

async function downloadArtifact() {
  if (!state.latestArtifactId) {
    await listArtifacts();
  }
  if (!state.latestArtifactId) {
    throw new Error("No export artifact available.");
  }
  const url = `${apiBase()}/datasets/artifacts/${state.latestArtifactId}/download`;
  window.open(url, "_blank", "noopener,noreferrer");
  log("OPEN artifact download", { url });
  write("datasetOut", { download_url: url });
}

async function datasetReadiness() {
  const payload = await runTool("dataset_readiness", {});
  write("datasetOut", payload);
}

async function startAdaption() {
  if (!state.latestArtifactId) {
    await exportDataset();
  }
  const payload = await request("POST", "/adaption/runs", {
    artifact_id: state.latestArtifactId,
    dataset_name: "argus-awaaz-static-test",
  });
  state.adaptionRunRecordId = payload.id;
  write("adaptionOut", payload);
}

async function resetDemo() {
  const payload = await request("POST", "/demo/reset", {
    confirm: true,
    include_seed_data: true,
    include_exports: true,
    include_voice_sessions: true,
    include_adaption_runs: true,
  });
  state.qaSessionId = "";
  state.qaResult = null;
  state.voiceSessionId = "";
  state.livekitToken = "";
  state.livekitUrl = "";
  state.latestArtifactId = "";
  state.adaptionRunRecordId = "";
  syncState();
  write("adaptionOut", payload);
}

async function refreshAdaption() {
  if (!state.adaptionRunRecordId) {
    throw new Error("Start an Adaption run first.");
  }
  const payload = await request("POST", "/adaption/status", {
    run_record_id: state.adaptionRunRecordId,
  });
  write("adaptionOut", payload);
}

async function downloadAdaption() {
  if (!state.adaptionRunRecordId) {
    throw new Error("Start an Adaption run first.");
  }
  const payload = await request("POST", "/adaption/download", {
    run_record_id: state.adaptionRunRecordId,
    file_format: "jsonl",
  });
  write("adaptionOut", payload);
}

async function runGoldenPath() {
  await health();
  const ready = await readiness();
  await loadScenarios();
  await runScenario();
  await createCorrection();
  await loadTools();
  await runRiskScan();
  await runEscalationPlan();
  if (ready.livekit_config?.ok) {
    await connectVoice();
    await sendPartialVoice();
    await sendFinalVoice();
  } else {
    log("SKIP voice golden path", { reason: ready.livekit_config?.detail || "LiveKit is not configured" });
  }
  await loadSeed();
  await exportDataset();
  await listArtifacts();
  await datasetReadiness();
  await analytics();
}

const actions = {
  health,
  readiness,
  analytics,
  loadScenarios,
  runScenario,
  createQaSession,
  submitTranscript,
  createCorrection,
  connectVoice,
  joinLiveKitRoom,
  leaveLiveKitRoom,
  sendPartialVoice,
  sendFinalVoice,
  sendInterruption,
  sendMetrics,
  loadVoiceTimeline,
  loadTools,
  runRiskScan,
  runEscalationPlan,
  runSessionSummary,
  loadSeed,
  listRows,
  exportDataset,
  listArtifacts,
  downloadArtifact,
  datasetReadiness,
  resetDemo,
  startAdaption,
  refreshAdaption,
  downloadAdaption,
};

document.addEventListener("click", async (event) => {
  const action = event.target?.dataset?.action;
  if (!action) {
    return;
  }
  try {
    await actions[action]();
  } catch (error) {
    setStatus("Error");
    log(`ERROR ${action}`, { message: error.message });
  }
});

$("runGoldenPath").addEventListener("click", async () => {
  try {
    await runGoldenPath();
  } catch (error) {
    setStatus("Error");
    log("ERROR golden path", { message: error.message });
  }
});

$("clearLog").addEventListener("click", () => {
  $("logOut").textContent = "";
});

syncState();
log("Static harness loaded", { apiBase: apiBase() });
