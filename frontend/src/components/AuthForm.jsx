// E5 Frontend (owner: Adrian) — US-1.1/US-1.2 auth screens.
// Contract: api.register({email, name, password}), api.login({email, password})
// -> {access_token}; store via setToken(), then api.me() -> user object.
import { useState } from 'react';
import { api, setToken } from '../api';

export default function AuthForm({ onSignedIn }) {
  const [mode, setMode] = useState('login'); // login | register
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === 'register') {
        await api.register({ email, name, password });
      }
      const { access_token } = await api.login({ email, password });
      setToken(access_token);
      const user = await api.me();
      onSignedIn(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setError(null);
  }

  return (
    <div className="card" style={{ maxWidth: 440, margin: '0 auto' }}>
      <h1>{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
      <p className="subtle">
        {mode === 'login'
          ? "New here? "
          : 'Already have an account? '}
        <a className="link" onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}>
          {mode === 'login' ? 'Create an account' : 'Sign in instead'}
        </a>
      </p>

      {error && <div className="error">{error}</div>}

      <form onSubmit={handleSubmit}>
        {mode === 'register' && (
          <div className="field">
            <label htmlFor="name">Name</label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
        )}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </div>
        <button type="submit" disabled={busy}>
          {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
      </form>
    </div>
  );
}
