const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const pageMeta = {
  dashboard: ["🎙", "Диктовка", "Быстрый голосовой ввод для 1С с офлайн fallback"],
  recognition: ["⚡", "Распознавание", "Движок, выбранный микрофон и реальная активность входящего звука"],
  dictionary: ["{}", "Словарь 1С", "Правила замен, команды и предпросмотр форматирования"],
  updates: ["⬇", "Обновления", "Проверка GitHub Releases и setup.exe"],
  settings: ["⚙", "Настройки", "Конфигурация приложения, логи и режим интерфейса"],
};

let backendReady = false;
let backendInitialized = false;
let backendProbeTimer = null;
let statusPollTimer = null;
let logPollTimer = null;
let pendingUpdate = false;
let levelHistory = new Array(12).fill(0);
let lastListeningState = null;
let lastHistorySignature = "";
let micTogglePending = false;
let splashStartedAt = Date.now();
let splashTimer = null;

const splashStages = [
  { at: 0, phase: "1 / 5", status: "Запуск интерфейса", hint: "Загружаем окно Voice 1C и ресурсы интерфейса." },
  { at: 3, phase: "2 / 5", status: "Чтение настроек", hint: "Поднимаем backend, читаем config и готовим логи." },
  { at: 6, phase: "3 / 5", status: "Проверка Chrome Speech", hint: "Ищем Chrome, готовим headless-профиль и Selenium bridge." },
  { at: 12, phase: "4 / 5", status: "Подготовка микрофонов", hint: "Проверяем устройства ввода и Vosk fallback." },
  { at: 18, phase: "5 / 5", status: "Финальная проверка", hint: "Синхронизируем состояние UI. Обычно осталось совсем немного." },
  { at: 30, phase: "дольше обычного", status: "Chrome/Selenium ещё готовятся", hint: "Первый запуск может занять до минуты, особенно после обновления." },
  { at: 60, phase: "проверьте лог", status: "Загрузка идёт слишком долго", hint: "Если экран не сменится, перезапустите приложение. Лог: %LOCALAPPDATA%\\Voice1C\\logs\\app.log" },
];

function api() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function showToast(text) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = text;
  toast.classList.add("show");
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function hideSplash() {
  if (splashTimer) {
    clearInterval(splashTimer);
    splashTimer = null;
  }
  const bar = $("#splashProgressBar");
  if (bar) bar.style.width = "100%";
  $("#splashStatus") && ($("#splashStatus").textContent = "Готово");
  $("#splashRemaining") && ($("#splashRemaining").textContent = "запуск завершён");
  setTimeout(() => $("#splashScreen")?.classList.add("hidden"), 180);
}

function updateSplash() {
  const elapsed = Math.max(0, Math.floor((Date.now() - splashStartedAt) / 1000));
  const stage = splashStages.reduce((current, item) => (elapsed >= item.at ? item : current), splashStages[0]);
  const targetPercent = elapsed < 20 ? 8 + elapsed * 4 : Math.min(94, 88 + ((elapsed - 20) % 7));

  const status = $("#splashStatus");
  const elapsedEl = $("#splashElapsed");
  const remaining = $("#splashRemaining");
  const phase = $("#splashPhase");
  const hint = $("#splashHint");
  const bar = $("#splashProgressBar");

  if (status) status.textContent = stage.status;
  if (elapsedEl) elapsedEl.textContent = `${elapsed} сек`;
  if (phase) phase.textContent = stage.phase;
  if (hint) hint.textContent = stage.hint;
  if (bar) bar.style.width = `${Math.min(96, Math.max(8, targetPercent))}%`;

  if (remaining) {
    if (elapsed < 20) {
      remaining.textContent = `примерно до ${20 - elapsed} сек`;
    } else if (elapsed < 60) {
      remaining.textContent = "дольше обычного";
    } else {
      remaining.textContent = "нужна проверка";
    }
  }
}

function startSplashAnimation() {
  splashStartedAt = Date.now();
  updateSplash();
  if (splashTimer) clearInterval(splashTimer);
  splashTimer = setInterval(updateSplash, 500);
}

function playTone(active) {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = active ? 740 : 420;
    gain.gain.value = 0.045;
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.11);
    oscillator.onended = () => context.close();
  } catch (error) {
    console.warn(error);
  }
}

function showModal(title, text, isUpdate = false) {
  pendingUpdate = isUpdate;
  $("#modalTitle").textContent = title;
  $("#modalText").textContent = text;
  $("#modalLayer").classList.add("show");
}

function closeModal() {
  $("#modalLayer").classList.remove("show");
}

async function logUi(message) {
  try {
    if (api()?.log_event) await api().log_event(`[UI] ${message}`);
  } catch (error) {
    console.warn(error);
  }
}

async function callBackend(method, ...args) {
  if (!api() || !api()[method]) {
    showToast("Backend ещё не готов");
    return null;
  }
  try {
    const result = await api()[method](...args);
    if (result && typeof result === "object" && result.status && typeof result.status === "object") {
      renderStatus(result.status);
    } else if (result && typeof result === "object" && "status_kind" in result) {
      renderStatus(result);
    }
    return result;
  } catch (error) {
    showToast("Ошибка: " + error);
    return null;
  }
}

function displayEngine(engine) {
  const value = String(engine || "auto").toLowerCase();
  if (value.includes("chrome")) return "Chrome Speech Free";
  if (value.includes("vosk")) return "Vosk Offline";
  return "Auto";
}

function setView(viewId) {
  $$(".nav button").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === viewId));
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === viewId));
  const [icon, title, subtitle] = pageMeta[viewId] || pageMeta.dashboard;
  $("#pageIcon").textContent = icon;
  $("#pageTitle").textContent = title;
  $("#pageSubtitle").textContent = subtitle;
}

function updateMicLevel(level) {
  const normalized = Math.max(0, Math.min(1, Number(level || 0)));
  const percent = Math.round(normalized * 100);
  $("#audioMeter").style.width = `${percent}%`;
  $("#meterLabel").textContent = `${percent}%`;

  levelHistory.push(normalized);
  levelHistory = levelHistory.slice(-12);
  $$(".sparkline i").forEach((bar, index) => {
    const value = levelHistory[index] || 0;
    const height = Math.round(8 + value * 52);
    bar.style.setProperty("--h", `${height}px`);
    bar.style.opacity = value > 0.02 ? "0.95" : "0.35";
  });
}

function setListeningVisual(state) {
  const listening = Boolean(state?.listening);
  const statusKind = state?.status_kind || "paused";
  const mic = $("#micButton");
  const badge = $("#statusBadge");
  const heroTitle = $("#heroTitle");
  const heroText = $("#heroText");

  mic.classList.toggle("listening", listening);
  badge.classList.toggle("listening", listening);
  badge.classList.toggle("error", statusKind === "error");

  if (statusKind === "error") {
    badge.innerHTML = `<span class="status-dot"></span><span>Ошибка</span>`;
    heroTitle.textContent = "Нужна проверка";
    heroText.textContent = state?.last_error || "Посмотрите лог и настройки микрофона.";
    return;
  }

  if (listening) {
    badge.innerHTML = `<span class="status-dot"></span><span>Слушаю</span>`;
    heroTitle.textContent = "Идёт диктовка";
    heroText.textContent = state?.partial_text || "Говорите фразу. Команды выполняются отдельно и не печатаются как текст.";
  } else {
    badge.innerHTML = `<span class="status-dot"></span><span>Пауза</span>`;
    heroTitle.textContent = "Готов к диктовке";
    heroText.textContent = "Поставьте курсор в редактор 1С или Блокнот, затем нажмите микрофон и говорите.";
  }
}

function renderHistory(items) {
  const list = $("#historyList");
  const visibleItems = (items || []).slice(0, 6);
  const signature = JSON.stringify(
    visibleItems.map((item) => [item.kind, item.time, item.result || item.phrase || ""])
  );
  if (signature === lastHistorySignature) return;
  lastHistorySignature = signature;

  list.innerHTML = "";
  if (visibleItems.length === 0) {
    list.innerHTML = `<div class="history-item"><strong><span>Система</span><span>сейчас</span></strong><p>Ожидание диктовки...</p></div>`;
    return;
  }

  visibleItems.forEach((item) => {
    const div = document.createElement("div");
    div.className = "history-item";
    div.innerHTML = `<strong><span>${escapeHtml(item.kind)}</span><span>${escapeHtml(item.time)}</span></strong><p>${escapeHtml(item.result || item.phrase)}</p>`;
    list.appendChild(div);
  });
}

function renderResult(state) {
  const box = $("#resultBox");
  if (state.status_kind === "error" && state.last_error) {
    box.innerHTML = `Ошибка<code>${escapeHtml(state.last_error)}</code>`;
    return;
  }
  if (state.partial_text) {
    box.innerHTML = `Распознаётся<code>${escapeHtml(state.partial_text)}</code>`;
    return;
  }
  if (state.last_result || state.last_phrase) {
    const phrase = state.last_phrase ? `Фраза: ${escapeHtml(state.last_phrase)}\n` : "";
    box.innerHTML = `${phrase}Результат<code>${escapeHtml(state.last_result || "")}</code>`;
    return;
  }
  box.textContent = "Здесь появится последняя распознанная фраза и результат форматирования.";
}

function renderMicrophones(devices, selectedId) {
  const select = $("#microphoneSelect");
  if (!select) return;
  select.innerHTML = "";
  if (!devices || devices.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Микрофоны не найдены";
    select.appendChild(option);
    return;
  }

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "Default input device";
  select.appendChild(defaultOption);

  devices.forEach((device) => {
    const option = document.createElement("option");
    option.value = String(device.id);
    option.textContent = `${device.name}${device.default ? " · default" : ""}`;
    select.appendChild(option);
  });

  const selected = selectedId === null || selectedId === undefined ? "" : String(selectedId);
  select.value = selected;
}

function renderChromeStatus(status) {
  if (!status) return;
  const found = status.chrome_found ?? status.found;
  const chromeFound = $("#chromeFound");
  const chromeVersion = $("#chromeVersion");
  const chromeSpeechApi = $("#chromeSpeechApi");
  const chromeBridgeUrl = $("#chromeBridgeUrl");
  const chromeState = $("#chromeState");

  if (chromeFound) chromeFound.textContent = found ? (status.chrome_path || status.path || "найден") : "не найден";
  if (chromeVersion) chromeVersion.textContent = status.chrome_version || status.version || "—";
  if (chromeSpeechApi) chromeSpeechApi.textContent = status.speech_api_available ? "доступен" : "не проверен";
  if (chromeBridgeUrl) chromeBridgeUrl.textContent = status.bridge_url || "—";
  if (chromeState) {
    const error = status.last_error ? ` · ${status.last_error}` : "";
    chromeState.textContent = `${status.state || "idle"}${error}`;
  }
}

async function refreshMicrophones() {
  const devices = await callBackend("get_microphones");
  const status = await callBackend("get_status");
  renderMicrophones(devices || [], status?.selected_microphone_id);
  return devices || [];
}

function syncControls(state) {
  const engineValue = String(state.speech_engine || "auto").toLowerCase();
  const engineSelect = $("#engineSelect");
  if (engineSelect) {
    if (engineValue.includes("chrome")) engineSelect.value = "chrome speech free";
    else if (engineValue.includes("vosk")) engineSelect.value = "vosk offline";
    else engineSelect.value = "auto";
  }

  const chromeModeSelect = $("#chromeModeSelect");
  if (chromeModeSelect) chromeModeSelect.value = state.chrome_mode || "headless";

  const inputMethod = $("#inputMethod");
  if (inputMethod) inputMethod.value = state.input_method === "keyboard" ? "keyboard" : "clipboard";

  const modeButton = document.querySelector(`[data-segment="mode"] button[data-value="${state.mode === "1c" ? "1c" : "text"}"]`);
  if (modeButton) {
    modeButton.parentElement.querySelectorAll("button").forEach((btn) => btn.classList.remove("active"));
    modeButton.classList.add("active");
  }

  $$(".engine-option").forEach((option) => {
    const value = option.dataset.engine || "";
    const active =
      value === engineValue ||
      (engineValue.includes("chrome") && value === "chrome speech free") ||
      (engineValue.includes("vosk") && value === "vosk offline") ||
      (engineValue === "auto" && value === "auto");
    option.classList.toggle("active", active);
  });

  $$("[data-setting]").forEach((toggle) => {
    const setting = toggle.dataset.setting;
    if (!setting || !(setting in state)) return;
    toggle.classList.toggle("on", Boolean(state[setting]));
  });

  document.body.classList.toggle("large-ui-mode", Boolean(state.large_ui_mode));
}

function renderStatus(state) {
  if (!state) return;
  if (backendReady && state.sound_enabled && lastListeningState !== null && lastListeningState !== Boolean(state.listening)) {
    playTone(Boolean(state.listening));
  }
  lastListeningState = Boolean(state.listening);
  setListeningVisual(state);
  updateMicLevel(state.mic_level);
  syncControls(state);

  $("#phrasesStat").textContent = state.phrases_count || 0;
  $("#accuracyStat").textContent = displayEngine(state.speech_engine);
  $("#latencyStat").textContent = "—";
  $("#engineInfo").textContent = `${displayEngine(state.speech_engine)}${state.engine_running ? " · запущен" : ""}`;
  $("#activeEngineInfo").textContent = displayEngine(state.active_engine_display || state.active_engine);
  $("#inputMethodInfo").textContent = state.input_method === "keyboard" ? "keyboard.write" : "clipboard paste";
  $("#connectionPill").innerHTML = `<span class="dot"></span> ${state.engine_running ? "Engine ready" : "UI ready"}`;
  $("#resultMode").textContent = state.mode === "1c" ? "1С-код" : "Обычный текст";
  $("#githubOwner").value = state.github_owner || "";
  $("#githubRepo").value = state.github_repo || "";
  $("#releaseAssetName").value = state.release_asset_name || "Voice1CSetup.exe";
  $("#appVersion").value = state.version || "1.0.0";
  $("#sidebarVersion").textContent = "v" + (state.version || "1.0.0");

  if (state.mic_test_result && state.mic_test_running) {
    $("#resultBox").innerHTML = `Тест микрофона<code>${escapeHtml(state.mic_test_result)}</code>`;
  } else {
    renderResult(state);
  }

  renderHistory(state.recent_phrases);
  renderChromeStatus(state.chrome_status);

  $("#updateLog").textContent = `[repo] ${state.github_owner}/${state.github_repo}
[asset] ${state.release_asset_name}
[status] ${state.update_message || "Готово"}`;
  const appLog = $("#appLog");
  if (state.log_tail) {
    appLog.textContent = state.log_tail;
    appLog.dataset.initialized = "true";
  } else if (!appLog.dataset.initialized) {
    appLog.textContent = `[status] ${state.status}
[mode] ${state.mode}
[engine] ${state.speech_engine}
[input] ${state.input_method}
[log] ${state.log_file}`;
    appLog.dataset.initialized = "true";
  }
}

async function pollStatus() {
  if (!backendReady || !api()) return;
  try {
    renderStatus(await api().get_status());
  } catch (error) {
    console.warn(error);
  }
}

async function refreshLogTail() {
  if (!backendReady || !api()?.read_log_tail) return;
  try {
    const logTail = await api().read_log_tail();
    if (logTail) $("#appLog").textContent = logTail;
  } catch (error) {
    console.warn(error);
  }
}

async function initializeBackend(source = "event") {
  if (backendInitialized || !api()) return;
  backendInitialized = true;
  backendReady = true;
  if (backendProbeTimer) {
    clearInterval(backendProbeTimer);
    backendProbeTimer = null;
  }

  hideSplash();
  showToast("Backend подключён");
  try {
    await api().log_event?.(`[UI] backend initialized via ${source}`);
  } catch (error) {
    console.warn(error);
  }

  try {
    renderStatus(await api().get_status());
  } catch (error) {
    console.warn(error);
  }

  refreshMicrophones().catch((error) => {
    console.warn(error);
    showToast("Не удалось загрузить микрофоны");
  });

  if (!statusPollTimer) {
    statusPollTimer = setInterval(pollStatus, 500);
  }
  if (!logPollTimer) {
    refreshLogTail();
    logPollTimer = setInterval(refreshLogTail, 3000);
  }
}

function startBackendProbe() {
  if (backendProbeTimer) clearInterval(backendProbeTimer);
  backendProbeTimer = setInterval(() => {
    if (api()) {
      initializeBackend("poll");
    }
  }, 250);
  if (api()) {
    initializeBackend("immediate");
  }
}

function bindUi() {
  $$(".nav button").forEach((btn) => btn.addEventListener("click", () => setView(btn.dataset.view)));

  $$(".segmented").forEach((group) => {
    group.addEventListener("click", async (event) => {
      if (event.target.tagName !== "BUTTON") return;
      await callBackend("set_mode", event.target.dataset.value === "1c" ? "1c" : "text");
      showToast("Режим изменён");
    });
  });

  $$("[data-toggle]").forEach((toggle) => {
    toggle.addEventListener("click", async () => {
      if (toggle.classList.contains("disabled")) return;
      toggle.classList.toggle("on");
      const setting = toggle.dataset.setting;
      if (setting) {
        await callBackend("save_settings", { [setting]: toggle.classList.contains("on") });
      }
      showToast(toggle.classList.contains("on") ? "Настройка включена" : "Настройка выключена");
    });
  });

  $$(".engine-option").forEach((option) => {
    option.addEventListener("click", async () => {
      await callBackend("set_engine", option.dataset.engine || "auto");
      showToast("Движок выбран: " + option.querySelector("h3").textContent);
    });
  });

  $("#engineSelect").addEventListener("change", async (event) => {
    await callBackend("set_engine", event.target.value);
    showToast("Движок: " + event.target.selectedOptions[0].textContent);
  });

  $("#chromeModeSelect").addEventListener("change", async (event) => {
    await callBackend("set_chrome_mode", event.target.value);
    showToast("Режим Chrome: " + event.target.selectedOptions[0].textContent);
  });

  $("#inputMethod").addEventListener("change", async (event) => {
    await callBackend("set_input_method", event.target.value);
    showToast("Метод ввода изменён");
  });

  $("#microphoneSelect").addEventListener("change", async (event) => {
    await callBackend("set_microphone", event.target.value);
    showToast("Микрофон выбран");
  });

  $("#refreshMicrophones").addEventListener("click", async () => {
    await refreshMicrophones();
    showToast("Список микрофонов обновлён");
  });

  $("#testMicrophone").addEventListener("click", async () => {
    const result = await callBackend("test_microphone");
    showToast(result?.message || "Тест микрофона запущен");
  });

  $("#testChromeSpeech").addEventListener("click", async () => {
    const result = await callBackend("test_chrome_speech");
    await pollStatus();
    showToast(result?.message || "Проверка Chrome завершена");
  });

  $("#restartChromeSpeech").addEventListener("click", async () => {
    await callBackend("restart_chrome_speech");
    showToast("Chrome Speech перезапущен");
  });

  $("#openChromeWindow").addEventListener("click", async () => {
    await callBackend("open_chrome_window");
    showToast("Открыто окно Chrome Speech");
  });

  $("#resetChromePermission").addEventListener("click", async () => {
    await callBackend("reset_chrome_permission");
    showToast("Профиль Chrome Speech сброшен");
  });

  $("#openChromeDownload").addEventListener("click", async () => {
    await callBackend("open_chrome_download");
    showToast("Открыта страница Google Chrome");
  });

  $("#testInsert").addEventListener("click", async () => {
    showToast("Переключитесь в редактор или Блокнот за 1.5 секунды");
    setTimeout(async () => {
      await callBackend("test_insert");
    }, 1500);
  });

  $("#micButton").addEventListener("click", async () => {
    if (micTogglePending) {
      showToast("Подождите, переключаю диктовку...");
      return;
    }
    const micButton = $("#micButton");
    micTogglePending = true;
    micButton.disabled = true;
    micButton.classList.add("busy");
    try {
      await logUi("toggle_listening called");
      const result = await callBackend("toggle_listening");
      if (result) showToast(result.listening ? "Диктовка включена" : "Диктовка остановлена");
    } finally {
      setTimeout(() => {
        micTogglePending = false;
        micButton.disabled = false;
        micButton.classList.remove("busy");
      }, 900);
    }
  });

  $("#formatTest").addEventListener("click", async () => {
    const formatted = await callBackend("test_formatting", $("#phraseInput").value);
    if (typeof formatted === "string") {
      $("#formatPreview").textContent = formatted;
      showToast("Фраза отформатирована");
    }
  });

  $("#checkUpdates").addEventListener("click", async () => {
    const result = await callBackend("check_updates");
    await pollStatus();
    if (!result) return;
    if (result.available) {
      showModal("Обновление найдено", `${result.message}\n\n${result.notes || ""}`, true);
    } else {
      showModal("Обновлений нет", result.message || "Актуальная версия уже установлена.");
    }
  });

  $("#openUpdateModal").addEventListener("click", () => setView("updates"));
  $("#quickSettings").addEventListener("click", () => setView("settings"));
  $("#modalCancel").addEventListener("click", closeModal);
  $("#modalOk").addEventListener("click", async () => {
    closeModal();
    if (pendingUpdate) {
      await callBackend("install_pending_update");
    }
  });
  $("#modalLayer").addEventListener("click", (event) => {
    if (event.target.id === "modalLayer") closeModal();
  });

  $("#addRule").addEventListener("click", () => showToast("Редактор словаря отключён до отдельного патча"));
  $("#importRules").addEventListener("click", () => showToast("Импорт словаря отключён"));
  $("#exportRules").addEventListener("click", () => showToast("Экспорт словаря отключён"));
  $("#openLogs").addEventListener("click", async () => {
    const result = await callBackend("open_logs");
    showToast(result?.ok ? "Лог открыт" : result?.message || "Не удалось открыть лог");
  });
  $("#copyLog").addEventListener("click", async () => {
    await navigator.clipboard?.writeText($("#appLog").textContent);
    showToast("Лог скопирован");
  });
  $("#clearLog").addEventListener("click", () => {
    $("#appLog").textContent = "[clear] Лог очищен в интерфейсе";
    showToast("Лог очищен в интерфейсе");
  });
  $("#saveSettings").addEventListener("click", async () => {
    await callBackend("save_settings", {
      github_owner: $("#githubOwner").value.trim(),
      github_repo: $("#githubRepo").value.trim(),
      release_asset_name: $("#releaseAssetName").value.trim(),
      chrome_mode: $("#chromeModeSelect").value,
    });
    showToast("Настройки сохранены");
  });

  document.addEventListener("keydown", (event) => {
    if (event.code === "Space" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      $("#micButton").click();
    }
    if (event.key === "Escape") closeModal();
  });
}

document.addEventListener("pywebviewready", () => {
  initializeBackend("pywebviewready");
});

window.addEventListener("DOMContentLoaded", () => {
  startSplashAnimation();
  bindUi();
  setListeningVisual({ listening: false, status_kind: "paused" });
  updateMicLevel(0);
  startBackendProbe();
  setTimeout(() => {
    if (!backendReady) showToast("Ожидание backend...");
  }, 900);
});
