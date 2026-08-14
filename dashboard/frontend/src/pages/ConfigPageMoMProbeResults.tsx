import type { RecipeProbeDetail, RecipeProbeValidationResult } from '../types/recipe'
import styles from './ConfigPageMoMProbesPanel.module.css'

function formatContent(content: unknown): string {
  if (typeof content === 'string') return content
  return JSON.stringify(content, null, 2) ?? String(content ?? '')
}

function compactDigest(value?: string): string {
  if (!value) return '—'
  return value.length > 24 ? `${value.slice(0, 15)}…${value.slice(-8)}` : value
}

export function RecipeProbeDetailPanel({ detail }: { detail: RecipeProbeDetail }) {
  return (
    <div className={styles.detailPanel}>
      {detail.notes ? <p className={styles.notes}>{detail.notes}</p> : null}
      {detail.display_prompt ? (
        <section>
          <h4>Demo prompt</h4>
          <pre>{detail.display_prompt}</pre>
        </section>
      ) : null}
      {detail.raw_payload_hidden ? (
        <section role="note">
          <h4>Exact payload</h4>
          <p>
            Hidden because this Eval-only fixture contains synthetic stress data. Validate sends the
            exact bounded payload directly to Router without rendering it in the browser.
          </p>
        </section>
      ) : null}
      {detail.query ? (
        <section>
          <h4>Query</h4>
          <pre>{detail.query}</pre>
        </section>
      ) : null}
      {detail.messages?.length ? (
        <section>
          <h4>Messages</h4>
          <div className={styles.messageList}>
            {detail.messages.map((message, index) => (
              <div key={`${message.role}-${index}`}>
                <strong>{message.role}</strong>
                <pre>{formatContent(message.content)}</pre>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {detail.tools?.length ? (
        <section>
          <h4>Tools · {detail.tools.length}</h4>
          <pre>{JSON.stringify(detail.tools, null, 2)}</pre>
        </section>
      ) : null}
      {detail.repeat > 1 || detail.padding ? (
        <section>
          <h4>Materialization</h4>
          <dl className={styles.materializationGrid}>
            <div>
              <dt>Query repeat</dt>
              <dd>{detail.repeat || 1}×</dd>
            </div>
            {detail.padding ? (
              <>
                <div>
                  <dt>Padding repeat</dt>
                  <dd>{detail.padding.repeat}×</dd>
                </div>
                <div>
                  <dt>Placement</dt>
                  <dd>{detail.padding.placement}</dd>
                </div>
              </>
            ) : null}
          </dl>
        </section>
      ) : null}
    </div>
  )
}

export function RecipeProbeValidation({ result }: { result: RecipeProbeValidationResult }) {
  const unavailable = Boolean(result.error)
  const finalModel = result.actual.model?.trim()
  return (
    <div
      className={`${styles.validationResult} ${result.passed ? styles.validationPass : styles.validationFail}`}
      role={result.passed ? 'status' : 'alert'}
    >
      <div>
        <strong>
          {unavailable
            ? 'Validation unavailable'
            : result.passed
              ? 'Route validated'
              : 'Route mismatch'}
        </strong>
        <span>{result.latency_ms} ms</span>
      </div>
      <dl>
        <div className={styles.finalModelResult}>
          <dt>Final model</dt>
          <dd>{finalModel || 'Not evaluated'}</dd>
        </div>
        <div>
          <dt>Selection status</dt>
          <dd>{result.actual.selection_status?.replace(/_/g, ' ') || 'not evaluated'}</dd>
        </div>
        <div>
          <dt>Expected decision</dt>
          <dd>{result.expected.decision || '—'}</dd>
        </div>
        <div>
          <dt>Actual decision</dt>
          <dd>{result.actual.decision || '—'}</dd>
        </div>
        <div>
          <dt>Request model</dt>
          <dd>{result.actual.requested_model || '—'}</dd>
        </div>
      </dl>
      {!finalModel && result.actual.recommended_models.length ? (
        <p className={styles.candidateModels}>
          Candidates: {result.actual.recommended_models.join(', ')}
        </p>
      ) : null}
      {result.actual.selection_reason ? (
        <p className={styles.candidateModels}>{result.actual.selection_reason}</p>
      ) : null}
      {result.provenance ? (
        <div
          className={`${styles.provenance} ${result.provenance.status === 'verified' ? styles.provenanceVerified : styles.provenanceUnverified}`}
        >
          <div>
            <strong>
              {result.provenance.status === 'verified'
                ? 'Runtime provenance verified'
                : 'Runtime provenance unverified'}
            </strong>
            {result.provenance.reason ? (
              <span>{result.provenance.reason.replace(/_/g, ' ')}</span>
            ) : null}
          </div>
          <dl>
            <div>
              <dt>Package</dt>
              <dd title={result.provenance.package_hash}>
                {compactDigest(result.provenance.package_hash)}
              </dd>
            </div>
            <div>
              <dt>Runtime before</dt>
              <dd title={result.provenance.before.active_runtime_hash}>
                {compactDigest(result.provenance.before.active_runtime_hash)}
              </dd>
            </div>
            <div>
              <dt>Runtime after</dt>
              <dd title={result.provenance.after.active_runtime_hash}>
                {compactDigest(result.provenance.after.active_runtime_hash)}
              </dd>
            </div>
          </dl>
        </div>
      ) : null}
      {result.failures.length ? (
        <ul>
          {result.failures.map((failure, index) => (
            <li key={`${index}-${failure}`}>{failure}</li>
          ))}
        </ul>
      ) : null}
      {result.error ? <p>{result.error}</p> : null}
    </div>
  )
}
