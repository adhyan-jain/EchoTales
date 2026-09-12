const STORAGE_KEY = 'echotales-theme';

export function getStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // private-mode/blocked storage: theme still applies for this load
  }
}

export function initTheme() {
  applyTheme(getStoredTheme() || 'dark');
}
