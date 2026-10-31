import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query } from './api.js';

const emptyForm = { name: '', capacity: '', attributes: [] };

/** Register, rename, describe, deactivate and delete the things people reserve. */
export default function ResourceAdmin({ uploadId, service, persona, csrf }) {
  const [trail, setTrail] = useState([]);
  const [list, setList] = useState({ resources: [], page: 1, count: 0, has_next: false });
  const [search, setSearch] = useState('');
  const [applied, setApplied] = useState('');
  const [editor, setEditor] = useState(null); // { id?, parent?, form }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const levels = service.resources.levels;
  const parent = trail[trail.length - 1];

  async function load(page = 1, at = parent, q = applied) {
    try {
      setList(await api(`/api/uploads/${uploadId}/resources/${query({ page, all: 1, q, parent: q ? '' : at?.id })}`));
      setError('');
    } catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(1, undefined, ''); }, [uploadId]);

  function go(next) { setTrail(next); setApplied(''); setSearch(''); load(1, next[next.length - 1], ''); }

  function openEditor(resource = null) {
    setError(''); setMessage('');
    setEditor(resource
      ? { id: resource.id, form: { name: resource.name, capacity: resource.capacity ?? '', attributes: Object.entries(resource.attributes || {}).map(([key, value]) => ({ key, value })) } }
      : { parent, form: { ...emptyForm, attributes: [] } });
  }

  async function save(event) {
    event.preventDefault();
    if (busy || !csrf) return;
    setBusy(true); setError('');
    const attributes = Object.fromEntries(editor.form.attributes.filter((item) => item.key.trim()).map((item) => [item.key.trim(), item.value]));
    const body = { persona: persona.id, name: editor.form.name.trim(), capacity: editor.form.capacity === '' ? null : Number(editor.form.capacity), attributes };
    try {
      if (editor.id) await api(`/api/uploads/${uploadId}/resources/${editor.id}/`, jsonOptions('PATCH', csrf, body));
      else await api(`/api/uploads/${uploadId}/resources/`, jsonOptions('POST', csrf, { ...body, parent_id: editor.parent?.id }));
      setMessage(editor.id ? '항목을 수정했습니다.' : '항목을 등록했습니다.');
      setEditor(null); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function toggleActive(resource) {
    if (busy || !csrf) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/resources/${resource.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, active: !resource.active }));
      setMessage(resource.active ? '사용 중지했습니다. 예약자에게 보이지 않습니다.' : '다시 사용합니다.'); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function remove(resource) {
    if (busy || !csrf || !window.confirm(`"${resource.name}"을(를) 삭제할까요? 예약 기록이 있으면 삭제 대신 사용 중지됩니다.`)) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await api(`/api/uploads/${uploadId}/resources/${resource.id}/`, jsonOptions('DELETE', csrf, { persona: persona.id }));
      setMessage(result.deleted ? '삭제했습니다.' : result.detail); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  const levelLabel = levels[trail.length] || '항목';
  return <section className="panel">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name="table" />{service.subject} 관리</h2>
      <button type="button" data-intent="primary" disabled={busy || !csrf} onClick={() => openEditor()}>{levelLabel} 추가</button></div>
    <form className="resource-search" onSubmit={(event) => { event.preventDefault(); setApplied(search.trim()); load(1, parent, search.trim()); }}>
      <input type="search" aria-label="검색어" placeholder="이름으로 검색" maxLength={100} value={search} onChange={(event) => setSearch(event.target.value)} />
      <button type="submit" disabled={busy}>검색</button>
      {applied && <button type="button" className="service-back-button" onClick={() => go(trail)}>검색 해제</button>}
    </form>
    <nav className="resource-trail" aria-label="위치">
      <button type="button" className="service-back-button" disabled={!trail.length} onClick={() => go([])}>전체</button>
      {trail.map((item, index) => <React.Fragment key={item.id}><span aria-hidden="true">›</span>
        <button type="button" className="service-back-button" onClick={() => go(trail.slice(0, index + 1))}>{item.name}</button></React.Fragment>)}
    </nav>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="table-scroll" role="region" aria-label="항목 목록" tabIndex={0}>
      <table className="resource-table">
        <thead><tr><th scope="col">{applied ? '경로' : levelLabel}</th><th scope="col">하위</th><th scope="col">정원</th><th scope="col">진행 중 예약</th><th scope="col">상태</th><th scope="col">관리</th></tr></thead>
        <tbody>{list.resources.map((item) => <tr key={item.id} className={item.active ? undefined : 'is-inactive'}>
          <td>{item.children_count > 0 && !applied
            ? <button type="button" className="service-title-button" onClick={() => go([...trail, item])}>{item.name}</button>
            : <span>{applied ? item.path : item.name}</span>}</td>
          <td>{item.children_count > 0 ? `${item.children_count}개` : '-'}</td>
          <td>{item.capacity ?? '-'}</td>
          <td>{item.booking_count}</td>
          <td>{item.active ? '사용 중' : '사용 중지'}</td>
          <td><div className="booking-actions">
            <button type="button" data-intent="secondary" disabled={busy} onClick={() => openEditor(item)}>수정</button>
            <button type="button" data-intent="secondary" disabled={busy} onClick={() => toggleActive(item)}>{item.active ? '사용 중지' : '사용 재개'}</button>
            <button type="button" className="admin-danger" disabled={busy} onClick={() => remove(item)}>삭제</button>
          </div></td>
        </tr>)}</tbody>
      </table>
    </div>
    {!list.resources.length && <p className="muted">항목이 없습니다. 위의 추가 버튼으로 등록하세요.</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {list.count > 20 && <nav className="service-pagination" aria-label="항목 페이지">
      <button type="button" disabled={busy || list.page === 1} onClick={() => load(list.page - 1)}>이전</button>
      <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
      <button type="button" disabled={busy || !list.has_next} onClick={() => load(list.page + 1)}>다음</button>
    </nav>}
    {editor && <ServiceDialog title={editor.id ? '항목 수정' : `${levelLabel} 추가`} busy={busy} error={error} onClose={() => setEditor(null)}>
      <form onSubmit={save}><fieldset className="inquiry-form" disabled={busy}>
        {editor.parent && <p className="muted">상위: {editor.parent.path}</p>}
        <label>이름<input type="text" required maxLength={300} value={editor.form.name} onChange={(event) => setEditor({ ...editor, form: { ...editor.form, name: event.target.value } })} /></label>
        <label>정원 (선택, 같은 시간에 받을 예약 수)<input type="number" min={1} max={100000} value={editor.form.capacity} onChange={(event) => setEditor({ ...editor, form: { ...editor.form, capacity: event.target.value } })} /></label>
        <div><span className="field-label">속성 (요금·위치·안내 등)</span>
          {editor.form.attributes.map((item, index) => <div className="attribute-row" key={index}>
            <input type="text" aria-label="속성 이름" placeholder="이름" maxLength={60} value={item.key} onChange={(event) => { const next = [...editor.form.attributes]; next[index] = { ...item, key: event.target.value }; setEditor({ ...editor, form: { ...editor.form, attributes: next } }); }} />
            <input type="text" aria-label="속성 값" placeholder="값" maxLength={500} value={item.value} onChange={(event) => { const next = [...editor.form.attributes]; next[index] = { ...item, value: event.target.value }; setEditor({ ...editor, form: { ...editor.form, attributes: next } }); }} />
            <button type="button" className="service-back-button" onClick={() => setEditor({ ...editor, form: { ...editor.form, attributes: editor.form.attributes.filter((_, i) => i !== index) } })}>삭제</button>
          </div>)}
          <button type="button" className="service-back-button" onClick={() => setEditor({ ...editor, form: { ...editor.form, attributes: [...editor.form.attributes, { key: '', value: '' }] } })}>속성 추가</button>
        </div>
        <div className="admin-row-actions"><button type="submit" data-intent="primary" disabled={busy || !csrf || !editor.form.name.trim()}>저장</button>
          <button type="button" className="service-back-button" onClick={() => setEditor(null)}>취소</button></div>
      </fieldset></form>
    </ServiceDialog>}
  </section>;
}
