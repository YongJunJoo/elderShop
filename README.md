# elderShop

어르신(60+) 대상 생활용품 정보 쇼츠를 자동으로 만드는 파이프라인입니다.
채널 원칙(써본 척 금지, 고르는 기준 + 구매자 장점·불만, 광고 고지)은 `prompts/script_system.md`에 들어 있습니다.

```
상품 JSON ─▶ ① 대본(script) ─▶ [사람 검수: approved=true] ─▶ ② 영상(render) ─▶ ③ 업로드(upload)
                  ▲                                                              │
                  └──────── data/learnings.md ◀── ④ 분석(analyze) ◀──────────────┘
```

| 단계 | 하는 일 | 사용 서비스 |
|---|---|---|
| ① script | 웹 검색으로 공개 리뷰를 모아 장점·불만 요약 → 50초 대본 JSON | Claude API (web search + structured output) |
| ② render | 상세 이미지 여러 장 1.7초 전환 + 줌·패닝, 상단 고정 2줄 제목, 말에 맞춘 짧은 자막, TTS 1.2배 → 25~30초 1080x1920 mp4 | Pillow, ffmpeg, Google Cloud TTS |
| ③ upload | 제목·설명·태그·AI 생성 표시 넣어 업로드, 예약 공개 | YouTube Data API v3 |
| ④ analyze | 영상별 조회수·시청 비율·구독 증가 수집, 교훈을 다음 대본에 반영 | YouTube Analytics API, Claude API |

## 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # ffmpeg도 필요 (brew install ffmpeg / apt install ffmpeg)
cp .env.example .env                # 키 채우기 (실행 시 자동으로 읽음, 윈도우 포함)
```

준비할 것
1. **Anthropic API 키** → `ANTHROPIC_API_KEY`
2. **Google Cloud 프로젝트** 하나에서
   - Text-to-Speech API 사용 설정 + 서비스 계정 키(JSON) → `secrets/gcp-tts.json`
   - YouTube Data API v3, YouTube Analytics API 사용 설정
   - OAuth 동의 화면 + OAuth 클라이언트(데스크톱 앱) → `secrets/client_secret.json`
   - 처음 업로드/분석할 때 브라우저가 열리면 **채널 소유 계정**으로 로그인 → `secrets/token.json` 저장
3. (선택) 쿠팡 파트너스 링크 → 상품 JSON의 `affiliate_url`

> ⚠️ 새 구글 API 프로젝트는 YouTube API 감사(audit)를 통과하기 전까지 API로 올린 영상이 **비공개로 고정**됩니다.
> 일찍 감사를 신청하고, 그동안은 비공개 업로드 후 스튜디오에서 공개로 바꾸세요.
> '유료 프로모션 포함' 표시는 API로 켤 수 없어 스튜디오에서 켜야 합니다.

## 사용법

```bash
python -m shorts images products/bath-safety-mat.json   # 상품 사진 자동 수집 → assets/products/<slug>/
python -m shorts script products/bath-safety-mat.json   # → out/bath-safety-mat/script.json
# script.json 검수: 내용 확인 후 "approved": true
python -m shorts render products/bath-safety-mat.json   # → out/bath-safety-mat/video.mp4
python -m shorts upload products/bath-safety-mat.json --publish-at 2026-11-22T19:00:00+09:00
python -m shorts analyze --days 28                      # → data/analytics_*.csv, data/learnings.md
```

### AI 방식 비용 비교 (편당, 대략)
| 방식 | 명령 | 비용 |
|---|---|---|
| 사진 전환형(기본) | script → render | Claude 대본 100~400원 |
| AI 장면 이미지형 | script --format aiimage → aiimage → render | + 이미지 4장 약 200원 |
| Flow 반자동 | script --format ai → flowprompt → (Flow에서 생성, out/<slug>/flow/에 mp4) → render | 무료 크레딧(하루 50, Veo Fast 8초=20), 720p, 수동 다운로드 |
| Veo API 자동 | script --format ai → aivideo → render | 8초당 약 1~3달러 |

### AI 생활 장면형 (선택)
```bash
python -m shorts script  products/bath-safety-mat.json --format ai   # 10~14초 대본 + 영어 장면 설명
# 검수 후 approved=true
python -m shorts aivideo products/bath-safety-mat.json   # Veo로 8초 장면 (8초당 약 1~3달러)
python -m shorts render  products/bath-safety-mat.json   # AI 장면 + 말풍선 → 실제 상품 사진 + 프로필 링크
```
상품 사진을 참고 이미지로 넣어 모양을 맞추고, 화면 상단에 "AI로 만든 장면"을 표시하며, 업로드 시 YouTube 합성 콘텐츠 표시를 켭니다.
말풍선은 상황 설명만 쓰고 "써봤더니" 같은 후기처럼 쓰지 않습니다.

음성 없이 화면만 미리 보려면 `TTS_PROVIDER=none python -m shorts render ... --force`.
대본 예시는 `examples/bath-safety-mat.script.json`.

상품 JSON의 `images`에 상세페이지 이미지 4~8장을 넣으면 화면이 1.7초마다 바뀝니다(`CUT_SEC`로 조정).
`link_no`는 프로필 링크 모음의 번호이며, 영상 끝 "프로필 링크 N번"과 설명란·댓글 번호에 쓰입니다.
TOP3 묶음 영상은 `{"slug": "...", "theme": "부모님 욕실 안전템", "products": [상품1, 상품2, 상품3]}` 형태로 만들면 됩니다.

## 비용 (하루 1편 기준, 대략)
- Claude: 편당 리뷰 조사 + 대본 약 100~300원, 주간 분석 소액
- Google TTS: 편당 약 300자라 월 무료 한도 안
- YouTube API: 무료 (일일 할당량 10,000 유닛, 업로드 1건 ≈ 1,600 유닛 → 하루 약 6편)
