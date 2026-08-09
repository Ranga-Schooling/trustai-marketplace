import { useState } from 'react';
import { ApiError, api } from '../api';

// Stretch (US-2.4, D-12). Mirrors backend defaults (settings.max_listing_images
// / max_image_bytes) -- this is UX only, the server enforces the real 413 caps.
const MAX_IMAGES = 3;
const MAX_IMAGE_BYTES = 2_000_000;

const initialState = {
  title: '',
  price: '',
  currency: 'USD',
  source: 'Marketplace',
  description: '',
  url: '',
};

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export default function ListingForm({ onResult }) {
  const [form, setForm] = useState(initialState);
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function handleImagesSelected(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (files.length === 0) return;

    if (images.length + files.length > MAX_IMAGES) {
      setError(`You can attach up to ${MAX_IMAGES} images.`);
      return;
    }
    const oversized = files.find((file) => file.size > MAX_IMAGE_BYTES);
    if (oversized) {
      setError(`"${oversized.name}" is over ${Math.round(MAX_IMAGE_BYTES / 1_000_000)}MB.`);
      return;
    }

    setError('');
    const dataUrls = await Promise.all(files.map(readAsDataUrl));
    setImages((current) => [...current, ...dataUrls]);
  }

  function removeImage(index) {
    setImages((current) => current.filter((_, i) => i !== index));
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
        images,
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
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="CAD">CAD</option>
                <option value="ZAR">ZAR</option>
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
            <input
              id="url"
              name="url"
              type="url"
              value={form.url}
              onChange={updateField}
              placeholder="https://…"
            />
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

          <div className="field">
            <label htmlFor="images">Listing photos (optional)</label>
            <input
              id="images"
              name="images"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              multiple
              onChange={handleImagesSelected}
              disabled={images.length >= MAX_IMAGES}
            />
            <p className="field-hint">
              Up to {MAX_IMAGES} photos, {Math.round(MAX_IMAGE_BYTES / 1_000_000)}MB each. Helps flag stock photos or mismatched items.
            </p>
            {images.length > 0 ? (
              <div className="image-preview-list">
                {images.map((src, index) => (
                  <div className="image-preview" key={`${index}-${src.slice(-12)}`}>
                    <img src={src} alt={`Listing photo ${index + 1}`} />
                    <button type="button" className="image-remove" onClick={() => removeImage(index)} aria-label="Remove photo">
                      ×
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
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
