import { useEffect, useMemo, useState } from 'react';
import { ApiError, api } from '../api';

const RECOMMENDATION_META = {
  buy: { label: 'Buy', level: 'low' },
  caution: { label: 'Caution', level: 'medium' },
  avoid: { label: 'Avoid', level: 'high' },
};

const DATE_RANGES = {
  all: { label: 'All time', days: null },
  '7d': { label: 'Last 7 days', days: 7 },
  '30d': { label: 'Last 30 days', days: 30 },
};

function formatDate(value) {
  return new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

export default function History({ onOpen, onNewListing }) {
  const [analyses, setAnalyses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [recommendationFilter, setRecommendationFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('all');
  const [selectedId, setSelectedId] = useState(null);

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

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    const range = DATE_RANGES[dateFilter];
    const cutoff = range.days ? Date.now() - range.days * 24 * 60 * 60 * 1000 : null;

    return analyses.filter((item) => {
      const matchesSearch = !query || item.listing_title.toLowerCase().includes(query);
      const matchesRecommendation =
        recommendationFilter === 'all' || item.recommendation === recommendationFilter;
      const matchesDate = !cutoff || new Date(item.created_at).getTime() >= cutoff;
      return matchesSearch && matchesRecommendation && matchesDate;
    });
  }, [analyses, search, recommendationFilter, dateFilter]);

  const selectedItem = filtered.find((item) => item.id === selectedId) || null;

  function handleOpenSelected() {
    if (selectedItem) onOpen(selectedItem);
  }

  return (
    <div className="card history-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Saved reviews</p>
          <h1>Saved Analysis History</h1>
        </div>
        <p className="subtle">Recent scans stay private to your account so you can compare them later.</p>
      </div>

      {loading ? <p className="subtle">Loading your review history…</p> : null}
      {error ? <div className="error">{error}</div> : null}

      {!loading && !error ? (
        <div className="history-filters">
          <input
            type="text"
            placeholder="Search listings…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select value={recommendationFilter} onChange={(event) => setRecommendationFilter(event.target.value)}>
            <option value="all">Recommendation</option>
            <option value="buy">Buy</option>
            <option value="caution">Caution</option>
            <option value="avoid">Avoid</option>
          </select>
          <select value={dateFilter} onChange={(event) => setDateFilter(event.target.value)}>
            {Object.entries(DATE_RANGES).map(([key, range]) => (
              <option key={key} value={key}>
                {range.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {!loading && !error && analyses.length === 0 ? (
        <div className="empty-state-box">
          <h2>No saved analyses yet</h2>
          <p className="subtle">
            Submit your first marketplace listing to receive an AI-assisted risk and price fairness review.
          </p>
          <button type="button" onClick={onNewListing}>
            Analyze a listing
          </button>
        </div>
      ) : null}

      {!loading && !error && analyses.length > 0 ? (
        <>
          <table className="history-table">
            <thead>
              <tr>
                <th>Listing title</th>
                <th>Source</th>
                <th>Price</th>
                <th>Risk</th>
                <th>Recommendation</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const meta = RECOMMENDATION_META[item.recommendation] || { label: 'Review', level: item.risk_level };
                return (
                  <tr
                    key={item.id}
                    className={item.id === selectedId ? 'selected' : ''}
                    onClick={() => setSelectedId(item.id)}
                    onDoubleClick={() => onOpen(item)}
                  >
                    <td>{item.listing_title}</td>
                    <td>{item.listing_source}</td>
                    <td>
                      {item.listing_price} {item.listing_currency}
                    </td>
                    <td>{item.risk_score ?? '—'}</td>
                    <td>
                      <span className={`recommendation-pill ${meta.level}`}>{meta.label}</span>
                    </td>
                    <td>{formatDate(item.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="history-actions">
            <button type="button" className="ghost" onClick={handleOpenSelected} disabled={!selectedItem}>
              Open selected result
            </button>
            <button type="button" onClick={onNewListing}>
              Analyze new listing
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
