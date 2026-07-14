import { useEffect, useState } from 'react';
import { api, hasToken, setToken } from './api';
import AnalysisResult from './components/AnalysisResult';
import AuthForm from './components/AuthForm';
import History from './components/History';
import ListingForm from './components/ListingForm';

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState('submit'); // submit | history
  const [result, setResult] = useState(null);
  const [booting, setBooting] = useState(hasToken());

  useEffect(() => {
    if (!hasToken()) return;
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setBooting(false));
  }, []);

  function signOut() {
    setToken(null);
    setUser(null);
    setResult(null);
    setView('submit');
  }

  if (booting) return <div className="shell"><p className="subtle">Loading…</p></div>;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">Trust<span>AI</span> Marketplace</div>
        {user && (
          <nav>
            <a className="link" onClick={() => { setResult(null); setView('submit'); }}>
              New analysis
            </a>
            <a className="link" onClick={() => { setResult(null); setView('history'); }}>
              History
            </a>
            <button className="ghost" onClick={signOut}>Sign out</button>
          </nav>
        )}
      </header>

      {!user && <AuthForm onSignedIn={setUser} />}

      {user && result && (
        <AnalysisResult
          analysis={result}
          onBack={() => setResult(null)}
        />
      )}

      {user && !result && view === 'submit' && (
        <ListingForm onResult={setResult} />
      )}

      {user && !result && view === 'history' && (
        <History onOpen={setResult} />
      )}

      <p className="disclaimer">
        TrustAI provides heuristic risk analysis to support your own judgement.
        It does not detect every scam and makes no financial guarantees.
      </p>
    </div>
  );
}
