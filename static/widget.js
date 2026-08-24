/* ============================================================
   Brand Assistant — floating chat widget
   Drop this + widget.css on any site (see README / wordpress
   snippet). Configure via window.BRAND_ASSISTANT_CONFIG before
   this script loads:

   window.BRAND_ASSISTANT_CONFIG = {
     apiUrl: "http://localhost:5000",   // where app.py is running
     brandName: "Your Brand",
     greeting: "heyyy 👋 what can I help you find today?"
   };
   ============================================================ */

(function () {
  var CFG = window.BRAND_ASSISTANT_CONFIG || {};
  var API_URL = (CFG.apiUrl || "http://localhost:5000").replace(/\/$/, "");
  var BRAND_NAME = CFG.brandName || "Brand Assistant";
  var GREETING = CFG.greeting || "heyyy 👋 what can I help you find today?";
  var STORAGE_KEY = "ba_session_id";
  var THINKING_MESSAGES = ["thinking", "on it", "one sec", "lemme check"];

  function getSessionId() {
    try {
      var id = localStorage.getItem(STORAGE_KEY);
      if (!id) {
        id = "sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
        localStorage.setItem(STORAGE_KEY, id);
      }
      return id;
    } catch (e) {
      // localStorage unavailable (e.g. private mode) — fall back to a per-load id
      return "sess_" + Math.random().toString(36).slice(2);
    }
  }

  var sessionId = getSessionId();

  function el(tag, className, html) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  // ---------------- Build DOM ----------------
  var root = el("div", "ba-root");

  var launcher = el(
    "button",
    "ba-launcher",
    '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>' +
      "</svg>" +
      '<span class="ba-dot"></span>'
  );
  launcher.setAttribute("aria-label", "Open chat");

  var panel = el("div", "ba-panel");

  var header = el("div", "ba-header");
  header.appendChild(el("div", "ba-avatar"));
  var headerText = el("div", "ba-header-text");
  headerText.appendChild(el("div", "ba-title", BRAND_NAME));
  headerText.appendChild(el("div", "ba-subtitle", "online now"));
  header.appendChild(headerText);
  var closeBtn = el("button", "ba-close", "&times;");
  closeBtn.setAttribute("aria-label", "Close chat");
  header.appendChild(closeBtn);

  var messages = el("div", "ba-messages");

  var inputRow = el("div", "ba-input-row");
  var textarea = el("textarea", "ba-input");
  textarea.setAttribute("rows", "1");
  textarea.setAttribute("placeholder", "Type a message\u2026");
  var sendBtn = el(
    "button",
    "ba-send",
    '<svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"></path></svg>'
  );
  sendBtn.setAttribute("aria-label", "Send message");
  inputRow.appendChild(textarea);
  inputRow.appendChild(sendBtn);

  panel.appendChild(header);
  panel.appendChild(messages);
  panel.appendChild(inputRow);

  root.appendChild(panel);
  root.appendChild(launcher);
  document.body.appendChild(root);

  // ---------------- Behaviour ----------------
  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function addMessage(text, who) {
    var bubble = el("div", who === "user" ? "ba-msg ba-msg-user" : "ba-msg ba-msg-bot", "");
    bubble.textContent = text;
    messages.appendChild(bubble);
    scrollToBottom();
    return bubble;
  }

  var typingEl = null;
  var typingTimer = null;

  function showTyping() {
    typingEl = el(
      "div",
      "ba-typing",
      "<span></span><span></span><span></span>"
    );
    messages.appendChild(typingEl);
    scrollToBottom();

    var i = 0;
    var statusEl = el("div", "ba-status-text", THINKING_MESSAGES[0] + "\u2026");
    messages.appendChild(statusEl);
    scrollToBottom();
    typingTimer = setInterval(function () {
      i = (i + 1) % THINKING_MESSAGES.length;
      statusEl.textContent = THINKING_MESSAGES[i] + "\u2026";
    }, 1800);
    typingEl._statusEl = statusEl;
  }

  function hideTyping() {
    if (typingTimer) clearInterval(typingTimer);
    if (typingEl) {
      if (typingEl._statusEl) typingEl._statusEl.remove();
      typingEl.remove();
      typingEl = null;
    }
  }

  function setSending(isSending) {
    sendBtn.disabled = isSending;
    textarea.disabled = isSending;
  }

  function sendMessage() {
    var text = textarea.value.trim();
    if (!text) return;

    addMessage(text, "user");
    textarea.value = "";
    autoGrow();
    setSending(true);
    showTyping();

    fetch(API_URL + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed: " + res.status);
        return res.json();
      })
      .then(function (data) {
        hideTyping();
        addMessage(data.reply || "\u2026", "bot");
      })
      .catch(function () {
        hideTyping();
        addMessage("Ugh, couldn't reach the server \ud83d\ude35\u200d\ud83d\udcab. Check your connection and try again.", "bot");
      })
      .finally(function () {
        setSending(false);
        textarea.focus();
      });
  }

  function autoGrow() {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 90) + "px";
  }

  textarea.addEventListener("input", autoGrow);
  textarea.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  sendBtn.addEventListener("click", sendMessage);

  var hasOpenedBefore = false;
  function openPanel() {
    root.classList.add("ba-open");
    if (!hasOpenedBefore) {
      hasOpenedBefore = true;
      addMessage(GREETING, "bot");
    }
    setTimeout(function () {
      textarea.focus();
    }, 200);
  }
  function closePanel() {
    root.classList.remove("ba-open");
  }

  launcher.addEventListener("click", function () {
    if (root.classList.contains("ba-open")) {
      closePanel();
    } else {
      openPanel();
    }
  });
  closeBtn.addEventListener("click", closePanel);
})();
