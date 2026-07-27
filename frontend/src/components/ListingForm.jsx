// E5 Frontend — US-2.1 listing submission + US-2.3 URL fetch preview.
// Contract: api.createAnalysis({title, price:Number, currency, source,
// description, url|null}) -> AnalysisOut. 422 -> show field errors;
// 502 -> tell the user the listing was saved and to retry.
// api.previewListingUrl(url) -> {title, description, source} suggestions
// (US-2.3); the user still reviews/edits before submitting — this never
// bypasses the ListingIn/POST /analyses contract.
import { useState } from 'react';
import { api } from '../api';

const CURRENCIES = ['ZAR', 'USD', 'EUR', 'GBP'];

export default function ListingForm({ onResult }) {
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [price, setPrice] = useState('');
  const [currency, setCurrency] = useState('ZAR');
  const [source, setSource] = useState('');
  const [description, setDescription] = useState('');

  const [fetchingUrl, setFetchingUrl] = useState(false);
  const [fetchError, setFetchError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  async function handleFetchUrl() {
    if (!url.trim()) return;
    setFetchError(null);
    setFetchingUrl(true);
    try {
      const preview = await api.previewListingUrl(url.trim());
      if (preview.title) setTitle(preview.title);
      if (preview.description) setDescription(preview.description);
      if (preview.source) setSource(preview.source);
    } catch (err) {
      setFetchError(err.message);
    } finally {
      setFetchingUrl(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      const analysis = await api.createAnalysis({
        title,
        price: Number(price),
        currency,
        source,
        description,
        url: url.trim() || null,
      });
      onResult(analysis);
    } catch (err) {
      setSubmitError(
        err.status === 502
          ? `${err.message} You can retry the analysis without resubmitting.`
          : err.message
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card">
      <h1>Analyze a listing</h1>
      <p className="subtle">
        Paste a listing URL to fetch suggested details, or fill in the fields
        yourself.
      </p>

      {fetchError && <div className="error">{fetchError}</div>}
      {submitError && <div className="error">{submitError}</div>}

      <div className="field">
        <label htmlFor="url">Listing URL (optional)</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            id="url"
            type="url"
            placeholder="https://example.com/item/123"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button
            type="button"
            className="ghost"
            onClick={handleFetchUrl}
            disabled={fetchingUrl || !url.trim()}
          >
            {fetchingUrl ? 'Fetching…' : 'Fetch details'}
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="title">Title</label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </div>

        <div className="row">
          <div className="field">
            <label htmlFor="price">Price</label>
            <input
              id="price"
              type="number"
              min="0.01"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="currency">Currency</label>
            <select id="currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="source">Marketplace</label>
            <input
              id="source"
              type="text"
              placeholder="e.g. Facebook Marketplace"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              required
            />
          </div>
        </div>

        <div className="field">
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            minLength={10}
            required
          />
        </div>

        <button type="submit" disabled={submitting}>
          {submitting ? 'Analyzing…' : 'Analyze listing'}
        </button>
      </form>
    </div>
  );
}
