import { useRef, useState } from 'react';
import { api } from '../api';

const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MAX_PHOTOS = 3;
const MAX_FILE_BYTES = 4 * 1024 * 1024;
const MAX_COMBINED_BYTES = 10 * 1024 * 1024;

const SAFE_ERROR_COPY = {
  413: 'The selected photos are too large. Choose smaller files and try again.',
  415: 'That file type is not supported. Choose JPEG, PNG, or WebP photos.',
  422: 'The selected photos could not be processed. Check your files and try again.',
  502: 'Visual inspection could not be completed. Please try again.',
  503: 'Visual inspection is temporarily unavailable. Please try again later.',
};

function validateFiles(files) {
  if (files.length === 0) return 'Select 1 to 3 photos.';
  if (files.length > MAX_PHOTOS) return 'Select no more than 3 photos.';
  if (files.some((file) => !ALLOWED_TYPES.has(file.type))) {
    return 'Choose JPEG, PNG, or WebP photos only.';
  }
  if (files.some((file) => file.size > MAX_FILE_BYTES)) {
    return 'Each photo must be 4 MiB or smaller.';
  }
  if (files.reduce((total, file) => total + file.size, 0) > MAX_COMBINED_BYTES) {
    return 'The combined photos must be 10 MiB or smaller.';
  }
  return '';
}

function categoryLabel(category) {
  const words = category.replaceAll('_', ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function photoReference(photoNumbers) {
  return photoNumbers.length === 1
    ? `Photo ${photoNumbers[0]}`
    : `Photos ${photoNumbers.join(', ')}`;
}

export default function VisualInspection({ analysisId }) {
  const fileInput = useRef(null);
  const [files, setFiles] = useState([]);
  const [consent, setConsent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const selectionError = validateFiles(files);
  const canSubmit = !selectionError && consent && !loading;

  function handleFileChange(event) {
    const nextFiles = Array.from(event.target.files || []);
    setFiles(nextFiles);
    setError(validateFiles(nextFiles));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const validationError = validateFiles(files);
    if (validationError || !consent || loading) {
      if (validationError) setError(validationError);
      return;
    }

    setLoading(true);
    setError('');
    try {
      setResult(await api.visualInspect(analysisId, files));
    } catch (requestError) {
      setError(
        SAFE_ERROR_COPY[requestError?.status]
          || 'Visual inspection could not be completed. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  }

  function resetInspection() {
    setFiles([]);
    setConsent(false);
    setLoading(false);
    setError('');
    setResult(null);
    if (fileInput.current) fileInput.current.value = '';
  }

  return (
    <section className="card visual-inspection">
      <header className="visual-inspection-header">
        <span className="visual-inspection-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <path d="M4 7.5h3l1.4-2h7.2l1.4 2h3a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9.5a2 2 0 0 1 2-2Z" />
            <circle cx="12" cy="13.5" r="3.5" />
          </svg>
        </span>
        <div>
          <p className="eyebrow">Visual Inspection</p>
          <h2>Add photos for visual inspection</h2>
          <p className="subtle visual-inspection-intro">
            Add up to 3 photos to check visible condition and listing consistency.
          </p>
        </div>
      </header>

      {result ? (
        <div className="visual-inspection-result">
          <div className="visual-result-heading">
            <div>
              <p className="eyebrow">Photo findings</p>
              <h3>Visible evidence from your upload</h3>
            </div>
            <span className="visual-advisory-chip">Advisory</span>
          </div>

          <div className="visual-findings">
            {result.findings.map((finding, index) => (
              <article className="visual-finding" key={`${finding.category}-${index}`}>
                <div className="visual-finding-heading">
                  <h3>{categoryLabel(finding.category)}</h3>
                  <span className="visual-photo-reference">
                    {photoReference(finding.photo_numbers)}
                  </span>
                </div>
                <p className="visual-finding-observation">{finding.observation}</p>
              </article>
            ))}
          </div>

          <aside className="visual-score-separation">
            <p>Visual findings do not change the existing Trust score or recommendation.</p>
          </aside>

          <aside className="visual-limitations">
            <h3>What this inspection cannot verify</h3>
            <ul>
              <li>Only the uploaded photos are inspected.</li>
              <li>
                Visual Inspection does not certify authenticity, establish ownership, or verify hidden or internal condition.
              </li>
              <li>It does not retrieve current market prices.</li>
            </ul>
          </aside>

          <div className="visual-result-actions">
            <button type="button" className="ghost" onClick={resetInspection}>Inspect another set</button>
          </div>
        </div>
      ) : (
        <form className="visual-inspection-form" onSubmit={handleSubmit}>
          <div className="visual-inspection-grid">
            <div className="visual-upload-panel">
              <p className="visual-input-label">Choose photos</p>
              <input
                ref={fileInput}
                id="visual-inspection-photos"
                className="visual-file-input"
                type="file"
                aria-label="Choose photos"
                accept="image/jpeg,image/png,image/webp"
                multiple
                disabled={loading}
                onChange={handleFileChange}
              />
              <label className="visual-file-trigger" htmlFor="visual-inspection-photos">
                <span aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false">
                    <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" />
                  </svg>
                </span>
                Select photos
              </label>
              <p className="visual-upload-guidance">
                Choose 1 to 3 JPEG, PNG, or WebP photos. Each photo must be 4 MiB or smaller.
                The combined selection must be 10 MiB or smaller.
              </p>
              {files.length > 0 ? (
                <p className="visual-selection-count" aria-live="polite">
                  {files.length} {files.length === 1 ? 'photo' : 'photos'} selected
                </p>
              ) : null}
            </div>

            <aside className="visual-privacy-disclosure">
              <div className="visual-notice-heading">
                <span aria-hidden="true">i</span>
                <h3>Before you upload</h3>
              </div>
              <p>Selected photos are sent to OpenAI for visual inspection.</p>
              <p>TrustAI does not save the photos or Visual Inspection findings in V1.</p>
              <p>Processing may be subject to OpenAI&apos;s API data-handling policy.</p>
              <p>Do not upload sensitive or personal images.</p>
            </aside>
          </div>

          <label className="visual-consent">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
            />
            I consent to sending these photos to OpenAI for visual inspection
          </label>

          {error ? <div className="error visual-inspection-error" role="alert" aria-live="assertive">{error}</div> : null}
          {loading ? (
            <div className="visual-inspection-loading" role="status">
              <span className="visual-loading-spinner" aria-hidden="true" />
              <span>
                <strong>Inspecting photos…</strong>
                <small>Reviewing only the visible evidence in your selected photos.</small>
              </span>
            </div>
          ) : null}

          <div className="visual-inspection-actions">
            <button type="submit" disabled={!canSubmit}>
              {loading ? 'Inspecting photos…' : 'Inspect photos'}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
