# 업로드 화면 사진

- 최종 파일: `frontend/public/images/sheet2service-workspace.png`
- 제작: 기본 제공 ImageGen 도구. 외부 사진을 가져오거나 Claude API를 호출하지 않았다.
- 사용 위치: 메인 페이지의 왼쪽 이미지 영역. 오른쪽은 실제 파일 업로드 카드이며 사진에 UI나 문구를 합성하지 않는다.
- 참고 사이트: https://www.remove.bg/ (간결한 업로드 중심 화면 참고).
- 출력 사진의 노트북·스프레드시트·색감·불필요한 문구 부재를 확인했다. 앱 브라우저 검사는 하지 않았다.

## 사용 프롬프트

```text
Use case: photorealistic-natural. Asset type: a single photographic website hero asset for Sheet2Service, placed in the left column beside a file upload card. Primary request: a quiet, minimal photo of a modern laptop open to an abstract spreadsheet on a clean light cream desk, three-quarter view, no person. Spreadsheet grid subtly visible but no legible words or numbers, no logos or branding. Soft natural daylight, realistic materials, restrained pale teal and warm cream color palette matching an existing teal/cream web design. Landscape 4:3 framing, generous uncluttered space, laptop centered in frame with ample breathing room. No headline, caption, watermark, UI layout or surrounding website screenshot. Output only the photographic asset.
```
