// E5 Frontend (owner: Adrian) — US-2.1 listing submission.
// Contract: api.createAnalysis({title, price:Number, currency, source,
// description, url|null}) -> AnalysisOut. 422 -> show field errors;
// 502 -> tell the user the listing was saved and to retry.
// TODO(E5): form fields (title, price, currency select, source,
// description textarea, optional url), busy state on submit.
import { api } from '../api';

export default function ListingForm({ onResult }) {
  return (
    <div className="card">
      <h1>Analyze a listing</h1>
      <p className="subtle">TODO(E5/US-2.1): build the submission form.</p>
    </div>
  );
}
