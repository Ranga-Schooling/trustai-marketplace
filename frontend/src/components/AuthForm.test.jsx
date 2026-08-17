import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import AuthForm from './AuthForm';

describe('AuthForm', () => {
  beforeEach(() => {
    vi.spyOn(api, 'login').mockResolvedValue({ access_token: 'fake-token' });
    vi.spyOn(api, 'me').mockResolvedValue({ id: 1, email: 'buyer@example.com', name: 'Buyer' });
    vi.spyOn(api, 'register').mockResolvedValue({ id: 1, email: 'buyer@example.com', name: 'Buyer' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls api.login then api.me on sign-in, and reports the signed-in user', async () => {
    const events = userEvent.setup();
    const onSignedIn = vi.fn();

    const { container } = render(<AuthForm onSignedIn={onSignedIn} />);
    await events.type(screen.getByLabelText(/email/i), 'Buyer@Example.com');
    await events.type(screen.getByLabelText(/password/i), 'hunter22222');
    // Two "Sign in" buttons exist (the signin/register mode toggle pill,
    // and the form's own submit button) -- disambiguate via type="submit".
    await events.click(container.querySelector('form button[type="submit"]'));

    await waitFor(() => {
      expect(api.login).toHaveBeenCalledWith({ email: 'buyer@example.com', password: 'hunter22222' });
    });
    expect(api.register).not.toHaveBeenCalled();
    await waitFor(() => expect(onSignedIn).toHaveBeenCalledWith({ id: 1, email: 'buyer@example.com', name: 'Buyer' }));
  });

  it('calls api.register then api.login/api.me when registering a new account', async () => {
    const events = userEvent.setup();
    const onSignedIn = vi.fn();

    render(<AuthForm onSignedIn={onSignedIn} />);
    await events.click(screen.getByRole('button', { name: 'Register' }));
    await events.type(screen.getByLabelText(/your name/i), 'New Buyer');
    await events.type(screen.getByLabelText(/email/i), 'new@example.com');
    await events.type(screen.getByLabelText(/password/i), 'hunter22222');
    await events.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => {
      expect(api.register).toHaveBeenCalledWith({
        email: 'new@example.com',
        name: 'New Buyer',
        password: 'hunter22222',
      });
    });
    expect(api.login).toHaveBeenCalledWith({ email: 'new@example.com', password: 'hunter22222' });
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled());
  });
});
