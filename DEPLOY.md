# Vercel 배포 가이드

이 프로젝트는 **2부분**으로 나뉩니다.

| 구성 | 배포 위치 | 역할 |
|------|-----------|------|
| **프론트** (`frontend/`) | **Vercel** | 웹 UI |
| **백엔드** (`backend/`) | **Render / Railway** | PDF 파싱 API |

Vercel만으로는 PDF 파싱 백엔드를 돌리기 어렵습니다. **프론트는 Vercel, API는 Render** 조합을 권장합니다.

---

## 1단계: 백엔드 배포 (Render)

### A. GitHub에 코드 올리기

```powershell
cd c:\Users\10124\Desktop\PV
git init
git add .
git commit -m "CIOMS literature converter"
# GitHub에서 새 repo 생성 후
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

### B. Render에서 Web Service 생성

1. https://render.com 가입 (GitHub 연동)
2. **New → Web Service** → 저장소 선택
3. 설정:

| 항목 | 값 |
|------|-----|
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Plan | Free (또는 Starter) |

4. **Environment Variables** 추가:

```
CORS_ORIGINS=https://your-app.vercel.app
```

(나중에 Vercel URL을 알면 수정)

5. Deploy 후 URL 확인 예: `https://cioms-api.onrender.com`

6. 동작 확인: `https://cioms-api.onrender.com/api/health` → `{"status":"ok"}`

> 무료 플랜은 15분 미사용 시 슬립 → 첫 요청이 30~60초 걸릴 수 있습니다.

---

## 2단계: 프론트 배포 (Vercel)

### A. Vercel 연결

1. https://vercel.com 가입 (GitHub 연동)
2. **Add New → Project** → 같은 GitHub 저장소 선택
3. 설정:

| 항목 | 값 |
|------|-----|
| Framework Preset | Vite |
| Root Directory | `frontend` |
| Build Command | `npm run build` |
| Output Directory | `dist` |

4. **Environment Variables** 추가:

| Name | Value |
|------|-------|
| `VITE_API_BASE` | `https://cioms-api.onrender.com/api` |

(Render URL 뒤에 `/api` 포함)

5. **Deploy** 클릭

### B. CORS 다시 설정

Vercel 배포가 끝나면 실제 URL이 생깁니다 (예: `https://cioms-converter.vercel.app`).

Render 대시보드 → Environment → `CORS_ORIGINS` 수정:

```
https://cioms-converter.vercel.app
```

저장 후 Render 서비스 **Manual Deploy** (재시작).

---

## 3단계: 동작 확인

1. Vercel URL 접속
2. 논문 PDF 업로드
3. CIOMS HTML 생성 확인

오류 시:
- 브라우저 F12 → Network 탭에서 API 요청 URL 확인
- `VITE_API_BASE`가 Render API 주소인지 확인
- Render `/api/health` 응답 확인

---

## 로컬에서 프로덕션 API 테스트

`frontend/.env`:

```
VITE_API_BASE=https://cioms-api.onrender.com/api
```

```powershell
cd frontend
npm run dev
```

---

## Vercel CLI로 배포 (선택)

```powershell
npm i -g vercel
cd frontend
vercel
# Environment Variable: VITE_API_BASE 입력
vercel --prod
```

---

## 요약 체크리스트

- [ ] GitHub에 코드 push
- [ ] Render: `backend` Web Service 배포
- [ ] Render: `CORS_ORIGINS` 설정
- [ ] Vercel: `frontend` 프로젝트, Root = `frontend`
- [ ] Vercel: `VITE_API_BASE=https://...onrender.com/api`
- [ ] Vercel URL을 Render `CORS_ORIGINS`에 추가
- [ ] PDF 업로드 테스트
