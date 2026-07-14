// E5 Frontend (owner: Adrian) — US-4.1 history list.
// Contract: api.listAnalyses() -> newest-first array with listing_title,
// listing_price, listing_currency, risk_level, created_at.
// TODO(E5): loading state, empty state, clickable rows calling onOpen(item).
import { api } from '../api';

export default function History({ onOpen }) {
  return (
    <div className="card">
      <h1>Your analyses</h1>
      <p className="subtle">TODO(E5/US-4.1): build the history list.</p>
    </div>
  );
}
