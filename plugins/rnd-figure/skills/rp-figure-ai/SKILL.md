---
name: rp-figure-ai
description: 사이클 개괄도를 제외한 연구계획서 그림을 AI 이미지로 만든다. "조직도", "추진체계도", "역할 분담", "진도표", "간트", "마일스톤", "위험도 매트릭스", "기대효과 그림", "개념도", "그림 그려줘"를 요청하면 사용한다. Gemini 와 ChatGPT 중 사용자가 고르며 Chrome MCP 로 웹 화면을 쓴다(API 키 불필요). 사이클 개괄도는 이 스킬이 아니라 rp-schematic 을 쓴다.
---

# AI 이미지 그림 스킬 (Gemini · ChatGPT)

## 0. 맡는 것 / 안 맡는 것

| | |
|---|---|
| **맡는다** | 조직도 · 추진체계도 · 진도표(간트) · 마일스톤 · 위험도 매트릭스 · 기대효과 · 개념도 |
| **안 맡는다** | **사이클 개괄도** → `rp-schematic` (위상이 곧 연구 내용이라 코드로 그린다) |

## 1. ★ 먼저 어느 AI 를 쓸지 묻는다

```
Gemini 와 ChatGPT 중 어느 쪽으로 그릴까요? (기본: Gemini)
```

| | 주소 | 입력 요소 | 상태 |
|---|---|---|---|
| **Gemini** | `https://gemini.google.com/app` | `div[contenteditable="true"]` | **실측 완료** |
| **ChatGPT** | `https://chatgpt.com` | `div#prompt-textarea` | 입력 요소만 확인 |

ChatGPT 전송 버튼은 **글자를 넣어야 나타난다** — 붙여넣기 **뒤에** `read_page` 로 찾는다.
로그인이 안 돼 있으면 `login-button` 이 보인다. 그때는 사용자에게 로그인을 청한다.

## 2. 프롬프트 — 라벨을 정확히 적어 준다

**★ 2026-09-10 실측: Gemini 가 한글 라벨을 정확히 낸다.**
조직도 11개·진도표 16개 라벨이 전부 맞았고 `REFPROP`·`ATW`·`100 g/day` 혼재도 무사했다.
**그러므로 라벨을 빼지 말고 그대로 적어 준다.**

```
Generate a 16:9 landscape <조직도/간트/매트릭스> image for a Korean government R&D proposal.

Style: flat vector infographic, deep navy and steel blue palette,
warm orange accent on <강조할 곳>, PURE WHITE background (#FFFFFF),
thin clean linework, no drop shadows, clean Korean typography.

<여기에 들어갈 한글 라벨을 계층·순서 그대로 적는다>

The Korean text must be rendered correctly and legibly. Do not invent extra text.
The background must be pure white, not cream, not ivory, not beige.
```

- **흰 배경을 두 번 말한다** (`PURE WHITE` + `not cream, not ivory, not beige`).
  그냥 두면 Gemini 는 아이보리를 즐겨 쓴다
- **`Do not invent extra text`** — 없는 라벨을 지어내는 것을 막는다

## 3. Chrome MCP 절차 — 여기서 세 번 막혔다

```
1) tabs_context_mcp {createIfEmpty: true}
2) navigate  <주소>
3) PowerShell  Set-Clipboard  로 프롬프트 적재
4) ★ JS 로 입력창에 focus()          ← ref 클릭·좌표 클릭보다 확실하다
5) computer key ctrl+v
6) 입력 길이 확인 (JS)
7) 전송 버튼 좌표를 **프레임 배율로 환산**해 클릭
8) 이미지 대기 → 캔버스 → 클립보드 → PowerShell 저장
```

### ★ 함정 셋 (전부 오류 없이 조용히 실패한다)

**① 클립보드가 덮인다.** 다른 도구가 클립보드를 쓰면 엉뚱한 게 붙는다.
**붙여넣기 직전에 내용을 확인한다.**

```powershell
$c = Get-Clipboard -Raw; Write-Output "$($c.Length)자 / $($c.Substring(0,40))"
```

**② 좌표계가 프레임마다 다르다.** 도구 프레임(933×564 또는 1400×846)과
뷰포트(1153×697)의 배율이 다르다. `getBoundingClientRect()` 값을 그대로 쓰면
**엉뚱한 곳을 눌러 `activeElement` 가 BODY 가 된다.**

```javascript
const k = <프레임 가로> / innerWidth;
const frameXY = [Math.round(vx * k), Math.round(vy * k)];
```

**③ 포커스는 JS 로 준다.** `ref` 클릭·좌표 클릭이 입력창을 못 잡는 경우가 있다.

```javascript
const ed = document.querySelector('[contenteditable="true"]');
ed.focus();
document.activeElement === ed;   // ← 반드시 true 인지 확인한다
```

`false` 면 붙여넣기가 무시된다. **확인 없이 다음으로 가지 마라.**

### 이미지 받아오기

`blob:` URL 이라 페이지 밖에서 못 읽는다. **캔버스 → 클립보드**가 유일한 길이다.

```javascript
const img = [...document.querySelectorAll('img[src^="blob:"]')].pop();
const c = document.createElement('canvas');
c.width = img.naturalWidth; c.height = img.naturalHeight;
c.getContext('2d').drawImage(img, 0, 0);
const blob = await new Promise(r => c.toBlob(r, 'image/png'));
await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
```

```powershell
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$img = [System.Windows.Forms.Clipboard]::GetImage()
$img.Save("<경로>\figN_name.png", [System.Drawing.Imaging.ImageFormat]::Png)
```

**막히면 2~3회에서 멈추고 사용자에게 보고한다.** 같은 동작을 반복하지 마라.

## 4. 받은 뒤 반드시 검사한다

**① 흰 배경 (기계)**

```bash
python -c "
from PIL import Image
im=Image.open('<파일>').convert('RGB'); w,h=im.size
print([im.getpixel(p) for p in [(10,10),(w-11,10),(10,h-11),(w-11,h-11)]])"
```

**② 라벨 (육안)** — `Read` 로 직접 열어 **한 글자씩 대조**한다.
기관명·연도·수치가 틀리면 못 쓴다. 다시 생성하거나 격자 엔진으로 돌린다.

## 5. 격자 엔진으로 되돌리는 판단

AI 가 한글을 낸다는 것이 확인됐으므로 **선택의 기준이 바뀌었다.**

| 기준 | 격자 엔진 `engine.figure.lattice` | AI 이미지 |
|---|---|---|
| **해상도** | **3200×1800** | 1024×572 (3배 작다) |
| **재현성** | 같은 입력 → 같은 그림 | 회차마다 다르다 |
| **수정 비용** | YAML 한 줄 | 다시 생성 |
| **겹침 검사** | `--assert-no-overlap` exit 2 | 없다 |
| 제작 시간 | 1초 | 1~2분 + 브라우저 |

> **재현이나 인쇄 품질이 걸리면 격자 엔진을 쓴다.**
> 같은 계획서를 여러 번 조립하거나, 값이 바뀔 수 있거나, 다른 PC 에서 같은 그림이
> 나와야 하면 AI 이미지는 맞지 않는다.

```bash
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.figure.lattice --spec specs/<이름>.yaml --out <출력>.png --assert-no-overlap
```

참고 스펙: `specs/airef_org_fig2.yaml`(조직도) · `specs/airef_gantt_fig3.yaml`(간트) ·
`specs/hthp_risk_fig7.yaml`(위험도 매트릭스)

## 6. 본문에 넣기

**마크다운 이미지 참조**가 정식 경로다. **파일명은 ASCII** —
한글이면 kordoc 이 못 찾고 **오류 없이 0장**이 된다.

```markdown
**[그림 2] 연구수행 체계 및 기관별 역할**

![수행체계](fig2_org_ai.png)
```

조립 후 **반드시 센다.**

```bash
python -c "
import zipfile
z=zipfile.ZipFile('<문서>.hwpx')
print(len([n for n in z.namelist() if n.startswith('BinData/')]))"
```

**0 이면 그림이 안 들어간 것이다.**

## 7. 양식의 그림 상한을 확인한다

하네스 기본 양식은 **그림 1장**이 상한이다. 여러 장을 넣으려면
워크스페이스의 `50_form_spec.json` 에서 `limits.figures` 를 올리고 **사유를 적는다.**

> ⚠️ **2026 경진대회 제출 계획서는 그림 0장이다**(심사가 그림을 평가하지 못한다).
> 그 계획서에 그림을 넣지 마라. 이 스킬은 시연·다른 문서용이다.
