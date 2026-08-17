import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { api, setToken } from './api';

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
