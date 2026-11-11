import React from 'react';

/*
  Sheet2Service landing (taste-skill 2.5.1, kind software).
  deal: hero centred, nav nav-mega, close close-word, footer footer-columns, rhythm space (+ one ground-surface
  section the moment needs), buttons arrow, mark wordmark, ground sage, palette cool-white-slate (the first,
  card-pastels, clashes with the teal wordmark), type instrument (Hangul falls back to Pretendard).
  moments: line-carries-colour on #rules (the rules are where a sheet becomes a service with its own terms).
  Every fact comes from the product: CSV only, 10MB and 50,000 rows, one Claude call per generation, the public
  sample sheets in docs/samples (내장산 국민여가캠핑장). The markup is static: kit scripts own its motion, and the
  upload buttons are wired by UploadFlow through [data-upload].
*/

const Arrow = () => <svg className="m-arrow" viewBox="0 0 12 12" aria-hidden="true"><path className="m-arrow__stem" d="M1 6h8" /><path className="m-arrow__head" d="M4.5 2.5 8 6l-3.5 3.5" /></svg>;
const Chev = () => <svg className="chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Upload = ({ className = 'btn btn--primary', children = 'CSV 올리기' }) => <button type="button" className={className} data-upload>{children}<Arrow /></button>;

// 내장산 국민여가캠핑장 (public data, docs/samples): name, zone, kind, units, weekday price
const SITES = [
  ['이글루A', 'A구역', '이글루', 5, '5만 원'],
  ['일반캠핑A', 'A구역', '일반캠핑', 12, '1.5만 원'],
  ['카라반B', 'B구역', '카라반', 3, '10만 원'],
  ['글램핑C', 'C구역', '글램핑', 6, '11만 원'],
  ['오토캠핑C', 'C구역', '오토캠핑', 23, '2만 원'],
];

function SiteWindow() {
  return <div className="ui ui-panel ui-win" data-ui="window" data-open="신청" data-work="확인 중" data-done="확정">
    <div className="ui-win__bar">
      <span className="ui-dots" aria-hidden="true"><i /><i /><i /></span>
      <span className="ui-win__crumb">내장산 국민여가캠핑장 <i>/</i> <b>시설</b></span>
      <span className="ui-spacer" />
      <span className="ui-win__search" aria-hidden="true"><svg className="ui-icon" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg><span className="ui-win__ph">시설 찾기</span></span>
    </div>
    <div className="ui-win__body">
      <nav className="ui-win__side" aria-hidden="true">
        <span className="ui-win__nav is-on">전체<em>5</em></span>
        <span className="ui-win__nav">A구역<em>2</em></span>
        <span className="ui-win__nav">B구역<em>1</em></span>
        <span className="ui-win__nav">C구역<em>2</em></span>
      </nav>
      <div className="ui-win__main">
        <div className="ui-win__cols" aria-hidden="true"><span>시설</span><span>구역 · 분류</span><span>상태</span><span>평일</span></div>
        <ul className="ui-win__rows">
          {SITES.map(([name, zone, kind, units, price], index) => <li className="ui-win__row" data-row key={name}>
            <span className="ui-avatar" data-tone={(index % 5) + 1}>{name.slice(0, 1)}</span>
            <span className="ui-win__who">{name}</span>
            <span className="ui-win__sub">{zone} · {kind} · {units}동</span>
            <span className={`ui-win__st${index > 2 ? ' is-done' : ''}`} data-st>{index > 2 ? '확정' : '신청'}</span>
            <span className="ui-win__age">{price}</span>
          </li>)}
        </ul>
      </div>
    </div>
  </div>;
}

function StayCalendar() {
  const lead = 6; // 2026-11-01 is a Sunday; the grid starts on Monday
  const cells = [];
  for (let i = 0; i < lead; i += 1) cells.push(<span className="ui-cal__d is-out" key={`o${i}`}><b>{26 + i}</b></span>);
  for (let d = 1; d <= 30; d += 1) {
    const cls = d === 14 ? ' is-start' : d === 15 ? ' is-end' : d === 8 ? ' is-today' : d === 21 || d === 22 ? ' is-mark' : '';
    cells.push(<span className={`ui-cal__d${cls}`} data-d={d} key={d}><b>{d}</b></span>);
  }
  return <div className="ui ui-panel ui-calendar" data-ui="calendar" data-start="14" data-end="15" data-month="11월">
    <div className="ui-cal__head">
      <div className="ui-cal__month">이글루A <span>2026년 11월</span></div>
      <span className="ui-spacer" />
      <span className="ui-chip ui-chip--plain ui-chip--ink" data-cal-range>11월 14 – 15</span>
    </div>
    <div className="ui-cal__dow" aria-hidden="true">{['월', '화', '수', '목', '금', '토', '일'].map((d) => <span key={d}>{d}</span>)}</div>
    <div className="ui-cal__days">{cells}</div>
    <div className="ui-cal__events">
      <div className="ui-cal__ev" data-ev="14"><span className="ui-cal__date"><b>14</b><i>토</i></span>
        <span className="ui-cal__evtext"><span className="ui-cal__evtitle">입실 14:00</span><span className="ui-cal__evsub">이글루A · 5동 중 1동</span></span></div>
      <div className="ui-cal__ev" data-ev="15"><span className="ui-cal__date"><b>15</b><i>일</i></span>
        <span className="ui-cal__evtext"><span className="ui-cal__evtitle">퇴실 11:00</span><span className="ui-cal__evsub">퇴실일 아침에 자리가 비어 다음 예약을 받습니다</span></span></div>
      <div className="ui-cal__ev" data-ev="21"><span className="ui-cal__date"><b>21</b><i>토</i></span>
        <span className="ui-cal__evtext"><span className="ui-cal__evtitle">마감</span><span className="ui-cal__evsub">5동이 모두 예약됨</span></span></div>
    </div>
  </div>;
}

export default function Landing() {
  return <>
    <header className="nav">
      <div className="wrap nav__bar">
        <a className="skip-link" href="#top">본문으로 건너뛰기</a>
        <a className="nav__logo" href="#top">Sheet2Service</a>
        <nav className="nav__links" aria-label="주 메뉴">
          <div className="nav__item">
            <a className="nav__link" href="#screens">화면 <Chev /></a>
            <div className="nav__menu">
              <div className="wrap grid">
                <div className="menu-col span-3">
                  <p className="t-label">예약하는 사람</p>
                  <a href="#screens">예약하기<span>찬 시간은 고를 수 없음</span></a>
                  <a href="#screens">내 예약<span>이름과 전화번호로 조회</span></a>
                  <a href="#screens">문의와 공지<span>항목을 골라 문의</span></a>
                </div>
                <div className="menu-col span-3">
                  <p className="t-label">관리하는 사람</p>
                  <a href="#screens">예약 관리<span>승인, 거절, 취소, 결제</span></a>
                  <a href="#screens">일정표<span>주간 표와 항목별 달력</span></a>
                  <a href="#rules">예약 규칙<span>타임, 정원, 1인 제한</span></a>
                </div>
                <a className="menu-card span-3 start-10" href="#rules">
                  <div className="panel menu-card__panel"><div className="ui lp-chips lp-chips--menu" aria-hidden="true">
                    <span>10:00~11:00</span><span className="is-taken">11:00~12:00</span><span>13:00~14:00</span></div></div>
                  <span className="t-card">관리자가 정하는 타임</span>
                  <span className="t-small muted">찬 타임은 예약 화면에서 꺼집니다</span>
                </a>
              </div>
            </div>
          </div>
          <div className="nav__item"><a className="nav__link" href="#how">만드는 법</a></div>
          <div className="nav__item"><a className="nav__link" href="#rules">예약 규칙</a></div>
          <div className="nav__item"><a className="nav__link" href="#faq">질문</a></div>
        </nav>
        <div className="nav__actions"><Upload /></div>
        <button className="nav__toggle" type="button" aria-expanded="false" aria-label="메뉴">
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M2 5h14M2 13h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
        </button>
      </div>
    </header>

    <main id="top">
      <section className="hero hero--centred" data-enter aria-labelledby="hero-h">
        <div className="wrap"><div className="hero-text">
          <div className="hero__c">
            <a className="pill" href="#faq"><span>CSV 한 장, 10MB · 5만 행까지</span><span className="muted">올릴 수 있는 시트</span></a>
            <h1 id="hero-h">예약 시트를 예약 서비스로 바꾸는 웹 앱</h1>
            <p className="hero__lead">예약 대장, 시설 목록, 회차표 CSV를 올리면 무엇을 누가 예약하는지 읽고 예약자 화면과 관리자 화면을 만듭니다.</p>
            <div className="btn-row"><Upload /><a className="btn btn--secondary" href="#screens">만들어지는 화면 보기</a></div>
          </div>
          <div className="hero__window" role="img" aria-label="캠핑장 시설 목록 CSV를 읽고 예약 서비스를 만드는 Sheet2Service 창">
            <div className="ui ly-piece lw" aria-hidden="true">
              <div className="lw__bar"><span className="lw__dots"><i /><i /><i /></span><span><b>새 서비스</b> · 내장산 국민여가캠핑장 예약정보.csv</span><span className="lw__sp" /><span>CP949 · 9행 · 19열</span></div>
              <div className="lw__body">
                <div className="lw__list">
                  <div className="lw__q">올린 시트</div>
                  <div className="lw__t is-on"><b>국민여가캠핑장 예약정보</b><span>자원 목록 · 시설 5곳</span></div>
                  <div className="lw__t"><b>통합예약시스템 수강신청자</b><span>예약 기록 · 7,414건</span></div>
                  <div className="lw__t"><b>숲해설 프로그램 예약</b><span>회차표</span></div>
                  <div className="lw__t"><b>문화회관 대관 예약</b><span>날짜별 대관표</span></div>
                </div>
                <div className="lw__work" data-ly-steps="900">
                  <div className="lw__file">구역명 · 시설명 · 시설분류 · 시설수 · 이용시작시간 · 이용종료시간 · 평일금액 · 주말금액 …</div>
                  <div className="lw__tool" data-step>Claude가 컬럼 19개와 예시 행을 읽는 중</div>
                  <div className="lw__done" data-step><b>예약 서비스를 만들었습니다</b><span>구역 › 시설 5곳 · 숙박 단위 · 즉시 확정</span></div>
                  <div className="lw__acts" data-step><span>예약자로 보기</span><span>관리자로 보기</span></div>
                </div>
              </div>
            </div>
          </div>
        </div></div>
      </section>

      <section className="section" id="screens" aria-labelledby="screens-h">
        <div className="wrap">
          <div className="grid">
            <h2 id="screens-h" className="span-5">예약자 화면과 관리자 화면</h2>
            <p className="span-6 start-7 lp-intro">시트의 항목이 예약 대상이 됩니다. 이미 찬 날짜와 시간은 고를 수 없고, 관리자는 승인과 취소, 일정표를 한곳에서 봅니다. <a className="link" href="#rules">예약 규칙 보기</a></p>
          </div>
          <div className="ui app fill" role="img" aria-label="캠핑장 시설 목록 옆에 이글루A의 11월 예약 달력이 열린 관리 화면" data-ui-pause-host>
            <div className="app__pane app__pane--list"><SiteWindow /></div>
            <div className="app__pane app__pane--open" data-ui-loop><StayCalendar /></div>
          </div>
        </div>
      </section>

      <section className="section" id="how" style={{ '--hm': 2 }} aria-labelledby="how-h">
        <div className="wrap">
          <div className="section-head"><h2 id="how-h">CSV 한 장에서 서비스까지 3단계</h2></div>
          <div className="grid">
            <article className="card card--row card--open span-4 m-nolift">
              <span className="step-num">1</span>
              <h3>CSV를 올립니다</h3>
              <p>UTF-8과 CP949를 알아서 읽고, 컬럼마다 값의 형식과 종류를 셉니다.</p>
              <div className="panel"><div className="ui lp-cols" aria-hidden="true">
                <div className="lp-cols__file"><b>내장산 국민여가캠핑장 예약정보.csv</b><span>9행 · 19열</span></div>
                {[['구역명', '텍스트 · 3종'], ['시설명', '텍스트 · 9종'], ['시설수', '숫자'], ['이용시작시간', '시간'], ['평일금액', '숫자']].map(([name, kind]) =>
                  <div className="lp-cols__row" key={name}><span>{name}</span><small>{kind}</small></div>)}
              </div></div>
            </article>
            <article className="card card--row card--open span-4 m-nolift">
              <span className="step-num">2</span>
              <h3>Claude가 시트를 한 번 읽습니다</h3>
              <p>컬럼 분석과 예시 행만 보냅니다. 호출은 생성 버튼을 누를 때 한 번입니다.</p>
              <div className="panel"><div className="ui lp-read" aria-hidden="true">
                <div className="lp-read__core"><img src="/kit/icons/claude.svg" alt="" width="28" height="28" loading="lazy" /><b>Claude</b><span>1회 호출</span></div>
                <div className="lp-read__row"><span>예약 대상</span><b>구역 › 시설</b></div>
                <div className="lp-read__row"><span>예약 방식</span><b>숙박 · 즉시 확정</b></div>
                <div className="lp-read__row"><span>역할</span><b>예약자 · 관리자</b></div>
              </div></div>
            </article>
            <article className="card card--row card--open span-4 m-nolift">
              <span className="step-num">3</span>
              <h3>화면이 만들어집니다</h3>
              <p>항목, 회차, 예약 기록을 옮기고 역할마다 메뉴를 만듭니다.</p>
              <div className="panel"><div className="ui lp-site" aria-hidden="true">
                <div className="lp-site__chips"><span className="is-on">A구역 2</span><span>B구역 1</span><span>C구역 2</span></div>
                <div className="lp-site__card"><b>이글루A</b><dl><div><dt>정원</dt><dd>5</dd></div><div><dt>평일금액</dt><dd>50,000원</dd></div></dl><span className="lp-site__btn">예약</span></div>
              </div></div>
            </article>
          </div>
        </div>
      </section>

      <section className="section g2 ground-surface" id="rules" data-moment="line-carries-colour" data-moment-opts='{"from": "base"}' aria-labelledby="rules-h">
        <div className="wrap">
          <div className="group">
            <div className="section-head">
              <h2 id="rules-h">관리자가 정하는 예약 규칙. <span className="muted">서비스 전체나 항목마다 따로 둡니다.</span></h2>
            </div>
            <div className="grid">
              <article className="card card--row card--open span-6 m-nolift">
                <h3>예약 타임을 정합니다</h3>
                <p>운영 시간과 한 타임 길이를 넣으면 10:00~11:00 같은 타임이 한 번에 생깁니다.</p>
                <div className="panel"><div className="ui lp-chips" aria-hidden="true">
                  {['10:00~11:00', '11:00~12:00', '12:00~13:00', '13:00~14:00', '14:00~15:00', '15:00~16:00'].map((label, index) =>
                    <span key={label} className={index === 1 || index === 4 ? 'is-taken' : undefined}>{label}<small>{index === 1 || index === 4 ? '마감' : `${10 - index}명 남음`}</small></span>)}
                </div></div>
              </article>
              <article className="card card--row card--open span-6 m-nolift">
                <h3>같은 시간의 정원을 셉니다</h3>
                <p>회의실처럼 건수로 세거나, 체험교실처럼 예약 인원을 더해 셉니다.</p>
                <div className="panel"><div className="ui lp-setting" aria-hidden="true">
                  <span className="lp-seg"><span>건수</span><span className="is-on">인원</span></span>
                  <span className="lp-step"><i>−</i><b>10</b><small>명</small><i>+</i></span>
                </div></div>
              </article>
            </div>
          </div>
          <div className="grid">
            <article className="card card--row card--open span-6 m-nolift">
              <h3>한 사람의 예약을 제한합니다</h3>
              <p>전화번호가 같으면 같은 사람으로 보고, 하루 1건처럼 막습니다.</p>
              <div className="panel"><div className="ui lp-setting" aria-hidden="true">
                <span className="lp-step"><i>−</i><b>1</b><small>건</small><i>+</i></span>
                <span className="lp-seg"><span className="is-on">하루에</span><span>예약해 둔 것 합쳐서</span></span>
              </div></div>
            </article>
            <article className="card card--row card--open span-6 m-nolift">
              <h3>휴무 요일을 막습니다</h3>
              <p>토요일에만 여는 체험이면 나머지 요일을 휴무로 고릅니다.</p>
              <div className="panel"><div className="ui lp-days" aria-hidden="true">
                {['월', '화', '수', '목', '금', '토', '일'].map((day) => <span key={day} className={day === '토' ? undefined : 'is-off'}>{day}</span>)}
              </div></div>
            </article>
          </div>
        </div>
      </section>

      <section className="section" id="faq" aria-labelledby="faq-h">
        <div className="wrap grid">
          <div className="span-5 lp-faq-head">
            <div className="lp-faq-title"><h2 id="faq-h">자주 묻는 질문</h2><span className="lp-faq-icon"><img src="/kit/icons/ui-file-spreadsheet.svg" alt="CSV 시트" width="24" height="24" loading="lazy" /></span></div>
            <p className="muted">더 궁금한 점은 메일로 보내 주세요.</p>
            <a className="link" href="mailto:firoms@ajou.ac.kr">메일 보내기</a>
          </div>
          <div className="faq span-6 start-7">
            <div className="faq__item"><h3>어떤 파일을 올릴 수 있나요?</h3><p>CSV만 받습니다. 10MB, 5만 행까지이며 Excel 파일은 CSV로 저장해서 올리세요.</p></div>
            <div className="faq__item"><h3>Claude에는 무엇이 전송되나요?</h3><p>컬럼 이름과 형식 분석, 예시 행 몇 개입니다. 전체 데이터는 보내지 않고, 생성할 때 한 번 호출합니다.</p></div>
            <div className="faq__item"><h3>어떤 시트가 맞나요?</h3><p>예약 기록, 시설·자원 목록, 회차표, 날짜별 대관표처럼 무엇을 언제 예약하는지 담긴 시트입니다.</p></div>
            <div className="faq__item"><h3>예약자는 어떻게 구분하나요?</h3><p>이름과 전화번호로 구분합니다. 로그인과 문자 인증은 아직 없습니다.</p></div>
            <div className="faq__item"><h3>원본 시트는 어떻게 되나요?</h3><p>원본 CSV는 그대로 보관되고 관리자 화면에서 언제든 내려받을 수 있습니다.</p></div>
          </div>
          <div className="panel span-12 lp-limit-panel"><div className="ui lp-limit" aria-hidden="true">
            <div className="lp-limit__file"><img src="/kit/icons/ui-file-spreadsheet.svg" alt="" width="28" height="28" loading="lazy" /><b>올릴 수 있는 시트</b></div>
            <div className="lp-limit__row"><span>형식</span><b>CSV</b></div>
            <div className="lp-limit__row"><span>크기</span><b>10MB까지</b></div>
            <div className="lp-limit__row"><span>행</span><b>5만 행까지</b></div>
            <div className="lp-limit__row"><span>인코딩</span><b>UTF-8 · CP949 자동</b></div>
          </div></div>
        </div>
      </section>
    </main>

    <footer className="footer closing" id="contact" aria-labelledby="close-h">
      <div className="wrap">
        <div className="closing__cta close--word">
          <div className="section-head--split">
            <div><h2 id="close-h">예약 시트로 서비스 만들기</h2><p className="t-lead">CSV를 올리고 생성 버튼을 누르면 Claude를 한 번 호출해 화면을 만듭니다.</p></div>
            <Upload />
          </div>
          <p className="close__word" aria-hidden="true">Sheet2Service</p>
        </div>
        <div className="closing__links">
          <div className="grid">
            <div className="span-4 stack-4">
              <a className="nav__logo" href="#top">Sheet2Service</a>
              <p className="footer__lede">예약 시트를 예약 서비스로</p>
            </div>
            <div className="span-2 footer__col"><h3>화면</h3><ul><li><a href="#screens">예약자 화면</a></li><li><a href="#screens">관리자 화면</a></li></ul></div>
            <div className="span-2 footer__col"><h3>만드는 법</h3><ul><li><a href="#how">3단계</a></li></ul></div>
            <div className="span-2 footer__col"><h3>예약 규칙</h3><ul><li><a href="#rules">타임과 정원</a></li></ul></div>
            <div className="span-2 footer__col"><h3>질문</h3><ul><li><a href="#faq">자주 묻는 질문</a></li><li><a href="mailto:firoms@ajou.ac.kr">메일 보내기</a></li></ul></div>
          </div>
          <div className="footer__legal">
            <span>&copy; 2026 Sheet2Service</span>
            <div className="socials" />
          </div>
        </div>
      </div>
    </footer>
  </>;
}
