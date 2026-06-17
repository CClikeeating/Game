from __future__ import annotations

import json
from typing import Any


def web_alpha_page_html(config: dict[str, Any]) -> str:
    boot = {
        "defaultMode": config.get("default_mode", "bailian_rag_fast"),
        "modes": config.get("modes", {}),
        "limits": {
            "daily_reply_quota": config.get("daily_reply_quota", 20),
            "web_ip_daily_quota": config.get("web_ip_daily_quota", 20),
            "web_site_daily_quota": config.get("web_site_daily_quota", 500),
            "max_images_per_reply": config.get("max_images_per_reply", 3),
            "min_images_per_reply": config.get("min_images_per_reply", 1),
            "max_image_mb": config.get("max_image_mb", 8),
            "mode_unit_costs": config.get("mode_unit_costs", {}),
        },
    }
    boot_json = json.dumps(boot, ensure_ascii=False).replace("<", "\\u003c")
    return PAGE.replace("__BAIOU_BOOT__", boot_json)


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Baiou</title>
  <style>
    :root {
      --bg: #f6f7f4;
      --surface: #ffffff;
      --surface-2: #eef3f1;
      --ink: #162033;
      --muted: #667085;
      --line: #d9e1dd;
      --accent: #176b5d;
      --accent-2: #c24f3d;
      --blue: #2f5f98;
      --bad: #b42318;
      --shadow: 0 16px 42px rgba(21, 36, 52, .10);
      --radius: 8px;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(135deg, rgba(23, 107, 93, .09), transparent 34%),
        linear-gradient(315deg, rgba(194, 79, 61, .08), transparent 30%),
        var(--bg);
      color: var(--ink);
    }
    button, input, textarea { font: inherit; }
    button {
      min-height: 46px;
      border: 0;
      border-radius: var(--radius);
      padding: 0 16px;
      background: var(--accent);
      color: #fff;
      font-weight: 800;
      cursor: pointer;
    }
    button:focus-visible, input:focus-visible, textarea:focus-visible { outline: 3px solid rgba(47, 95, 152, .28); outline-offset: 2px; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    button.mode { background: #fff; color: var(--muted); border: 1px solid var(--line); }
    button.mode.active { background: var(--ink); color: #fff; border-color: var(--ink); }
    button.ghost { background: #fff; color: var(--accent); border: 1px solid #b8d6ce; }
    .shell { width: min(1080px, 100%); margin: 0 auto; padding: 12px; }
    .topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    h2 { margin: 0; font-size: 17px; letter-spacing: 0; }
    h3 { margin: 0 0 8px; font-size: 13px; color: #344054; }
    .subtle { color: var(--muted); font-size: 13px; line-height: 1.45; margin: 4px 0 0; }
    .quota { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    .pill { border: 1px solid var(--line); background: rgba(255,255,255,.86); border-radius: 999px; padding: 7px 10px; color: var(--muted); font-size: 13px; white-space: nowrap; }
    .layout { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 12px; align-items: start; }
    .panel { background: rgba(255,255,255,.95); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); }
    .panel-head { padding: 15px 15px 0; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .panel-body { padding: 15px; }
    .field { display: grid; gap: 7px; margin-bottom: 13px; }
    label, .label { color: #263445; font-size: 13px; font-weight: 800; }
    textarea, input[type="text"], input[type="password"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 12px;
      background: #fff;
      color: var(--ink);
      outline: none;
    }
    textarea { min-height: 88px; resize: vertical; line-height: 1.55; }
    #question { min-height: 74px; font-size: 16px; }
    .upload {
      display: grid;
      gap: 8px;
      border: 1px dashed #9eb8b0;
      border-radius: var(--radius);
      padding: 12px;
      background: var(--surface-2);
    }
    .upload-state {
      display: grid;
      gap: 7px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      padding: 10px;
    }
    .upload-count { font-weight: 800; color: var(--ink); font-size: 13px; }
    .file-list { display: flex; gap: 6px; flex-wrap: wrap; }
    .file-chip {
      border: 1px solid #cddbd7;
      border-radius: 999px;
      padding: 5px 8px;
      background: #f8fbfa;
      color: var(--muted);
      font-size: 12px;
      max-width: 100%;
      overflow-wrap: anywhere;
    }
    .upload-error { color: var(--bad); font-size: 12px; line-height: 1.45; }
    .privacy { color: var(--muted); font-size: 12px; line-height: 1.5; }
    .mode-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .mode small { display: block; margin-top: 2px; font-weight: 600; opacity: .78; }
    .actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
    .dry { display: inline-flex; align-items: center; gap: 7px; color: var(--muted); font-size: 13px; }
    .status { min-height: 21px; color: var(--muted); font-size: 13px; }
    .status.bad { color: var(--bad); }
    .gate { max-width: 420px; margin: 12vh auto 0; }
    .gate h1 { font-size: 30px; }
    .hidden { display: none !important; }
    .result-empty { min-height: 360px; display: grid; place-items: center; color: var(--muted); text-align: center; padding: 24px; }
    .answer {
      border: 1px solid #a8d3c8;
      background: linear-gradient(180deg, #edf8f4, #f8fffc);
      border-radius: var(--radius);
      padding: 18px;
      white-space: pre-wrap;
      line-height: 1.75;
      font-size: 18px;
      font-weight: 750;
    }
    .assist { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }
    .box { border: 1px solid var(--line); border-radius: var(--radius); background: #fff; padding: 12px; min-height: 88px; }
    .box pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--muted); font-family: inherit; font-size: 13px; line-height: 1.55; }
    .feedback { display: grid; gap: 8px; margin-top: 12px; }
    .feedback-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    @media (max-width: 820px) {
      .shell { padding: 10px; }
      .topbar { align-items: flex-start; }
      .layout { grid-template-columns: 1fr; }
      .input-panel { order: 1; }
      .result-panel { order: 2; }
      .assist { grid-template-columns: 1fr; }
      .quota { justify-content: flex-start; }
    }
    @media (max-width: 460px) {
      h1 { font-size: 22px; }
      .topbar { display: grid; }
      .mode-row { grid-template-columns: 1fr; }
      .actions { display: grid; }
      button { width: 100%; }
      .dry { justify-content: center; }
      .answer { font-size: 17px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section id="gate" class="gate panel">
      <div class="panel-body">
        <h1>Baiou</h1>
        <p class="subtle">内测访问</p>
        <div class="field" style="margin-top:18px">
          <label for="accessCode">访问码</label>
          <input id="accessCode" type="password" autocomplete="one-time-code">
        </div>
        <div class="actions">
          <button id="loginBtn" type="button">进入</button>
          <span id="loginStatus" class="status" aria-live="polite"></span>
        </div>
      </div>
    </section>

    <section id="app" class="hidden">
      <div class="topbar">
        <div>
          <h1>Baiou</h1>
          <p class="subtle">把截图变成一条更合适的回复</p>
        </div>
        <div class="quota">
          <span class="pill" id="userQuota">今日剩余 --</span>
          <span class="pill" id="siteQuota">全站剩余 --</span>
        </div>
      </div>
      <div class="layout">
        <section class="panel input-panel">
          <div class="panel-head">
            <h2>生成回复</h2>
            <span class="pill" id="modeCost">扣费 --</span>
          </div>
          <div class="panel-body">
            <div class="field">
              <label for="images">聊天截图</label>
              <div class="upload">
                <input id="images" type="file" accept="image/png,image/jpeg,image/webp" multiple>
                <div class="upload-state" aria-live="polite">
                  <div class="upload-count" id="uploadCount">已选择 0 张 / 最多 3 张</div>
                  <div class="file-list" id="fileList"><span class="file-chip">还没选择图片</span></div>
                  <div class="upload-error hidden" id="uploadError"></div>
                </div>
                <div class="privacy" id="uploadHint">截图仅用于本次分析与服务优化，并会按保留周期清理；请勿上传身份证、银行卡、住址等敏感信息。</div>
              </div>
            </div>
            <div class="field">
              <label for="question">我该怎么回</label>
              <textarea id="question">我该怎么回</textarea>
            </div>
            <div class="field">
              <label for="context">补充背景</label>
              <textarea id="context" placeholder="可选：关系阶段、刚才发生了什么、你想要的语气"></textarea>
            </div>
            <div class="field">
              <div class="label">模式</div>
              <div class="mode-row">
                <button class="mode active" type="button" data-mode="bailian_rag_fast">快速<small>日常够用</small></button>
                <button class="mode" type="button" data-mode="bailian_rag_quality">质量<small>会更慢，消耗 2 次额度</small></button>
                <button class="mode" type="button" data-mode="bailian_rag_strategy_fast">策略<small>实验模式，速度接近快速</small></button>
                <button class="mode" type="button" data-mode="bailian_rag_strategy_quality">策略质量<small>显式策略，消耗 2 次额度</small></button>
              </div>
            </div>
            <div class="actions">
              <label class="dry"><input id="dryRun" type="checkbox"> dry-run</label>
              <button id="generateBtn" type="button">生成推荐回复</button>
            </div>
            <div id="workStatus" class="status" aria-live="polite"></div>
          </div>
        </section>

        <section class="panel result-panel">
          <div class="panel-head"><h2>推荐回复</h2></div>
          <div id="result" class="panel-body result-empty">生成后会显示在这里。</div>
        </section>
      </div>
    </section>
  </main>

  <script id="boot" type="application/json">__BAIOU_BOOT__</script>
  <script>
    const boot = JSON.parse(document.getElementById("boot").textContent);
    const state = {
      token: localStorage.getItem("baiou_web_token") || "",
      conversation: null,
      mode: boot.defaultMode || "bailian_rag_fast",
      lastRun: null,
      limits: boot.limits || {},
      uploadError: "",
      waitingTimer: null,
      waitingStartedAt: 0,
      waitingPhase: ""
    };
    const $ = selector => document.querySelector(selector);
    const escapeHtml = value => String(value || "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    const setStatus = (selector, text, bad = false) => {
      const node = $(selector);
      node.textContent = text || "";
      node.classList.toggle("bad", !!bad);
    };
    function headers(json = true) {
      const output = state.token ? { Authorization: "Bearer " + state.token } : {};
      if (json) output["Content-Type"] = "application/json";
      return output;
    }
    async function api(path, options = {}) {
      const res = await fetch(path, { ...options, headers: { ...headers(options.json !== false), ...(options.headers || {}) } });
      const type = res.headers.get("content-type") || "";
      const data = type.includes("application/json") ? await res.json() : await res.text();
      if (!res.ok || data.ok === false) throw new Error((data.error && data.error.message) || "请求失败");
      return data;
    }
    function showApp(show) {
      $("#gate").classList.toggle("hidden", show);
      $("#app").classList.toggle("hidden", !show);
    }
    function updateLimits(limits) {
      state.limits = limits || state.limits || {};
      $("#userQuota").textContent = "今日剩余 " + (state.limits.daily_reply_remaining ?? "--");
      $("#siteQuota").textContent = "全站剩余 " + (state.limits.web_site_daily_remaining ?? "--");
      const max = state.limits.max_images_per_reply || 3;
      const mb = state.limits.max_image_mb || 8;
      $("#uploadHint").textContent = `最多 ${max} 张，单张 ${mb}MB。截图仅用于本次分析与服务优化，并会按保留周期清理；请勿上传身份证、银行卡、住址等敏感信息。`;
      updateModeCost();
      renderUploadState();
    }
    function updateModeCost() {
      const costs = state.limits.mode_unit_costs || {};
      const cost = costs[state.mode] || 1;
      if (state.mode === "bailian_rag_quality") {
        $("#modeCost").textContent = `质量模式：更慢，消耗 ${cost} 次额度`;
      } else if (state.mode === "bailian_rag_strategy_fast") {
        $("#modeCost").textContent = `策略实验：消耗 ${cost} 次额度`;
      } else if (state.mode === "bailian_rag_strategy_quality") {
        $("#modeCost").textContent = `策略质量：更慢，消耗 ${cost} 次额度`;
      } else {
        $("#modeCost").textContent = `本次消耗 ${cost}`;
      }
    }
    function selectedFiles() {
      return Array.from($("#images").files || []);
    }
    function validateSelectedImages() {
      const files = selectedFiles();
      const maxImages = state.limits.max_images_per_reply || 3;
      const maxBytes = (state.limits.max_image_mb || 8) * 1024 * 1024;
      const allowed = new Set(["png", "jpg", "jpeg", "webp"]);
      if (files.length > maxImages) return `一次最多上传 ${maxImages} 张截图。`;
      for (const file of files) {
        const ext = (file.name.split(".").pop() || "").toLowerCase();
        if (!allowed.has(ext)) return `${file.name} 格式不支持，请上传 png、jpg、jpeg 或 webp。`;
        if (file.size > maxBytes) return `${file.name} 超过 ${state.limits.max_image_mb || 8}MB。`;
      }
      return "";
    }
    function renderUploadState() {
      const files = selectedFiles();
      const maxImages = state.limits.max_images_per_reply || 3;
      $("#uploadCount").textContent = `已选择 ${files.length} 张 / 最多 ${maxImages} 张`;
      $("#fileList").innerHTML = files.length
        ? files.map(file => `<span class="file-chip">${escapeHtml(file.name)} · ${formatBytes(file.size)}</span>`).join("")
        : '<span class="file-chip">还没选择图片</span>';
      const error = state.uploadError || validateSelectedImages();
      $("#uploadError").textContent = error;
      $("#uploadError").classList.toggle("hidden", !error);
    }
    function formatBytes(size) {
      if (!size) return "0KB";
      if (size < 1024 * 1024) return Math.max(1, Math.round(size / 1024)) + "KB";
      return (size / 1024 / 1024).toFixed(1) + "MB";
    }
    async function loadSession() {
      if (!state.token) return showApp(false);
      try {
        const me = await api("/api/v1/me");
        updateLimits(me.limits);
        const convs = await api("/api/v1/conversations");
        state.conversation = (convs.conversations || [])[0] || null;
        showApp(true);
      } catch (error) {
        localStorage.removeItem("baiou_web_token");
        state.token = "";
        showApp(false);
      }
    }
    async function login() {
      setStatus("#loginStatus", "校验中...");
      try {
        const data = await api("/api/v1/auth/web-login", {
          method: "POST",
          body: JSON.stringify({ access_code: $("#accessCode").value.trim() })
        });
        state.token = data.token;
        localStorage.setItem("baiou_web_token", state.token);
        updateLimits(data.limits);
        await loadSession();
        setStatus("#loginStatus", "");
      } catch (error) {
        setStatus("#loginStatus", error.message, true);
      }
    }
    function selectMode(mode) {
      state.mode = mode;
      document.querySelectorAll("button.mode").forEach(button => button.classList.toggle("active", button.dataset.mode === mode));
      updateModeCost();
    }
    async function ensureConversation() {
      if (state.conversation && state.conversation.conversation_id) return state.conversation;
      const convs = await api("/api/v1/conversations");
      state.conversation = (convs.conversations || [])[0] || null;
      return state.conversation;
    }
    async function generate() {
      const conversation = await ensureConversation();
      if (!conversation) throw new Error("会话初始化失败，请刷新重试。");
      state.uploadError = validateSelectedImages();
      renderUploadState();
      if (state.uploadError) throw new Error(state.uploadError);
      const files = selectedFiles();
      const maxImages = state.limits.max_images_per_reply || 3;
      if (!$("#question").value.trim()) throw new Error("请填写要回复的问题。");
      if (files.length < (state.limits.min_images_per_reply || 1)) throw new Error("请上传聊天截图。");
      if (files.length > maxImages) throw new Error(`一次最多上传 ${maxImages} 张截图。`);
      const form = new FormData();
      form.append("conversation_id", conversation.conversation_id);
      form.append("question", $("#question").value.trim());
      form.append("context", $("#context").value.trim());
      form.append("mode", state.mode);
      if ($("#dryRun").checked) form.append("dry_run", "true");
      files.forEach(file => form.append("images", file));
      $("#generateBtn").disabled = true;
      startWaitingTimer();
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 90000);
        const data = await fetch("/api/v1/replies", { method: "POST", headers: headers(false), body: form, signal: controller.signal }).finally(() => clearTimeout(timeout));
        const type = data.headers.get("content-type") || "";
        const payload = type.includes("application/json") ? await data.json() : { error: { message: await data.text() } };
        if (!data.ok || payload.ok === false) throw new Error((payload.error && payload.error.message) || "生成失败");
        state.lastRun = payload.reply_run;
        updateLimits(payload.limits);
        renderResult(payload.reply_run);
        $("#images").value = "";
        state.uploadError = "";
        renderUploadState();
        setStatus("#workStatus", "已生成");
      } catch (error) {
        setStatus("#workStatus", visibleRequestError(error), true);
      } finally {
        stopWaitingTimer();
        $("#generateBtn").disabled = false;
      }
    }
    function startWaitingTimer() {
      stopWaitingTimer();
      state.waitingStartedAt = Date.now();
      state.waitingPhase = "正在理解截图";
      updateWaitingStatus();
      state.waitingTimer = setInterval(() => {
        const seconds = Math.floor((Date.now() - state.waitingStartedAt) / 1000);
        state.waitingPhase = seconds >= 8 ? "正在生成回复" : "正在理解截图";
        updateWaitingStatus();
      }, 1000);
    }
    function updateWaitingStatus() {
      const seconds = Math.floor((Date.now() - state.waitingStartedAt) / 1000);
      setStatus("#workStatus", `${state.waitingPhase} · 已等待 ${seconds} 秒`);
    }
    function stopWaitingTimer() {
      if (state.waitingTimer) clearInterval(state.waitingTimer);
      state.waitingTimer = null;
    }
    function visibleRequestError(error) {
      if (error && error.name === "AbortError") return "请求超时，请稍后重试。";
      if (!navigator.onLine) return "网络已断开，请检查网络后重试。";
      return (error && error.message) || "请求失败，请稍后重试。";
    }
    function renderResult(run) {
      const answer = run.answer || {};
      $("#result").classList.remove("result-empty");
      $("#result").innerHTML = `
        <div class="answer">${escapeHtml(answer.reply || "暂无回复")}</div>
        <div class="assist">
          <div class="box"><h3>分析</h3><pre>${escapeHtml(answer.coach_analysis || "无")}</pre></div>
          <div class="box"><h3>下一步</h3><pre>${escapeHtml(answer.next_step || "无")}</pre></div>
          <div class="box"><h3>提醒</h3><pre>${escapeHtml(answer.risk_warning || "无")}</pre></div>
        </div>
        <div class="feedback">
          <div class="feedback-actions">
            <button class="ghost" type="button" data-rating="good">好</button>
            <button class="ghost" type="button" data-rating="ok">还行</button>
            <button class="ghost" type="button" data-rating="bad">不好</button>
          </div>
          <input id="feedbackNotes" type="text" placeholder="反馈备注，可选">
          <div id="feedbackStatus" class="status" aria-live="polite"></div>
        </div>`;
      document.querySelectorAll("[data-rating]").forEach(button => button.addEventListener("click", () => sendFeedback(button.dataset.rating)));
    }
    async function sendFeedback(rating) {
      if (!state.lastRun || !state.conversation) return;
      try {
        await api("/api/v1/feedback", {
          method: "POST",
          body: JSON.stringify({
            conversation_id: state.conversation.conversation_id,
            run_id: state.lastRun.run_id,
            rating,
            notes: ($("#feedbackNotes") && $("#feedbackNotes").value) || ""
          })
        });
        setStatus("#feedbackStatus", "已记录");
      } catch (error) {
        setStatus("#feedbackStatus", error.message, true);
      }
    }
    $("#loginBtn").addEventListener("click", login);
    $("#accessCode").addEventListener("keydown", event => { if (event.key === "Enter") login(); });
    $("#images").addEventListener("change", () => {
      state.uploadError = validateSelectedImages();
      renderUploadState();
      if (state.uploadError) setStatus("#workStatus", state.uploadError, true);
      else setStatus("#workStatus", selectedFiles().length ? "图片已选择，可以生成。" : "");
    });
    $("#generateBtn").addEventListener("click", () => generate().catch(error => setStatus("#workStatus", error.message, true)));
    document.querySelectorAll("button.mode").forEach(button => button.addEventListener("click", () => selectMode(button.dataset.mode)));
    selectMode(state.mode);
    updateLimits(boot.limits);
    loadSession();
  </script>
</body>
</html>
"""
