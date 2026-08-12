import { useState } from 'react';
import RiskGauge from './RiskGauge';

export default function AnalysisResult({ analysis, onBack, onViewHistory }) {
  const [copied, setCopied] = useState(false);
  const riskLevel = analysis.risk_level || 'low';
  const recommendationLabel = {
    buy: 'Buy',
    caution: 'Caution',
    avoid: 'Avoid',
  }[analysis.recommendation] || 'Review';

  const riskScore = typeof analysis.risk_score === 'number' ? analysis.risk_score : null;
  const indicators = Array.isArray(analysis.risk_indicators) ? analysis.risk_indicators : [];
  const sellerQuestions = Array.isArray(analysis.seller_questions) ? analysis.seller_questions : [];

  async function handleCopyQuestions() {
    if (sellerQuestions.length === 0) return;

    try {
      await navigator.clipboard.writeText(sellerQuestions.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can fail silently (e.g. permissions); no user-facing error needed here.
    }
  }

  return (
    <div className="result-page">
      <h1>Analysis Result</h1>

      <div className="result-summary-row">
        <div className="card summary-box">
          <p className="eyebrow">Recommendation</p>
          <span className={`recommendation-pill ${riskLevel}`}>{recommendationLabel}</span>
        </div>

        <RiskGauge riskScore={riskScore} />

        <div className="card summary-box">
          <p className="eyebrow">Price fairness</p>
          <p>{analysis.price_assessment || 'No price assessment was provided.'}</p>
        </div>
      </div>

      <div className="content-grid">
        <section className="card">
          <h2>AI summary</h2>
          <p className="subtle">{analysis.summary || 'The AI generated a structured review for this listing.'}</p>

          <h2 className="section-heading">Risk indicators</h2>
          {indicators.length > 0 ? (
            <ul className="indicator-list">
              {indicators.map((indicator, index) => (
                <li key={`${indicator.category}-${index}`} className={`indicator ${indicator.severity || riskLevel}`}>
                  <div className="cat">{indicator.category}</div>
                  <p>{indicator.explanation}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="subtle">No specific indicators were returned, but this review does not guarantee the listing is safe.</p>
          )}
        </section>

        <section className="card">
          <h2>Suggested seller questions</h2>
          {sellerQuestions.length > 0 ? (
            <ol className="questions-list numbered">
              {sellerQuestions.map((question, index) => (
                <li key={`${question}-${index}`}>{question}</li>
              ))}
            </ol>
          ) : (
            <p className="subtle">No seller questions were supplied for this check.</p>
          )}

          <button type="button" className="ghost" onClick={handleCopyQuestions} disabled={sellerQuestions.length === 0}>
            {copied ? 'Copied!' : 'Copy questions'}
          </button>
        </section>
      </div>

      <p className="disclaimer dashed">Disclaimer — TrustAI provides decision-support guidance, not a guarantee.</p>

      <div className="result-actions">
        <button type="button" onClick={onBack}>
          Analyze another listing
        </button>
        <button type="button" className="ghost" onClick={onViewHistory}>
          View saved history
        </button>
      </div>
    </div>
  );
}
