/**
 * AI Portfolio - Main JavaScript
 * Фирменный дизайн AI Automation Portfolio Lab
 */

(function() {
  'use strict';

  // ============================================
  // Tabs
  // ============================================
  function initTabs() {
    const tabContainers = document.querySelectorAll('.tabs');

    tabContainers.forEach(function(container) {
      const tabs = container.querySelectorAll('.tabs__tab');
      const panels = container.querySelectorAll('.tabs__panel');

      tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
          const targetTab = this.getAttribute('data-tab');

          // Remove active class from all tabs and panels
          tabs.forEach(function(t) {
            t.classList.remove('tabs__tab--active');
          });
          panels.forEach(function(p) {
            p.classList.remove('tabs__panel--active');
          });

          // Add active class to clicked tab and corresponding panel
          this.classList.add('tabs__tab--active');
          const targetPanel = container.querySelector('[data-panel="' + targetTab + '"]');
          if (targetPanel) {
            targetPanel.classList.add('tabs__panel--active');
          }
        });
      });
    });
  }

  // ============================================
  // Mobile Menu
  // ============================================
  function initMobileMenu() {
    const menuToggle = document.querySelector('.menu-toggle');
    const nav = document.querySelector('.nav');

    if (menuToggle && nav) {
      menuToggle.addEventListener('click', function() {
        nav.classList.toggle('nav--open');
        const isOpen = nav.classList.contains('nav--open');
        menuToggle.setAttribute('aria-expanded', isOpen);
      });

      // Close menu on link click
      const navLinks = nav.querySelectorAll('.nav__link');
      navLinks.forEach(function(link) {
        link.addEventListener('click', function() {
          nav.classList.remove('nav--open');
          menuToggle.setAttribute('aria-expanded', 'false');
        });
      });
    }
  }

  // ============================================
  // Smooth Scroll
  // ============================================
  function initSmoothScroll() {
    const links = document.querySelectorAll('a[href^="#"]');

    links.forEach(function(link) {
      link.addEventListener('click', function(e) {
        const href = this.getAttribute('href');
        if (href.length > 1) {
          const target = document.querySelector(href);
          if (target) {
            e.preventDefault();
            target.scrollIntoView({
              behavior: 'smooth',
              block: 'start'
            });
          }
        }
      });
    });
  }

  // ============================================
  // Active Nav Link
  // ============================================
  function setActiveNavLink() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav__link');

    navLinks.forEach(function(link) {
      const href = link.getAttribute('href');
      if (href) {
        const linkPath = href.replace(/^\.\//, '');
        if (currentPath.includes(linkPath) ||
            (currentPath.endsWith('/') && linkPath === 'index.html') ||
            (currentPath.includes('cases/') && linkPath === 'portfolio.html')) {
          link.classList.add('nav__link--active');
        }
      }
    });
  }

  // ============================================
  // Card Hover Effects
  // ============================================
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

  // ============================================
  // Button Hover Effects
  // ============================================
  function initButtonEffects() {
    const primaryButtons = document.querySelectorAll('.btn--primary');

    primaryButtons.forEach(function(btn) {
      btn.addEventListener('mouseenter', function() {
        this.style.transform = 'translateY(-2px)';
      });

      btn.addEventListener('mouseleave', function() {
        this.style.transform = 'translateY(0)';
      });
    });
  }

  // ============================================
  // Neural Network Animation (for hero)
  // ============================================
  function initNeuralAnimation() {
    const neuralSvg = document.querySelector('.neural-network');
    if (!neuralSvg) return;

    // Animation is handled by CSS, this is just a placeholder for future enhancements
    // Could add interactive hover effects here
  }

  // ============================================
  // Visit tracking
  // ============================================
  function trackVisit() {
    if (window.APIClient && typeof window.APIClient.trackVisit === 'function') {
      window.APIClient.trackVisit().catch(function() {
        // Silently ignore tracking errors to not break UX
      });
    }
  }

  // ============================================
  // Initialize
  // ============================================
  function init() {
    initTabs();
    initMobileMenu();
    initSmoothScroll();
    setActiveNavLink();
    initCardHoverEffects();
    initButtonEffects();
    initNeuralAnimation();
    trackVisit();
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();