# CIOMS Literature Converter

논문 Case report PDF → **CIOMS Form I 26개 항목** 추출 → **HTML** 다운로드 (DB 없음, 단일 페이지 앱)

## 사용법

1. 백엔드 + 프론트엔드 실행
2. 브라우저에서 http://localhost:5173 접속
3. 논문 PDF 업로드 → HTML 미리보기 / 다운로드

## 실행

```powershell
.\start.ps1
```

- 프론트: http://localhost:5173
- API: http://127.0.0.1:8000

## API (무상태)

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/literature/convert` | PDF → `{ cioms, html }` |
| POST | `/api/literature/html` | 수정된 cioms → HTML 재생성 |

DB 저장 없이 요청마다 변환합니다.

## 배포 참고

- **Vercel**: React 프론트만 배포 가능
- **백엔드**: Railway / Render 등 (PDF 파싱용 Python API)
