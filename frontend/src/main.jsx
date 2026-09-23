import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import ServicePreview from './preview/ServicePreview';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'The request could not be completed. Please try again.');
  }
  if (!data) throw new Error('Could not read the server response.');
  return data;
}

function Cell({ value }) {
  if (value === null || value === '') return <span className="empty">Empty</span>;
  const text = String(value);
  if (text.length > 100) return (
    <details><summary>{text.slice(0, 80)}...</summary><div className="full-value">{text}</div></details>
  );
  return <span className="cell-value">{text}</span>;
}

function Preview({ upload }) {
  const report = upload.analysis;
  return <section className="panel" aria-labelledby="preview-title">
    <div className="section-title"><h2 id="preview-title">CSV Preview</h2><a href={`/api/uploads/${upload.id}/original/`}>Download original</a></div>
    <p className="filename">{upload.name}</p>
    <dl className="metrics">
      <div><dt>Rows</dt><dd>{report.row_count.toLocaleString()}</dd></div>
      <div><dt>Columns</dt><dd>{report.column_count}</dd></div>
      <div><dt>Encoding</dt><dd>{upload.encoding === 'utf-8-sig' ? 'UTF-8' : upload.encoding.toUpperCase()}</dd></div>
    </dl>
    {report.warnings.length > 0 && <aside className="notice"><ul>{report.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></aside>}
    <p className="muted">Showing {report.preview.length} preview rows. The header is row 0, and the first data row is row 1.</p>
    <div className="table-scroll" role="region" aria-label="Uploaded CSV preview" tabIndex={0}>
      <table>
        <thead><tr><th scope="col">Row 0</th>{report.columns.map((column, index) => <th scope="col" key={column.id}><small>Column {index + 1}</small>{column.label}</th>)}</tr></thead>
        <tbody>{report.preview.map((row) => <tr key={row.row_number}><th scope="row">{row.row_number - 1}</th>{row.values.map((value, index) => <td key={index}><Cell value={value} /></td>)}</tr>)}</tbody>
      </table>
    </div>
    {!report.row_count && <p>The file has headers but no data rows.</p>}
  </section>;
}

const typeLabels = {
  text: 'Text', number: 'Number', date: 'Date', datetime: 'Date/time',
  time: 'Time', boolean: 'Boolean', formula: 'Formula-like', mixed: 'Mixed', unknown: 'Unknown',
};
const percent = (value) => `${(value * 100).toFixed(1)}%`;

function ColumnAnalysis({ report }) {
  return <section className="panel" aria-labelledby="analysis-title">
    <h2 id="analysis-title">Column analysis</h2>
    <p className="muted">This analysis uses all {report.row_count.toLocaleString()} data rows, not only the preview rows. Type labels are candidates based on value format, and original values are not changed.</p>
    <details className="help analysis-help"><summary>How to read the statistics</summary>
      <ul>
        <li>Missing values count empty cells or cells that contain only whitespace. Fully blank rows are excluded from analysis.</li>
        <li>Unique values count distinct non-empty values using original string values.</li>
        <li>Number/date ratios show how many non-empty values can be read as those formats.</li>
        <li>No relationship or business-rule inference is performed from these statistics alone.</li>
      </ul>
    </details>
    <div className="table-scroll" role="region" aria-label="Column analysis results" tabIndex={0}>
      <table className="analysis-table">
        <thead><tr>{['Column', 'Type candidate', 'Missing', 'Unique', 'Number ratio', 'Date ratio', 'Value format notes'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{report.columns.map((column, index) => <tr key={column.id}>
          <th scope="row"><small>Column {index + 1}</small>{column.label}</th>
          <td><span className={`type-badge ${column.candidate === 'mixed' ? 'type-mixed' : ''}`}>{typeLabels[column.candidate] || column.candidate}</span></td>
          <td>{column.missing_count.toLocaleString()} <small>{report.row_count ? percent(column.missing_ratio) : '-'}</small></td>
          <td>{column.unique_count.toLocaleString()}</td>
          <td>{column.non_empty_count ? percent(column.number_ratio) : '-'}</td>
          <td>{column.non_empty_count ? percent(column.date_ratio) : '-'}</td>
          <td><div className="muted">{Object.entries(column.type_counts).map(([kind, count]) => `${typeLabels[kind] || kind} ${count.toLocaleString()}`).join(' ? ') || 'Empty column'}</div>
            {column.issues.length > 0 && <ul className="column-issues">{column.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>}
          </td>
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}

function ClaudePreviewApproval({ upload, csrfToken, onResult }) {
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(null);

  async function loadSummary() {
    setBusy(true); setError('');
    try {
      setSummary(await api(`/api/uploads/${upload.id}/inference/`));
    } catch (err) {
      setError(err.message);
    } finally { setBusy(false); }
  }

  async function approve() {
    if (!summary || busy) return;
    setBusy(true); setError('');
    try {
      const result = await api(`/api/uploads/${upload.id}/inference/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ approved: true, approval_note: `${summary.model} one-call approval` }),
      });
      setDone(result);
      onResult(result);
    } catch (err) {
      setError(err.message);
    } finally { setBusy(false); }
  }

  return <section className="panel" aria-labelledby="claude-title">
    <div className="section-title"><h2 id="claude-title">Create Claude Preview</h2>
      {!summary && <button type="button" onClick={loadSummary} disabled={busy}>{busy ? 'Checking...' : 'Check call scope'}</button>}</div>
    <p className="muted">Uploading and checking the CSV does not cost money. Claude API is called only after you approve one call.</p>
    {summary && <div className="approval-box">
      <dl className="metrics">
        <div><dt>Model</dt><dd>{summary.model}</dd></div>
        <div><dt>Calls</dt><dd>{summary.planned_call_count}</dd></div>
        <div><dt>Max output</dt><dd>{summary.max_output_tokens.toLocaleString()} tokens</dd></div>
      </dl>
      <p className="muted">Data sent: original CSV excluded, {summary.transmitted_data.column_count.toLocaleString()} analyzed columns, {summary.transmitted_data.sample_count.toLocaleString()} sample rows, {summary.transmitted_data.request_bytes.toLocaleString()} request bytes.</p>
      <p className="muted">{summary.cost_note}</p>
      <button type="button" onClick={approve} disabled={busy || done}>{busy ? 'Calling...' : 'Approve 1 Claude API call'}</button>
    </div>}
    {done && <p className="notice">Claude result was validated and applied as the Preview config. Call record ID: {done.model_call_id}</p>}
    {error && <div className="error" role="alert">{error}</div>}
  </section>;
}

function App() {
  const [file, setFile] = useState(null);
  const [encoding, setEncoding] = useState('auto');
  const [allowReplacement, setAllowReplacement] = useState(false);
  const [upload, setUpload] = useState(null);
  const [csrfToken, setCsrfToken] = useState('');
  const [claudeResult, setClaudeResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (!file || busy) return;
    setError('');
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('Please select a CSV file.'); return; }
    if (!file.size || file.size > 10 * 1024 * 1024) { setError('The file must be larger than 0 bytes and at most 10MB.'); return; }
    setBusy(true); setUpload(null); setClaudeResult(null);
    try {
      const { csrf_token } = await api('/api/session/');
      setCsrfToken(csrf_token);
      const body = new FormData();
      body.append('file', file); body.append('encoding', encoding);
      body.append('allow_replacement', String(allowReplacement));
      setUpload(await api('/api/uploads/', { method: 'POST', body, headers: { 'X-CSRFToken': csrf_token } }));
    } catch (err) {
      setError(err instanceof TypeError ? 'Could not connect to the server. Check the connection and try again.' : err.message);
    } finally { setBusy(false); }
  }

  return (
    <main>
      <header><p className="eyebrow">Sheet2Service</p><h1>Turn a spreadsheet into a service preview</h1><p>Upload a CSV and confirm that the data was read correctly first.</p></header>
      <section className="panel" aria-labelledby="upload-title">
        <h2 id="upload-title">Upload CSV</h2>
        <p className="muted">Upload a comma-separated CSV where the first row contains column names and later rows contain records.</p>
        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            <label className="file-label">Choose file<input type="file" accept=".csv,text/csv" required onChange={(event) => { setFile(event.target.files[0] || null); setUpload(null); setClaudeResult(null); setError(''); }} /></label>
            <button type="submit" disabled={!file}>{busy ? 'Reading...' : 'Upload and check'}</button>
            <details className="advanced"><summary>Advanced settings</summary>
              <label>Character encoding<select value={encoding} onChange={(event) => { setEncoding(event.target.value); setAllowReplacement(false); setUpload(null); setError(''); }}>
                <option value="auto">Auto (recommended)</option><option value="utf-8-sig">UTF-8 / UTF-8 BOM</option><option value="euc-kr">EUC-KR</option><option value="cp949">CP949 (extended EUC-KR)</option>
              </select></label>
              {encoding !== 'auto' && <label><span><input type="checkbox" checked={allowReplacement} onChange={(event) => { setAllowReplacement(event.target.checked); setUpload(null); }} /> Replace unreadable characters</span><small>Unreadable characters are shown as replacement marks. The original file is kept unchanged.</small></label>}
            </details>
          </fieldset>
        </form>
        <p className="muted">Limits: 10MB, 50,000 rows, 200 columns, 500,000 cells. The original file is preserved.</p>
        <p className="muted">Character encoding is selected automatically. Unreadable characters are reported in the result.</p>
        <details className="help"><summary>When exporting from Excel or text looks broken</summary><p>Save as CSV UTF-8 from Excel. Before exporting, check that leading zeroes and dates still have the intended values. If text is broken, change the encoding in Advanced settings.</p></details>
      </section>
      {error && <div className="error" role="alert">{error}</div>}
      <div role="status" aria-live="polite">{busy ? 'Reading the file. Please wait.' : upload ? 'Upload complete.' : ''}</div>
      {upload && <Preview upload={upload} />}
      {upload && <ClaudePreviewApproval upload={upload} csrfToken={csrfToken} onResult={setClaudeResult} />}
      {upload && <ServicePreview key={`${upload.id}-${claudeResult?.model_call_id || 'dev-sample'}`} report={upload.analysis} config={claudeResult?.result.preview} />}
      {upload && <ColumnAnalysis report={upload.analysis} />}
    </main>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>,
);
