# Sheet2Service

단일 표 형태의 스프레드시트를 분석해 데이터의 의미, 엔티티, 관계와 필요한 기능을 추론하고 실제 웹 서비스 형태의 임시 Preview를 제공하는 프로젝트입니다.

## 기술 구성

- Backend: Python 3.14, Django 5.2, Django REST Framework
- Frontend: React, Vite, JavaScript
- Database: PostgreSQL 17
- 개발 실행: Docker Compose

일반 로직으로 데이터 파싱과 검증을 처리하고, Claude API는 의미와 구조 추론에 사용하는 방향입니다. 분석 결과는 독립된 중간 표현으로 관리하고 검증된 통합 템플릿이 이를 읽어 Preview를 구성합니다. 현재 CSV 업로드·기본 분석 API와 업로드·앞 20행 미리보기 화면을 구현했습니다. 컬럼별 분석 표도 제공하며, Claude 연동·서비스 Preview 생성은 후속 범위입니다. 초기 입력은 CSV 전용입니다.

API 사용법과 분석 규칙: [CSV 업로드 API](docs/csv-upload-api.md).

다음 작업을 위한 현황과 합의 사항: [작업 인수인계](docs/handoff.md).

## 개발 환경 실행

Docker Engine과 Compose 플러그인 또는 Docker Desktop이 필요합니다.

1. 루트의 `.env.example`을 `.env`로 복사합니다. PowerShell: `Copy-Item .env.example .env`
2. `docker compose up --build`를 실행합니다.
3. 프론트엔드: http://localhost:5173
4. API 상태 확인: http://localhost:8000/api/health/

프론트엔드에서 CSV와 인코딩을 선택한 뒤 **업로드하고 확인**을 누르면 앞 20행을 확인할 수 있습니다. 긴 셀은 클릭해서 펼치고, 원본 다운로드로 저장된 파일을 받을 수 있습니다. 현재 화면은 새로고침하면 초기화됩니다. 업로드 이력·결과 복원 화면은 아직 제공하지 않습니다.

API 상태 확인은 Django 응답 여부만 확인하며 DB 상태를 보장하지 않습니다. 프론트엔드의 `/api` 요청은 Vite가 Django로 프록시합니다. DB 포트는 호스트에 공개하지 않습니다. Django 시작 시 기본 마이그레이션을 적용합니다.

현재 Compose는 소스 변경이 반영되는 **로컬 개발용**입니다. 공개 배포용 서버, 정적 파일 서빙, HTTPS 등은 추후 구성합니다. 예제 환경변수는 개발용이며 실제 비밀값과 업로드 데이터는 커밋하지 않습니다.

종료: `docker compose down`. DB는 named volume에 보존됩니다. `docker compose down -v`는 DB를 포함한 볼륨 데이터를 삭제하므로 초기화가 필요할 때만 사용합니다.

프론트엔드 의존성 변경 후에는 `docker compose run --rm --no-deps frontend npm ci`로 의존성 볼륨을 갱신하고 다시 빌드합니다.

## 검증

```sh
docker compose exec backend python manage.py check
docker compose exec frontend npm run build
```

프론트엔드는 로컬에서도 `frontend` 디렉토리에서 `npm ci`, `npm run build`로 검증할 수 있습니다. PowerShell 실행 정책으로 `npm`이 차단되면 `npm.cmd`를 사용합니다.

## 작업 규칙

커밋 전 변경 내용과 메시지를 제안하고 사용자 승인을 받습니다. AI 작성자·공동 작성자 표기는 추가하지 않습니다. 이후 기능 작업은 필요에 따라 브랜치를 분리합니다.
