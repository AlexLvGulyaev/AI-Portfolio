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
    // Staggered welcome (короткие сообщения вместо одного полотна)
    WELCOME_STEPS: [
      'Привет! Я AI-ассистент портфолио.',
      'Отвечаю о кейсах, услугах и компетенциях по документам GitHub-репозиториев — с указанием источников.',
      'Спросите про любой кейс — или опишите свою рутину, и я подскажу, есть ли похожий проект.',
    ],

    // Заготовленные вопросы (conversation starters). Ключ = тип страницы.
    STARTERS: {
      default: ['Что такое AI Portfolio?', 'Какие кейсы реализованы?', 'Как устроена база знаний?', 'Я иду смотреть демо — что проверить?'],
      case: ['Как устроен этот кейс?', 'Какие результаты и метрики?', 'Какие технологии использованы?', 'Я иду смотреть демо — что проверить?'],
      services: ['Что входит в услуги?', 'Как проходит работа над проектом?', 'Как связаться?'],
    },

    // Проактивный тизер/бейдж: задержка до появления, один раз за сессию
    TEASER_DELAY_MS: 30000,
    TEASER_SHOWN_KEY: 'ai_portfolio_teaser_shown',
    EXPANDED_KEY: 'ai_portfolio_widget_expanded',

    // Оценка ответов 👍/👎 → /track-event (event_type=chat_feedback)
    FEEDBACK: true,
    QUESTION_PREVIEW_MAX: 120,

    // Typing indicator dots
    TYPING_DOTS: 3,

    // Animation duration
    ANIMATION_MS: 200,

    // Show metadata (sources, provider, model, time)
    SHOW_METADATA: true,
  };

  // Заготовленные вопросы для текущего типа страницы
  function pageKind() {
    const path = window.location.pathname || '';
    if (/\/cases\/[a-z0-9-]+\.html$/.test(path)) return 'case';
    if (/\/services\.html$/.test(path)) return 'services';
    return 'default';
  }

  function teaserText() {
    const kind = pageKind();
    if (kind === 'case') return 'Спросите ассистента, как устроен этот кейс.';
    if (kind === 'services') return 'Спросите ассистента, что входит в услуги.';
    return 'Спросите ассистента о кейсах и услугах.';
  }

  // ============================================
  // State
  // ============================================

  let isOpen = false;
  let isSending = false;
  let lastUserText = '';
  let startersEl = null;

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

  // Стили виджета инъектируются одним <style> на страницу (CSS виджета
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
      /* Кнопка «Развернуть» в шапке виджета */
      .chat-expand {
        border: none;
        background: transparent;
        color: var(--text-secondary, inherit);
        font-size: 15px;
        line-height: 1;
        cursor: pointer;
        opacity: 0.8;
        transition: opacity 150ms ease;
        padding: var(--space-xs, 4px);
      }
      .chat-expand:hover { opacity: 1; }
      .chat-widget--expanded {
        width: 480px !important;
        height: 720px !important;
        max-height: calc(100vh - 60px) !important;
      }
      /* CTA «Обсудить проект» над полем ввода */
      .chat-discuss-bar {
        display: flex;
        justify-content: center;
        padding: 6px 14px;
        border-top: 1px solid var(--border, rgba(128, 128, 128, 0.25));
      }
      .chat-discuss {
        font-size: 0.78rem;
        color: var(--accent, inherit);
        text-decoration: none;
        transition: opacity 150ms ease;
      }
      .chat-discuss:hover { text-decoration: underline; }
      /* Полноэкранный режим на мобильных (стандарт Intercom/Crisp) */
      @media (max-width: 600px) {
        .chat-widget {
          right: 0 !important;
          bottom: 0 !important;
          width: 100vw !important;
          height: 100vh !important;
          max-height: none !important;
          max-width: none !important;
          border-radius: 0 !important;
        }
        .chat-expand { display: none; }
        .chat-teaser { right: 16px; }
      }
      /* Заготовленные вопросы (conversation starters) */
      .chat-starters {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 4px;
      }
      .chat-question-chip {
        display: inline-flex;
        align-items: center;
        font-size: 0.75rem;
        line-height: 1.4;
        color: var(--accent, inherit);
        background: transparent;
        border: 1px solid var(--accent, currentColor);
        border-radius: 999px;
        padding: 4px 10px;
        cursor: pointer;
        text-align: left;
        transition: color .15s ease, background .15s ease, border-color .15s ease;
      }
      .chat-question-chip:hover {
        background: var(--surface-elevated, rgba(128,128,128,.12));
      }
      /* Оценка ответа 👍/👎 (SVG, color наследуется темой) */
      .chat-feedback {
        display: flex;
        gap: 4px;
        margin-top: 2px;
      }
      .chat-feedback__btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        border: none;
        background: transparent;
        cursor: pointer;
        color: var(--text-muted, #888);
        line-height: 1;
        padding: 0;
        opacity: 0.75;
        transition: opacity .15s ease, color .15s ease, transform .15s ease;
      }
      .chat-feedback__btn svg { display: block; }
      .chat-feedback__btn:hover {
        opacity: 1;
        color: var(--text-primary, inherit);
        transform: scale(1.12);
      }
      .chat-feedback__btn[disabled] {
        cursor: default;
        opacity: 0.3;
        transform: none;
      }
      .chat-feedback__btn--active,
      .chat-feedback__btn.chat-feedback__btn--active {
        opacity: 1;
        color: var(--accent, currentColor);
      }
      /* Проактивный бейдж на launcher */
      .chat-launcher { position: fixed; }
      .chat-launcher--badge::after {
        content: '';
        position: absolute;
        top: 2px;
        right: 2px;
        width: 12px;
        height: 12px;
        background: #e5484d;
        border-radius: 999px;
        border: 2px solid var(--bg, #fff);
      }
      /* Проактивный тизер возле launcher */
      .chat-teaser {
        position: fixed;
        bottom: 100px;
        right: 24px;
        max-width: 260px;
        display: flex;
        gap: 8px;
        align-items: flex-start;
        background: var(--surface, #fff);
        color: var(--text-primary, inherit);
        border: 1px solid var(--border, rgba(128,128,128,.35));
        border-radius: 12px;
        box-shadow: var(--shadow-lg, 0 8px 24px rgba(0,0,0,.15));
        padding: 10px 12px;
        font-size: 0.8rem;
        line-height: 1.45;
        z-index: 1000;
        animation: chat-teaser-in .25s ease;
      }
      .chat-teaser__text { flex: 1; cursor: pointer; }
      .chat-teaser__close {
        border: none;
        background: none;
        color: var(--text-muted, #888);
        cursor: pointer;
        font-size: 14px;
        line-height: 1;
        padding: 0;
      }
      @keyframes chat-teaser-in {
        from { opacity: 0; transform: translateY(6px); }
        to { opacity: 1; transform: none; }
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

      // Оценка ответа 👍/👎 → chat_feedback в operational_logs
      if (CONFIG.FEEDBACK) {
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'chat-feedback';

        // SVG-иконки вместо эмодзи: эмодзи (жёлтый) теряются на серо-голубом
        // фоне и по-разному рендерятся на разных ОС; stroke=currentColor
        // наследует цвет темы, активный голос подсвечивается акцентом.
        const THUMB_UP_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>';
        const THUMB_DOWN_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zM17 2h2.67A2.31 2.31 0 0 1 22 4v7a2 2 0 0 1-2 2h-3"/></svg>';

        const upBtn = document.createElement('button');
        upBtn.type = 'button';
        upBtn.className = 'chat-feedback__btn';
        upBtn.title = 'Полезный ответ';
        upBtn.setAttribute('aria-label', 'Полезный ответ');
        upBtn.innerHTML = THUMB_UP_SVG;

        const downBtn = document.createElement('button');
        downBtn.type = 'button';
        downBtn.className = 'chat-feedback__btn';
        downBtn.title = 'Неполезный ответ';
        downBtn.setAttribute('aria-label', 'Неполезный ответ');
        downBtn.innerHTML = THUMB_DOWN_SVG;

        const markVoted = function(activeBtn) {
          upBtn.disabled = true;
          downBtn.disabled = true;
          activeBtn.classList.add('chat-feedback__btn--active');
        };

        upBtn.addEventListener('click', function() {
          if (upBtn.disabled) return;
          window.APIClient.trackEvent('chat_feedback', {
            rating: 'up',
            question_preview: (lastUserText || '').slice(0, CONFIG.QUESTION_PREVIEW_MAX),
          });
          markVoted(upBtn);
        });
        downBtn.addEventListener('click', function() {
          if (downBtn.disabled) return;
          window.APIClient.trackEvent('chat_feedback', {
            rating: 'down',
            question_preview: (lastUserText || '').slice(0, CONFIG.QUESTION_PREVIEW_MAX),
          });
          markVoted(downBtn);
        });

        feedbackDiv.appendChild(upBtn);
        feedbackDiv.appendChild(downBtn);
        metaDiv.appendChild(feedbackDiv);
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
   * Remove conversation starters (after the first user message)
   */
  function removeStarters() {
    if (startersEl && startersEl.parentNode) {
      startersEl.parentNode.removeChild(startersEl);
    }
    startersEl = null;
  }

  /**
   * Render page-aware question chips under the welcome message
   */
  function renderStarters() {
    const chips = CONFIG.STARTERS[pageKind()] || CONFIG.STARTERS.default;
    startersEl = document.createElement('div');
    startersEl.className = 'chat-starters';
    chips.forEach(function(q) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chat-question-chip';
      chip.textContent = q;
      chip.addEventListener('click', function() {
        sendMessage(q);
      });
      startersEl.appendChild(chip);
    });
    messagesEl.appendChild(startersEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  /**
   * Staggered welcome: короткие сообщения с задержками + вопрос-чипы
   */
  function showWelcome() {
    appendMessage(CONFIG.WELCOME_STEPS[0], 'bot');
    setTimeout(function() {
      appendTyping();
      setTimeout(function() {
        removeTyping();
        appendMessage(CONFIG.WELCOME_STEPS[1], 'bot');
        setTimeout(function() {
          appendTyping();
          setTimeout(function() {
            removeTyping();
            appendMessage(CONFIG.WELCOME_STEPS[2], 'bot');
            if (CONFIG.SHOW_METADATA) renderStarters();
          }, 900);
        }, 500);
      }, 900);
    }, 500);
  }

  /**
   * Send message to backend
   * @param {string} [textOverride] - текст из вопрос-чипа (иначе — из инпута)
   */
  async function sendMessage(textOverride) {
    if (isSending) return;

    const text = (typeof textOverride === 'string' && textOverride.trim())
      ? textOverride.trim()
      : inputEl.value.trim();
    if (!text) return;

    removeStarters();
    lastUserText = text;

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
      showWelcome();
    }

    dismissTeaser(true);

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

  /**
   * Кнопка «Развернуть» в шапке: десктоп 480×720, состояние запоминается.
   * На мобильных (≤600px) виджет и так полноэкранный — кнопка скрыта CSS.
   */
  function addExpandButton() {
    const expandBtn = document.createElement('button');
    expandBtn.type = 'button';
    expandBtn.id = 'chat-expand';
    expandBtn.className = 'chat-expand';
    expandBtn.title = 'Развернуть окно';
    expandBtn.setAttribute('aria-label', 'Развернуть окно');
    expandBtn.textContent = '⤢';

    expandBtn.addEventListener('click', function() {
      const expanded = widget.classList.toggle('chat-widget--expanded');
      expandBtn.title = expanded ? 'Свернуть окно' : 'Развернуть окно';
      expandBtn.setAttribute('aria-label', expandBtn.title);
      try {
        localStorage.setItem(CONFIG.EXPANDED_KEY, expanded ? '1' : '0');
      } catch (e) { /* localStorage недоступен */ }
    });

    try {
      if (localStorage.getItem(CONFIG.EXPANDED_KEY) === '1') {
        widget.classList.add('chat-widget--expanded');
        expandBtn.title = 'Свернуть окно';
        expandBtn.setAttribute('aria-label', expandBtn.title);
      }
    } catch (e) { /* localStorage недоступен */ }

    closeBtn.parentNode.insertBefore(expandBtn, closeBtn);
  }

  /**
   * Проактивный тизер: через 30 сек бездействия — бейдж на launcher и
   * подсказка с текстом под тип страницы. Один раз за сессию (sessionStorage).
   */
  function scheduleTeaser() {
    let shown = false;
    try {
      shown = sessionStorage.getItem(CONFIG.TEASER_SHOWN_KEY) === '1';
    } catch (e) { /* sessionStorage недоступен */ }
    if (shown) return;
    setTimeout(function() {
      if (!isOpen) showTeaser();
    }, CONFIG.TEASER_DELAY_MS);
  }

  function showTeaser() {
    ensureSourceChipStyles();
    if (document.getElementById('chat-teaser')) return;
    const teaser = document.createElement('div');
    teaser.className = 'chat-teaser';
    teaser.id = 'chat-teaser';

    const text = document.createElement('span');
    text.className = 'chat-teaser__text';
    text.textContent = teaserText();

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'chat-teaser__close';
    close.setAttribute('aria-label', 'Скрыть подсказку');
    close.textContent = '×';

    text.addEventListener('click', function() {
      dismissTeaser(true);
      openWidget();
    });
    close.addEventListener('click', function() {
      dismissTeaser(true);
    });

    teaser.appendChild(text);
    teaser.appendChild(close);
    document.body.appendChild(teaser);
    if (launcher) launcher.classList.add('chat-launcher--badge');
  }

  function dismissTeaser(permanent) {
    const teaser = document.getElementById('chat-teaser');
    if (teaser) teaser.remove();
    if (launcher) launcher.classList.remove('chat-launcher--badge');
    if (permanent) {
      try {
        sessionStorage.setItem(CONFIG.TEASER_SHOWN_KEY, '1');
      } catch (e) { /* sessionStorage недоступен */ }
    }
  }

  // ============================================
  /**
   * CTA «Обсудить проект»: строка над полем ввода. Инъекция из JS —
   * разметка виджета продублирована в HTML всех страниц витрины, одну
   * правку делаем здесь. target=_blank: диалог остаётся в текущей
   * вкладке, обращение открывается рядом. Клик трекается как inquiry
   * (channel: chat_widget) — см. initPresaleTracking в api-client.js.
   */
  function addDiscussBar() {
    if (widget.querySelector('.chat-discuss-bar')) return;
    // На «Контактах» CTA не нужен — зритель уже на странице обращения
    if (window.location.pathname === '/contacts.html') return;
    const bar = document.createElement('div');
    bar.className = 'chat-discuss-bar';
    const link = document.createElement('a');
    link.className = 'chat-discuss aip-discuss';
    link.href = '/contacts.html';
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = 'Обсудить проект →';
    bar.appendChild(link);
    const footer = widget.querySelector('.chat-footer');
    if (!footer) return;
    footer.parentNode.insertBefore(bar, footer);
  }

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

    // UX-расширения: «Развернуть», вопрос-чипы, проактивный тизер,
    // CTA «Обсудить проект»
    ensureSourceChipStyles();
    addExpandButton();
    addDiscussBar();
    scheduleTeaser();
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Публичный API: наводка в hero (index.html) открывает виджет программно
  window.AIPortfolioChat = { open: openWidget, close: closeWidget };

})();