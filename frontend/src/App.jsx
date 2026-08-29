import { useEffect, useState } from 'react';
import { api, hasToken, setOnSessionExpired, setToken } from './api';
import AnalysisResult from './components/AnalysisResult';
import AuthForm from './components/AuthForm';
import History from './components/History';
import ListingForm from './components/ListingForm';

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState('submit');
  const [result, setResult] = useState(null);
  const [booting, setBooting] = useState(hasToken());
  const [accountForm, setAccountForm] = useState({ email: '', name: '' });
  const [accountError, setAccountError] = useState('');
  const [accountSuccess, setAccountSuccess] = useState('');
  const [accountLoading, setAccountLoading] = useState(false);
  const [sessionNotice, setSessionNotice] = useState('');

  useEffect(() => {
    if (!hasToken()) {
      setBooting(false);
      return;
    }

    api
      .me()
      .then(setUser)
      .catch(() => {
        setToken(null);
        setUser(null);
      })
      .finally(() => setBooting(false));
  }, []);

  // Fires for a 401 hit on any already-mounted authenticated screen, not
  // just the boot-time check above -- keeps `user` in sync with the token
  // api.js just cleared, so the UI falls back to the login screen
  // immediately instead of still looking signed in until a token-less
  // retry surfaces a confusing raw backend error (issue #82).
  useEffect(() => {
    setOnSessionExpired(() => {
      setUser(null);
      setResult(null);
      setView('submit');
      setSessionNotice('Your session has expired. Please sign in again.');
    });
    return () => setOnSessionExpired(null);
  }, []);

  function signOut() {
    setToken(null);
    setUser(null);
    setResult(null);
    setView('submit');
  }

  function openSubmit() {
    setResult(null);
    setView('submit');
  }

  function openHistory() {
    setResult(null);
    setView('history');
  }

  function openAccount() {
    setResult(null);
    setView('account');
    if (user) {
      setAccountForm({ email: user.email, name: user.name });
      setAccountError('');
      setAccountSuccess('');
    }
  }

  async function handleAccountSave(event) {
    event.preventDefault();
    setAccountError('');
    setAccountSuccess('');
    setAccountLoading(true);

    try {
      const updatedUser = await api.updateMe({
        email: accountForm.email,
        name: accountForm.name,
      });
      setUser(updatedUser);
      setAccountSuccess('Account details updated successfully.');
    } catch (err) {
      setAccountError(err instanceof Error ? err.message : 'Unable to update your account right now.');
    } finally {
      setAccountLoading(false);
    }
  }

  async function handleAccountDelete() {
    if (!window.confirm('Delete your account? This cannot be undone.')) {
      return;
    }

    try {
      await api.deleteMe();
      signOut();
    } catch (err) {
      setAccountError(err instanceof Error ? err.message : 'Unable to delete your account right now.');
    }
  }

  if (booting) {
    return (
      <div className="shell">
        <div className="hero-card card">
          <p className="eyebrow">Preparing your workspace</p>
          <h1>Loading your TrustAI dashboard…</h1>
          <p className="subtle">Please wait while we restore your session.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">Trust<span>AI</span> Marketplace</div>
        {user ? (
          <nav className="top-nav">
            <button type="button" className={`nav-pill ${view === 'submit' ? 'active' : ''}`} onClick={openSubmit}>
              New analysis
            </button>
            <button type="button" className={`nav-pill ${view === 'history' ? 'active' : ''}`} onClick={openHistory}>
              History
            </button>
            <button type="button" className={`nav-pill ${view === 'account' ? 'active' : ''}`} onClick={openAccount}>
              Account
            </button>
            <button type="button" className="ghost" onClick={signOut}>
              Sign out
            </button>
          </nav>
        ) : null}
      </header>

      {!user ? (
        <div className="landing-grid">
          <section className="hero-card card">
            <div className="logo-mark">T</div>
            <h1>TrustAI Marketplace</h1>
            <p className="subtle">Safer buying decisions for online marketplace users</p>

            <div className="promo-block">
              <p className="eyebrow">AI-assisted marketplace safety</p>
              <h2>Inspect a listing before you commit to the deal.</h2>
              <p className="subtle">
                TrustAI helps buyers spot pressure tactics, suspicious pricing, and scam-style signals before they hand over money.
              </p>
              <div className="hero-list">
                <div>
                  <strong>Fast review</strong>
                  <p>Paste a listing title, price, source, and notes in seconds.</p>
                </div>
                <div>
                  <strong>Structured risk output</strong>
                  <p>Get a clear buy, caution, or avoid recommendation with evidence.</p>
                </div>
                <div>
                  <strong>Private history</strong>
                  <p>Keep every analysis in one place so you can compare decisions over time.</p>
                </div>
              </div>
            </div>

            <div className="value-prop">
              <p className="eyebrow">Why use TrustAI</p>
              <ul className="check-list">
                <li>AI listing summary</li>
                <li>Risk indicators</li>
                <li>Seller questions</li>
                <li>Saved history</li>
              </ul>
            </div>
          </section>
          <AuthForm
            notice={sessionNotice}
            onSignedIn={(signedInUser) => {
              setSessionNotice('');
              setUser(signedInUser);
            }}
          />
        </div>
      ) : null}

      {user && result ? (
        <AnalysisResult
          analysis={result}
          onBack={() => setResult(null)}
          onViewHistory={() => {
            setResult(null);
            setView('history');
          }}
        />
      ) : null}

      {user && !result && view === 'submit' ? <ListingForm onResult={setResult} /> : null}

      {user && !result && view === 'history' ? (
        <History onOpen={(item) => setResult(item)} onNewListing={openSubmit} />
      ) : null}

      {user && !result && view === 'account' ? (
        <section className="card account-panel">
          <p className="eyebrow">Account</p>
          <h1>Account details</h1>
          <p className="subtle">Manage your TrustAI account and session.</p>

          {accountError ? <div className="error">{accountError}</div> : null}
          {accountSuccess ? <div className="success">{accountSuccess}</div> : null}

          <form onSubmit={handleAccountSave}>
            <div className="field">
              <label htmlFor="account-name">Name</label>
              <input
                id="account-name"
                name="name"
                value={accountForm.name}
                onChange={(event) => setAccountForm((current) => ({ ...current, name: event.target.value }))}
                required
              />
            </div>

            <div className="field">
              <label htmlFor="account-email">Email</label>
              <input
                id="account-email"
                name="email"
                type="email"
                value={accountForm.email}
                onChange={(event) => setAccountForm((current) => ({ ...current, email: event.target.value }))}
                required
              />
            </div>

            <div className="row two-col">
              <button type="submit" disabled={accountLoading}>
                {accountLoading ? 'Saving…' : 'Save changes'}
              </button>
              <button type="button" className="ghost" onClick={handleAccountDelete}>
                Delete account
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <p className="disclaimer">
        TrustAI provides heuristic risk analysis to support your own judgment. It does not detect every scam and makes no financial guarantees.
      </p>
    </div>
  );
}
