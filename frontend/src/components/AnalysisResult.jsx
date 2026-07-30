export default function AnalysisResult({ analysis, onBack }) {
  const riskLevel = analysis.risk_level || 'low';
  const recommendationLabel = {
    buy: 'Buy',
    caution: 'Caution',
    avoid: 'Avoid',
  }[analysis.recommendation] || 'Review';

  const indicators = Array.isArray(analysis.risk_indicators) ? analysis.risk_indicators : [];
  const sellerQuestions = Array.isArray(analysis.seller_questions) ? analysis.seller_questions : [];

  return (
    <div className="result-page">
      <div className={`verdict ${riskLevel}`}>
        <div>
          <div className="word">{recommendationLabel}</div>
          <p className="verdict-copy">{analysis.summary || 'The AI generated a structured review for this listing.'}</p>
        </div>
        <span className={`badge ${riskLevel}`}>{riskLevel}</span>
      </div>

      <div className="content-grid">
        <section className="card">
          <p className="eyebrow">Analysis overview</p>
          <h2>What the AI is saying</h2>
          <p className="subtle">{analysis.summary}</p>
          <div className="info-block">
            <h3>Price assessment</h3>
            <p>{analysis.price_assessment || 'No price assessment was provided.'}</p>
          </div>
          <div className="info-block">
            <h3>Model used</h3>
            <p>{analysis.model_used || 'Preview mode'}</p>
          </div>
        </section>

        <section className="card">
          <p className="eyebrow">Risk indicators</p>
          <h2>Why this score landed here</h2>
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
      </div>

      <section className="card">
        <p className="eyebrow">Seller questions</p>
        <h2>Use these questions before you buy</h2>
        {sellerQuestions.length > 0 ? (
          <ul className="questions-list">
            {sellerQuestions.map((question, index) => (
              <li key={`${question}-${index}`}>{question}</li>
            ))}
          </ul>
        ) : (
          <p className="subtle">No seller questions were supplied for this check.</p>
        )}
      </section>

      <button type="button" className="ghost" onClick={onBack}>
        Back to submissions
      </button>
    </div>
  );
}
