import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query } from './api.js';
import { rulesOf } from './rules.js';
import { ItemLink } from './nav';
import { Empty, Icon, IconButton, Pager, SearchField, Stepper } from '../components/ui';

const emptyForm = { name: '', capacity: '', attributes: [] };

/** Register, rename, describe, deactivate and delete the things people reserve. */
export default function ResourceAdmin({ uploadId, service, persona, csrf }) {
  const [trail, setTrail] = useState([]);
  const [list, setList] = useState({ resources: [], page: 1, count: 0, has_next: false });
  const [applied, setApplied] = useState('');
  const [editor, setEditor] = useState(null); // { id?, parent?, form }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const levels = service.resources.levels;
  const rules = rulesOf(service);
  const capacityLabel = rules.capacityBy === 'people' ? '정원' : '같은 시간 최대';
  const parent = trail[trail.length - 1];

  async function load(page = 1, at = parent, q = applied) {
    try {
      setList(await api(`/api/uploads/${uploadId}/resources/${query({ page, all: 1, q, parent: q ? '' : at?.id })}`));
      setError('');
    } catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(1, undefined, ''); }, [uploadId]);

  function go(next) { setTrail(next); setApplied(''); load(1, next[next.length - 1], ''); }

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
  const setForm = (changes) => setEditor({ ...editor, form: { ...editor.form, ...changes } });
  const setAttribute = (index, changes) => setForm({ attributes: editor.form.attributes.map((item, i) => (i === index ? { ...item, ...changes } : item)) });
  return <section className="panel">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name="table" />항목 관리</h2>
      <span className="section-tools"><span className="section-count">{list.count.toLocaleString()}개</span>
        <button type="button" data-intent="primary" className="with-icon" disabled={busy || !csrf} onClick={() => openEditor()}><Icon name="plus" size={16} />{levelLabel} 추가</button></span></div>
    <div className="ui-toolbar">
      <SearchField value={applied} placeholder="이름으로 찾기" onSearch={(text) => { setApplied(text); load(1, parent, text); }} />
    </div>
    {!applied && trail.length > 0 && <nav className="resource-trail" aria-label="위치">
      <IconButton icon="back" label="위로" onClick={() => go(trail.slice(0, -1))} />
      <button type="button" className="crumb" onClick={() => go([])}>전체</button>
      {trail.map((item, index) => <React.Fragment key={item.id}><Icon name="next" size={14} />
        <button type="button" className="crumb" onClick={() => go(trail.slice(0, index + 1))}>{item.name}</button></React.Fragment>)}
    </nav>}
    {error && !editor && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {list.resources.length > 0 && <div className="table-scroll" role="region" aria-label="항목 목록" tabIndex={0}>
      <table className="resource-table">
        <thead><tr><th scope="col">{applied ? '항목' : levelLabel}</th><th scope="col" className="num">{capacityLabel}</th><th scope="col" className="num">진행 중 예약</th>
          <th scope="col"><span className="visually-hidden">관리</span></th></tr></thead>
        <tbody>{list.resources.map((item) => <tr key={item.id} className={item.active ? undefined : 'is-inactive'}>
          <td className="cell-resource">{item.children_count > 0 && !applied
            ? <button type="button" className="service-title-button with-icon" onClick={() => go([...trail, item])}>{item.name}<span className="count-badge">{item.children_count}<Icon name="next" size={12} /></span></button>
            : <ItemLink item={item.id} path={item.path} menu="schedule">{item.name}</ItemLink>}
            {applied && item.path.split(' / ').slice(-2, -1)[0] && item.path.split(' / ').slice(-2, -1)[0] !== item.name && <small className="cell-sub" title={item.path.split(' / ').join(' › ')}>{item.path.split(' / ').slice(-2, -1)[0]}</small>}
            {!item.active && <small className="cell-sub">사용 중지</small>}</td>
          <td className="num">{item.children_count > 0 ? <span className="muted">–</span> : item.capacity ?? <span className="muted">{rules.limit}</span>}</td>
          <td className="num">{item.children_count > 0 ? <span className="muted">–</span> : item.booking_count.toLocaleString()}</td>
          <td className="cell-actions"><div className="ui-actions">
            <IconButton icon="edit" tone="info" label="수정" disabled={busy} onClick={() => openEditor(item)} />
            <IconButton icon={item.active ? 'pause' : 'play'} tone={item.active ? 'warn' : 'approve'} label={item.active ? '사용 중지' : '다시 사용'} disabled={busy} onClick={() => toggleActive(item)} />
            <IconButton icon="trash" tone="danger" label="삭제" disabled={busy} onClick={() => remove(item)} />
          </div></td>
        </tr>)}</tbody>
      </table>
    </div>}
    {!list.resources.length && <Empty>{applied ? '맞는 항목이 없습니다.' : '항목이 없습니다.'}</Empty>}
    <Pager page={list.page} count={list.count} disabled={busy} onPage={(page) => load(page)} />
    {editor && <ServiceDialog title={editor.id ? '항목 수정' : `${levelLabel} 추가`} busy={busy} error={error} onClose={() => setEditor(null)}>
      <form onSubmit={save}><fieldset className="form-grid" disabled={busy}>
        {editor.parent && <p className="muted">{editor.parent.path.split(' / ').join(' › ')}</p>}
        <label>이름<input type="text" required maxLength={300} value={editor.form.name} onChange={(event) => setForm({ name: event.target.value })} /></label>
        <div><span className="field-label">{capacityLabel}</span>
          <div className="setting-control">
            <Stepper label={capacityLabel} min={0} zeroLabel={`기본값 (${rules.limit})`} unit={rules.capacityBy === 'people' ? '명' : '건'}
              value={editor.form.capacity === '' ? 0 : Number(editor.form.capacity)} onChange={(value) => setForm({ capacity: value || '' })} />
          </div></div>
        <div><span className="field-label">안내 정보</span>
          <ul className="attribute-list">{editor.form.attributes.map((item, index) => <li key={index}>
            <input type="text" aria-label="이름" placeholder="예: 요금" maxLength={60} value={item.key} onChange={(event) => setAttribute(index, { key: event.target.value })} />
            <input type="text" aria-label="값" placeholder="예: 10,000원" maxLength={500} value={item.value} onChange={(event) => setAttribute(index, { value: event.target.value })} />
            <IconButton icon="trash" tone="danger" label="삭제" onClick={() => setForm({ attributes: editor.form.attributes.filter((_, i) => i !== index) })} />
          </li>)}</ul>
          <button type="button" className="text-button with-icon" onClick={() => setForm({ attributes: [...editor.form.attributes, { key: '', value: '' }] })}><Icon name="plus" size={16} />정보 추가</button>
        </div>
        <div className="dialog-actions"><button type="submit" disabled={busy || !csrf || !editor.form.name.trim()}>저장</button></div>
      </fieldset></form>
    </ServiceDialog>}
  </section>;
}
