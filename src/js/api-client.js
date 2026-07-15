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

})();