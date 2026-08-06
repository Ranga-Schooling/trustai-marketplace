import { useState } from 'react';
import { ApiError, api, setToken } from '../api';

export default function AuthForm({ onSignedIn }) {
  const [mode, setMode] = useState('signin');
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (mode === 'signup') {
        await api.register({
          email: form.email.trim().toLowerCase(),
          name: form.name.trim(),
          password: form.password,
        });
      }

      const tokenResponse = await api.login({
        email: form.email.trim().toLowerCase(),
        password: form.password,
      });

      setToken(tokenResponse.access_token);
      const user = await api.me();
      onSignedIn(user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to complete that action.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="content-grid">
      <section className="card hero-card compact">
        <p className="eyebrow">Why use TrustAI</p>
        <h1>Safer buying decisions for online marketplace users</h1>
        <ul className="check-list">
          <li>AI listing summary</li>
          <li>Risk indicators</li>
          <li>Seller questions</li>
          <li>Saved history</li>
        </ul>
      </section>

      <div className="card auth-card">
        <p className="eyebrow">Login form</p>
        <div className="auth-toggle" role="tablist" aria-label="Authentication mode">
          <button type="button" className={mode === 'signin' ? 'pill active' : 'pill'} onClick={() => setMode('signin')}>
            Sign in
          </button>
          <button type="button" className={mode === 'signup' ? 'pill active' : 'pill'} onClick={() => setMode('signup')}>
            Register
          </button>
        </div>

        <h2>{mode === 'signin' ? 'Welcome back' : 'Create your account'}</h2>
        <p className="subtle">
          {mode === 'signin'
            ? 'Use your credentials to re-open your private analysis history.'
            : 'Join TrustAI to review marketplace listings with structured guidance.'}
        </p>

        <form onSubmit={handleSubmit}>
          {error ? <div className="error">{error}</div> : null}

          {mode === 'signup' ? (
            <div className="field">
              <label htmlFor="name">Your name</label>
              <input id="name" name="name" value={form.name} onChange={updateField} required />
            </div>
          ) : null}

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              name="email"
              type="email"
              placeholder="name@example.com"
              value={form.email}
              onChange={updateField}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" value={form.password} onChange={updateField} minLength="8" required />
          </div>

          <button type="submit" disabled={loading}>
            {loading ? 'Working…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </button>

          <p className="subtle" style={{ marginTop: 12 }}>
            {mode === 'signin' ? (
              <>New user? <a className="link" onClick={() => setMode('signup')}>Create account</a></>
            ) : (
              <>Already have an account? <a className="link" onClick={() => setMode('signin')}>Sign in</a></>
            )}
          </p>
        </form>

        <p className="security-copy">TrustAI stores analysis history for signed-in users.</p>
      </div>
    </div>
  );
}
