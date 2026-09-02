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
  const [failedListings, setFailedListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // D-20, issue #80: per-listing state so one retry's spinner/error doesn't
  // block or clobber another's while both sit in the failed list.
  const [retryingIds, setRetryingIds] = useState(() => new Set());
  const [retryErrors, setRetryErrors] = useState({});

  useEffect(() => {
    loadHistory();
  }, []);

  async function loadHistory() {
    setLoading(true);
    try {
      const [analysesResult, failedResult] = await Promise.all([
        api.listAnalyses(),
        api.listFailedListings(),
      ]);
      setAnalyses(analysesResult);
      setFailedListings(failedResult);
      setError('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load your history.');
    } finally {
      setLoading(false);
    }
  }

  async function handleRetry(listingId) {
    setRetryErrors((current) => {
      const next = { ...current };
      delete next[listingId];
      return next;
    });
    setRetryingIds((current) => new Set(current).add(listingId));
    try {
      const analysis = await api.retryAnalysis(listingId);
      onOpen(analysis);
    } catch (err) {
      setRetryErrors((current) => ({
        ...current,
        [listingId]: err instanceof ApiError
          ? err.message
          : 'Unable to retry that listing right now.',
      }));
    } finally {
      setRetryingIds((current) => {
        const next = new Set(current);
        next.delete(listingId);
        return next;
      });
    }
  }

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

      {!loading && !error && failedListings.length > 0 ? (
        <div className="failed-listings">
          <p className="eyebrow">Failed listings</p>
          <p className="subtle">
            The AI check didn't complete for these — your listing details were still saved. Retry without re-entering anything.
          </p>
          <div className="history-list">
            {failedListings.map((item) => (
              <div key={item.id} className="history-card failed-listing-card">
                <div>
                  <div className="history-topline">
                    <strong>{item.title}</strong>
                    <span className="badge medium">needs retry</span>
                  </div>
                  <p className="subtle">
                    {item.price} {item.currency} • {formatDate(item.created_at)}
                  </p>
                  {retryErrors[item.id] ? <div className="error">{retryErrors[item.id]}</div> : null}
                </div>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => handleRetry(item.id)}
                  disabled={retryingIds.has(item.id)}
                >
                  {retryingIds.has(item.id) ? 'Retrying…' : 'Retry analysis'}
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {!loading && !error && analyses.length === 0 && failedListings.length === 0 ? (
        <div className="empty-state">
          <h2>No analyses yet</h2>
          <p className="subtle">Start by submitting your first listing and building a history of your reviews.</p>
          <button type="button" onClick={onNewListing}>Submit a listing</button>
        </div>
      ) : null}

      {analyses.length > 0 ? (
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
      ) : null}
    </div>
  );
}
