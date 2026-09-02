import { useEffect, useLayoutEffect, useState } from 'react';

export const THEME_STORAGE_KEY = 'trustai_theme';

const DARK_THEME_QUERY = '(prefers-color-scheme: dark)';
const VALID_THEMES = new Set(['light', 'dark']);

function getMediaQuery() {
  try {
    return typeof window.matchMedia === 'function'
      ? window.matchMedia(DARK_THEME_QUERY)
      : null;
  } catch {
    return null;
  }
}

export function readStoredTheme() {
  try {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (VALID_THEMES.has(storedTheme)) {
      return storedTheme;
    }
    if (storedTheme !== null) {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    }
  } catch {
    // Storage can be unavailable in privacy modes; system preference remains usable.
  }
  return null;
}

export function getSystemTheme() {
  return getMediaQuery()?.matches ? 'dark' : 'light';
}

export function applyTheme(theme) {
  const resolvedTheme = VALID_THEMES.has(theme) ? theme : 'light';
  document.documentElement.dataset.theme = resolvedTheme;
  document.documentElement.style.colorScheme = resolvedTheme;
}

function persistTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // The in-memory preference still works for this session when storage fails.
  }
}

export function useTheme() {
  const [preference, setPreference] = useState(readStoredTheme);
  const [systemTheme, setSystemTheme] = useState(getSystemTheme);
  const theme = preference ?? systemTheme;

  useLayoutEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (preference !== null) {
      return undefined;
    }

    const mediaQuery = getMediaQuery();
    if (!mediaQuery) {
      return undefined;
    }

    function handleSystemThemeChange(event) {
      setSystemTheme(event.matches ? 'dark' : 'light');
    }

    mediaQuery.addEventListener('change', handleSystemThemeChange);
    return () => mediaQuery.removeEventListener('change', handleSystemThemeChange);
  }, [preference]);

  function toggleTheme() {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setPreference(nextTheme);
    persistTheme(nextTheme);
  }

  return { theme, toggleTheme };
}
