import React, { useEffect, useRef, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { ACTOR_KINDS, BASES, CONFIDENCE, KINDS, ROLES, STATE_KINDS } from './labels';
import './understanding.css';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다. 다시 시도해 주세요.');
  if (!data) throw new Error('서버 응답을 읽지 못했습니다.');
  return data;
}

function columnName(columns, number) {
  const column = columns[number - 1];
  return column?.label || column?.name || `열 ${number}`;
}

// One plain sentence per flow: what moves, and in which columns.
function flowSentence(process, columns) {
  const names = process.columns.map((number) => columnName(columns, number));
  switch (process.basis) {
    case 'status_column': return `${names[0]} 값이 바뀌며 진행됩니다.`;
    case 'milestone_dates': return `${names.join(' → ')} 순서로 날짜가 채워지며 진행됩니다.`;
    case 'flag_and_dates': return `${names[0]}이(가) 표시되면 ${names.slice(1).join(', ') || '관련 항목'}이(가) 함께 채워집니다.`;
    case 'amount_balance': return `${names.join(', ')}에서 수량·금액이 늘고 줄며 쌓입니다.`;
    default: return '데이터 근거 없이 의미로만 추정한 흐름입니다.';
  }
}

function Flow({ index, process, columns, processes, actors, busy, onFlag }) {
  const previous = processes.find((item) => item.id === process.after);
  const actorLabel = (id) => actors.find((actor) => actor.id === id)?.label || id;
  const tone = process.excluded ? 'excluded' : process.confirmed ? 'confirmed' : process.confidence || 'medium';
  return <article className={`u-flow u-flow-${tone}`} aria-labelledby={`flow-${process.id}`}>
    <div className="u-flow-head">
      <span className="u-flow-index" aria-hidden="true">{index + 1}</span>
      <div className="u-flow-title">
        <h3 id={`flow-${process.id}`}>{process.title}</h3>
        <p>{flowSentence(process, columns)}{previous && <> <strong>{previous.title}</strong>이(가) 끝난 뒤에 진행됩니다.</>}</p>
      </div>
      <div className="u-flow-side">
        {process.excluded ? <span className="u-pill u-pill-muted">제외됨</span>
          : process.confirmed ? <span className="u-pill u-pill-ok">확인함</span>
          : <span className={`u-pill u-pill-${process.confidence || 'medium'}`}>확신 {CONFIDENCE[process.confidence] || '보통'}</span>}
        <div className="u-flow-actions">
          {!process.excluded && !process.confirmed && <button type="button" disabled={busy} onClick={() => onFlag(process.id, { confirmed: true })}>맞아요</button>}
          <button type="button" className="u-ghost" disabled={busy} onClick={() => onFlag(process.id, { excluded: !process.excluded })}>{process.excluded ? '다시 포함' : '제외'}</button>
        </div>
      </div>
    </div>
    {process.states.length > 0 && <ol className="u-steps" aria-label="상태 순서">
      {process.states.map((state) => <li key={state.value} className={`u-step u-step-${state.kind}`}>
        <span>{state.value || '—'}</span><small>{STATE_KINDS[state.kind] || state.kind}</small></li>)}
    </ol>}
    <details className="u-details">
      <summary>근거와 상태 변경 {process.transitions.length > 0 && `(${process.transitions.length}가지)`}</summary>
      <p className="u-evidence">{process.evidence || '근거 설명이 없습니다.'}</p>
      <p className="u-columns">관여 컬럼: {process.columns.map((number) => <span key={number} className="u-chip">{number}. {columnName(columns, number)}</span>)}</p>
      {process.transitions.length > 0 && <ul className="u-transitions">
        {process.transitions.map((step, index) => <li key={index}>{step.from} → {step.to}{step.actor && <span className="muted"> · {actorLabel(step.actor)}</span>}</li>)}
      </ul>}
    </details>
  </article>;
}

function Answer({ index, value, busy, onSave }) {
  const [text, setText] = useState(value || '');
  useEffect(() => { setText(value || ''); }, [value]);
  const dirty = text.trim() !== (value || '');
  return <form className="u-answer" onSubmit={(event) => { event.preventDefault(); if (dirty && text.trim()) onSave(text); }}>
    <label><span className="visually-hidden">질문 {index + 1} 답변</span>
      <textarea rows={2} maxLength={300} value={text} disabled={busy} placeholder="답을 적어 두면 서비스 생성에 반영됩니다."
        onChange={(event) => setText(event.target.value)} /></label>
    <button type="submit" className="u-ghost" disabled={busy || !dirty || !text.trim()}>{value ? '수정' : '저장'}</button>
  </form>;
}

function Derived({ derived, columns }) {
  // The service the effective understanding produces; the server recomputes it on every read.
  const name = (number) => columnName(columns, number);
  const list = (numbers) => numbers.length ? numbers.map(name).join(', ') : '없음';
  const catalog = derived.blueprint.catalog;
  return <section className="panel u-section" id="u-derived" aria-labelledby="u-derived-title">
    <div className="u-section-head"><span className="u-section-step">5</span><h2 id="u-derived-title">이렇게 서비스가 만들어집니다</h2>
      <p>아래 내용을 고치면 여기도 바로 바뀝니다.</p></div>
    <div className="u-derived-grid">
      <div className="u-derived-card"><h3><SectionIcon name="user" />사용자 화면</h3>
        <dl><div><dt>제목</dt><dd>{name(catalog.titleColumn)}</dd></div>
          <div><dt>목록에 보이는 항목</dt><dd>{list(catalog.visibleColumns.slice(0, 6))}{catalog.visibleColumns.length > 6 && ` 외 ${catalog.visibleColumns.length - 6}개`}</dd></div>
          <div><dt>검색·필터</dt><dd>{list(catalog.searchColumns.slice(0, 4))} / {list(catalog.filterColumns)}</dd></div>
          {derived.createForm && <div><dt>새 건 접수 폼</dt><dd>{list(derived.createForm.columns)}</dd></div>}</dl></div>
      <div className="u-derived-card"><h3><SectionIcon name="admin" />관리자 화면</h3>
        {derived.rowWorkflows.length === 0 && <p className="muted">행의 상태를 바꾸는 흐름이 없어 데이터 관리만 제공합니다.</p>}
        <ul className="u-derived-flows">{derived.rowWorkflows.map((flow) => <li key={flow.id}>
          <strong>{flow.title}</strong>
          <span>{flow.basis === 'status_column' ? `${name(flow.statusColumn)} 값을 버튼으로 바꿉니다`
            : flow.basis === 'milestone_dates' ? `${flow.dateColumns.map(name).join(' → ')} 날짜를 기록합니다`
            : `${name(flow.flagColumn)}을(를) "${flow.doneValue}"로 표시합니다`}</span>
          <small>{[flow.ownerColumn && `담당자 ${name(flow.ownerColumn)}`, flow.dueColumn && `기한 ${name(flow.dueColumn)}`,
            flow.closedColumn && `종료일 자동 기록`, flow.resultColumn && `결과 입력`].filter(Boolean).join(' · ')}</small>
        </li>)}</ul></div>
      <div className="u-derived-card"><h3><SectionIcon name="dashboard" />대시보드</h3>
        <p>{catalog.charts.length ? `${list(catalog.charts.map((chart) => chart.groupColumn))}별 건수 차트` : '집계할 분류 컬럼이 없어 비워 둡니다.'}</p>
        {catalog.sort && <p className="muted">목록 기본 정렬: {name(catalog.sort.column)} {catalog.sort.direction === 'desc' ? '최신순' : '오름차순'}</p>}</div>
    </div>
    {derived.notes.length > 0 && <details className="u-details"><summary>도출 메모 {derived.notes.length}개</summary><ul>{derived.notes.map((note, index) => <li key={index}>{note}</li>)}</ul></details>}
  </section>;
}

export default function UnderstandingPage({ uploadId }) {
  const [upload, setUpload] = useState(null);
  const [result, setResult] = useState(null);
  const [csrfToken, setCsrfToken] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState(null);
  const [onlyUnsure, setOnlyUnsure] = useState(false);
  const running = useRef(false);

  useEffect(() => {
    let active = true;
    Promise.all([api(`/api/uploads/${uploadId}/`), api(`/api/uploads/${uploadId}/understanding/`), api('/api/session/')])
      .then(([data, understanding, session]) => {
        if (!active) return;
        setUpload(data); setResult(understanding); setCsrfToken(session.csrf_token);
      })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId]);

  async function call(work) {
    if (busy || running.current) return;
    running.current = true; setBusy(true); setError('');
    try { await work(); } catch (caught) {
      setError(caught instanceof TypeError ? '서버에 연결할 수 없습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.' : caught.message);
    } finally { running.current = false; setBusy(false); }
  }
  const headers = { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken };
  const understand = (regenerate) => call(async () => {
    const approval = await api(`/api/uploads/${uploadId}/understanding/approval/`);
    setSummary(approval);
    setResult(await api(`/api/uploads/${uploadId}/understanding/`, { method: 'POST', headers,
      body: JSON.stringify({ approved: true, regenerate, request_fingerprint: approval.request_fingerprint,
        approval_note: `시트 이해 화면의 ${regenerate ? '다시 이해하기' : '시트 이해하기'} 버튼으로 ${approval.model} 1회 호출 승인` }) }));
  });
  // Deterministic: the server derives the service from the effective understanding. No model call.
  const applyUnderstanding = () => call(async () => {
    await api(`/api/uploads/${uploadId}/understanding/apply/`, { method: 'POST', headers, body: '{}' });
    window.location.assign(`/${uploadId}/User`);
  });
  // The user's corrections overlay the model's reading on the server; no model call.
  const save = (patch) => call(async () => {
    setResult(await api(`/api/uploads/${uploadId}/understanding/`, { method: 'PATCH', headers, body: JSON.stringify(patch) }));
  });

  const understanding = result?.understanding;
  const columns = upload?.analysis?.columns || [];
  const edited = result?.overrides && Object.keys(result.overrides).length > 0;
  const unsure = understanding ? understanding.columnConfidence.filter((level) => level !== 'high').length : 0;
  const answered = understanding ? understanding.questions.filter((question) => question.answer).length : 0;
  const activeFlows = understanding ? understanding.processes.filter((process) => !process.excluded).length : 0;
  const rowsShown = understanding ? columns.map((column, index) => ({ column, index }))
    .filter(({ index }) => !onlyUnsure || understanding.columnConfidence[index] !== 'high') : [];

  return <main className="select-page understanding-page">
    <header className="upload-header"><h1>Sheet2Service</h1></header>
    <div className="selection-toolbar">
      <a className="selection-back" href="/">← 파일 업로드로 돌아가기</a>
      {upload && <a className="selection-file-name" href={`/api/uploads/${uploadId}/original/`} download>{upload.name}</a>}
    </div>
    {error && <div className="error" role="alert">{error}</div>}
    {!upload && !error && <div className="selection-loading" role="status"><span className="loading-spinner" aria-hidden="true" /><span className="visually-hidden">불러오는 중입니다.</span></div>}

    {upload && !understanding && <section className="panel u-empty">
      <h2>이 시트가 무엇인지 먼저 읽어 봅니다</h2>
      <p>파일 이름, 컬럼 분석과 예시 행 10개, 컬럼 간 운영 신호를 보내 이 시트가 무엇이고 어떻게 운영되는지 묻습니다. 원본 파일 전체는 보내지 않습니다.</p>
      <p className="muted">버튼을 누르면 Claude API를 1회 호출하며 자동 재시도하지 않습니다.</p>
      <button type="button" disabled={busy || !csrfToken} onClick={() => understand(false)}>{busy ? '이해하는 중…' : '시트 이해하기 · Claude 1회'}</button>
    </section>}

    {understanding && <>
      <section className="panel u-hero" aria-labelledby="u-hero-title">
        <p className="u-eyebrow">AI가 읽은 이 시트</p>
        <h2 id="u-hero-title">{understanding.subject || upload.name}</h2>
        <p className="u-purpose">{understanding.purpose}</p>
        <div className="u-hero-meta">
          <label className="u-kind"><span>종류</span>
            <select value={understanding.kind} disabled={busy} onChange={(event) => save({ kind: event.target.value })}>
              {Object.entries(KINDS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select></label>
          {understanding.actors.length > 0 && <div className="u-actors"><span>관련된 사람</span>
            {understanding.actors.map((actor) => <span key={actor.id} className="u-chip">{actor.label} <small>{ACTOR_KINDS[actor.kind] || actor.kind}</small></span>)}</div>}
        </div>
        <ol className="u-lifecycle" aria-label="행의 생애">
          <li><span>행이 생길 때</span><p>{understanding.lifecycle.rowCreated || '-'}</p></li>
          <li><span>행이 바뀔 때</span><p>{understanding.lifecycle.rowUpdated || '-'}</p></li>
          <li><span>행이 끝날 때</span><p>{understanding.lifecycle.rowClosed || '-'}</p></li>
        </ol>
        <nav className="u-glance" aria-label="한눈에 보기">
          <a href="#u-flows"><strong>{activeFlows}</strong> 업무 흐름</a>
          <a href="#u-columns"><strong>{columns.length - unsure}/{columns.length}</strong> 컬럼 역할 확신 높음</a>
          <a href="#u-questions"><strong>{answered}/{understanding.questions.length}</strong> 질문 답변</a>
          {edited && <button type="button" className="u-ghost" disabled={busy} onClick={() => save({ reset: true })}>모델 결과로 되돌리기</button>}
          {result.notes?.length > 0 && <span className="muted">서버가 조정한 항목 {result.notes.length}개</span>}
        </nav>
      </section>

      <section className="panel u-section" id="u-flows" aria-labelledby="u-flows-title">
        <div className="u-section-head"><span className="u-section-step">2</span><h2 id="u-flows-title">업무 흐름</h2>
          <p>시트 안에서 상태가 바뀌는 일들입니다. 맞으면 "맞아요", 아니면 "제외"를 눌러 주세요.</p></div>
        {understanding.processes.length === 0 && <p className="muted">상태가 바뀌는 흐름을 찾지 못했습니다. 조회·안내용 목록으로 보입니다.</p>}
        <div className="u-flows">
          {understanding.processes.map((process, index) => <Flow key={process.id} index={index} process={process} columns={columns}
            processes={understanding.processes} actors={understanding.actors} busy={busy} onFlag={(id, flags) => save({ processes: { [id]: flags } })} />)}
        </div>
      </section>

      <section className="panel u-section" id="u-columns" aria-labelledby="u-columns-title">
        <div className="u-section-head"><span className="u-section-step">3</span><h2 id="u-columns-title">컬럼 역할</h2>
          <p>각 컬럼이 서비스에서 어떤 뜻인지입니다. 틀린 것은 바로 고칠 수 있습니다.</p>
          <label className="u-toggle"><input type="checkbox" checked={onlyUnsure} onChange={(event) => setOnlyUnsure(event.target.checked)} /> 확신 낮은 것만 보기 ({unsure})</label></div>
        <table className="u-table">
          <thead><tr><th scope="col">#</th><th scope="col">컬럼</th><th scope="col">역할</th><th scope="col">근거</th></tr></thead>
          <tbody>{rowsShown.map(({ column, index }) => {
            const level = understanding.columnConfidence[index];
            return <tr key={column.id} className={`u-level-${level}`}>
              <td className="u-num">{index + 1}</td>
              <th scope="row">{column.label}</th>
              <td><select className="u-role" value={understanding.columnRoles[index]} disabled={busy} aria-label={`${column.label} 역할`}
                onChange={(event) => save({ columnRoles: { [index + 1]: event.target.value } })}>
                {Object.entries(ROLES).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
              </select>{level !== 'high' && <span className={`u-pill u-pill-${level}`}>{CONFIDENCE[level]}</span>}</td>
              <td className="u-why">{understanding.columnEvidence[index]}</td>
            </tr>;
          })}</tbody>
        </table>
        {onlyUnsure && !rowsShown.length && <p className="muted">확신이 낮은 컬럼이 없습니다.</p>}
      </section>

      {(understanding.questions.length > 0 || result.notes?.length > 0) && <section className="panel u-section" id="u-questions" aria-labelledby="u-questions-title">
        <div className="u-section-head"><span className="u-section-step">4</span><h2 id="u-questions-title">확인이 필요한 것</h2>
          <p>답하지 않아도 서비스는 만들어집니다. 답하면 더 정확해집니다.</p></div>
        <ol className="u-questions">{understanding.questions.map((question, index) => <li key={index}>
          <details className="u-details" open={!question.answer && index === 0}>
            <summary>{question.column > 0 && <span className="u-chip">{columnName(columns, question.column)}</span>}{question.text}
              {question.answer && <span className="u-pill u-pill-ok">답변함</span>}</summary>
            <Answer index={index} value={question.answer} busy={busy} onSave={(text) => save({ answers: { [index]: text } })} />
          </details>
        </li>)}</ol>
        {result.notes?.length > 0 && <details className="u-details"><summary>서버가 조정한 항목 {result.notes.length}개</summary><ul>{result.notes.map((note, index) => <li key={index}>{note}</li>)}</ul></details>}
      </section>}

      {result.derived && <Derived derived={result.derived} columns={columns} />}

      <div className="u-actionbar" role="region" aria-label="다음 단계">
        <div className="u-actionbar-inner">
          <span className="muted">{summary ? `마지막 호출 ${summary.model}` : '고친 내용은 자동으로 저장됩니다'}</span>
          <div>
            <button type="button" className="u-ghost" disabled={busy} onClick={() => understand(true)}>다시 이해하기 · Claude 1회</button>
            <button type="button" className="u-primary" disabled={busy} onClick={applyUnderstanding}>{busy ? '처리 중…' : '이해대로 서비스 만들기'}</button>
          </div>
        </div>
      </div>
    </>}
  </main>;
}
