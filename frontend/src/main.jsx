import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.');
  }
  if (!data) throw new Error('서버 응답을 읽지 못했습니다.');
  return data;
}

function Cell({ value }) {
  if (value === null || value === '') return <span className="empty">빈 값</span>;
  const text = String(value);
  if (text.length > 100) return (
    <details><summary>{text.slice(0, 80)}…</summary><div className="full-value">{text}</div></details>
  );
  return <span className="cell-value">{text}</span>;
}

function Preview({ upload }) {
  const report = upload.analysis;
  return <section className="panel" aria-labelledby="preview-title">
    <div className="section-title"><h2 id="preview-title">표 미리보기</h2><a href={`/api/uploads/${upload.id}/original/`}>원본 다운로드</a></div>
    <p className="filename">{upload.name}</p>
    <dl className="metrics">
      <div><dt>데이터 행</dt><dd>{report.row_count.toLocaleString()}</dd></div>
      <div><dt>컬럼</dt><dd>{report.column_count}</dd></div>
      <div><dt>읽기 인코딩</dt><dd>{upload.encoding === 'utf-8-sig' ? 'UTF-8' : upload.encoding.toUpperCase()}</dd></div>
    </dl>
    {report.warnings.length > 0 && <aside className="notice"><ul>{report.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></aside>}
    <p className="muted">전체 중 앞 {report.preview.length}행입니다. 컬럼명은 0행, 첫 데이터는 1행으로 표시합니다. 긴 값은 눌러서 펼칠 수 있어요.</p>
    <div className="table-scroll" role="region" aria-label="업로드한 CSV 미리보기" tabIndex={0}>
      <table>
        <thead><tr><th scope="col">0행</th>{report.columns.map((column, index) => <th scope="col" key={column.id}><small>{index + 1}열</small>{column.label}</th>)}</tr></thead>
        <tbody>{report.preview.map((row) => <tr key={row.row_number}><th scope="row">{row.row_number - 1}</th>{row.values.map((value, index) => <td key={index}><Cell value={value} /></td>)}</tr>)}</tbody>
      </table>
    </div>
    {!report.row_count && <p>컬럼명만 있고 데이터 행은 없습니다.</p>}
  </section>;
}

const typeLabels = {
  text: '텍스트', number: '숫자', date: '날짜', datetime: '날짜·시간',
  time: '시간', boolean: '참·거짓', formula: '수식 형태', mixed: '혼합', unknown: '판단 불가',
};
const percent = (value) => `${(value * 100).toFixed(1)}%`;

function ColumnAnalysis({ report }) {
  return <section className="panel" aria-labelledby="analysis-title">
    <h2 id="analysis-title">컬럼별 기본 분석</h2>
    <p className="muted">미리보기 20행이 아닌 전체 데이터 {report.row_count.toLocaleString()}행을 분석한 결과입니다. 타입은 값 형식에 따른 후보이며 원본 값은 변환하지 않습니다.</p>
    <details className="help analysis-help"><summary>통계 읽는 방법</summary>
      <ul>
        <li>결측: 빈 값이나 공백만 있는 셀의 수와 비율입니다. 완전히 빈 데이터 행은 분석에서 제외합니다.</li>
        <li>고유값: 결측을 제외한 서로 다른 값의 개수입니다. 원본 문자열 기준으로 구분합니다.</li>
        <li>숫자·날짜 비율: 비어 있지 않은 값 중 해당 형식으로 읽을 수 있는 비율입니다. 날짜는 현재 지원하는 ISO 형식 기준입니다.</li>
        <li>—: 계산할 데이터가 없습니다. 타입 후보만으로 컬럼의 의미나 업무 규칙을 확정하지 않습니다.</li>
      </ul>
    </details>
    <div className="table-scroll" role="region" aria-label="컬럼별 기본 분석 결과" tabIndex={0}>
      <table className="analysis-table">
        <thead><tr>{['컬럼', '타입 후보', '결측 수·비율', '고유값 수', '숫자 비율', '날짜 비율', '값 형식·확인 사항'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{report.columns.map((column, index) => <tr key={column.id}>
          <th scope="row"><small>{index + 1}열</small>{column.label}</th>
          <td><span className={`type-badge ${column.candidate === 'mixed' ? 'type-mixed' : ''}`}>{typeLabels[column.candidate] || column.candidate}</span></td>
          <td>{column.missing_count.toLocaleString()}개<small>{report.row_count ? percent(column.missing_ratio) : '—'}</small></td>
          <td>{column.unique_count.toLocaleString()}개</td>
          <td>{column.non_empty_count ? percent(column.number_ratio) : '—'}</td>
          <td>{column.non_empty_count ? percent(column.date_ratio) : '—'}</td>
          <td><div className="muted">{Object.entries(column.type_counts).map(([kind, count]) => `${typeLabels[kind] || kind} ${count.toLocaleString()}개`).join(' · ') || '비어 있는 컬럼'}</div>
            {column.issues.length > 0 && <ul className="column-issues">{column.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>}
          </td>
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}

function App() {
  const [file, setFile] = useState(null);
  const [encoding, setEncoding] = useState('auto');
  const [allowReplacement, setAllowReplacement] = useState(false);
  const [upload, setUpload] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (!file || busy) return;
    setError('');
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('CSV 파일을 선택해 주세요.'); return; }
    if (!file.size || file.size > 10 * 1024 * 1024) { setError('파일은 0바이트보다 크고 10MB 이하여야 합니다.'); return; }
    setBusy(true); setUpload(null);
    try {
      const { csrf_token } = await api('/api/session/');
      const body = new FormData();
      body.append('file', file); body.append('encoding', encoding);
      body.append('allow_replacement', String(allowReplacement));
      setUpload(await api('/api/uploads/', { method: 'POST', body, headers: { 'X-CSRFToken': csrf_token } }));
    } catch (err) {
      setError(err instanceof TypeError ? '서버에 연결하지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.' : err.message);
    } finally { setBusy(false); }
  }

  return (
    <main>
      <header><p className="eyebrow">Sheet2Service</p><h1>표에서 시작하는 웹 서비스</h1><p>CSV를 올리고 데이터가 올바르게 읽히는지 먼저 확인하세요.</p></header>
      <section className="panel" aria-labelledby="upload-title">
        <h2 id="upload-title">CSV 파일 업로드</h2>
        <p className="muted">첫 행은 컬럼명, 이후 행은 레코드인 쉼표 구분 CSV를 올려주세요.</p>
        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            <label className="file-label">파일 선택<input type="file" accept=".csv,text/csv" required onChange={(event) => { setFile(event.target.files[0] || null); setUpload(null); setError(''); }} /></label>
            <button type="submit" disabled={!file}>{busy ? '읽는 중…' : '업로드하고 확인'}</button>
            <details className="advanced"><summary>고급 설정</summary>
              <label>문자 인코딩<select value={encoding} onChange={(event) => { setEncoding(event.target.value); setAllowReplacement(false); setUpload(null); setError(''); }}>
                <option value="auto">자동 (권장)</option><option value="utf-8-sig">UTF-8 / UTF-8 BOM</option><option value="euc-kr">EUC-KR</option><option value="cp949">CP949 (확장 EUC-KR)</option>
              </select></label>
              {encoding !== 'auto' && <label><span><input type="checkbox" checked={allowReplacement} onChange={(event) => { setAllowReplacement(event.target.checked); setUpload(null); }} /> 읽을 수 없는 문자 대체</span><small>해석 불가 문자를 �로 표시합니다. 원본은 유지됩니다.</small></label>}
            </details>
          </fieldset>
        </form>
        <p className="muted">최대 10MB · 50,000행 · 200열 · 500,000셀. 원본 파일은 그대로 보관합니다.</p>
        <p className="muted">문자 인코딩은 자동으로 선택합니다. 일부 읽을 수 없는 문자는 �로 표시하고 결과에 안내합니다.</p>
        <details className="help"><summary>Excel에서 내보내거나 한글이 깨질 때</summary><p>Excel에서 CSV UTF-8로 저장해 주세요. 내보내기 전에 앞자리 0과 날짜가 의도한 값인지 확인하세요. 한글이 깨지면 고급 설정에서 문자 인코딩을 변경할 수 있어요.</p></details>
      </section>
      {error && <div className="error" role="alert">{error}</div>}
      <div role="status" aria-live="polite">{busy ? '파일을 읽고 있어요. 잠시 기다려 주세요.' : upload ? '업로드가 완료되었습니다.' : ''}</div>
      {upload && <Preview upload={upload} />}
      {upload && <ColumnAnalysis report={upload.analysis} />}
    </main>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>,
);
