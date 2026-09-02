import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { api, setToken } from './api';
import VisualInspection from './components/VisualInspection';
import { THEME_STORAGE_KEY, useTheme } from './theme';

function createMemoryStorage() {
  const values = new Map();
  return {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    key(index) {
      return [...values.keys()][index] ?? null;
    },
    removeItem(key) {
      values.delete(key);
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

function installMatchMedia(initiallyDark) {
  let matches = initiallyDark;
  const listeners = new Set();
  const mediaQuery = {
    media: '(prefers-color-scheme: dark)',
    get matches() {
      return matches;
    },
    addEventListener: vi.fn((eventName, listener) => {
      if (eventName === 'change') listeners.add(listener);
    }),
    removeEventListener: vi.fn((eventName, listener) => {
      if (eventName === 'change') listeners.delete(listener);
    }),
  };

  vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery));

  return {
    mediaQuery,
    setDark(nextValue) {
      matches = nextValue;
      act(() => {
        listeners.forEach((listener) => listener({ matches: nextValue }));
      });
    },
  };
}

function ThemedVisualInspectionHarness() {
  const { theme, toggleTheme } = useTheme();
  return (
    <>
      <button type="button" onClick={toggleTheme}>
        Switch to {theme === 'dark' ? 'light' : 'dark'} mode
      </button>
      <VisualInspection analysisId={42} />
    </>
  );
}

describe('theme preference', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: createMemoryStorage(),
    });
    setToken(null);
    window.localStorage.clear();
    window.sessionStorage.clear();
    delete document.documentElement.dataset.theme;
    document.documentElement.style.colorScheme = '';
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    setToken(null);
    window.localStorage.clear();
    window.sessionStorage.clear();
    delete document.documentElement.dataset.theme;
    document.documentElement.style.colorScheme = '';
  });

  it.each([
    ['dark', false],
    ['light', true],
  ])('uses the stored %s preference instead of the system theme', (storedTheme, systemDark) => {
    window.localStorage.setItem(THEME_STORAGE_KEY, storedTheme);
    installMatchMedia(systemDark);

    render(<App />);

    expect(document.documentElement.dataset.theme).toBe(storedTheme);
    expect(document.documentElement.style.colorScheme).toBe(storedTheme);
  });

  it.each([
    [true, 'dark'],
    [false, 'light'],
  ])('uses the %s system preference when no preference is stored', (systemDark, expectedTheme) => {
    installMatchMedia(systemDark);

    render(<App />);

    expect(document.documentElement.dataset.theme).toBe(expectedTheme);
  });

  it('removes an invalid stored value and falls back to the system preference', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'sepia');
    installMatchMedia(true);

    render(<App />);

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('continues with the system preference when localStorage is unavailable', async () => {
    installMatchMedia(true);
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage unavailable');
    });
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage unavailable');
    });
    const events = userEvent.setup();

    render(<App />);
    const toggle = screen.getByRole('button', { name: 'Switch to light mode' });

    expect(document.documentElement.dataset.theme).toBe('dark');
    await events.click(toggle);
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it.each([
    [false, 'Dark mode', 'Switch to dark mode', 'moon'],
    [true, 'Light mode', 'Switch to light mode', 'sun'],
  ])(
    'shows the %s system theme with the matching action and icon',
    (systemDark, actionLabel, accessibleName, icon) => {
      installMatchMedia(systemDark);
      render(<App />);

      const toggle = screen.getByRole('button', { name: accessibleName });
      const indicator = toggle.querySelector(`[data-theme-icon="${icon}"]`);

      expect(toggle).toHaveTextContent(actionLabel);
      expect(toggle).not.toHaveAttribute('aria-pressed');
      expect(indicator).toBeInTheDocument();
      expect(indicator).toHaveAttribute('aria-hidden', 'true');
    },
  );

  it('toggles data-theme, color-scheme, persistence, and its accessible action', async () => {
    installMatchMedia(false);
    const events = userEvent.setup();
    render(<App />);
    const toggle = screen.getByRole('button', { name: 'Switch to dark mode' });

    expect(toggle).toHaveAttribute('type', 'button');
    expect(toggle).toHaveTextContent('Dark mode');

    await events.click(toggle);

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.style.colorScheme).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    const lightModeToggle = screen.getByRole('button', { name: 'Switch to light mode' });
    expect(lightModeToggle).toHaveTextContent('Light mode');
    expect(lightModeToggle.querySelector('[data-theme-icon="sun"]')).toBeInTheDocument();
  });

  it('supports keyboard focus and activation', async () => {
    installMatchMedia(false);
    const events = userEvent.setup();
    render(<App />);

    await events.tab();
    const toggle = screen.getByRole('button', { name: 'Switch to dark mode' });
    expect(toggle).toHaveFocus();

    await events.keyboard('{Enter}');

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toHaveTextContent('Light mode');
  });

  it('follows system changes while no explicit preference exists', () => {
    const system = installMatchMedia(false);
    render(<App />);

    system.setDark(true);
    expect(document.documentElement.dataset.theme).toBe('dark');

    system.setDark(false);
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('ignores system changes after an explicit preference is selected', async () => {
    const system = installMatchMedia(false);
    const events = userEvent.setup();
    render(<App />);

    await events.click(screen.getByRole('button', { name: 'Switch to dark mode' }));
    expect(document.documentElement.dataset.theme).toBe('dark');

    system.setDark(false);
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('removes the system preference listener when the application unmounts', () => {
    const { mediaQuery } = installMatchMedia(false);
    const { unmount } = render(<App />);

    expect(mediaQuery.addEventListener).toHaveBeenCalledWith('change', expect.any(Function));
    const listener = mediaQuery.addEventListener.mock.calls[0][1];

    unmount();

    expect(mediaQuery.removeEventListener).toHaveBeenCalledWith('change', listener);
  });

  it('preserves transient visual findings while the theme changes', async () => {
    installMatchMedia(false);
    vi.spyOn(api, 'visualInspect').mockResolvedValue({
      findings: [
        {
          category: 'visible_damage',
          observation: 'Photo 1 visibly shows a scratch.',
          photo_numbers: [1],
        },
      ],
    });
    const events = userEvent.setup();
    render(<ThemedVisualInspectionHarness />);

    await events.upload(
      screen.getByLabelText('Choose photos'),
      new File(['jpeg'], 'synthetic-photo.jpg', { type: 'image/jpeg' }),
    );
    await events.click(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    );
    await events.click(screen.getByRole('button', { name: 'Inspect photos' }));
    expect(await screen.findByText('Photo 1 visibly shows a scratch.')).toBeVisible();

    await events.click(screen.getByRole('button', { name: 'Switch to dark mode' }));

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(screen.getByText('Photo 1 visibly shows a scratch.')).toBeVisible();
    expect(screen.getByText(/Visual findings do not change the existing Trust score/i)).toBeVisible();
  });

  it('keeps the theme preference through sign-in and sign-out', async () => {
    installMatchMedia(false);
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    vi.spyOn(api, 'login').mockResolvedValue({ access_token: 'fake-token' });
    vi.spyOn(api, 'me').mockResolvedValue({ id: 1, email: 'buyer@example.com', name: 'Buyer' });
    const events = userEvent.setup();
    const { container } = render(<App />);

    await events.type(screen.getByLabelText(/email/i), 'buyer@example.com');
    await events.type(screen.getByLabelText(/password/i), 'hunter22222');
    await events.click(container.querySelector('form button[type="submit"]'));
    await screen.findByRole('button', { name: 'Sign out' });

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');

    await events.click(screen.getByRole('button', { name: 'Sign out' }));

    await waitFor(() => expect(screen.getByText('Welcome back')).toBeInTheDocument());
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});
