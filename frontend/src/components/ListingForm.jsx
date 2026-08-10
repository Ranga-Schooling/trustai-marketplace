import { useState } from 'react';
import { ApiError, api } from '../api';

const initialState = {
  title: '',
  price: '',
  currency: 'USD',
  source: 'Marketplace',
  description: '',
  url: '',
};

const CURRENCIES = ['USD', 'EUR', 'GBP', 'CAD', 'ZAR'];

export default function ListingForm({ onResult }) {
  const [form, setForm] = useState(initialState);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  // US-2.3: server-side URL fetch to suggest title/description/source.
  // Never bypasses this form -- the user still reviews/edits and submits
  // through the same handleSubmit/POST /analyses path as manual entry.
  const [fetchingUrl, setFetchingUrl] = useState(false);
  const [fetchError, setFetchError] = useState('');

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function handleFetchUrl() {
    const url = form.url.trim();
    if (!url) return;
    setFetchError('');
    setFetchingUrl(true);
    try {
      const preview = await api.previewListingUrl(url);
      setForm((current) => ({
        ...current,
        title: preview.title || current.title,
        description: preview.description || current.description,
        source: preview.source || current.source,
      }));
    } catch (err) {
      setFetchError(err instanceof ApiError ? err.message : 'Unable to fetch that URL right now.');
    } finally {
      setFetchingUrl(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setLoading(true);

    try {
      const analysis = await api.createAnalysis({
        ...form,
        price: Number(form.price),
        currency: form.currency.toUpperCase(),
        url: form.url.trim() ? form.url.trim() : null,
      });
      onResult(analysis);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to analyze that listing right now.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="submit-grid">
      <section className="card">
        <h1>Submit a marketplace listing for analysis</h1>

        <h2 className="section-heading">Listing details</h2>
        <form onSubmit={handleSubmit}>
          {error ? <div className="error">{error}</div> : null}

          <div className="field">
            <label htmlFor="title">
              Title <span className="req">*</span>
            </label>
            <input
              id="title"
              name="title"
              value={form.title}
              onChange={updateField}
              placeholder="iPhone 14 Pro 256GB"
              required
            />
          </div>

          <div className="row two-col">
            <div className="field">
              <label htmlFor="price">
                Price <span className="req">*</span>
              </label>
              <input
                id="price"
                name="price"
                type="number"
                step="0.01"
                min="0.01"
                value={form.price}
                onChange={updateField}
                placeholder="6500"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="currency">
                Currency <span className="req">*</span>
              </label>
              <select id="currency" name="currency" value={form.currency} onChange={updateField}>
                {CURRENCIES.map((code) => (
                  <option key={code} value={code}>{code}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="field">
            <label htmlFor="source">
              Source <span className="req">*</span>
            </label>
            <input
              id="source"
              name="source"
              value={form.source}
              onChange={updateField}
              placeholder="Facebook Marketplace"
              required
            />
            <p className="field-hint">e.g. Facebook Marketplace, Gumtree, OLX</p>
          </div>

          <div className="field">
            <label htmlFor="url">Optional URL</label>
            <div className="url-fetch-row">
              <input
                id="url"
                name="url"
                type="url"
                value={form.url}
                onChange={updateField}
                placeholder="https://…"
              />
              <button
                type="button"
                className="ghost"
                onClick={handleFetchUrl}
                disabled={fetchingUrl || !form.url.trim()}
              >
                {fetchingUrl ? 'Fetching…' : 'Fetch details'}
              </button>
            </div>
            <p className="field-hint">Suggests the title, description, and source below — review before submitting.</p>
            {fetchError ? <div className="error">{fetchError}</div> : null}
          </div>

          <div className="field">
            <label htmlFor="description">
              Description <span className="req">*</span>
            </label>
            <textarea
              id="description"
              name="description"
              value={form.description}
              onChange={updateField}
              placeholder="Paste listing text"
              required
            />
          </div>

          <button type="submit" disabled={loading}>
            {loading ? 'Analyzing…' : 'Analyze listing'}
          </button>
        </form>
      </section>

      <aside className="card tips-card">
        <p className="eyebrow">Tips for better analysis</p>
        <ul className="check-list">
          <li>Include full description</li>
          <li>Include price and seller claims</li>
          <li>Add URL if available</li>
          <li>Do not include private data</li>
        </ul>
      </aside>
    </div>
  );
}
