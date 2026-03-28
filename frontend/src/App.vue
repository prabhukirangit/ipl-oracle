<template>
  <div id="app-root">
    <!-- Non-dismissible disclaimer bar — mandatory on every page -->
    <DisclaimerBar />

    <!-- Main navigation -->
    <header class="site-header">
      <div class="header-inner">
        <div class="brand">
          <span class="brand-icon">🏏</span>
          <span class="brand-name">IPL Oracle</span>
          <span class="brand-tag">Swarm Intelligence Engine</span>
        </div>
        <nav class="nav-links">
          <router-link to="/">Today's Matches</router-link>
        </nav>
      </div>
    </header>

    <!-- Page content -->
    <main class="main-content">
      <router-view />
    </main>

    <!-- Footer -->
    <footer class="site-footer">
      <p>
        IPL Oracle v0.4.0 — Persona · Hybrid · Probabilistic Engine ·
        <a href="https://github.com/666ghj/MiroFish" target="_blank" rel="noopener">
          MiroFish-inspired
        </a>
      </p>
      <p class="footer-disclaimer">
        For research and entertainment only. Not betting advice. Not financial advice.
      </p>
    </footer>
  </div>
</template>

<script setup>
import DisclaimerBar from './components/DisclaimerBar.vue'
</script>

<style>
/* -------------------------------------------------- */
/* Reset & Base                                        */
/* -------------------------------------------------- */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --color-bg: #0f1117;
  --color-surface: #1a1d2e;
  --color-surface-2: #242840;
  --color-border: #2e3250;
  --color-text: #e8eaf6;
  --color-text-muted: #9399b2;
  --color-primary: #6c63ff;
  --color-primary-dark: #5a52d5;
  --color-accent: #ff6584;
  --color-success: #4caf50;
  --color-warning: #ff9800;
  --color-danger: #f44336;
  --color-ipl-blue: #004e98;
  --color-ipl-gold: #f5a623;
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --border-radius: 8px;
  --border-radius-lg: 12px;
  --shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  --transition: all 0.2s ease;
}

body {
  font-family: var(--font-family);
  background: var(--color-bg);
  color: var(--color-text);
  line-height: 1.6;
  min-height: 100vh;
}

a {
  color: var(--color-primary);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

#app-root {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* -------------------------------------------------- */
/* Header                                              */
/* -------------------------------------------------- */
.site-header {
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: 0 1rem;
  position: sticky;
  top: 36px; /* below disclaimer bar */
  z-index: 100;
}

.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.brand-icon {
  font-size: 1.5rem;
}

.brand-name {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--color-text);
}

.brand-tag {
  font-size: 0.7rem;
  color: var(--color-text-muted);
  background: var(--color-surface-2);
  padding: 2px 8px;
  border-radius: 20px;
  border: 1px solid var(--color-border);
}

.nav-links {
  display: flex;
  gap: 1.5rem;
}

.nav-links a {
  color: var(--color-text-muted);
  font-size: 0.9rem;
  font-weight: 500;
  transition: var(--transition);
}

.nav-links a:hover,
.nav-links a.router-link-active {
  color: var(--color-text);
  text-decoration: none;
}

/* -------------------------------------------------- */
/* Main Content                                        */
/* -------------------------------------------------- */
.main-content {
  flex: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem 1rem;
  width: 100%;
}

/* -------------------------------------------------- */
/* Footer                                              */
/* -------------------------------------------------- */
.site-footer {
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  padding: 1.5rem 2rem;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 0.8rem;
}

.site-footer p + p {
  margin-top: 0.25rem;
}

.footer-disclaimer {
  color: var(--color-warning);
}

/* -------------------------------------------------- */
/* Utility classes                                     */
/* -------------------------------------------------- */
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-lg);
  padding: 1.5rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.6rem 1.25rem;
  border-radius: var(--border-radius);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
  border: none;
  font-family: var(--font-family);
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover {
  background: var(--color-primary-dark);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--color-surface-2);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}

.btn-secondary:hover {
  background: var(--color-border);
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge-live {
  background: rgba(244, 67, 54, 0.2);
  color: var(--color-danger);
  border: 1px solid var(--color-danger);
  animation: pulse 2s infinite;
}

.badge-future {
  background: rgba(108, 99, 255, 0.2);
  color: var(--color-primary);
  border: 1px solid var(--color-primary);
}

.badge-imminent {
  background: rgba(255, 152, 0, 0.2);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.loading-spinner {
  display: inline-block;
  width: 20px;
  height: 20px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
