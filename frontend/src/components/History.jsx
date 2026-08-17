import { useEffect, useState } from 'react';
import { ApiError, api } from '../api';

function formatDate(value) {
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function History({ onOpen, onNewListing }) {
  const [analyses, setAnalyses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function loadAnalyses() {
      try {
        const items = await api.listAnalyses();
        setAnalyses(items);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Unable to load your history.');
      } finally {
        setLoading(false);
      }
    }

    loadAnalyses();
  }, []);

  return (
    <div className="card history-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Saved reviews</p>
          <h1>Your analyses</h1>
        </div>
        <p className="subtle">Recent scans stay private to your account so you can compare them later.</p>
      </div>

      {loading ? <p className="subtle">Loading your review history…</p> : null}
      {error ? <div className="error">{error}</div> : null}

      {!loading && !error && analyses.length === 0 ? (
        <div className="empty-state">
          <h2>No analyses yet</h2>
          <p className="subtle">Start by submitting your first listing and building a history of your reviews.</p>
          <button type="button" onClick={onNewListing}>Submit a listing</button>
        </div>
      ) : null}

      <div className="history-list">
        {analyses.map((item) => (
          <button key={item.id} type="button" className="history-card" onClick={() => onOpen(item)}>
            <div>
              <div className="history-topline">
                <strong>{item.listing_title}</strong>
                {typeof item.risk_score === 'number' ? (
                  <span className="risk-score">{item.risk_score} / 100</span>
                ) : null}
                <span className={`badge ${item.risk_level}`}>{item.risk_level}</span>
              </div>
              <p className="subtle">
                {item.listing_price} {item.listing_currency} • {formatDate(item.created_at)}
              </p>
            </div>
            <span className="link">Open</span>
          </button>
        ))}
      </div>
    </div>
  );
}
