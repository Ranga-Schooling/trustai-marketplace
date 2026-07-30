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

const CURRENCIES = ['ZAR', 'USD', 'EUR', 'GBP'];

export default function ListingForm({ onResult }) {
  const [form, setForm] = useState(initialState);
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
    <div className="content-grid">
      <section className="card hero-card compact">
        <p className="eyebrow">New review</p>
        <h1>Evaluate a marketplace listing</h1>
        <p className="subtle">
          Share the listing basics and let TrustAI produce a structured recommendation that highlights the strongest warning signs.
        </p>
        <ul className="check-list">
          <li>Title, price, and marketplace context</li>
          <li>Short description of the listing</li>
          <li>Optional URL for supporting context</li>
        </ul>
      </section>

      <section className="card">
        <h2>Listing details</h2>
        <form onSubmit={handleSubmit}>
          {error ? <div className="error">{error}</div> : null}

          <div className="field">
            <label htmlFor="title">Title</label>
            <input id="title" name="title" value={form.title} onChange={updateField} required />
          </div>

          <div className="row">
            <div className="field">
              <label htmlFor="price">Price</label>
              <input id="price" name="price" type="number" step="0.01" min="0.01" value={form.price} onChange={updateField} required />
            </div>
            <div className="field">
              <label htmlFor="currency">Currency</label>
              <select id="currency" name="currency" value={form.currency} onChange={updateField}>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="CAD">CAD</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="source">Marketplace</label>
              <input id="source" name="source" value={form.source} onChange={updateField} required />
            </div>
          </div>

          <div className="field">
            <label htmlFor="description">Description</label>
            <textarea id="description" name="description" value={form.description} onChange={updateField} required />
          </div>

          <div className="field">
            <label htmlFor="url">Listing URL (optional)</label>
            <input id="url" name="url" type="url" value={form.url} onChange={updateField} placeholder="https://example.com/listing" />
          </div>

          <button type="submit" disabled={loading}>
            {loading ? 'Analyzing…' : 'Analyze listing'}
          </button>
        </form>
      </section>
    </div>
  );
}
