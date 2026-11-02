const byId = (id) => document.getElementById(id);

const LANGUAGE_OPTIONS = [
  { code: "zh", label: "中文", locale: "zh-CN" },
  { code: "en", label: "英语", locale: "en-US" },
  { code: "ja", label: "日语", locale: "ja-JP" },
  { code: "ko", label: "韩语", locale: "ko-KR" },
  { code: "es", label: "西班牙语", locale: "es-ES" },
  { code: "fr", label: "法语", locale: "fr-FR" },
  { code: "de", label: "德语", locale: "de-DE" },
  { code: "pt", label: "葡萄牙语", locale: "pt-BR" },
  { code: "ru", label: "俄语", locale: "ru-RU" },
  { code: "it", label: "意大利语", locale: "it-IT" },
];
const READ_KINDS = ["text", "gift", "entry", "like", "paid", "membership"];

const elements = {
  connectionBadge: byId("connectionBadge"), notice: byId("notice"), conflictBar: byId("conflictBar"),
  saveDirtyDot: byId("saveDirtyDot"), currentYamlDirtyDot: byId("currentYamlDirtyDot"), cookieState: byId("cookieState"),
  room: byId("room"), cookieFile: byId("cookieFile"), cookieText: byId("cookieText"), cookieFileInput: byId("cookieFileInput"),
  historyLines: byId("historyLines"), entryMerge: byId("entryMerge"), giftMerge: byId("giftMerge"), autoConnect: byId("autoConnect"),
  width: byId("width"), height: byId("height"), panelRadius: byId("panelRadius"), panelPadding: byId("panelPadding"),
  rowGap: byId("rowGap"), maxMessages: byId("maxMessages"), panelBackground: byId("panelBackground"), panelOpacity: byId("panelOpacity"),
  panelOpacityValue: byId("panelOpacityValue"), panelBorder: byId("panelBorder"), panelBorderOpacity: byId("panelBorderOpacity"),
  panelBorderOpacityValue: byId("panelBorderOpacityValue"), showStatus: byId("showStatus"), fontFamily: byId("fontFamily"),
  fontSize: byId("fontSize"), fontFile: byId("fontFile"), textColor: byId("textColor"), mutedColor: byId("mutedColor"),
  accentColor: byId("accentColor"), ttsEnabled: byId("ttsEnabled"), ttsProxy: byId("ttsProxy"), ttsPreferMultilingual: byId("ttsPreferMultilingual"),
  ttsMultilingualVoice: byId("ttsMultilingualVoice"), ttsLanguagePriority: byId("ttsLanguagePriority"),
  voiceGrid: byId("voiceGrid"), ttsVoiceList: byId("ttsVoiceList"), ttsCatalogState: byId("ttsCatalogState"),
  ttsRate: byId("ttsRate"), ttsVolume: byId("ttsVolume"), ttsPitch: byId("ttsPitch"), ttsIncludeUsername: byId("ttsIncludeUsername"),
  ttsMaxChars: byId("ttsMaxChars"), ttsQueueSize: byId("ttsQueueSize"), ttsMinInterval: byId("ttsMinInterval"),
  ttsTestText: byId("ttsTestText"), ttsTestLanguage: byId("ttsTestLanguage"), serverHost: byId("serverHost"),
  serverPort: byId("serverPort"), serverOpenBrowser: byId("serverOpenBrowser"), storageDataDir: byId("storageDataDir"),
  loggingLevel: byId("loggingLevel"), reconnectBase: byId("reconnectBase"), reconnectMax: byId("reconnectMax"),
  configVersion: byId("configVersion"), configRevision: byId("configRevision"), configPath: byId("configPath"),
  examplePath: byId("examplePath"), yamlEditor: byId("yamlEditor"), yamlExample: byId("yamlExample"),
  yamlError: byId("yamlError"), currentYamlTab: byId("currentYamlTab"), exampleYamlTab: byId("exampleYamlTab"),
  currentYamlPanel: byId("currentYamlPanel"), exampleYamlPanel: byId("exampleYamlPanel"),
  previewFrame: byId("previewFrame"), previewViewport: byId("previewViewport"), overlayUrl: byId("overlayUrl"),
};

const state = {
  currentDocument: null, savedConfig: null, draft: null, fontsLoaded: false, dirty: false,
  draftSource: "form", yamlValid: true, suppressEvents: false, conflictDocument: null,
  formRenderTimer: null, yamlValidateTimer: null, formRenderSequence: 0, yamlValidateSequence: 0,
  socket: null, socketTimer: null,
};

const clone = (value) => JSON.parse(JSON.stringify(value));

function showNotice(message, isError = false) {
  elements.notice.textContent = message;
  elements.notice.classList.toggle("error", isError);
  elements.notice.classList.add("visible");
  window.clearTimeout(showNotice.timer);
  showNotice.timer = window.setTimeout(() => elements.notice.classList.remove("visible"), 6000);
}

function makeError(message, status, detail) {
  const error = new Error(message);
  error.status = status;
  error.detail = detail;
  return error;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {}
    const message = typeof detail === "string" ? detail : detail.message || `HTTP ${response.status}`;
    throw makeError(message, response.status, detail);
  }
  return response.json();
}

function numberValue(element, fallback) {
  const value = Number(element.value);
  return Number.isFinite(value) ? value : fallback;
}

function parseLanguagePriority(value) {
  return value.split(",").map((language) => language.trim().toLowerCase()).filter(Boolean);
}

function activeLanguages() {
  const parsed = parseLanguagePriority(elements.ttsLanguagePriority.value);
  return parsed.length ? parsed : LANGUAGE_OPTIONS.map((item) => item.code);
}

function buildVoiceGrid() {
  elements.voiceGrid.replaceChildren();
  for (const language of LANGUAGE_OPTIONS) {
    const label = document.createElement("label");
    label.className = "field voice-field";
    const title = document.createElement("span");
    title.textContent = `${language.label} (${language.code})`;
    const input = document.createElement("input");
    input.id = `ttsVoice-${language.code}`;
    input.type = "text";
    input.setAttribute("list", "ttsVoiceList");
    input.spellcheck = false;
    input.dataset.path = `tts.voices.${language.code}`;
    input.placeholder = language.locale;
    label.append(title, input);
    elements.voiceGrid.append(label);
  }
}

function buildTestLanguageOptions(selected = null) {
  const previous = selected || elements.ttsTestLanguage.value || "zh";
  elements.ttsTestLanguage.replaceChildren();
  const enabled = new Set(activeLanguages());
  for (const language of LANGUAGE_OPTIONS) {
    if (!enabled.has(language.code)) continue;
    const option = document.createElement("option");
    option.value = language.code;
    option.textContent = `${language.label} (${language.code})`;
    elements.ttsTestLanguage.append(option);
  }
  if ([...elements.ttsTestLanguage.options].some((option) => option.value === previous)) {
    elements.ttsTestLanguage.value = previous;
  }
}

function addFontOption(family, url = "", label = family) {
  const option = document.createElement("option");
  option.value = family;
  option.textContent = label;
  option.dataset.url = url;
  elements.fontFamily.append(option);
  return option;
}

function selectFont(font) {
  let option = [...elements.fontFamily.options].find(
    (candidate) => candidate.value === font.family && (candidate.dataset.url || null) === (font.url || null),
  );
  if (!option) option = addFontOption(font.family, font.url || "", `${font.family}（当前）`);
  elements.fontFamily.value = option.value;
  elements.fontFamily.selectedOptions[0].dataset.url = font.url || "";
}

function loadFonts(data, desired) {
  elements.fontFamily.replaceChildren();
  const systems = new Set(data.system || []);
  for (const family of systems) addFontOption(family);
  for (const uploaded of data.uploaded || []) addFontOption(uploaded.family, uploaded.url, `${uploaded.family}（已上传）`);
  if (desired) selectFont(desired);
  state.fontsLoaded = true;
}

function collectConfig() {
  const base = clone(state.draft || state.savedConfig || state.currentDocument?.config || {});
  const selectedFont = elements.fontFamily.selectedOptions[0];
  base.room = elements.room.value.trim();
  base.cookie_file = elements.cookieFile.value.trim();
  base.history_lines = numberValue(elements.historyLines, 60);
  base.entry_merge_seconds = numberValue(elements.entryMerge, 5);
  base.gift_merge_seconds = numberValue(elements.giftMerge, 5);
  base.auto_connect = elements.autoConnect.checked;
  base.server = { ...(base.server || {}), host: elements.serverHost.value.trim(), port: numberValue(elements.serverPort, 6161), open_browser: elements.serverOpenBrowser.checked };
  base.storage = { ...(base.storage || {}), data_dir: elements.storageDataDir.value.trim() };
  base.reconnect = { ...(base.reconnect || {}), base_seconds: numberValue(elements.reconnectBase, 1), max_seconds: numberValue(elements.reconnectMax, 30) };
  base.logging = { ...(base.logging || {}), level: elements.loggingLevel.value };
  base.theme = {
    ...(base.theme || {}), width: numberValue(elements.width, 480), height: numberValue(elements.height, 1080),
    font: { family: elements.fontFamily.value || "LXGW WenKai Mono", size: numberValue(elements.fontSize, 28), url: selectedFont?.dataset.url || null },
    panel_background: elements.panelBackground.value, panel_opacity: numberValue(elements.panelOpacity, 0.58),
    panel_radius: numberValue(elements.panelRadius, 28), panel_border: elements.panelBorder.value,
    panel_border_opacity: numberValue(elements.panelBorderOpacity, 0.12), panel_padding: numberValue(elements.panelPadding, 18),
    row_gap: numberValue(elements.rowGap, 8), text_color: elements.textColor.value, muted_color: elements.mutedColor.value,
    accent_color: elements.accentColor.value, show_status: elements.showStatus.checked, max_messages: numberValue(elements.maxMessages, 80),
  };
  const voices = {};
  for (const language of LANGUAGE_OPTIONS) voices[language.code] = byId(`ttsVoice-${language.code}`).value.trim();
  base.tts = {
    ...(base.tts || {}), enabled: elements.ttsEnabled.checked,
    proxy: elements.ttsProxy.value.trim(),
    prefer_multilingual_voice: elements.ttsPreferMultilingual.checked,
    multilingual_voice: elements.ttsMultilingualVoice.value.trim(),
    language_priority: parseLanguagePriority(elements.ttsLanguagePriority.value), voices,
    rate: elements.ttsRate.value, volume: elements.ttsVolume.value, pitch: elements.ttsPitch.value,
    read_kinds: [...document.querySelectorAll(".read-kind:checked")].map((input) => input.value),
    include_username: elements.ttsIncludeUsername.checked, max_chars: numberValue(elements.ttsMaxChars, 180),
    queue_size: numberValue(elements.ttsQueueSize, 32), min_interval_ms: numberValue(elements.ttsMinInterval, 300),
  };
  return base;
}

function applyConfigToControls(config) {
  state.suppressEvents = true;
  try {
    elements.room.value = config.room || "";
    elements.cookieFile.value = config.cookie_file || "";
    elements.historyLines.value = config.history_lines;
    elements.entryMerge.value = config.entry_merge_seconds;
    elements.giftMerge.value = config.gift_merge_seconds;
    elements.autoConnect.checked = config.auto_connect;
    elements.serverHost.value = config.server.host;
    elements.serverPort.value = config.server.port;
    elements.serverOpenBrowser.checked = config.server.open_browser;
    elements.storageDataDir.value = config.storage.data_dir;
    elements.loggingLevel.value = config.logging.level;
    elements.reconnectBase.value = config.reconnect.base_seconds;
    elements.reconnectMax.value = config.reconnect.max_seconds;
    elements.width.value = config.theme.width;
    elements.height.value = config.theme.height;
    elements.panelRadius.value = config.theme.panel_radius;
    elements.panelPadding.value = config.theme.panel_padding;
    elements.rowGap.value = config.theme.row_gap;
    elements.maxMessages.value = config.theme.max_messages;
    elements.panelBackground.value = config.theme.panel_background;
    elements.panelOpacity.value = config.theme.panel_opacity;
    elements.panelOpacityValue.textContent = Number(config.theme.panel_opacity).toFixed(2);
    elements.panelBorder.value = config.theme.panel_border;
    elements.panelBorderOpacity.value = config.theme.panel_border_opacity;
    elements.panelBorderOpacityValue.textContent = Number(config.theme.panel_border_opacity).toFixed(2);
    elements.showStatus.checked = config.theme.show_status;
    elements.fontSize.value = config.theme.font.size;
    elements.textColor.value = config.theme.text_color;
    elements.mutedColor.value = config.theme.muted_color;
    elements.accentColor.value = config.theme.accent_color;
    if (state.fontsLoaded) selectFont(config.theme.font);
    elements.ttsEnabled.checked = config.tts.enabled;
    elements.ttsProxy.value = config.tts.proxy || "";
    elements.ttsPreferMultilingual.checked = config.tts.prefer_multilingual_voice;
    elements.ttsMultilingualVoice.value = config.tts.multilingual_voice || "";
    elements.ttsLanguagePriority.value = config.tts.language_priority.join(", ");
    elements.ttsRate.value = config.tts.rate;
    elements.ttsVolume.value = config.tts.volume;
    elements.ttsPitch.value = config.tts.pitch;
    elements.ttsIncludeUsername.checked = config.tts.include_username;
    elements.ttsMaxChars.value = config.tts.max_chars;
    elements.ttsQueueSize.value = config.tts.queue_size;
    elements.ttsMinInterval.value = config.tts.min_interval_ms;
    for (const language of LANGUAGE_OPTIONS) byId(`ttsVoice-${language.code}`).value = config.tts.voices[language.code] || "";
    for (const input of document.querySelectorAll(".read-kind")) input.checked = config.tts.read_kinds.includes(input.value);
    buildTestLanguageOptions(config.tts.language_priority[0] || "zh");
    elements.configVersion.value = String(config.version);
  } finally {
    state.suppressEvents = false;
  }
}

function getPathValue(object, path) {
  return path.split(".").reduce((value, key) => (value == null ? undefined : value[key]), object);
}

function controlValue(element) {
  const path = element.dataset.path;
  if (path === "tts.language_priority") return parseLanguagePriority(element.value);
  if (path === "tts.read_kinds") return [...document.querySelectorAll(".read-kind:checked")].map((input) => input.value);
  if (element.type === "checkbox") return element.checked;
  if (element.type === "number") return numberValue(element, 0);
  return element.value;
}

function valuesEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function refreshDirtyIndicators() {
  if (!state.savedConfig || !state.draft) return;
  const elementsWithPath = [...document.querySelectorAll("[data-path]")];
  const paths = new Set(elementsWithPath.map((element) => element.dataset.path));
  for (const path of paths) {
    const element = elementsWithPath.find((candidate) => candidate.dataset.path === path);
    if (!element) continue;
    const dirty = !valuesEqual(controlValue(element), getPathValue(state.draft, path));
    const wrapper = element.closest(".field, .switch-row, .checkbox-grid") || element;
    wrapper.classList.toggle("is-dirty", dirty);
  }
  elements.saveDirtyDot.hidden = !state.dirty;
  elements.currentYamlDirtyDot.hidden = !state.dirty;
  document.title = `${state.dirty ? "● " : ""}Bili Live Danmaku · 控制台`;
}

function markDirty(source = "form") {
  state.draft = collectConfig();
  state.draftSource = source;
  state.dirty = !valuesEqual(state.draft, state.savedConfig);
  refreshDirtyIndicators();
}

function setYamlError(message = "") {
  elements.yamlError.hidden = !message;
  elements.yamlError.textContent = message;
}

function setYamlTab(tab) {
  const current = tab === "current";
  elements.currentYamlTab.classList.toggle("active", current);
  elements.exampleYamlTab.classList.toggle("active", !current);
  elements.currentYamlPanel.hidden = !current;
  elements.exampleYamlPanel.hidden = current;
}

function applyDocument(documentData, { clearDirty = true } = {}) {
  state.currentDocument = clone(documentData);
  state.savedConfig = clone(documentData.config);
  state.draft = clone(documentData.config);
  applyConfigToControls(documentData.config);
  elements.yamlEditor.value = documentData.yaml_text;
  elements.yamlExample.value = documentData.example_yaml || "示例配置文件不存在。";
  elements.configPath.textContent = `当前配置：${documentData.config_path}`;
  elements.examplePath.textContent = `示例配置：${documentData.example_path}`;
  elements.configRevision.textContent = `revision: ${documentData.revision.slice(0, 12)}`;
  if (clearDirty) {
    state.dirty = false;
    state.yamlValid = true;
    state.draftSource = "form";
    state.conflictDocument = null;
    elements.conflictBar.hidden = true;
    setYamlError("");
    refreshDirtyIndicators();
  }
  sendPreview();
}

function updateRangeOutputs() {
  elements.panelOpacityValue.textContent = Number(elements.panelOpacity.value).toFixed(2);
  elements.panelBorderOpacityValue.textContent = Number(elements.panelBorderOpacity.value).toFixed(2);
}

function sendPreview() {
  const config = state.draft || collectConfig();
  resizePreview(config.theme.width, config.theme.height);
  elements.previewFrame.contentWindow?.postMessage({ type: "preview-config", config }, location.origin);
}

function resizePreview(width, height) {
  const viewportWidth = elements.previewViewport.clientWidth - 36;
  const viewportHeight = Math.max(420, window.innerHeight - 300);
  const scale = Math.min(viewportWidth / width, viewportHeight / height, 0.78);
  elements.previewFrame.style.width = `${width}px`;
  elements.previewFrame.style.height = `${height}px`;
  elements.previewFrame.style.transform = `scale(${scale})`;
  const stage = elements.previewFrame.parentElement;
  stage.style.width = `${Math.max(1, width * scale)}px`;
  stage.style.height = `${Math.max(1, height * scale)}px`;
}

function scheduleFormYamlRender() {
  window.clearTimeout(state.formRenderTimer);
  const sequence = ++state.formRenderSequence;
  state.formRenderTimer = window.setTimeout(async () => {
    if (state.draftSource !== "form") return;
    try {
      const response = await fetchJson("/api/config/render", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config: state.draft }),
      });
      if (sequence !== state.formRenderSequence || state.draftSource !== "form") return;
      elements.yamlEditor.value = response.yaml;
      state.yamlValid = true;
      setYamlError("");
    } catch (error) {
      setYamlError(error.message);
    }
  }, 300);
}

async function validateYamlDraft({ applyToForm = true } = {}) {
  const sequence = ++state.yamlValidateSequence;
  try {
    const response = await fetchJson("/api/config/validate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ yaml: elements.yamlEditor.value }),
    });
    if (sequence !== state.yamlValidateSequence) return false;
    state.yamlValid = true;
    setYamlError("");
    if (applyToForm) {
      applyConfigToControls(response.config);
      state.draft = clone(response.config);
      state.draftSource = "yaml";
      state.dirty = !valuesEqual(state.draft, state.savedConfig);
      refreshDirtyIndicators();
      sendPreview();
    }
    return true;
  } catch (error) {
    if (sequence !== state.yamlValidateSequence) return false;
    state.yamlValid = false;
    const errors = error.detail?.errors;
    setYamlError(errors ? `${error.message}\n${JSON.stringify(errors, null, 2)}` : error.message);
    return false;
  }
}

function scheduleYamlValidation() {
  window.clearTimeout(state.yamlValidateTimer);
  state.yamlValidateTimer = window.setTimeout(() => void validateYamlDraft({ applyToForm: true }), 300);
}

async function saveConfig(showMessage = true, baseRevision = null) {
  if (state.draftSource === "yaml" && !state.yamlValid) {
    showNotice("YAML 仍有错误，无法保存。", true);
    return null;
  }
  state.draft = state.draftSource === "yaml" ? state.draft : collectConfig();
  const revision = baseRevision || state.currentDocument.revision;
  const yamlSource = state.draftSource === "yaml";
  const options = {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(yamlSource ? { yaml: elements.yamlEditor.value, base_revision: revision } : { config: state.draft, base_revision: revision }),
  };
  try {
    const documentData = await fetchJson(yamlSource ? "/api/config/document/yaml" : "/api/config/document", options);
    applyDocument(documentData);
    if (showMessage) showNotice("配置已保存并应用。");
    return documentData;
  } catch (error) {
    if (error.status === 409 && error.detail?.document) {
      state.conflictDocument = error.detail.document;
      elements.conflictBar.hidden = false;
      showNotice("检测到外部配置修改，请选择载入磁盘版本或保存当前草稿。", true);
      return null;
    }
    showNotice(`保存失败：${error.message}`, true);
    return null;
  }
}

async function refreshStatus() {
  try {
    const data = await fetchJson("/api/status");
    const status = data.status;
    elements.connectionBadge.dataset.state = status.state;
    elements.connectionBadge.textContent = status.message || status.state;
    elements.cookieState.textContent = data.cookie_present ? "Cookie：已配置" : "Cookie：匿名模式";
    elements.cookieState.style.color = data.cookie_present ? "#8ce7ae" : "";
  } catch {
    elements.connectionBadge.dataset.state = "error";
    elements.connectionBadge.textContent = "服务不可用";
  }
}

async function loadConfigDocument() {
  const documentData = await fetchJson("/api/config/document");
  if (state.dirty) {
    state.conflictDocument = documentData;
    elements.conflictBar.hidden = false;
  } else {
    applyDocument(documentData);
  }
}

async function connectSocket() {
  window.clearTimeout(state.socketTimer);
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws`);
  state.socket = socket;
  socket.addEventListener("message", (event) => {
    let envelope;
    try { envelope = JSON.parse(event.data); } catch { return; }
    if (envelope.type === "config") void loadConfigDocument();
    else if (envelope.type === "config_error") setYamlError(`配置文件监听失败：${envelope.payload.message}`);
  });
  socket.addEventListener("close", () => { state.socketTimer = window.setTimeout(connectSocket, 2000); });
}

async function importCookie() {
  await saveConfig(false);
  let cookie = elements.cookieText.value.trim();
  if (!cookie && elements.cookieFileInput.files?.[0]) cookie = (await elements.cookieFileInput.files[0].text()).trim();
  if (!cookie) { showNotice("请先粘贴 Cookie 或选择 Cookie 文件。", true); return; }
  await fetchJson("/api/cookie", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cookie }) });
  elements.cookieText.value = "";
  showNotice("Cookie 已导入，连接正在刷新。");
  await refreshStatus();
}

async function uploadFont() {
  const file = elements.fontFile.files?.[0];
  if (!file) { showNotice("请先选择字体文件。", true); return; }
  const form = new FormData();
  form.append("file", file);
  const uploaded = await fetchJson("/api/fonts", { method: "POST", body: form });
  const fonts = await fetchJson("/api/fonts");
  loadFonts(fonts, { family: uploaded.family, url: uploaded.url });
  markDirty("form");
  await saveConfig(false);
  showNotice("字体已上传并应用。");
}

async function loadTtsVoices() {
  try {
    const data = await fetchJson("/api/tts/voices");
    elements.ttsVoiceList.replaceChildren();
    for (const voice of data.voices) {
      const option = document.createElement("option");
      option.value = voice.short_name;
      option.label = `${voice.short_name} · ${voice.locale}${voice.gender ? ` · ${voice.gender}` : ""}`;
      elements.ttsVoiceList.append(option);
    }
    elements.ttsCatalogState.textContent = data.offline ? `离线推荐 ${data.voices.length} 个` : `在线音色 ${data.voices.length} 个`;
  } catch {
    elements.ttsCatalogState.textContent = "音色列表读取失败";
  }
}

async function testTts() {
  const saved = await saveConfig(false);
  if (!saved) return;
  await fetchJson("/api/tts/test", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: elements.ttsTestText.value.trim() || "弹幕朗读测试成功", language: elements.ttsTestLanguage.value || null }),
  });
  showNotice("测试朗读已提交。");
}

function bindEvents() {
  document.querySelectorAll("[data-path]").forEach((element) => {
    if (element.classList.contains("checkbox-grid")) return;
    const eventName = element.tagName === "SELECT" || element.type === "checkbox" || element.type === "range" ? "change" : "input";
    element.addEventListener(eventName, () => {
      if (state.suppressEvents) return;
      if (element === elements.panelOpacity || element === elements.panelBorderOpacity) updateRangeOutputs();
      if (element.closest(".preview-field") || element === elements.fontFamily) sendPreview();
      if (element === elements.ttsLanguagePriority) buildTestLanguageOptions();
      markDirty("form");
      scheduleFormYamlRender();
    });
  });
  document.querySelectorAll(".read-kind").forEach((input) => {
    input.addEventListener("change", () => {
      if (state.suppressEvents) return;
      markDirty("form");
      scheduleFormYamlRender();
    });
  });
  elements.yamlEditor.addEventListener("input", () => {
    if (state.suppressEvents) return;
    state.draftSource = "yaml";
    state.dirty = true;
    state.yamlValid = false;
    refreshDirtyIndicators();
    scheduleYamlValidation();
  });
  elements.currentYamlTab.addEventListener("click", () => setYamlTab("current"));
  elements.exampleYamlTab.addEventListener("click", () => setYamlTab("example"));
  byId("applyYamlBtn").addEventListener("click", async () => {
    const valid = await validateYamlDraft({ applyToForm: true });
    if (valid) showNotice("YAML 已校验并应用为草稿，按 Ctrl+S 保存。");
  });
  byId("loadExampleBtn").addEventListener("click", async () => {
    elements.yamlEditor.value = elements.yamlExample.value;
    setYamlTab("current");
    state.draftSource = "yaml";
    state.dirty = true;
    state.yamlValid = false;
    refreshDirtyIndicators();
    if (await validateYamlDraft({ applyToForm: true })) showNotice("示例配置已载入为草稿。");
  });
  byId("reloadConfigBtn").addEventListener("click", async () => {
    if (state.dirty && !window.confirm("当前有未保存修改，确定重新读取磁盘配置？")) return;
    applyDocument(await fetchJson("/api/config/document"));
    showNotice("已重新读取 config.yaml。");
  });
  byId("loadConflictBtn").addEventListener("click", () => {
    if (!state.conflictDocument) return;
    applyDocument(state.conflictDocument);
    showNotice("已载入磁盘配置。");
  });
  byId("saveConflictBtn").addEventListener("click", async () => {
    if (!state.conflictDocument) return;
    await saveConfig(true, state.conflictDocument.revision);
  });
  byId("saveBtn").addEventListener("click", () => void saveConfig());
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void saveConfig();
    }
  });
  byId("openOverlayBtn").addEventListener("click", () => window.open("/overlay", "_blank", "noopener"));
  byId("copyOverlayBtn").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(`${location.origin}/overlay`); showNotice("OBS 浏览器源地址已复制。"); }
    catch { showNotice("复制失败，请手动选择下方地址。", true); }
  });
  byId("importCookieBtn").addEventListener("click", () => importCookie().catch((error) => showNotice(error.message, true)));
  byId("deleteCookieBtn").addEventListener("click", async () => {
    if (!window.confirm("确定删除本地 Cookie 文件？")) return;
    try { await fetchJson("/api/cookie", { method: "DELETE" }); showNotice("Cookie 已删除，当前连接切换为匿名模式。"); await refreshStatus(); }
    catch (error) { showNotice(error.message, true); }
  });
  byId("restartBtn").addEventListener("click", async () => {
    try { await saveConfig(false); await fetchJson("/api/restart", { method: "POST" }); showNotice("正在重新连接直播间。"); }
    catch (error) { showNotice(error.message, true); }
  });
  byId("demoBtn").addEventListener("click", async () => {
    try { await fetchJson("/api/demo?count=10", { method: "POST" }); showNotice("已发送一组演示消息。"); }
    catch (error) { showNotice(error.message, true); }
  });
  byId("previewDemoBtn").addEventListener("click", async () => {
    try { await fetchJson("/api/demo?count=10", { method: "POST" }); showNotice("已发送带本地头像的测试消息。"); }
    catch (error) { showNotice(error.message, true); }
  });
  byId("uploadFontBtn").addEventListener("click", () => uploadFont().catch((error) => showNotice(error.message, true)));
  elements.fontFile.addEventListener("change", () => { if (elements.fontFile.files?.length) uploadFont().catch((error) => showNotice(error.message, true)); });
  elements.cookieFileInput.addEventListener("change", async () => {
    const file = elements.cookieFileInput.files?.[0];
    if (!file) return;
    elements.cookieText.value = await file.text();
    showNotice(`已读取 ${file.name}，点击“导入 Cookie”写入。`);
  });
  byId("testTtsBtn").addEventListener("click", () => testTts().catch((error) => showNotice(error.message, true)));
  elements.previewFrame.addEventListener("load", () => sendPreview());
  window.addEventListener("resize", () => { const config = state.draft || collectConfig(); resizePreview(config.theme.width, config.theme.height); });
}

async function boot() {
  buildVoiceGrid();
  buildTestLanguageOptions("zh");
  bindEvents();
  elements.overlayUrl.textContent = `${location.origin}/overlay`;
  try {
    const [documentData, fonts] = await Promise.all([fetchJson("/api/config/document"), fetchJson("/api/fonts")]);
    loadFonts(fonts, documentData.config.theme.font);
    applyDocument(documentData);
    await loadTtsVoices();
    await refreshStatus();
    connectSocket();
  } catch (error) {
    showNotice(`配置加载失败：${error.message}`, true);
  }
  window.setInterval(refreshStatus, 2000);
}

void boot();
