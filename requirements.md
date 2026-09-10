# TechBlog 요구사항 정의서

> 최종 수정: 2026-09-10
> 상태: 운영 중 — https://lleg.dev

---

## 1. 프로젝트 개요

AI, Web, 인프라 등 다양한 기술 주제를 다루는 개인 기술 블로그.

운영 방식은 단순하다. **사용자가 주제를 하나 던지면 → Claude가 조사·집필·시각화·게시까지 한 번에 처리한다.**

| 항목 | 내용 |
|---|---|
| 블로그 이름 | **Lleg's study** |
| 작업 디렉터리 | `D:\workspace\TechBlog` |
| GitHub 저장소 | `sehyunnoh/techblog` |
| 배포 URL | **`https://lleg.dev`** (Cloudflare Registrar 등록, apex 서빙) |
| 저자 | **lleg** — [GitHub](https://github.com/sehyunnoh) · [LinkedIn](https://www.linkedin.com/in/devnoh) |
| 집필 언어 | **영어 (English)** |
| 대화 언어 | 한국어 (Claude ↔ 사용자) |
| 주제 범위 | AI/ML, Web, Backend, DevOps, 아키텍처 등 기술 전반 (제한 없음) |

---

## 2. 기술 스택

| 레이어 | 선택 | 비고 |
|---|---|---|
| 사이트 생성기 | **Astro** | Content Collections로 글·태그 관리 |
| 콘텐츠 포맷 | **MDX** (Markdown + 컴포넌트) | 차트/SVG 컴포넌트 삽입용 |
| 스타일 | Tailwind CSS | 라이트/다크 테마 모두 대응 |
| 다이어그램 | Mermaid | 빌드 타임 렌더링 |
| 차트 | Chart.js 또는 Recharts | Astro Island로 필요한 글에만 로드 |
| 배포 | **GitHub Pages** | GitHub Actions로 `main` push 시 자동 배포 |
| 검색 | Pagefind (정적 검색) | 빌드 시 인덱스 생성 |
| 피드 | RSS + sitemap.xml | `@astrojs/rss`, `@astrojs/sitemap` |
| 폰트 | **자체 호스팅** (Astro Fonts API) | Inter 가변 + JetBrains Mono. 외부 폰트 CDN 요청 없음 |
| 애널리틱스 | **Umami Cloud** | 쿠키리스·2KB 스크립트. 무료 티어 월 10만 이벤트 |
| 검색 유입 분석 | **Google Search Console** | 유입 검색어 확인용 (애널리틱스로는 불가) |
| 댓글 | 없음 (**추후 giscus**) | 글이 쌓이면 GitHub Discussions 기반으로 추가 |

---

## 3. 글 작성 규칙

### 3.1 대상 독자 및 분량

- **대상**: 중급 이상 실무 개발자
- **분량**: 1,500 ~ 2,500 단어 (읽는 데 8~12분)
- **톤**: 실무적이고 구체적. 마케팅 문구·과장 금지. 트레이드오프를 반드시 언급.

### 3.2 리서치

**모든 글은 웹 검색 조사를 선행한다.**

1. 주제 접수 → WebSearch/WebFetch로 최신 자료 조사
   - 공식 문서 / 릴리스 노트
   - 벤치마크·측정 데이터
   - 주요 블로그·논문·RFC
2. 조사 결과를 근거로 집필
3. 모든 참조 링크는 **실제 접근 가능한 URL만** 사용 (환각 링크 금지)

### 3.3 글 구조 (표준 템플릿)

```
1. Hook / Problem statement   — 왜 이 주제가 지금 중요한가
2. Background                 — 최소한의 전제 지식
3. Core content (3~5 sections) — 각 섹션마다 시각 자료 1개 이상
4. Trade-offs / Pitfalls      — 실무에서 걸리는 지점
5. Takeaways                  — 3~5개 불릿 요약
6. References                 — 번호 매긴 링크 목록
```

### 3.4 코드 예제

- 실행 가능한 수준의 완결된 스니펫
- 언어 태그 명시 (`ts`, `py`, `bash` 등)
- 20줄 초과 시 핵심 부분만 발췌하고 주석으로 생략 표시

---

## 4. 인포그래픽 / 시각화 (핵심 요구사항)

> **"최대한 인포그래픽을 사용한다"** — 글마다 최소 3개 이상의 시각 자료를 목표로 한다.

### 4.1 시각화 유형별 사용 기준

| 유형 | 사용처 | 구현 |
|---|---|---|
| **Mermaid 다이어그램** | 플로우차트, 시퀀스, 아키텍처, 상태 전이, ER | ```` ```mermaid ```` 코드 블록 |
| **인라인 SVG** | 개념도, 비교표, 타임라인, 레이어 구조 등 Mermaid로 표현 안 되는 것 | 직접 작성한 `<svg>` |
| **데이터 차트** | 벤치마크, 비용 비교, 성능 추이, 점유율 | Chart.js / Recharts 컴포넌트 |

> **데이터가 없으면 차트를 만들지 않는다.** 시각 자료 개수를 채우려고 근거 없는 수치를
> 차트로 그리는 것은 이 블로그가 반대하는 바로 그 행위다. 메커니즘이 주제인 글은
> 다이어그램만으로 끝내도 된다 (예: Googlebot 글은 차트 없이 다이어그램 3개).

### 4.2 시각화 공통 규칙

- **다크모드 대응 필수**: 색상은 CSS 변수 또는 `prefers-color-scheme`으로 양쪽 테마 처리
- **반응형**: 모바일에서 가로 스크롤 컨테이너(`overflow-x: auto`) 안에 배치
- **접근성**: 모든 시각 자료에 캡션 + `aria-label`/`<title>` 제공
- **차트 팔레트**: `dataviz` 스킬의 검증된 팔레트 규칙을 따름
- **텍스트 최소 크기**: 12px 이상 (모바일에서 읽을 수 있어야 함)

---

## 5. 태그 시스템

### 5.1 기능 요구사항

- 글마다 **3~6개** 태그 부여
- `/tags` — 전체 태그 목록 (글 수 표시)
- `/tags/[tag]` — 해당 태그의 글 목록 페이지
- 글 상단/하단에 태그 배지 표시 (클릭 시 태그 페이지로 이동)
- 태그는 **정해진 어휘집(taxonomy)에서만** 선택 → 무한 증식 방지

### 5.2 태그 어휘집 (초안, 확장 가능)

| 카테고리 | 태그 |
|---|---|
| 분야 | `ai`, `llm`, `web`, `backend`, `frontend`, `devops`, `data`, `security`, `mobile` |
| 기술 | `python`, `typescript`, `rust`, `go`, `react`, `docker`, `kubernetes`, `postgres` |
| 성격 | `tutorial`, `deep-dive`, `benchmark`, `architecture`, `opinion`, `news` |

> 새 태그가 필요하면 `content/tags.json`에 추가한 뒤 사용.

---

## 6. 콘텐츠 스키마 (frontmatter)

```yaml
---
title: "Article title in English"
description: "One-sentence summary for SEO and card previews"
pubDate: 2026-09-09
updatedDate: 2026-09-15      # optional
tags: ["ai", "llm", "deep-dive"]
heroImage: "./hero.svg"       # optional
draft: false
readingTime: 11               # auto-calculated
---
```

---

## 7. 작업 워크플로 (주제 접수 → 게시)

```
[사용자] 주제 제시
    ↓
[1] 리서치      — WebSearch/WebFetch로 최신 자료 수집
    ↓
[2] 아웃라인    — 섹션 구성 + 각 섹션의 시각 자료 계획 수립
    ↓
[3] 집필        — 영어로 본문 작성 (1500~2500 words)
    ↓
[4] 시각화      — Mermaid / SVG / 차트 제작 및 삽입
    ↓
[5] 참조 정리   — References 섹션에 링크 목록 정리 + 유효성 확인
    ↓
[6] 태그 부여   — 어휘집에서 3~6개 선택
    ↓
[7] 로컬 빌드   — `npm run build` + `astro check`
    ↓
[8] 브라우저 검증 — preview를 실제로 열어 눈으로 확인 (라이트/다크 양쪽)
    ↓
[9] 게시        — git commit & push → GitHub Actions → 배포 확인
```

### 7.1 브라우저 검증은 생략하지 않는다

빌드가 통과해도 화면에서만 드러나는 결함이 반복적으로 나왔다. 실제로 이 단계에서 잡은 것들:

- line 차트용 플러그인이 bar 차트에도 그려짐 (Chart.js는 등록된 플러그인을 전 타입에 실행)
- 차트 direct label이 고정 여백에 잘림
- Tailwind가 스캔하지 못하는 `.sr-only`가 생성되지 않아 숨김 요소가 노출
- Mermaid가 레이아웃 후 렌더링되며 **모든 목차 앵커**가 어긋남
- 인용문 따옴표가 이중으로 출력
- Astro가 인라인 태그 앞 공백을 제거해 `the<a href=...>`로 붙음

전부 `astro check`와 빌드를 통과한 상태였다. **눈으로 보지 않으면 못 잡는다.**

### 7.2 사용자 확인 지점

- **주제 접수 시**: 주제가 너무 광범위하면 좁힐 안을 제시하고 확인받는다
- **아웃라인**: 첫 글에서만 확인받았고 이후엔 생략했다. 방향이 갈릴 여지가 크면 확인받는다
- **게시**: "글 써줘"에 게시가 포함된 것으로 본다. 첫 글만 push 전 승인을 받았고,
  이후에는 작성→검증→게시까지 진행한 뒤 결과와 발견 사항을 보고했다.
  별도 리뷰를 원하면 요청 시점에 말하면 된다

---

## 8. 사이트 설정값

```
site      : https://lleg.dev      (apex, base 경로 없음)
title     : Lleg's study
author    : Lleg
github    : https://github.com/sehyunnoh
linkedin  : https://www.linkedin.com/in/devnoh
```

> 내부 링크·자산 경로는 계속 `withBase()` 헬퍼를 통해 생성한다.
> 지금은 `base`가 비어 있어 사실상 항등 함수지만, 이 규칙 덕분에 `/techblog` →
> apex 이전이 **설정 한 줄 변경**으로 끝났다. 다음 이전에도 같은 비용을 유지하기 위해 남겨둔다.

### 8.1 셋업 상태 (완료)

| # | 항목 | 상태 |
|---|---|---|
| 1 | GitHub 저장소 + Pages | ✅ `sehyunnoh/techblog`, Actions 자동 배포 |
| 2 | 커스텀 도메인 | ✅ `lleg.dev` — Cloudflare DNS, Let's Encrypt, HTTPS 강제 |
| 3 | 폰트 자체 호스팅 | ✅ 외부 폰트 CDN 요청 0 |
| 4 | Umami 애널리틱스 | ✅ 이벤트 전송 확인 |
| 5 | Search Console | ✅ **도메인 속성**, DNS TXT 검증, 사이트맵 제출 |
| 6 | 개인정보처리방침 | ✅ `/privacy` |
| 7 | 글 | ✅ 3편 (Observability · LLM 추론 · Googlebot) |

#### 도메인 이전 시 알게 된 것

- GitHub Pages는 커스텀 도메인 설정 후 기존 주소를 **경로를 보존한 채** 리다이렉트한다.
  `github.io/techblog/posts/x` → `lleg.dev/posts/x`. 공식 문서에 없어 직접 확인한 동작이다.
- `lleg.dev`는 **다른 계정이 선점**해 둔 상태였다. GitHub 프로필 설정의 도메인 검증
  (TXT `_github-pages-challenge-sehyunnoh`)으로 해제했다. 이 TXT는 **삭제하면 안 된다.**
- CAA 레코드는 **넣지 않는다.** GitHub Pages 요건은 "CAA를 쓰고 있다면"이라는 조건부이고,
  `letsencrypt.org`만 허용해두면 나중에 Cloudflare 프록시를 켤 때 인증서 발급이 막힌다.

#### 애널리틱스 배선

- Website ID는 GitHub Actions **variable** `UMAMI_WEBSITE_ID`에 저장한다 (secret 아님).
  이 값은 모든 페이지 HTML에 그대로 출력되므로 애초에 공개 값이다.
- 빌드 시 `import.meta.env.UMAMI_WEBSITE_ID`로 읽고, **값이 없으면 스크립트 태그 자체를 출력하지 않는다.**
  덕분에 로컬 `npm run dev`/`npm run build`는 통계를 오염시키지 않는다.

#### SEO 배선

- 사이트맵은 `noindex` 페이지를 제외한다 (`astro.config.mjs`의 `sitemap({ filter })`).
  넣어두면 Search Console이 "noindex 태그에 의해 제외됨"으로 리포트해 경고처럼 보인다.
- Search Console은 **도메인 속성**이라 `www`·서브도메인·http/https를 한 속성으로 묶는다.

### 8.2 보류 항목 (나중에)

| 항목 | 시점 |
|---|---|
| 댓글(giscus) | 글이 어느 정도 쌓인 뒤 |
| Google AdSense | **권장하지 않음.** 기술 독자의 광고 차단률이 높아 수익이 지급 기준액에 도달하기 어렵고, EEA·영국 대상 맞춤 광고는 인증 CMP(쿠키 배너)가 의무라 쿠키리스 구성이 무너진다. 트래픽 데이터를 본 뒤 재검토 |
| 기존 블로그와 Umami 분리 | 기존 개인 블로그에도 추적을 붙일 때 |

---

## 9. 비범위 (하지 않는 것)

- 다국어(i18n) 지원 — 영어 단일 언어
- 회원가입 / 로그인 / 유료 구독
- CMS 관리자 UI — 집필은 Claude + Markdown 파일로만
- 뉴스레터 발송 시스템
