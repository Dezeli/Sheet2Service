import React, { useEffect, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';

export default function DisableChoiceDialog({ uploadId, column, choice, busy, error, onClearError, onUpdate, onClose }) {
  const [detail, setDetail] = useState(null);
  const [options, setOptions] = useState([]);
  const [replacement, setReplacement] = useState('');
  const [loadError, setLoadError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setLoadError(''); setReplacement('');
    async function get(path) {
      const response = await fetch(`/api/uploads/${uploadId}/${path}`, { credentials: 'same-origin', signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '사용 정보를 불러오지 못했습니다.');
      return data;
    }
    Promise.all([get(`choices/${choice.id}/`), get(`choices/?column=${column}`)])
      .then(([item, list]) => { if (!controller.signal.aborted) { setDetail(item); setOptions(list.choices.filter((candidate) => candidate.active && candidate.id !== choice.id)); } })
      .catch((caught) => { if (!controller.signal.aborted) setLoadError(caught.message); });
    return () => controller.abort();
  }, [uploadId, column, choice.id, retry]);
  const target = options.find((item) => item.id === replacement);
  return <ServiceDialog title="선택지 사용 중지" className="choice-disable-dialog" busy={busy} error={loadError || error} onClose={onClose}>
    <div className="delete-target"><p>{detail?.value || choice.value}</p></div>
    {!detail && !loadError && <p className="muted" role="status">사용 건수를 확인하고 있습니다.</p>}
    {detail && (detail.usage_count ? <>
      <p><strong>{detail.usage_count.toLocaleString()}개 데이터</strong>에서 사용 중입니다.</p>
      <label>대체 선택지<select aria-label="대체 선택지" disabled={busy} value={replacement} onChange={(event) => setReplacement(event.target.value)}>
        <option value="">선택해 주세요</option>{options.map((item) => <option key={item.id} value={item.id}>{item.value}</option>)}
      </select></label>
      {!options.length && <p className="muted">같은 필드에 활성 선택지를 추가한 후 중지할 수 있습니다.</p>}
      {target && <div className="choice-replacement-summary"><p>{detail.value} → {target.value}</p><span className="muted">{detail.usage_count.toLocaleString()}개 데이터의 값을 변경한 후 기존 선택지를 중지합니다.</span></div>}
    </> : <p className="muted">사용 중인 데이터가 없어 바로 중지할 수 있습니다.</p>)}
    {(loadError || error) && <button type="button" className="service-back-button" disabled={busy} onClick={() => { onClearError(); setRetry((current) => current + 1); }}>다시 확인</button>}
    <div className="dialog-form-actions"><button type="button" className="service-back-button" disabled={busy} onClick={onClose}>취소</button>
      <button type="button" data-intent="danger" disabled={busy || !detail || !!loadError || (detail.usage_count > 0 && !target)} onClick={async () => {
        if (await onUpdate(choice, { active: false, expected_usage: detail.usage_count, expected_value: detail.value,
          ...(target ? { replacement_id: target.id, replacement_value: target.value } : {}) })) onClose();
      }}>{busy ? '적용 중…' : detail?.usage_count ? '변경하고 중지' : '사용 중지'}</button>
    </div>
  </ServiceDialog>;
}
