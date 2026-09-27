import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import ServicePreviewV2 from './preview/ServicePreviewV2';
import TemplateExamples from './preview/TemplateExamples';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다. 다시 시도해 주세요.');
  }
  if (!data) throw new Error('서버 응답을 읽지 못했습니다.');
  return data;
}

function Cell({ value }) {
  if (value === null || value === '') return <span className="empty">빈 값</span>;
  const text = String(value);
  if (text.length > 100) return (
    <details><summary>{text.slice(0, 80)}...</summary><div className="full-value">{text}</div></details>
  );
  return <span className="cell-value">{text}</span>;
}

function Preview({ upload }) {
  const report = upload.analysis;
  return <section className="panel" aria-labelledby="preview-title">
    <div className="section-title"><h2 id="preview-title">CSV 미리보기</h2><a href={`/api/uploads/${upload.id}/original/`}>원본 다운로드</a></div>
    <p className="filename">{upload.name}</p>
    <dl className="metrics">
      <div><dt>데이터 행</dt><dd>{report.row_count.toLocaleString()}</dd></div>
      <div><dt>열</dt><dd>{report.column_count}</dd></div>
      <div><dt>문자 인코딩</dt><dd>{upload.encoding === 'utf-8-sig' ? 'UTF-8' : upload.encoding.toUpperCase()}</dd></div>
    </dl>
    {report.warnings.length > 0 && <aside className="notice"><ul>{report.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></aside>}
    <p className="muted">데이터 {report.preview.length.toLocaleString()}행을 미리 보여줍니다. 헤더는 0행, 첫 데이터는 1행으로 표시합니다.</p>
    <div className="table-scroll" role="region" aria-label="업로드한 CSV 미리보기" tabIndex={0}>
      <table>
        <thead><tr><th scope="col">0행</th>{report.columns.map((column, index) => <th scope="col" key={column.id}><small>{index + 1}열</small>{column.label}</th>)}</tr></thead>
        <tbody>{report.preview.map((row) => <tr key={row.row_number}><th scope="row">{row.row_number - 1}</th>{row.values.map((value, index) => <td key={index}><Cell value={value} /></td>)}</tr>)}</tbody>
      </table>
    </div>
    {!report.row_count && <p>헤더는 있지만 데이터 행이 없습니다.</p>}
  </section>;
}

const typeLabels = {
  text: '텍스트', number: '숫자', date: '날짜', datetime: '날짜·시간',
  time: '시간', boolean: '참·거짓', formula: '수식 형태', mixed: '혼합', unknown: '알 수 없음',
};
const percent = (value) => `${(value * 100).toFixed(1)}%`;

function ColumnAnalysis({ report }) {
  return <section className="panel" aria-labelledby="analysis-title">
    <h2 id="analysis-title">열별 분석</h2>
    <p className="muted">미리보기 행뿐 아니라 데이터 {report.row_count.toLocaleString()}행 전체를 분석했습니다. 값의 형식으로 추정한 타입이며 원본 값은 바꾸지 않았습니다.</p>
    <details className="help analysis-help"><summary>통계 읽는 방법</summary>
      <ul>
        <li>결측값은 빈 셀과 공백만 있는 셀입니다. 완전히 빈 행은 분석에서 제외합니다.</li>
        <li>고유값 수는 비어 있지 않은 원본 문자열을 기준으로 계산합니다.</li>
        <li>숫자·날짜 비율은 비어 있지 않은 값 중 해당 형식으로 읽을 수 있는 값의 비율입니다.</li>
        <li>이 통계만으로 데이터 관계나 업무 규칙을 추론하지 않습니다.</li>
      </ul>
    </details>
    <div className="table-scroll" role="region" aria-label="열별 분석 결과" tabIndex={0}>
      <table className="analysis-table">
        <thead><tr>{['열', '타입 후보', '결측값', '고유값', '숫자 비율', '날짜 비율', '값 형식·확인 사항'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{report.columns.map((column, index) => <tr key={column.id}>
          <th scope="row"><small>{index + 1}열</small>{column.label}</th>
          <td><span className={`type-badge ${column.candidate === 'mixed' ? 'type-mixed' : ''}`}>{typeLabels[column.candidate] || column.candidate}</span></td>
          <td>{column.missing_count.toLocaleString()} <small>{report.row_count ? percent(column.missing_ratio) : '-'}</small></td>
          <td>{column.unique_count.toLocaleString()}</td>
          <td>{column.non_empty_count ? percent(column.number_ratio) : '-'}</td>
          <td>{column.non_empty_count ? percent(column.date_ratio) : '-'}</td>
          <td><div className="muted">{Object.entries(column.type_counts).map(([kind, count]) => `${typeLabels[kind] || kind} ${count.toLocaleString()}`).join(' · ') || '값이 없는 열'}</div>
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
        body: JSON.stringify({ approved: true, approval_note: `${summary.model} 1회 호출 승인` }),
      });
      setDone(result);
      onResult(result);
    } catch (err) {
      setError(err.message);
    } finally { setBusy(false); }
  }

  return <section className="panel" aria-labelledby="claude-title">
    <div className="section-title"><h2 id="claude-title">Claude로 서비스 미리보기 만들기</h2>
      {!summary && <button type="button" onClick={loadSummary} disabled={busy}>{busy ? '확인 중...' : '전송 범위 확인'}</button>}</div>
    <p className="muted">CSV 업로드와 분석에는 Claude API 비용이 들지 않습니다. 1회 호출을 승인한 뒤에만 Claude API를 호출합니다.</p>
    {summary && <div className="approval-box">
      <dl className="metrics">
        <div><dt>모델</dt><dd>{summary.model}</dd></div>
        <div><dt>호출 횟수</dt><dd>{summary.planned_call_count}</dd></div>
        <div><dt>최대 출력</dt><dd>{summary.max_output_tokens.toLocaleString()}토큰</dd></div>
      </dl>
      <p className="muted">목적: {summary.purpose}</p>
      <p className="muted">전송 범위: CSV 원본 파일 전체는 제외합니다. 전체 행에서 계산한 {summary.transmitted_data.column_count.toLocaleString()}개 열의 통계와 컬럼명, 예시 {summary.transmitted_data.sample_count.toLocaleString()}행의 실제 셀 값을 보냅니다. {summary.transmitted_data.sample_count === 10
        ? '앞·중간·뒤 각 2행과 분산 추출한 4행을 사용합니다.'
        : '데이터가 10행 이하라 모든 데이터 행을 사용합니다.'} 각 문자열은 최대 {summary.transmitted_data.max_text_chars}자로 제한합니다. 잘린 값은 {summary.transmitted_data.truncated_value_count.toLocaleString()}개입니다. 요청 본문은 {summary.transmitted_data.request_bytes.toLocaleString()}바이트입니다.</p>
      <p className="muted">{summary.cost_note}</p>
      <p className="muted"><a href="https://platform.claude.com/docs/en/about-claude/pricing" target="_blank" rel="noopener noreferrer">Claude 공식 요금 확인</a> · 자동 재시도 {summary.automatic_retries}회</p>
      <button type="button" onClick={approve} disabled={busy || done || !summary.pricing_estimate_available}>{busy ? '호출 중...' : 'Claude API 1회 호출 승인'}</button>
    </div>}
    {done && <p className="notice">{done.result.used_fallback
      ? 'Claude 설정을 적용할 수 없어 기본 표를 사용합니다.'
      : 'Claude 결과를 검증하고 서비스 미리보기 설정에 적용했습니다.'} 호출 기록 ID: {done.model_call_id}</p>}
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
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('CSV 파일을 선택해 주세요.'); return; }
    if (!file.size || file.size > 10 * 1024 * 1024) { setError('파일은 0바이트보다 크고 10MB 이하여야 합니다.'); return; }
    setBusy(true); setUpload(null); setClaudeResult(null);
    try {
      const { csrf_token } = await api('/api/session/');
      setCsrfToken(csrf_token);
      const body = new FormData();
      body.append('file', file); body.append('encoding', encoding);
      body.append('allow_replacement', String(allowReplacement));
      setUpload(await api('/api/uploads/', { method: 'POST', body, headers: { 'X-CSRFToken': csrf_token } }));
    } catch (err) {
      setError(err instanceof TypeError ? '서버에 연결할 수 없습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.' : err.message);
    } finally { setBusy(false); }
  }

  return (
    <main>
      <header><p className="eyebrow">Sheet2Service</p><h1>CSV로 서비스 미리보기 만들기</h1><p>먼저 CSV를 업로드하고 데이터가 올바르게 읽혔는지 확인해 주세요.</p><a href="/templates/">템플릿 예시 보기</a></header>
      <section className="panel" aria-labelledby="upload-title">
        <h2 id="upload-title">CSV 업로드</h2>
        <p className="muted">첫 행에 열 이름이 있고 이후 행에 데이터가 있는 쉼표 구분 CSV 파일을 업로드해 주세요.</p>
        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            <label className="file-label">파일 선택<input type="file" accept=".csv,text/csv" required onChange={(event) => { setFile(event.target.files[0] || null); setUpload(null); setClaudeResult(null); setError(''); }} /></label>
            <button type="submit" disabled={!file}>{busy ? '읽는 중...' : '업로드하고 확인'}</button>
            <details className="advanced"><summary>고급 설정</summary>
              <label>문자 인코딩<select value={encoding} onChange={(event) => { setEncoding(event.target.value); setAllowReplacement(false); setUpload(null); setError(''); }}>
                <option value="auto">자동 선택 (권장)</option><option value="utf-8-sig">UTF-8 / UTF-8 BOM</option><option value="euc-kr">EUC-KR</option><option value="cp949">CP949 (확장 EUC-KR)</option>
              </select></label>
              {encoding !== 'auto' && <label><span><input type="checkbox" checked={allowReplacement} onChange={(event) => { setAllowReplacement(event.target.checked); setUpload(null); }} /> 읽을 수 없는 문자 대체</span><small>읽을 수 없는 문자는 대체 기호(�)로 표시합니다. 원본 파일은 변경하지 않습니다.</small></label>}
            </details>
          </fieldset>
        </form>
        <p className="muted">제한: 10MB, 데이터 50,000행, 200열, 500,000셀. 원본 파일은 보존합니다.</p>
        <p className="muted">문자 인코딩은 자동으로 선택하며 읽을 수 없는 문자는 결과에 알려드립니다.</p>
        <details className="help"><summary>Excel에서 내보내거나 글자가 깨져 보일 때</summary><p>Excel에서 CSV UTF-8로 저장해 주세요. 저장하기 전에 앞자리 0과 날짜가 의도한 값인지 확인하고, 글자가 깨지면 고급 설정에서 인코딩을 바꿔 주세요.</p></details>
      </section>
      {error && <div className="error" role="alert">{error}</div>}
      <div role="status" aria-live="polite">{busy ? '파일을 읽고 있습니다. 잠시 기다려 주세요.' : upload ? '업로드가 완료됐습니다.' : ''}</div>
      {upload && <Preview upload={upload} />}
      {upload && <ClaudePreviewApproval upload={upload} csrfToken={csrfToken} onResult={setClaudeResult} />}
      {upload && claudeResult && <ServicePreviewV2 key={`${upload.id}-${claudeResult.model_call_id}`}
        uploadId={upload.id} report={upload.analysis} config={claudeResult.result.preview}
        usedFallback={claudeResult.result.used_fallback} />}
      {upload && <ColumnAnalysis report={upload.analysis} />}
    </main>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>{window.location.pathname.replace(/\/+$/, '') === '/templates' ? <TemplateExamples /> : <App />}</React.StrictMode>,
);
