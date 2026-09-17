---
name: rp-figure
description: >
  연구계획서 그림을 만들어 본문에 **마크다운 이미지 참조**로 넣는다(파일명 ASCII).
  사이클 개괄도는 `engine.figure.schematic` 으로 그리고(위상이 곧 연구 내용),
  그 외(조직도·진도표·매트릭스·기대효과)는 Chrome MCP 로 Gemini 또는 ChatGPT 에서
  받아오거나 재현·인쇄가 걸리면 `engine.figure.lattice` 로 돌린다.
  사람이 직접 부르는 입구는 스킬 `rp-schematic` · `rp-figure-ai` 다.
---

> ★ **요청받은 그림만 만든다** (2026-09-17). `requirements.md` 의 `figures:` 에
> 없는 그림은 만들지 않는다 — 「이 그림도 있으면 좋겠다」는 판단으로 추가하지 마라.


# 0단계 — 엔진에게 물어보기 (생략 금지)

```bash
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.figure.schematic --help
```
**이 출력이 유일한 진실이다.** 아래 표와 어긋나면 출력을 따르고 불일치를
`workspace/<과제>/figures/_engine_drift.md` 에 기록하라.

# 그림 종류를 먼저 판별한다 — 이 갈림길이 가장 중요하다

| 성격 | 어디서 그리나 | 왜 |
|---|---|---|
| **에너지 시스템 사이클 개괄도**<br>(압축기·팽창기·열교환기·밸브·축이 배관으로 연결된 것) | `engine.figure.schematic`<br>선언적 YAML | **위상(topology)이 곧 연구 내용**이다. AI 이미지는 사이클 연결을 정확히 그리지 못한다. 사용자가 직접 그린 사이클 그림의 문법을 따르는 **기본 도형 배치**여야 한다 |
| **데이터 격자**<br>조직도 · 진도표(간트) · 위험도 매트릭스 | `engine.figure.lattice`<br>선언적 YAML | **라벨이 곧 내용**이라 AI 이미지로는 한글을 정확히 못 넣는다. 그렇다고 사이클 글리프 어휘(압축기·열교환기·밸브)로도 환원되지 않는다. **A도 B도 아닌 세 번째 부류다** |
| **그 외 전부** — 기대효과, 개념도, 로드맵, 수요 대응 관계, 시스템 조감도 … | **Chrome MCP → Gemini** | 도형 어휘로 환원되지 않는 복잡한 그림이다 |
| 표 | **그리지 마라** | 네이티브 `hp:tbl`로 들어간다 |

> **표를 그림으로 만들지 마라.** 한글 텍스트 추출에서 이미지 표는 **0자**로
> 나온다(실측). LLM Council이 텍스트를 파싱하면 표 내용이 통째로 사라진다.

---

# 경로 A — 사이클 개괄도 (선언적 스펙)

`specs/<이름>.yaml` 을 쓰고 렌더한다. 그림 1장당 파이썬을 새로 짜지 마라.

```yaml
preset: turbo          # turbo(터보기계) | pfd(공정도)
canvas: wide           # wide 16:9 | band 2.5:1 | hero 1.6:1 | tall 0.8
grid: [2, 2]
panels:
  - title: "(a) Case 1"
    components:
      - {id: comp, type: compressor, at: [0.17, 0.50], w: 0.15, h: 0.26, label: "압축기"}
      - {id: hhx,  type: hx,         at: [0.50, 0.84], w: 0.20, h: 0.11, label: "증기발생기"}
    shafts:  [{from: comp, to: exp}]
    streams:
      - {from: comp.top, to: hhx.left, fluid: primary, route: VH}
      - {to: hhx.top,    fluid: heat_sink,   direction: up,   length: 0.10, dx: -0.06, label: "공정 스팀"}
      - {to: ev.bottom,  fluid: heat_source, direction: down, length: 0.08, into: true, label: "공정 폐열"}
```

부품: `compressor` `expander`(=turbine) `hx` `valve` `motor` `generator`
앵커: `.left .right .top .bottom .center .in .out`
유체: `primary`(검정 실선) `secondary`(초록 실선) `heat_sink`(파란 점선) `heat_source`(빨간 점선)
경로: `HV` `VH` `HVH` `VHV` `auto`
`into: true` — 열이 **들어오는** 쪽(증발기의 폐열 등)은 화살촉을 부품 쪽으로 돌린다

```bash
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.figure.schematic --spec specs/x.yaml --out <출력>.png --assert-no-overlap
```
**`--assert-no-overlap` 없이 넘기지 마라.** exit 2면 라벨이 겹친 것이다.

## 목표 기준선 — 사용자가 PowerPoint 로 직접 만든 도면

이 엔진의 합격 기준은 AI 가 만든 무엇이 아니라 **사용자가 손으로 만든 실제 논문 그림**이다.

```
~/Desktop/실적/저널/IJ/2. (2026) HP cascade/2. 파일/26.07.22/paper/figures/
    Fig1_schematic.png / .pdf / .emf      ← 목표물
    Fig1_source.pptx                      ← 원본 (저장소 밖, 대외 공개 금지)
```

**판정**: 재현본을 원본과 나란히 놓고 *「이 정도면 쓰겠다」* 가 나올 것.
4패널 전부 위상(topology)이 정확할 것. 라벨 겹침 0건.

> ⚠️ 조사 중 나온 18KB matplotlib 스크립트를 목표로 삼지 마라.
> 그것은 이미지 생성 실패 후의 **일회용 폴백**이고 상태점·그룹박스·온도배지를
> 붙여 **과잉 장식**했다. 실제 문법은 훨씬 미니멀하다.

## 이 문법을 지켜라 (사용자 논문 3편의 공통 철학)

- **도면에 수치를 넣지 않는다.** 조건은 표·캡션으로 분리한다.
- **상태점 번호를 쓰지 않는다.**
- **그룹 박스·온도 배지를 넣지 않는다.** 과잉 장식이다.
- 캡션을 그림 안에 넣지 마라 — HWPX가 `hp:autoNum`으로 붙인다.
  범례가 꼭 필요하면 `legend:` 로 한 줄만.
- 배경은 흰색이다(테마 `surface: #FFFFFF`). 바꾸지 마라.

---

# 경로 C — 데이터 격자 (선언적 스펙)

**엔진**: `PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.figure.lattice --spec specs/<이름>.yaml --out <png> --assert-no-overlap`

## C-1. 언제 이 경로인가

| 그림 | 왜 격자인가 |
|---|---|
| **조직도** | 기관·역할이 계층 칸에 들어간다. 추진체계 절의 필수 그림 |
| **진도표(간트)** | 연차 × 세부과제 격자에 막대. 추진 일정 절 |
| **위험도 매트릭스** | 가능성 × 심각도 2차원 격자. 위험관리 절 |

> **왜 경로 A로 안 그리나** — 개괄도 엔진의 글리프는 압축기·열교환기·밸브·모터·축이다.
> 격자를 그릴 어휘가 없다.
>
> **왜 코드로 그리는가 (2026-09-10 근거 정정)** — 원래 이유는 「라벨이 곧 내용인데
> Gemini 가 한글을 정확히 못 넣는다」였고, 그 때문에 `[FIG-6] 위험도 매트릭스`·
> `[FIG-7] 마일스톤`을 한 번 철회하기도 했다(2026-08-26).
>
> **그 전제는 깨졌다.** 실측에서 Gemini 가 조직도 11개·진도표 16개 라벨을 전부
> 정확히 냈다. **지금 격자 엔진을 쓰는 이유는 재현성·해상도·겹침 검사다** —
> 3200×1800 대 1024×572, 같은 입력이 같은 그림을 내는가, 겹침을 exit 2 로 잡는가.

## C-2. ★ A와 라벨 실패 처리가 정반대다 — 모듈이 나뉜 이유

| | 경로 A `textfit` | 경로 C `textbox` |
|---|---|---|
| 도형 안에 안 들어가면 | **도형 밖 아래로 내보낸다** | **내보내지 않는다** |
| 왜 | 배관 사이 여백이 넉넉하다 | **밖이 곧 옆 칸**이다. 내보내면 이웃을 덮는다 |
| 대신 | — | 줄바꿈 → 축소 → 그래도 안 되면 **적발(exit 2)** |

**같은 파일에 두 정책을 넣으면 어느 쪽이 먹었는지 알 수 없어진다.**
테마·표준 캔버스·인쇄폭 계산은 A와 같은 값을 쓴다(한 벌로 보여야 하므로).

## C-3. 검사기가 잡는 것 — 네 가지, 전부 실제 bbox 측정

1. 글자 ↔ 글자 교차
2. **칸 넘침** — 자기 칸을 벗어남
3. **칸 침범** — 남의 칸을 파고듦
4. **도판 이탈** — 그림 경계 밖

`--assert-no-overlap` 이 하나라도 걸리면 **exit 2**.

> **`Checker` 에는 잎 상자만 등록한다.** 칸 안에 칸을 등록하면 안쪽 글자가 바깥 칸을
> 「침범」한 것으로 잡혀 거짓 적발이 난다.

> ★ 반증 테스트가 실제 버그를 두 개 잡았다(2026-09-01).
> 그중 하나는 **진도표 막대 라벨이 6pt 로 렌더되고 있었는데 이전 판이
> 「충돌 0건」으로 통과**시킨 것이다. `fs_min` 을 「축소 하한」이 아니라
> **인쇄 가독 하한**으로 확정해 잡았다. 이 저장소가 세 번 당한 거짓 통과와 같은 부류다.

## C-4. 스펙 예시

`specs/hthp_org_fig5.yaml` (조직도) · `specs/hthp_gantt_fig6.yaml` (진도표) ·
`specs/hthp_risk_fig7.yaml` (위험도 매트릭스) 를 그대로 본떠 쓴다.

**지켜야 할 것은 A와 같다** — 배경 흰색 · 인쇄 폭(`width_mm`)으로 저작 ·
상태점 번호·도면 내 수치·그룹박스 넣지 않기.

---

## ★ 2026-09-10 실측 정정 — Gemini 가 한글 라벨을 정확히 낸다

경로 C 를 만든 근거는 *「라벨이 곧 내용인데 AI 이미지가 한글을 정확히 못 넣는다」*
였다. **이번 실측에서 그 전제가 깨졌다.**

AI 냉매 과제의 조직도·진도표를 Gemini 로 만들어 대조했다.

| | 결과 |
|---|---|
| 조직도 | 라벨 **11개 전부 정확** (기관명·역할 포함) |
| 진도표 | 행 6 + 막대 6 + 연도 4, **전부 정확**. `REFPROP`·`ATW`·`100 g/day` 혼재도 무사 |
| 배경 | 둘 다 **네 모서리 순백** |

**그러므로 「AI 는 한글을 못 넣는다」를 경로 판정 근거로 쓰지 않는다.**
대신 남는 차이로 고른다.

| 기준 | 격자 엔진 (C) | Gemini (B) |
|---|---|---|
| **해상도** | **3200×1800** | 1024×572 (3배 작다) |
| **재현성** | 같은 입력 → 같은 그림 | 회차마다 다르다 |
| **수정 비용** | YAML 한 줄 | 다시 생성 |
| **겹침 검사** | `--assert-no-overlap` exit 2 | 없다 |
| 제작 시간 | 1초 | 1~2분 + 브라우저 |

**판정 규칙 (갱신)**

- **재현이 필요하면 C.** 같은 계획서를 여러 번 조립하거나, 값이 바뀔 수 있거나,
  다른 PC 에서 같은 그림이 나와야 하면 격자 엔진을 쓴다
- **한 번 쓰고 마는 그림이면 B 도 된다.** 시연·발표용처럼 재생성할 일이 없으면
  Gemini 가 보기 좋고 빠르다
- **인쇄 품질이 중요하면 C.** 1024×572 는 본문폭(48,189 HWPUNIT)에 넣으면
  3배 확대돼 흐려진다

---

# 경로 B — 그 외 그림 (Chrome MCP → Gemini)

## B-1. 프롬프트 규칙

**고정 블록 3개 + 가변 슬롯 1개**로 쓴다. 고정 블록을 매 그림마다 그대로 반복해야
그림들이 한 벌로 보인다.

```
[1] 형식     Generate a 16:9 landscape image.
[2] 스타일   flat isometric vector infographic, deep navy and steel blue palette,
             warm orange accents only on the heat/energy path,
             PURE WHITE background (#FFFFFF), thin clean linework,
             no drop shadows, generous white space
[3] 주제     ← 여기만 그림마다 바꾼다
[4] 금지     CRITICAL: the image must contain absolutely NO text, NO letters,
             NO numbers, NO labels, NO signage, NO logos, NO gauges with digits.
             Every surface that would normally carry writing must be left blank
             or covered with a plain geometric pattern.
             The background must be pure white, not cream, not ivory, not beige.
```

### 왜 흰 배경을 강제하는가 (사용자 지시)

**바탕이 흰색이 아니면 남의 그림을 가져온 것처럼 보인다.** Gemini는 그냥 두면
아이보리·크림색 배경을 즐겨 쓴다. 프롬프트에 `PURE WHITE background (#FFFFFF)` 와
`not cream, not ivory, not beige` 를 **둘 다** 넣어야 흰색이 나온다.
받은 뒤 아래 B-4로 반드시 기계 검사하라.

### 왜 글자를 금지하는가

이미지 안의 글자는 **한글 텍스트 추출에 잡히지 않는다.** 평가가 LLM Council의
HWPX 자동 채점이므로, 그림이 지는 의미는 전부 **캡션**(네이티브 HWPX 텍스트)이
담아야 한다. 게다가 AI 이미지는 한글을 깨뜨린다.

## B-2. 절차

```
1) tabs_create_mcp → navigate  https://gemini.google.com/app
2) 프롬프트 입력 + 전송   ← 좌표 클릭 말고 JS로 (아래)
3) 40~60초 대기
4) **대화 맨 아래로 스크롤**   ← 안 하면 이미지가 지연 로딩이라 안 잡힌다
5) Chrome 창을 포그라운드로 올린다
6) canvas → 클립보드
7) PowerShell로 클립보드를 PNG로 저장
```

### 어느 AI 를 쓸지 먼저 묻는다

```
Gemini 와 ChatGPT 중 어느 쪽으로 그릴까요? (기본: Gemini)
```

| | 주소 | 입력 요소 | 상태 |
|---|---|---|---|
| **Gemini** | `https://gemini.google.com/app` | `div[contenteditable="true"]` | **실측 완료** |
| **ChatGPT** | `https://chatgpt.com` | `div#prompt-textarea` (contenteditable) | 입력 요소만 확인 |

> ChatGPT 는 버튼에 `data-testid` 를 쓴다(`composer-plus-btn` 등). 전송 버튼은
> **글자를 넣어야 나타나므로** 붙여넣기 **뒤에** `read_page` 로 찾는다.
> 로그인이 안 돼 있으면 `login-button` 이 보인다 — 그때는 사용자에게 로그인을 청한다.

### 입력·전송 — ★ JS 로는 안 된다 (2026-09-09 실측)

**클립보드 붙여넣기 + 실제 클릭**이라야 한다.

```powershell
Set-Clipboard -Value (Get-Content <프롬프트파일> -Raw -Encoding UTF8)
```

```
① computer left_click   → 입력창 (screenshot 으로 좌표를 먼저 잡는다)
② computer key ctrl+v
③ javascript_tool       → 입력 길이 확인 + 전송 버튼 좌표 계산
④ computer left_click   → 전송 버튼 좌표
```

> ★ **왜 JS 가 안 되나.** `document.execCommand('insertText')` 는 DOM 에는
> 글자를 넣지만 **프레임워크 상태가 그걸 모른다.** 화면에는 빈 입력창이 그대로
> 보이고 전송 버튼을 눌러도 아무 일도 일어나지 않는다.
> 합성 `PointerEvent`·`MouseEvent` 도 마찬가지다(`isTrusted` 검사로 보인다).
> **세 번 막히고 실제 클릭으로 뚫렸다.**
>
> JS 는 **읽기 전용**으로만 쓴다 — 입력 길이, 버튼 좌표, 응답 대기.

> Gemini 전송 버튼은 `aria-label="메시지 보내기"` 다. `보내기` 로 부분 매칭하면
> **`공유 및 내보내기`** 가 먼저 잡힌다 — 누르면 안 되는 버튼이다.

> **모델을 고른다.** Gemini 기본값 Flash 는 긴 입력을 거부한다(실측: 11,562자
> 거부). 입력창 오른쪽 모델 선택기에서 **Pro** 로 바꾼다.

### ★ 좌표로 클릭하지 마라 — `ref` 를 쓴다 (2026-09-09 실측)

도구 프레임과 페이지 뷰포트의 **좌표계가 다르다.**

    도구 프레임   933 x 564
    뷰포트       1153 x 697      ← 0.809배

`getBoundingClientRect()` 로 얻은 좌표를 그대로 클릭하면 **엉뚱한 곳을 눌러
`document.activeElement` 가 BODY 가 된다.** 붙여넣기가 조용히 무시된다.

**해법은 좌표를 안 쓰는 것이다.**

```
find("Gemini prompt input textbox")  →  ref_NNN
computer left_click  ref=ref_NNN     →  activeElement 가 입력창이 된다
computer key ctrl+v
find("send message button")          →  ref_MMM
computer left_click  ref=ref_MMM
```

**클릭한 뒤에는 반드시 확인한다.**

```javascript
document.activeElement === document.querySelector('div[contenteditable="true"]')
```

`false` 면 클릭이 빗나간 것이다. 다시 좌표를 계산하지 말고 `ref` 로 가라.

> 이것 때문에 오늘 세 번 막혔다. 「Chrome 창이 포그라운드가 아니라서」라고
> 잘못 진단했는데, `document.hasFocus()` 는 내내 `true` 였다.

### 받아오기 — 이 세 가지가 다 막힌다는 걸 알고 시작하라

Gemini 이미지는 `blob:https://gemini.google.com/...` 다.
- blob을 페이지 밖에서 fetch → **차단**
- 페이지가 로컬 서버로 POST → **Chrome 사설망 접근 차단(PNA)**
- **클립보드 → 동작함.** 단 Chrome 창이 **포그라운드**여야 한다
  (아니면 `NotAllowedError: Document is not focused`)

```bash
powershell.exe -File scripts/gemini_image.ps1 -Focus
```
```javascript
const sc = document.querySelector('infinite-scroller') || document.scrollingElement;
sc.scrollTop = sc.scrollHeight;                 // ★ 지연 로딩 해제
await new Promise(r=>setTimeout(r,2500));
const imgs = Array.from(document.querySelectorAll('img')).filter(i=>i.naturalWidth>300);
const img = imgs[imgs.length-1];
const c = document.createElement('canvas');
c.width = img.naturalWidth; c.height = img.naturalHeight;
c.getContext('2d').drawImage(img,0,0);
const blob = await new Promise(r=>c.toBlob(r,'image/png'));
await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);
```
```bash
powershell.exe -File scripts/gemini_image.ps1 -Save "workspace/<과제>/figures/figNN_....png"
```
> 스크롤과 `-Focus` 사이에 시간이 벌어지면 포커스를 잃는다.
> `Document is not focused` 가 나면 **`-Focus` 를 다시 부르고 바로 캡처**하라.
>
> **★ 캡처 전에 클립보드를 비워라.** 안 비우면 쓰기가 늦거나 실패했을 때
> 직전 그림이 그대로 남아 **다른 파일명으로 같은 그림이 조용히 저장된다**
> (실측: fig01과 fig02가 sha256까지 동일했다).
> ```powershell
> Add-Type -AssemblyName System.Windows.Forms
> try { [System.Windows.Forms.Clipboard]::Clear() } catch { }
> ```
> 저장 후 **직전 그림과 sha256을 대조**해 같으면 다시 받아라.
>
> **★★ PowerShell 로 포커스를 잡는 것보다 확실한 방법이 있다 (실측 2026-08-19).**
> `AppActivate` 는 성공을 보고하고도 `document.hasFocus()` 가 `false` 인 일이 잦다
> (PowerShell 프로세스가 끝나면 포커스가 되돌아간다).
> **페이지 안의 요소를 `computer` 로 클릭하면 그 자체로 탭에 포커스가 간다.**
> Gemini 의 `aria-label="이미지 복사"` 버튼을 `find` 로 잡아 클릭한 뒤
> **바로 다음 호출에서 캔버스→클립보드**를 실행하면 확실히 성공한다.
> `-Focus` 는 이 경로가 막혔을 때의 보조 수단으로만 쓴다.
>
> **★ 사용자가 컴퓨터를 쓰는 중이면 창을 반복해서 가로채지 마라.**
> 페이지 클릭 경로도 실패하면 **사용자에게 창을 앞에 둬 달라고 요청**하라.

## B-3. 해상도 — Gemini는 1024×572 고정이다

게이트 3.6b가 **가로 2000px 이상**을 요구한다(본문폭 300 DPI). 2배로 올려라.
평면 벡터풍 그림이라 LANCZOS 확대가 사진보다 훨씬 잘 버틴다.

```python
from PIL import Image, ImageFilter
im = Image.open(p).convert("RGB"); w, h = im.size
up = im.resize((w*2, h*2), Image.LANCZOS)
up = up.filter(ImageFilter.UnsharpMask(radius=1.4, percent=45, threshold=3))
up.save(p, "PNG", optimize=True)
```
manifest의 `px` 를 확대 후 크기로 적어라.

## B-4. 흰 배경 기계 검사 (눈으로만 보지 마라)

```python
from PIL import Image
im = Image.open(p).convert("RGB")
w, h = im.size
# 네 모서리 20px 평균이 흰색에 가까운가
xs = [(0,0), (w-20,0), (0,h-20), (w-20,h-20)]
bad = []
for x, y in xs:
    px = im.crop((x, y, x+20, y+20)).resize((1,1)).getpixel((0,0))
    if min(px) < 244 or max(px) - min(px) > 6:
        bad.append(px)
assert not bad, f"배경이 흰색이 아니다: {bad}"
```
실패하면 **프롬프트에 흰 배경 문구를 강화해 다시 생성**하라.
이미지 편집으로 배경만 칠하지 마라 — 도형 가장자리가 상한다.

---

# ★ 파일명은 ASCII 로 (2026-09-09 실측)

    fig1_system.png      O
    fig1_시스템개요도.png   X  ← kordoc 이 못 찾는다

**오류를 내지 않는다.** `이미지 임베드: 0개` 로 조용히 지나가고 조립본의
`hp:pic` 이 0장이 된다. 캡션 텍스트는 한글로 쓰되 **파일명만** 영문이면 된다.

조립 후 반드시 센다.

```bash
python -c "
import zipfile
z=zipfile.ZipFile('<문서>.hwpx')
print(len([n for n in z.namelist() if n.startswith('BinData/')]))"
```

---

# 산출물 — 본문에 넣는 방법 (2026-09-10 실측으로 정정)

## 마크다운 이미지 참조가 정식 경로다

```markdown
**[그림 1] 200℃급 고온 히트펌프-MVR 연계 시스템 개요도**

![시스템 개요도](fig1_system.png)
```

- 캡션은 **그림 바로 위** 한 줄, `**[그림 N] 제목**` 형태
- 경로는 **파일명만** 쓴다. 조립기가 `<워크스페이스>/figures/` 를 `--image-dir` 로 넘긴다
- **파일명은 ASCII** — 한글이면 kordoc 이 못 찾고 **오류 없이 0장**이 된다

## ★ `figure_manifest.json` 은 조립기가 읽지 않는다

전에는 이 문서가 `[FIG-N]` 플레이스홀더 → `figure_manifest.json` → 조립기가
자리를 찾는 **결합 계약**을 규정했다. **그 경로는 `harness_assemble.py` 에
물려 있지 않다**(2026-09-10 확인). 문서만 보고 `[FIG-N]` 방식으로 쓰면
**그림이 한 장도 안 들어간다.**

manifest 를 만들어 두는 것 자체는 해가 없다(그림 이력·스펙 추적). 다만
**본문 삽입은 마크다운 참조로 한다.** 캡션은 어차피 사람이 읽는 텍스트로
넣고 있어 제목 대조·번호 재부여의 이점이 크지 않다.

## 캡션 규칙

- **명사형으로 끝낸다** (`…구성`, `…구조`, `…경로`)
- **캡션이 그림의 의미를 전부 져야 한다** — 그림 안에 글자가 없기 때문이다
- 번호는 **문서 등장 순서대로** `그림 1`·`그림 2`
- 표는 위, 그림은 아래가 관례지만 이 파이프라인은 **캡션을 그림 위**에 둔다
  (마크다운에서 앞줄이 곧 캡션이 되므로)

## 조립 후 반드시 센다

```bash
python -c "
import zipfile
z=zipfile.ZipFile('<문서>.hwpx')
print(len([n for n in z.namelist() if n.startswith('BinData/')]))"
```

**0 이면 그림이 안 들어간 것이다.** 파일명이 한글인지, `figures/` 에 있는지 본다.

# 자가검증 (필수)

1. `Read`로 생성된 PNG를 **직접 열어 눈으로 확인**한다.
   - **배경이 흰색인가** (B-4 기계 검사도 함께)
   - 글자·숫자가 섞여 들어가지 않았는가
   - 라벨이 도형·선과 겹치지 않는가 (경로 A)
   - 배관 방향(화살촉)이 사이클 순서와 맞는가 (경로 A)
   - 그림들이 서로 같은 테마로 보이는가
2. 게이트:
   ```bash
   PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.quality.gate --stage S3 --figures workspace/<과제>/figures
   ```

# 절대 하지 말 것

- **사이클 그림을 Gemini로 그리지 마라.** 위상이 틀린다.
- **사이클이 아닌 복잡한 그림을 개괄도 엔진으로 억지로 그리지 마라.** 도형 어휘가 없다.
- 배경이 흰색이 아닌 그림을 통과시키지 마라.
- 허구의 데이터로 결과 그래프를 그리지 마라. 개념도·흐름도는 OK.
- 표를 이미지로 만들지 마라.
- 그림 안에 캡션을 넣지 마라.
- `--assert-no-overlap` 결과를 무시하지 마라.
