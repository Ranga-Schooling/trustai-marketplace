import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { api, hasToken, setToken } from './api';

// Regression coverage for #68: App.jsx called api.updateMe()/api.deleteMe(),
// which didn't exist on the api client -- backend tests never caught it
// because they hit FastAPI directly, never through this component. Spying
// on the real `api` module (not a hand-authored mock) means these tests
// fail the same way #68 did if a method is renamed/removed without
// updating the caller, or vice versa.
describe('App account management', () => {
  const user = { id: 1, email: 'buyer@example.com', name: 'Buyer' };

  beforeEach(() => {
    setToken('fake-token');
    vi.spyOn(api, 'me').mockResolvedValue(user);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    setToken(null);
  });

  it('calls api.updateMe with the edited fields when saving account changes', async () => {
    const events = userEvent.setup();
    vi.spyOn(api, 'updateMe').mockResolvedValue({ ...user, name: 'New Name' });

    render(<App />);
    await events.click(await screen.findByRole('button', { name: 'Account' }));

    const nameInput = await screen.findByLabelText(/^name$/i);
    await events.clear(nameInput);
    await events.type(nameInput, 'New Name');
    await events.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(api.updateMe).toHaveBeenCalledWith({ email: user.email, name: 'New Name' });
    });
    expect(await screen.findByText('Account details updated successfully.')).toBeInTheDocument();
  });

  it('calls api.deleteMe when the user confirms account deletion', async () => {
    const events = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(api, 'deleteMe').mockResolvedValue(undefined);

    render(<App />);
    await events.click(await screen.findByRole('button', { name: 'Account' }));
    await events.click(screen.getByRole('button', { name: 'Delete account' }));

    await waitFor(() => {
      expect(api.deleteMe).toHaveBeenCalled();
    });
  });

  it('does not call api.deleteMe if the user cancels the confirmation', async () => {
    const events = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    vi.spyOn(api, 'deleteMe').mockResolvedValue(undefined);

    render(<App />);
    await events.click(await screen.findByRole('button', { name: 'Account' }));
    await events.click(screen.getByRole('button', { name: 'Delete account' }));

    expect(api.deleteMe).not.toHaveBeenCalled();
  });
});

// Regression coverage for #82: a 401 hit on an already-mounted authenticated
// screen (not the boot-time check) used to clear the token but leave
// `user` state untouched, so the UI kept rendering the authenticated shell.
// A retry from there went out with no token at all, and the friendly
// "session expired" message PR #81 introduced never got a chance to show.
// This goes through the real api.js request() (via a stubbed fetch, not a
// mocked api.listAnalyses), so it fails the same way #82 did if the
// api.js <-> App.jsx wiring regresses.
describe('App session expiry mid-session', () => {
  const user = { id: 1, email: 'buyer@example.com', name: 'Buyer' };

  beforeEach(() => {
    setToken('fake-token');
    vi.spyOn(api, 'me').mockResolvedValue(user);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    setToken(null);
  });

  it('falls back to the login screen and shows a notice, without a token-less retry', async () => {
    const events = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 401,
        ok: false,
        json: async () => ({ detail: 'Could not validate credentials' }),
      }),
    );

    render(<App />);
    await events.click(await screen.findByRole('button', { name: 'History' }));

    expect(
      await screen.findByText('Your session has expired. Please sign in again.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'History' })).not.toBeInTheDocument();
    expect(hasToken()).toBe(false);
    // D-20/#80: History now fires listAnalyses and listFailedListings
    // concurrently on mount, so the stubbed 401 fetch is hit twice here --
    // still zero token-less retries, which is the actual invariant this
    // test protects (see the fetch mock above: it's never asked to return
    // anything other than a 401).
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
