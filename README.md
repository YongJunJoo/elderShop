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
| ② render | 장면별 카드(라벨·상품 이미지·큰 자막) + TTS → 1080x1920 mp4 | Pillow, ffmpeg, Google Cloud TTS |
| ③ upload | 제목·설명·태그·AI 생성 표시 넣어 업로드, 예약 공개 | YouTube Data API v3 |
| ④ analyze | 영상별 조회수·시청 비율·구독 증가 수집, 교훈을 다음 대본에 반영 | YouTube Analytics API, Claude API |

## 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # ffmpeg도 필요 (brew install ffmpeg / apt install ffmpeg)
cp .env.example .env                # 키 채우기
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
python -m shorts script products/bath-safety-mat.json   # → out/bath-safety-mat/script.json
# script.json 검수: 내용 확인 후 "approved": true
python -m shorts render products/bath-safety-mat.json   # → out/bath-safety-mat/video.mp4
python -m shorts upload products/bath-safety-mat.json --publish-at 2026-11-22T19:00:00+09:00
python -m shorts analyze --days 28                      # → data/analytics_*.csv, data/learnings.md
```

음성 없이 화면만 미리 보려면 `TTS_PROVIDER=none python -m shorts render ... --force`.
대본 예시는 `examples/bath-safety-mat.script.json`.

## 비용 (하루 1편 기준, 대략)
- Claude: 편당 리뷰 조사 + 대본 약 100~300원, 주간 분석 소액
- Google TTS: 편당 약 300자라 월 무료 한도 안
- YouTube API: 무료 (일일 할당량 10,000 유닛, 업로드 1건 ≈ 1,600 유닛 → 하루 약 6편)
