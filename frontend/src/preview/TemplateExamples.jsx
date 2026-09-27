import React from 'react';
import { templates } from './config';
import { exampleColumns, exampleConfig, exampleRecords } from './examples';
import { PreviewRuntime } from './ServicePreview';

const descriptions = {
  cards: '항목을 카드로 보여주고 상세 화면으로 이동합니다.',
  detail: '선택한 항목의 여러 필드와 연락처를 보여줍니다.',
  table: '여러 항목과 열을 한눈에 비교합니다.',
  grouped: '같은 분류의 항목을 묶어서 보여줍니다.',
  map: '위치 정보를 지도에 표시할 예정입니다.',
  calendar: '날짜가 있는 항목을 달력에 표시할 예정입니다.',
  form: '데이터 입력 화면으로 사용할 예정입니다.',
};

export default function TemplateExamples() {
  return <main>
    <header>
      <p className="eyebrow">Sheet2Service</p>
      <h1>서비스 템플릿 예시</h1>
      <p>전체 7개 템플릿 중 4개를 사용할 수 있습니다. 아래 화면은 가상 데이터로 만든 예시이며, 업로드한 CSV와 연결되지 않습니다.</p>
      <a href="/">CSV 업로드로 돌아가기</a>
    </header>
    <section className="panel" aria-labelledby="template-catalog-title">
      <h2 id="template-catalog-title">템플릿 목록</h2>
      <div className="template-catalog">{Object.entries(templates).map(([id, template]) => <article className="template-catalog-item" key={id}>
        <div className="section-title"><h3>{template.label}</h3><span className={template.ready ? 'template-ready' : 'template-planned'}>{template.ready ? '사용 가능' : '준비 중'}</span></div>
        <p className="muted">{descriptions[id]}</p>
      </article>)}</div>
    </section>
    <section className="panel" aria-labelledby="template-demo-title">
      <h2 id="template-demo-title">사용 가능한 템플릿 체험</h2>
      <p className="muted">카드 제목을 누르면 상세 화면을 볼 수 있습니다. 상단에서 표 목록과 그룹 목록도 선택할 수 있습니다.</p>
      <PreviewRuntime config={exampleConfig} columns={exampleColumns} records={exampleRecords} />
    </section>
  </main>;
}
