/**
 * AI Portfolio - Dynamic Project Cards
 *
 * Loads project cards from the backend read-only API and renders them
 * into the public frontend. ProjectCard in PostgreSQL is the single
 * Source of Truth for portfolio cards.
 */

(function() {
  'use strict';

  const CONFIG = {
    API_BASE: '', // same origin (nginx proxies /project-cards to backend)
    ENDPOINT: '/project-cards',
    TIMEOUT_MS: 10000,
  };

  /**
   * Render a single project card.
   */
  function renderCard(card) {
    const tagsHtml = (card.tags || [])
      .map(function(tag) { return '<span class="tag">' + escapeHtml(tag) + '</span>'; })
      .join('');

    return (
      '<article class="case-card">' +
        '<div class="case-card__icon">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
            '<path d="' + escapeHtml(card.icon_path || '') + '"/>' +
          '</svg>' +
        '</div>' +
        '<h3 class="case-card__title">' +
          '<a href="' + escapeHtml(card.external_url || '') + '">' + escapeHtml(card.title) + '</a>' +
        '</h3>' +
        '<p class="case-card__excerpt">' + escapeHtml(card.short_description) + '</p>' +
        '<div class="case-card__tags">' + tagsHtml + '</div>' +
        '<a href="' + escapeHtml(card.external_url || '') + '" class="case-card__link">Подробнее</a>' +
      '</article>'
    );
  }

  /**
   * Escape HTML special characters.
   */
  function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /**
   * Select and order cards for a container based on its mode.
   *
   * - Portfolio containers (no mode): all visible cards by display_order.
   * - Homepage containers (mode="homepage"): cards with show_on_homepage > 0
   *   ordered by show_on_homepage (1..4, left-to-right).
   */
  function selectCardsForContainer(cards, container) {
    const mode = container.getAttribute('data-project-cards');
    if (mode === 'homepage') {
      return cards
        .filter(function(card) { return (card.show_on_homepage || 0) > 0; })
        .sort(function(a, b) { return (a.show_on_homepage || 0) - (b.show_on_homepage || 0); });
    }
    return cards.slice().sort(function(a, b) {
      return (a.display_order || 0) - (b.display_order || 0);
    });
  }

  /**
   * Render cards into a container.
   */
  function renderContainer(container, cards) {
    if (!cards.length) {
      container.innerHTML = '<p class="case-card__excerpt">Карточки проектов временно недоступны.</p>';
      return;
    }
    container.innerHTML = cards.map(renderCard).join('');
  }

  /**
   * Fetch project cards from backend and render them.
   */
  async function loadProjectCards() {
    const containers = document.querySelectorAll('[data-project-cards]');
    if (!containers.length) return;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(function() { controller.abort(); }, CONFIG.TIMEOUT_MS);

      const response = await fetch(CONFIG.API_BASE + CONFIG.ENDPOINT, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error('Failed to load project cards: ' + response.status);
      }

      const data = await response.json();
      const cards = data.items || [];

      containers.forEach(function(container) {
        renderContainer(container, selectCardsForContainer(cards, container));
      });

      // Re-attach hover effects after dynamic render
      initCardHoverEffects();

    } catch (error) {
      console.error('Project cards load error:', error);
      containers.forEach(function(container) {
        container.innerHTML = '<p class="case-card__excerpt">Не удалось загрузить проекты. Попробуйте обновить страницу.</p>';
      });
    }
  }

  /**
   * Re-initialize card hover effects for dynamically rendered cards.
   */
  function initCardHoverEffects() {
    const cards = document.querySelectorAll('.case-card');
    cards.forEach(function(card) {
      card.addEventListener('mouseenter', function() {
        this.style.transform = 'translateY(-4px)';
      });
      card.addEventListener('mouseleave', function() {
        this.style.transform = 'translateY(0)';
      });
    });
  }

  function init() {
    loadProjectCards();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
