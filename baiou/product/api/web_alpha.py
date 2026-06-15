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
            "web_site_daily_quota": config.get("web_site_daily_quota", 300),
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
  <title>Baiou Alpha</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --paper: #fffdf8;
      --ink: #172033;
      --muted: #687083;
      --line: #d9d2c3;
      --accent: #166b5d;
      --accent-2: #b35235;
      --soft: #eaf4f0;
      --warn: #8a4a18;
      --bad: #b42318;
      --shadow: 0 18px 42px rgba(42, 36, 27, .10);
      --radius: 8px;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(90deg, rgba(22, 107, 93, .055) 1px, transparent 1px),
        linear-gradient(180deg, rgba(22, 107, 93, .04) 1px, transparent 1px),
        var(--bg);
      background-size: 34px 34px;
      color: var(--ink);
    }
    button, input, textarea { font: inherit; }
    button {
      min-height: 44px;
      border: 0;
      border-radius: var(--radius);
      padding: 0 16px;
      background: var(--accent);
      color: #fff;
      font-weight: 800;
      cursor: pointer;
    }
    button:disabled { opacity: .55; cursor: not-allowed; }
    button.secondary { background: #eef1ed; color: var(--ink); border: 1px solid var(--line); }
    button.ghost { background: transparent; color: var(--accent); border: 1px solid #b7d7ce; }
    button.mode { background: #fff; color: var(--muted); border: 1px solid var(--line); }
    button.mode.active { background: var(--ink); color: #fff; border-color: var(--ink); }
    .shell { width: min(1180px, 100%); margin: 0 auto; padding: 18px; }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    .brand-line { color: var(--muted); font-size: 13px; margin-top: 3px; }
    .quota { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    .pill {
      border: 1px solid var(--line);
      background: rgba(255, 253, 248, .86);
      border-radius: 999px;
      padding: 7px 10px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .layout { display: grid; grid-template-columns: minmax(320px, 430px) minmax(0, 1fr); gap: 14px; align-items: start; }
    .panel {
      background: rgba(255, 253, 248, .96);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }
    .panel-head { padding: 16px 16px 0; }
    h2 { margin: 0; font-size: 17px; letter-spacing: 0; }
    .panel-body { padding: 16px; }
    .field { display: grid; gap: 7px; margin-bottom: 14px; }
    label, .label { font-size: 13px; font-weight: 800; color: #2d3748; }
    textarea, input[type="text"], input[type="password"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 11px 12px;
      background: #fff;
      color: var(--ink);
      outline: none;
    }
    textarea { resize: vertical; min-height: 92px; line-height: 1.55; }
    textarea:focus, input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(22, 107, 93, .12); }
    .upload {
      display: grid;
      gap: 8px;
      border: 1px dashed #b8ad98;
      border-radius: var(--radius);
      padding: 14px;
      background: #fbfaf5;
    }
    .privacy { color: var(--muted); font-size: 12px; line-height: 1.5; }
    .mode-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
    .dry { display: inline-flex; align-items: center; gap: 7px; color: var(--muted); font-size: 13px; }
    .status { min-height: 22px; color: var(--muted); font-size: 13px; }
    .status.bad { color: var(--bad); }
    .gate {
      max-width: 460px;
      margin: 12vh auto 0;
    }
    .gate h1 { font-size: 30px; }
    .result-empty {
      min-height: 320px;
      display: grid;
      place-items: center;
      color: var(--muted);
      text-align: center;
      padding: 24px;
    }
    .answer {
      border: 1px solid #b7d7ce;
      background: var(--soft);
      border-radius: var(--radius);
      padding: 16px;
      white-space: pre-wrap;
      line-height: 1.7;
      font-size: 16px;
    }
    .result-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }
    .box {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      padding: 12px;
      min-height: 86px;
    }
    .box h3 { margin: 0 0 8px; font-size: 13px; }
    .box pre, details pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: var(--muted);
      font-family: inherit;
      font-size: 13px;
      line-height: 1.55;
    }
    details {
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      padding: 12px;
    }
    summary { cursor: pointer; font-weight: 800; font-size: 13px; }
    .refs { display: grid; gap: 8px; margin-top: 10px; }
    .ref { border-top: 1px solid #edf0e9; padding-top: 8px; }
    .feedback { display: grid; gap: 8px; margin-top: 12px; }
    .feedback-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .hidden { display: none !important; }
    @media (max-width: 880px) {
      .shell { padding: 12px; }
      .topbar { display: block; }
      .quota { justify-content: flex-start; margin-top: 10px; }
      .layout, .result-grid { grid-template-columns: 1fr; }
      .mode-row { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 430px) {
      h1 { font-size: 21px; }
      .mode-row { grid-template-columns: 1fr; }
      .actions { display: grid; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section id="gate" class="gate panel">
      <div class="panel-body">
        <h1>Baiou Alpha</h1>
        <p class="brand-line">内测工作台</p>
        <div class="field" style="margin-top:18px">
          <label for="accessCode">内测访问码</label>
          <input id="accessCode" type="password" autocomplete="one-time-code">
        </div>
        <div class="actions">
          <button id="loginBtn" type="button">进入</button>
          <span id="loginStatus" class="status"></span>
        </div>
      </div>
    </section>

    <section id="app" class="hidden">
      <div class="topbar">
        <div>
          <h1>Baiou Alpha</h1>
          <p class="brand-line">回复工作台</p>
        </div>
        <div class="quota">
          <span class="pill" id="userQuota">今日剩余 --</span>
          <span class="pill" id="ipQuota">IP 剩余 --</span>
        </div>
      </div>
      <div class="layout">
        <section class="panel">
          <div class="panel-head"><h2>输入</h2></div>
          <div class="panel-body">
            <div class="field">
              <label for="images">聊天截图</label>
              <div class="upload">
                <input id="images" type="file" accept="image/png,image/jpeg,image/webp" multiple>
                <div class="privacy" id="uploadHint">截图会临时保存用于本次分析和质量排查，并按保留周期清理；请不要上传身份证、银行卡、住址等敏感信息。</div>
              </div>
            </div>
            <div class="field">
              <label for="question">我该怎么回</label>
              <textarea id="question">我该怎么回</textarea>
            </div>
            <div class="field">
              <label for="context">补充背景</label>
              <textarea id="context" placeholder="可选：认识多久、关系阶段、你希望回复更轻松还是更认真"></textarea>
            </div>
            <div class="field">
              <div class="label">模式</div>
              <div class="mode-row">
                <button class="mode active" type="button" data-mode="bailian_rag_fast">快速模式</button>
                <button class="mode" type="button" data-mode="bailian_rag_quality">质量模式</button>
              </div>
            </div>
            <div class="actions">
              <label class="dry"><input id="dryRun" type="checkbox"> dry-run</label>
              <button id="generateBtn" type="button">生成推荐回复</button>
            </div>
            <div id="workStatus" class="status"></div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2>结果</h2></div>
          <div id="result" class="panel-body result-empty">生成后，推荐回复和分析会显示在这里。</div>
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
      limits: boot.limits || {}
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
      $("#ipQuota").textContent = "IP 剩余 " + (state.limits.web_ip_daily_remaining ?? "--");
      const max = state.limits.max_images_per_reply || 3;
      const mb = state.limits.max_image_mb || 8;
      $("#uploadHint").textContent = `最多 ${max} 张，单张 ${mb}MB。截图会临时保存用于本次分析和质量排查，并按保留周期清理；请不要上传身份证、银行卡、住址等敏感信息。`;
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
      const files = Array.from($("#images").files || []);
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
      setStatus("#workStatus", "生成中...");
      try {
        const data = await fetch("/api/v1/replies", { method: "POST", headers: headers(false), body: form });
        const payload = await data.json();
        if (!data.ok || payload.ok === false) throw new Error((payload.error && payload.error.message) || "生成失败");
        state.lastRun = payload.reply_run;
        updateLimits(payload.limits);
        renderResult(payload.reply_run);
        $("#images").value = "";
        setStatus("#workStatus", "已生成");
      } finally {
        $("#generateBtn").disabled = false;
      }
    }
    function renderResult(run) {
      const answer = run.answer || {};
      const refs = run.reference_segments || [];
      $("#result").classList.remove("result-empty");
      $("#result").innerHTML = `
        <div class="answer">${escapeHtml(answer.reply || "暂无回复")}</div>
        <div class="result-grid">
          <div class="box"><h3>教练分析</h3><pre>${escapeHtml(answer.coach_analysis || "无")}</pre></div>
          <div class="box"><h3>下一步</h3><pre>${escapeHtml(answer.next_step || "无")}</pre></div>
          <div class="box"><h3>风险提醒</h3><pre>${escapeHtml(answer.risk_warning || "无")}</pre></div>
          <div class="box"><h3>状态</h3><pre>${escapeHtml(run.display_mode || run.mode)} · ${escapeHtml(run.status)}</pre></div>
        </div>
        <details>
          <summary>截图理解</summary>
          <pre style="margin-top:8px">${escapeHtml(run.image_understanding || "暂无截图理解")}</pre>
        </details>
        <details>
          <summary>参考片段</summary>
          <div class="refs">${refs.length ? refs.map(renderRef).join("") : "<pre style=\\"margin-top:8px\\">暂无参考片段</pre>"}</div>
        </details>
        <div class="feedback">
          <div class="feedback-actions">
            <button class="ghost" type="button" data-rating="good">好</button>
            <button class="ghost" type="button" data-rating="ok">还行</button>
            <button class="ghost" type="button" data-rating="bad">不好</button>
          </div>
          <input id="feedbackNotes" type="text" placeholder="反馈备注，可选">
          <div id="feedbackStatus" class="status"></div>
        </div>`;
      document.querySelectorAll("[data-rating]").forEach(button => button.addEventListener("click", () => sendFeedback(button.dataset.rating)));
    }
    function renderRef(ref) {
      return `<div class="ref"><pre>${escapeHtml(ref.segment_id || ref.filename || "参考片段")}
${escapeHtml(ref.text || "")}</pre></div>`;
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
    $("#generateBtn").addEventListener("click", () => generate().catch(error => setStatus("#workStatus", error.message, true)));
    document.querySelectorAll("button.mode").forEach(button => button.addEventListener("click", () => selectMode(button.dataset.mode)));
    selectMode(state.mode);
    updateLimits(boot.limits);
    loadSession();
  </script>
</body>
</html>
"""
