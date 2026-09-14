import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

function App() {
  return (
    <main>
      <p className="eyebrow">스프레드시트에서 웹 서비스로</p>
      <h1>Sheet2Service</h1>
      <p>데이터의 의미와 관계를 분석해, 업무에 맞는 웹 서비스를 구성합니다.</p>
      <p>현재 프로젝트 초기 설정 단계입니다. 파일 업로드와 Preview 기능은 준비 중입니다.</p>
    </main>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>,
);
