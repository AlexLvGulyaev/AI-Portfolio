/**
 * AI Portfolio Chat Widget
 * Floating chat widget for AI assistant.
 *
 * Based on PEcf11 Frontend Widget with extensions:
 * - Sources display
 * - Provider/Model display
 * - Response time display
 * - Session management
 * - Error handling
 * - Timeouts
 * - Dark theme adaptation
 */

(function() {
  'use strict';

  // ============================================
  // Configuration
  // ============================================

  const CONFIG = {
    // Welcome message
    WELCOME_MESSAGE: 'Привет! Я AI-ассистент. Могу рассказать о кейсах, услугах и компетенциях. Задайте вопрос.',

    // Typing indicator dots
    TYPING_DOTS: 3,

    // Animation duration
    ANIMATION_MS: 200,

    // Show metadata (sources, provider, model, time)
    SHOW_METADATA: true,
  };

  // ============================================
  // State
  // ============================================

  let isOpen = false;
  let isSending = false;

  // ============================================
  // DOM Elements
  // ============================================

  let launcher = null;
  let widget = null;
  let messagesEl = null;
  let inputEl = null;
  let sendBtn = null;
  let closeBtn = null;

  // ============================================
  // Helper Functions
  // ============================================

  // Стили чипов источников инъектируются одним <style> на страницу (CSS виджета
  // дублируется в 17 HTML-страницах — инъекция из JS исключает правку всех страниц;
  // цвета берутся из CSS-переменных темы страницы, fallback — нейтральные).
  function ensureSourceChipStyles() {
    if (document.getElementById('chat-source-chip-style')) return;
    const style = document.createElement('style');
    style.id = 'chat-source-chip-style';
    style.textContent = `
      .chat-source-chip {
        display: inline-flex;
        align-items: center;
        font-size: 0.75rem;
        line-height: 1.4;
        color: var(--text-secondary, inherit);
        background: var(--surface-elevated, transparent);
        border: 1px solid var(--border, rgba(128,128,128,.35));
        border-radius: 999px;
        padding: 2px 10px;
        text-decoration: none;
        transition: color .15s ease, border-color .15s ease;
      }
      a.chat-source-chip:hover {
        color: var(--accent, inherit);
        border-color: var(--accent, currentColor);
      }
    `;
    document.head.appendChild(style);
  }

  /**
   * Append message to chat
   * @param {string} text - Message text
   * @param {string} from - 'user' or 'bot'
   * @param {Object} metadata - Optional metadata (sources, provider, model, time)
   */
  function appendMessage(text, from, metadata = null) {
    const div = document.createElement('div');
    div.className = 'chat-message ' + from;

    // Message text
    const textDiv = document.createElement('div');
    textDiv.className = 'chat-message__text';
    textDiv.textContent = text;
    div.appendChild(textDiv);

    // Metadata (sources, provider, time)
    if (metadata && CONFIG.SHOW_METADATA && from === 'bot') {
      const metaDiv = document.createElement('div');
      metaDiv.className = 'chat-message__meta';

      // Sources
      if (metadata.sources && metadata.sources.length > 0) {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'chat-message__sources';

        const sourcesLabel = document.createElement('span');
        sourcesLabel.className = 'chat-message__meta-label';
        sourcesLabel.textContent = 'Источники:';
        sourcesDiv.appendChild(sourcesLabel);

        // Кликабельные карточки источников (вариант C, 02.09.2026): читабельная
        // подпись + GitHub blob-ссылка из sources_detail. Без detail — plain text.
        const detail = metadata.sourcesDetail || [];
        const byLabel = new Map();
        detail.forEach((d) => {
          if (d && d.label && d.html_url && !byLabel.has(d.label)) {
            byLabel.set(d.label, d.html_url);
          }
        });

        if (byLabel.size > 0) {
          ensureSourceChipStyles();
          metadata.sources.forEach((label) => {
            const href = byLabel.get(label);
            const chip = document.createElement(href ? 'a' : 'span');
            chip.className = 'chat-source-chip';
            if (href) {
              chip.href = href;
              chip.target = '_blank';
              chip.rel = 'noopener noreferrer';
            }
            chip.textContent = label;
            sourcesDiv.appendChild(chip);
          });
        } else {
          const sourcesList = document.createElement('span');
          sourcesList.className = 'chat-message__meta-value';
          sourcesList.textContent = metadata.sources.join(', ');
          sourcesDiv.appendChild(sourcesList);
        }

        metaDiv.appendChild(sourcesDiv);
      }

      // Provider & Model
      if (metadata.provider && metadata.model) {
        const providerDiv = document.createElement('div');
        providerDiv.className = 'chat-message__provider';

        const providerLabel = document.createElement('span');
        providerLabel.className = 'chat-message__meta-label';
        providerLabel.textContent = 'Модель:';
        providerDiv.appendChild(providerLabel);

        const providerValue = document.createElement('span');
        providerValue.className = 'chat-message__meta-value';
        providerValue.textContent = `${metadata.provider} / ${metadata.model}`;
        providerDiv.appendChild(providerValue);

        metaDiv.appendChild(providerDiv);
      }

      // Response time
      if (metadata.responseTimeMs) {
        const timeDiv = document.createElement('div');
        timeDiv.className = 'chat-message__time';

        const timeLabel = document.createElement('span');
        timeLabel.className = 'chat-message__meta-label';
        timeLabel.textContent = 'Время:';
        timeDiv.appendChild(timeLabel);

        const timeValue = document.createElement('span');
        timeValue.className = 'chat-message__meta-value';
        timeValue.textContent = `${metadata.responseTimeMs}ms`;
        timeDiv.appendChild(timeValue);

        metaDiv.appendChild(timeDiv);
      }

      // Cache indicator
      if (metadata.fromCache) {
        const cacheDiv = document.createElement('div');
        cacheDiv.className = 'chat-message__cache';
        cacheDiv.textContent = 'Из кеша';
        metaDiv.appendChild(cacheDiv);
      }

      div.appendChild(metaDiv);
    }

    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  /**
   * Append typing indicator
   */
  function appendTyping() {
    const div = document.createElement('div');
    div.className = 'chat-message bot';
    div.id = 'typing-indicator';

    const dotsDiv = document.createElement('div');
    dotsDiv.className = 'typing-indicator';

    for (let i = 0; i < CONFIG.TYPING_DOTS; i++) {
      const dot = document.createElement('div');
      dot.className = 'dot';
      dotsDiv.appendChild(dot);
    }

    div.appendChild(dotsDiv);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  /**
   * Remove typing indicator
   */
  function removeTyping() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
  }

  /**
   * Append error message
   * @param {string} message - Error message
   */
  function appendError(message) {
    const div = document.createElement('div');
    div.className = 'chat-message bot chat-message--error';

    const textDiv = document.createElement('div');
    textDiv.className = 'chat-message__text';
    textDiv.textContent = message;
    div.appendChild(textDiv);

    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ============================================
  // Send Message
  // ============================================

  /**
   * Send message to backend
   */
  async function sendMessage() {
    if (isSending) return;

    const text = inputEl.value.trim();
    if (!text) return;

    // Append user message
    appendMessage(text, 'user');
    inputEl.value = '';

    // Disable input
    isSending = true;
    sendBtn.disabled = true;
    inputEl.disabled = true;

    // Show typing indicator
    appendTyping();

    try {
      // Use APIClient
      const response = await window.APIClient.chat(text);

      removeTyping();

      if (response.success) {
        // Append bot response with metadata
        appendMessage(response.answer, 'bot', {
          sources: response.sources,
          sourcesDetail: response.sourcesDetail,
          provider: response.provider,
          model: response.model,
          responseTimeMs: response.responseTimeMs,
          fromCache: response.fromCache,
        });
      } else {
        // Append error message
        appendError(response.message || 'Не удалось получить ответ. Попробуйте позже.');
      }

    } catch (error) {
      removeTyping();
      console.error('Chat error:', error);
      appendError('Произошла ошибка. Попробуйте позже.');
    } finally {
      // Re-enable input
      isSending = false;
      sendBtn.disabled = false;
      inputEl.disabled = false;
      inputEl.focus();
    }
  }

  // ============================================
  // Widget Toggle
  // ============================================

  /**
   * Open widget
   */
  function openWidget() {
    isOpen = true;
    widget.style.display = 'flex';
    launcher.style.display = 'none';

    // Show welcome message if empty
    if (!messagesEl.hasChildNodes()) {
      appendMessage(CONFIG.WELCOME_MESSAGE, 'bot');
    }

    setTimeout(() => inputEl.focus(), CONFIG.ANIMATION_MS);
  }

  /**
   * Close widget
   */
  function closeWidget() {
    isOpen = false;
    widget.style.display = 'none';
    launcher.style.display = 'flex';
  }

  // ============================================
  // Initialize
  // ============================================

  function init() {
    // Get DOM elements
    launcher = document.getElementById('chat-launcher');
    widget = document.getElementById('chat-widget');
    messagesEl = document.getElementById('chat-messages');
    inputEl = document.getElementById('chat-input');
    sendBtn = document.getElementById('chat-send');
    closeBtn = document.getElementById('chat-close');

    if (!launcher || !widget || !messagesEl || !inputEl || !sendBtn || !closeBtn) {
      console.warn('Chat Widget: Missing required elements');
      return;
    }

    // Event listeners
    launcher.addEventListener('click', openWidget);
    closeBtn.addEventListener('click', closeWidget);
    sendBtn.addEventListener('click', sendMessage);

    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Escape key to close
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isOpen) {
        closeWidget();
      }
    });
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();