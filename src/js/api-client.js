/**
 * AI Portfolio API Client
 * Production configuration.
 */

(function() {
  'use strict';

  // ============================================
  // Configuration
  // ============================================

  const CONFIG = {
    // Backend URL - uses same origin as frontend
    API_BASE: '', // Empty string means same origin (relative URLs)

    // Request timeout in milliseconds
    TIMEOUT_MS: 30000,

    // Session storage key
    SESSION_KEY: 'ai_portfolio_session',

    // User ID storage key
    USER_KEY: 'ai_portfolio_user',

    // Visitor ID storage key for anonymous visit tracking
    VISITOR_KEY: 'ai_portfolio_visitor',
  };

  // ============================================
  // API Client
  // ============================================

  const APIClient = {
    /**
     * Get or create session ID
     * @returns {string|null} Session ID
     */
    getSessionId() {
      try {
        return sessionStorage.getItem(CONFIG.SESSION_KEY);
      } catch (e) {
        console.warn('SessionStorage not available:', e);
        return null;
      }
    },

    /**
     * Set session ID
     * @param {string} sessionId - Session ID
     */
    setSessionId(sessionId) {
      try {
        sessionStorage.setItem(CONFIG.SESSION_KEY, sessionId);
      } catch (e) {
        console.warn('SessionStorage not available:', e);
      }
    },

    /**
     * Get or create user ID
     * @returns {string|null} User ID
     */
    getUserId() {
      try {
        let userId = localStorage.getItem(CONFIG.USER_KEY);
        if (!userId) {
          // Generate new user ID (simple UUID v4)
          userId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
          });
          localStorage.setItem(CONFIG.USER_KEY, userId);
        }
        return userId;
      } catch (e) {
        console.warn('LocalStorage not available:', e);
        return null;
      }
    },

    /**
     * Send chat message
     * @param {string} message - User message
     * @param {Object} options - Additional options
     * @returns {Promise<Object>} Response object
     */
    async chat(message, options = {}) {
      const sessionId = this.getSessionId();

      const requestBody = {
        message: message,
      };

      // Контекст кейс-страницы: вопрос «этот кейс» привязывается к проекту
      // (slug валидируется бэкендом по реестру)
      const slugMatch = (window.location.pathname || '').match(/\/cases\/([a-z0-9-]+)\.html$/);
      if (slugMatch) {
        requestBody.page_slug = slugMatch[1];
      }

      // Include session_id if we have one
      if (sessionId) {
        try {
          // Validate UUID format
          const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
          if (uuidRegex.test(sessionId)) {
            requestBody.session_id = sessionId;
          }
        } catch (e) {
          console.warn('Invalid session ID format:', sessionId);
        }
      }

      // Include visitor_id for cross-session observability
      const visitorId = this.getVisitorId();
      if (visitorId) {
        requestBody.visitor_id = visitorId;
      }

      // Create AbortController for timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

      try {
        const response = await fetch(`${CONFIG.API_BASE}/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestBody),
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `Server error: ${response.status}`);
        }

        const data = await response.json();

        // Save session_id for future requests
        if (data.session_id) {
          this.setSessionId(data.session_id);
        }

        return {
          success: true,
          answer: data.answer || '',
          sessionId: data.session_id,
          sources: data.sources || [],
          sourcesDetail: data.sources_detail || [],
          provider: data.provider || 'unknown',
          model: data.model || 'unknown',
          fromCache: data.from_cache || false,
          ragUsed: data.rag_used || false,
          responseTimeMs: data.response_time_ms || 0,
          userId: data.user_id,
        };

      } catch (error) {
        clearTimeout(timeoutId);

        // Handle timeout
        if (error.name === 'AbortError') {
          return {
            success: false,
            error: 'timeout',
            message: 'Превышено время ожидания. Попробуйте позже.',
          };
        }

        // Handle network errors
        if (error.message === 'Failed to fetch' || error.message.includes('NetworkError')) {
          return {
            success: false,
            error: 'network',
            message: 'Не удалось подключиться к серверу. Проверьте подключение.',
          };
        }

        // Handle other errors
        // Clear stale session_id so the next request creates a fresh session
        this.clearSession();

        return {
          success: false,
          error: 'server',
          message: error.message || 'Произошла ошибка. Попробуйте позже.',
        };
      }
    },

    /**
     * Get or create anonymous visitor ID for visit tracking
     * @returns {string|null} Visitor ID
     */
    getVisitorId() {
      try {
        let visitorId = localStorage.getItem(CONFIG.VISITOR_KEY);
        if (!visitorId) {
          visitorId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
          });
          localStorage.setItem(CONFIG.VISITOR_KEY, visitorId);
        }
        return visitorId;
      } catch (e) {
        console.warn('LocalStorage not available:', e);
        return null;
      }
    },

    /**
     * Track anonymous page visit
     * @returns {Promise<Object>} Tracking result
     */
    async trackVisit() {
      try {
        const visitorId = this.getVisitorId();
        if (!visitorId) {
          return { success: false };
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

        const response = await fetch(`${CONFIG.API_BASE}/track-visit`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            visitor_id: visitorId,
            path: window.location.pathname,
            referrer: document.referrer || null,
            user_agent: navigator.userAgent,
          }),
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          return { success: false };
        }

        const data = await response.json();
        if (data.visitor_id && data.visitor_id !== visitorId) {
          localStorage.setItem(CONFIG.VISITOR_KEY, data.visitor_id);
        }

        return { success: true, visitorId: data.visitor_id || visitorId };
      } catch (error) {
        return { success: false };
      }
    },

    /**
     * Health check
     * @returns {Promise<Object>} Health status
     */
    async health() {
      try {
        const response = await fetch(`${CONFIG.API_BASE}/health`, {
          method: 'GET',
        });

        if (!response.ok) {
          throw new Error(`Health check failed: ${response.status}`);
        }

        const data = await response.json();
        return {
          success: true,
          status: data.status,
          provider: data.provider,
          providerStatus: data.provider_status,
        };

      } catch (error) {
        return {
          success: false,
          error: error.message,
        };
      }
    },

    /**
     * Track one presale funnel event (case_view / inquiry, §4.5).
     *
     * Fire-and-forget: sendBeacon when available (event survives
     * navigation to an external case/telegram), fetch keepalive fallback.
     * @param {string} eventType 'case_view' | 'inquiry'
     * @param {Object} metadata Event context { card_slug, card_title,
     *   external_url, channel, label } — server keeps only whitelist
     * @returns {boolean} true when the event was queued
     */
    trackEvent(eventType, metadata) {
      const payload = {
        event_type: eventType,
        visitor_id: this.getVisitorId(),
        path: window.location.pathname,
        metadata: metadata || {},
      };

      try {
        if (typeof navigator.sendBeacon === 'function') {
          const blob = new Blob([JSON.stringify(payload)], {
            type: 'application/json',
          });
          if (navigator.sendBeacon(`${CONFIG.API_BASE}/track-event`, blob)) {
            return true;
          }
        }
        // Fallback: keepalive request survives page navigation
        fetch(`${CONFIG.API_BASE}/track-event`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          keepalive: true,
        }).catch(function() {
          // Silently ignore tracking errors to not break UX
        });
        return true;
      } catch (e) {
        return false;
      }
    },

    /**
     * Clear session
     */
    clearSession() {
      try {
        sessionStorage.removeItem(CONFIG.SESSION_KEY);
      } catch (e) {
        console.warn('SessionStorage not available:', e);
      }
    },
  };

  // ============================================
  // Export
  // ============================================

  // Make APIClient available globally
  window.APIClient = APIClient;

  // ============================================
  // Presale funnel auto-instrumentation (§4.5)
  // ============================================
  // Один делегированный capture-обработчик на всех страницах витрины
  // (api-client.js загружен везде, включая главную с инлайн-рендерером
  // карточек). sendBeacon внутри trackEvent переживает уход со страницы.
  function initPresaleTracking() {
    if (window.__presaleTrackingBound) return;
    window.__presaleTrackingBound = true;
    document.addEventListener('click', function(event) {
      const link = event.target.closest('a[href]');
      if (!link) return;
      const href = link.getAttribute('href');
      if (!href || href === '#') return;

      // 1) Касание кейса: ссылки внутри карточки проекта (главная:
      //    project-card / featured-card — «Узнать больше», external_url)
      if (link.closest('.project-card, .featured-card')) {
        const article = link.closest('article');
        const heading = article ? article.querySelector('h2, h3') : null;
        const slugMatch = href.match(/\/cases\/([a-z0-9-]+)\.html/);
        APIClient.trackEvent('case_view', {
          card_slug: slugMatch ? slugMatch[1] : null,
          card_title: heading ? heading.textContent.trim() : null,
          external_url: href,
        });
        return;
      }

      // 2) Обращение: контактные ссылки Telegram / email
      if (href.indexOf('https://t.me') === 0 || href.indexOf('mailto:') === 0) {
        APIClient.trackEvent('inquiry', {
          channel: href.indexOf('mailto:') === 0 ? 'email' : 'telegram',
          label: (link.textContent || '').trim(),
        });
      }
    }, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPresaleTracking);
  } else {
    initPresaleTracking();
  }

})();