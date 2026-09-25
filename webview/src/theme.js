const STORAGE_KEY = 'echotales-theme';

export function getStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

// Browser chrome (mobile address bar, PWA title bar) should match the page
// background of each theme -- the CRA default #000000 matched neither.
const THEME_COLOR = { dark: '#101113', light: '#e9e7dd' };

export function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme] || THEME_COLOR.dark);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // private-mode/blocked storage: theme still applies for this load
  }
}

export function initTheme() {
  applyTheme(getStoredTheme() || 'dark');
}
