# 다른 PC 에서 실행하기

**Claude Code 만 깔린 PC** 기준 전체 안내. 위에서부터 순서대로 하면 된다.

> 이 순서는 실제로 빈 폴더에 clone 해서 검증한 것이다.
> 마지막 검증: 2026-09-09 — `188 passed` · 조립 10쪽 · 게이트 3종 통과 ·
> **산출물 sha256 이 원본 PC 와 동일**.

---

# 1. 미리 깔 것 두 개

Claude Code 말고 **Python 과 Node.js** 가 필요하다.

| | 어디서 | 확인 |
|---|---|---|
| **Python 3.13** | <https://www.python.org/downloads/> | `python --version` |
| **Node.js 18+** (LTS) | <https://nodejs.org/> | `node --version` |

> ⚠️ Python 설치 화면에서 **`Add python.exe to PATH`** 를 반드시 체크한다.
> 안 하면 `python` 명령이 안 먹는다.

Node 는 직접 쓰지 않는다. HWPX 를 만드는 `kordoc` 을 `npx` 가 자동으로 받아 쓴다.

---

# 2. 저장소 받기

```bash
git clone https://github.com/Pat2star/Worktodo.git
cd Worktodo
```

**저장소는 비공개다.** 처음 clone 할 때 GitHub 로그인을 물으면 계정으로 인증한다.

받아지는 것(약 32MB):

| 폴더 | 무엇 |
|---|---|
| `engine/` | 양식 추출 · HWPX 조립 · 검증 · 그림 엔진 |
| `harness_patches/` | **류박사님 하네스 수정본 5개** (3장에서 쓴다) |
| `forms/` | 양식 추출본 7종 |
| `specs/` | 그림 스펙 YAML |
| `workspace/hthp-final/` | 완성된 계획서 (10쪽) |
| `tests/` | 188개 |
| `.claude/agents/`, `.claude/skills/` | 에이전트 8종 · 스킬 3종 |

---

# 3. 파이썬 패키지

```bash
pip install -r requirements.txt
```

`playwright install` 은 **하지 않아도 된다.** 옛 HTML 그림 엔진에만 쓰고,
지금 쓰는 개괄도·격자 엔진은 matplotlib 만 쓴다.

---

# 4. ★ 여기서 먼저 검증한다 (플러그인 깔기 전)

```bash
python -m pytest tests/ -q
```

**`188 passed` 가 나와야 한다.**

> **왜 플러그인보다 먼저 하나** — 엔진·게이트·그림·검증기는 플러그인 없이도 전부 돈다.
> 여기서 깨지면 **파이썬 문제**, 다음 단계 이후에 깨지면 **플러그인 문제**로 구분된다.
> 순서를 바꾸면 이 구분이 사라져서 원인을 못 찾는다.

이 188개는 「통과했다」가 아니라 **「결함을 심으면 잡는다」**를 확인하는 테스트가 섞여 있다.
예컨대 문서에 미해결 마커를 **일부러 심고** 게이트가 잡는지 본다.

---

# 5. 플러그인 설치 (Claude Code 안에서)

Claude Code 를 켜고 프롬프트에 **그대로** 친다.

```
/plugin marketplace add JINWOOYOO86/claude-skills-marketplace
/plugin install rfp-proposal-harness@jinwoo-skills
```

이걸 깔아야 조사·작성·평가 에이전트와 조립 스크립트가 돈다.

> 버전은 신경 쓰지 않아도 된다. `scripts/harness_assemble.py` 가 설치된 버전을
> 자동으로 찾고, 여러 개면 가장 높은 것을 쓴다.

---

# 6. ★ Windows 면 반드시 — 패치 덮어쓰기

플러그인 원본은 **한국어 Windows 에서 안 돈다.** 두 가지 결함이 있다.

| # | 증상 |
|---|---|
| ① | 게이트 5종이 **켜자마자 꺼진다** (`cp949` 가 `—` 를 출력 못 함) |
| ② | `gate_pages.py` 가 **WSL 전용** (`wslpath`·`which`·`cp` 는 리눅스 명령) |

`harness_patches/` 의 `.py` 5개를 플러그인의 같은 경로에 덮어쓴다.

**PowerShell:**

```powershell
$dst = (Get-ChildItem "$env:USERPROFILE\.claude\plugins\cache\jinwoo-skills\rfp-proposal-harness\*\skills\hwpx-writing\scripts" -Directory | Select-Object -Last 1).FullName
Copy-Item harness_patches\*.py $dst -Force
$dst   # 어디에 넣었는지 확인
```

**Git Bash:**

```bash
dst=$(ls -d "$HOME"/.claude/plugins/cache/jinwoo-skills/rfp-proposal-harness/*/skills/hwpx-writing/scripts | tail -1)
cp harness_patches/*.py "$dst" && echo "$dst"
```

덮어쓰는 파일: `gate_form.py` `gate_hwpx.py` `gate_pages.py` `gate_regress.py` `form_strip.py`

상세는 `harness_patches/README.md`.

---

# 7. 세팅이 끝났는지 — 3줄로 확인

```bash
# ① 테스트
python -m pytest tests/ -q

# ② 그림 엔진
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.figure.lattice --spec specs/hthp_org_fig5.yaml --out ./_o.png --assert-no-overlap

# ③ 조립 전 구간 (플러그인 필요)
python "$CLAUDE_PLUGIN_ROOT/scripts/harness_assemble.py" --run workspace/hthp-final --max-pages 10
```

| | 나와야 하는 것 |
|---|---|
| ① | `188 passed` |
| ② | 아무 말 없이 종료 (`_o.png` 생성). 라벨이 겹치면 exit 2 |
| ③ | 마지막 줄 **`✔ 10쪽 (상한 10)`** |

**③ 이 통과하면 전부 정상이다.**

---

# 7-1. 외부 교정을 쓰려면 (Phase 5)

계획서 작성 파이프라인의 **마지막 단계가 외부 모델 교정**이다. 코드가 아니라
**브라우저**를 쓰므로 조건이 다르다.

| 필요 | 왜 |
|---|---|
| **Chrome + Claude in Chrome 확장** | Chrome MCP 도구가 이걸로 붙는다 |
| **Gemini 로그인** | 그 브라우저 세션을 그대로 쓴다 |
| **Gemini 3.1 Pro 접근** | ★ **Flash 는 전문(약 11,500자)을 거부한다**(실측) |

셋 중 하나라도 없으면 **교정만 건너뛴다.** 나머지 파이프라인은 그대로 돈다.

**검사기는 브라우저 없이 돈다.** 교정본만 있으면 어디서든 검증된다.

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/check_proofread.py" --before <원본>.md --after <교정본>.md
```

`exit 2` 면 채택하지 않는다 — 수치·출처가 사라졌거나 골격이 바뀐 것이다.

---

# 8. 한컴오피스 (선택)

있으면 쪽수를 실측하고, 없으면 `kordoc` 으로 잰다. **없어도 된다.**

```bash
npx -y kordoc@4.12.3 render workspace/hthp-final/30_proposal.hwpx -o preview.svg
```

## 한컴이 멈출 때

한글을 강제 종료한 뒤 숨은 창이 남으면 COM 이 무한 대기한다.
게이트는 이 경우 **실패가 아니라 미채점**으로 처리한다(거짓 FAIL 방지).

**한글을 GUI 로 한 번 직접 실행했다 닫으면 풀린다.**

---

# 9. 실제로 쓰기 — 이렇게 요청한다

## 9-1. 가장 흔한 경우 — 계획서 한 편

**한 문장이면 된다.** 나머지는 파이프라인이 알아서 간다.

```
○○ 주제로 15쪽 계획서 만들어줘. 시스템 개요도·조직도·추진일정 그림 넣어서.
```

| 주면 좋은 것 | 예 | 안 주면 |
|---|---|---|
| **분량** | 「15쪽」 | **10쪽**으로 진행 |
| **그림 종류** | 「개요도·조직도·진도표」 | **그림 없이 진행** — 요청한 것만 넣는다. 조립기가 `requirements.md` 의 `figures:` 와 대조해 많으면 멈춘다 |
| **주제** | 「AI 냉매」 | 묻는다 |
| 양식 | 「이 양식으로」(.hwpx 첨부) | 하네스 기본 양식 |
| 근거 자료 | 「자료는 이 폴더에」 | 조사 4축을 새로 돌린다 |

### 파이프라인이 도는 순서

```
Phase 0.5  공고 탐색        [선택 — 주제를 직접 정하면 건너뛴다]
Phase 1    공고문·양식 파악                                    → S1
Phase 2    조사 4축 (기술·시장·정책·특허)   병렬
Phase 3    집필 · 그림 · 조립 · 분량 실측                      → S2·S3·S4·L
Phase 3.5  내용 검토
Phase 4    평가위원단 6인 채점 → 개정                          → H
Phase 5    외부 교정 (Gemini Pro)          [기본 수행]
```

**Phase 4~5 는 시간이 오래 걸린다**(위원 6인 + 개정). 초안만 필요하면
「평가위원단은 생략하고 초안까지만」이라고 말하면 된다.

## 9-2. 그림만 필요할 때 — 스킬 둘

스킬은 **이름으로 부르지 않아도 된다.** 말로 하면 성격을 보고 갈린다.

| 말하는 것 | 가는 곳 | 수단 |
|---|---|---|
| 「시스템 개요도」 「사이클도」 「히트펌프 구성도」 | **`rp-schematic`** | 코드 (결정적) |
| 「조직도」 「추진체계도」 「진도표」 「간트」 「위험도 매트릭스」 「기대효과 그림」 | **`rp-figure-ai`** | **Gemini 또는 ChatGPT (고른다)** |

### 왜 개요도만 코드인가

사이클은 **위상(topology)이 곧 연구 내용**이다. 배관 하나가 잘못 연결되면
못생긴 게 아니라 **틀린 것**인데, AI 이미지는 틀려도 그럴듯해 보인다.

### 직접 돌리려면

```bash
# 사이클 개괄도
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.figure.schematic --spec specs/airef_system_fig1.yaml        --out <워크스페이스>/figures/fig1_system.png --assert-no-overlap

# 격자 (조직도·간트·매트릭스) — 재현·인쇄가 걸릴 때
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.figure.lattice --spec specs/airef_org_fig2.yaml        --out <워크스페이스>/figures/fig2_org.png --assert-no-overlap
```

**`--assert-no-overlap` 을 빼지 마라.** 라벨이 겹치면 exit 2 다.

### 격자 엔진 ↔ AI 이미지, 어느 쪽인가

| 기준 | 격자 엔진 | AI 이미지 |
|---|---|---|
| 한글 라벨 | 정확 | **정확** (2026-09-10 실측으로 확인) |
| **해상도** | **3200×1800** | 1024×572 (3배 작다) |
| **재현성** | 같은 입력 → 같은 그림 | 회차마다 다르다 |
| 수정 | YAML 한 줄 | 다시 생성 |
| 겹침 검사 | exit 2 로 적발 | 없다 |

> **재현이나 인쇄 품질이 걸리면 격자.** 한 번 쓰고 마는 그림이면 AI 가 빠르다.

## 9-3. 표 · 특허 · 교정

| 말하는 것 | 스킬 |
|---|---|
| 「표 만들어줘」 「성과지표표」 「추진일정표」 | `rp-table` |
| 「특허 조사」 「선행특허」 「회피설계」 | `rp-patent` |
| 「교정」 「윤문」 「제미나이한테 봐달라고」 | `rp-proofread` |

**교정(`rp-proofread`)은 Phase 5 로 파이프라인에 들어 있다** — 따로 부르지 않아도
계획서 작성 끝에 돌아간다. 스킬로 부르는 건 **아무 문서나 교정할 때**다.

## 9-4. 완성본 다시 만들기

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/harness_assemble.py" --run workspace/<과제>                  # 명세값, 없으면 10쪽
python "$CLAUDE_PLUGIN_ROOT/scripts/harness_assemble.py" --run workspace/<과제> --max-pages 12   # 분량을 바꿀 때
```

`workspace/<과제>/30_proposal.md` 를 고치고 이 명령을 다시 돌린다.

> **분량은 여기 한 곳에서만 정한다.** `--max-pages` 를 주면 그 값이
> `50_form_spec.json` 의 `page_budget`(`total`·`hard_max`·장별 배분)에 그대로
> 써진다. 그래서 조립 하드캡과 `gate_pages` 가 **다른 수를 볼 수 없다**.
> 생략하면 명세에 적힌 값을 쓰고, 명세도 없으면 10쪽이다(사용자 규칙).
> 명령 첫 줄에 `[분량] 12쪽 — …` 로 어디서 온 수인지 찍는다.

> ⚠️ **마지막 행위는 반드시 이 조립이다.** 조립 뒤에 원고를 고치면
> 쪽수가 안 맞는데도 맞는 것처럼 보인다. 실제로 한 번 그랬다 —
> 「10쪽」이라 보고된 것이 실제로는 11쪽이었다.

## 9-5. 새 양식 투입

```bash
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.hwpx.extract_form <양식>.hwpx --out forms/<이름>
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.quality.gate --stage S1 --form forms/<이름>
```

> **S1 이 exit 2 로 멈추는 것이 정상이다.** 고장이 아니다.
> 스타일 역할 매핑은 **틀려도 검증기가 통과시키는 유일한 부류**라
> 사람이 승인하게 설계돼 있다. `extract_report.md` 의 질문에 답하고
> `profile.override.yaml` 에 적으면 재추출해도 정정이 살아남는다.

---

# 10. 검사기 셋 — 기계가 잡는 것

규칙은 문서에 적어도 안 지켜진다. **셋 다 코드로 센다.**

## 10-1. `check_wording` — 미뤄 놓은 티가 나는 표현

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/check_wording.py" --md workspace/<과제>/30_proposal.build.md
```

| 잡는 것 | 왜 |
|---|---|
| 「협약 시 확정」·「추후 확정」·「확정 예정」 | 정하는 **절차와 시점**을 쓰라는 뜻 |
| 「미확보」·「미확정」·「별도 산정」 | 값이 없으면 **그 문장을 빼라** |
| **영문 과제명이 비어 있음** | 국문이 있으면 짝이 있어야 한다 |

**「1차년도 설계에서 확정」처럼 시점이 적혀 있으면 통과한다.**
없는 사실을 지어내라는 뜻이 아니다.

## 10-2. `check_numbers` — 본문 수치가 근거팩에 있는가 ★

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/check_numbers.py" --md workspace/<과제>/30_proposal.build.md                                 --pack workspace/<과제>/_ws
```

**재현성의 마지막 구멍이 이것이었다.** 3회 실행에서 결론 일치도 0.64 의
유일한 원인이 「입력에 없는 값을 회차마다 다르게 채우는 것」이었다.

```
기술분류 비중   c1 50/30/20 안분 · c2 총액만 · c3 미정
```

기본은 **보고**다(계산값이 있을 수 있다). `--strict` 를 주면 exit 2.
**계산값이면 산출식을 본문에 적으면 된다.**

## 10-3. `check_proofread` — 교정본이 무엇을 지웠는가

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/check_proofread.py" --before <원본>.md --after <교정본>.md
```

외부 모델은 문장을 다듬으라는 지시에 **수치와 출처를 지운다**
(`COP 2.5` → 「높은 성능계수」). 수치·출처 소멸, 골격 마커 변동,
em-dash 복귀, 깨진 표 칸을 잡는다. `exit 2` 면 채택하지 않는다.

---

# 11. 게이트 셋 — 서식·분량

류박사님 하네스의 게이트에 이식성 수정 3건을 얹은 것이다(`harness_patches/`).

```bash
W=workspace/<과제>
S=$W/50_form_spec.json     # 없으면 플러그인 기본 명세

python "$CLAUDE_PLUGIN_ROOT/harness_patches/gate_form.py"  --hwpx $W/30_proposal.hwpx        --md $W/30_proposal.build.md --spec $S
python "$CLAUDE_PLUGIN_ROOT/harness_patches/gate_hwpx.py"  --hwpx $W/30_proposal.hwpx
python "$CLAUDE_PLUGIN_ROOT/harness_patches/gate_pages.py" --hwpx $W/30_proposal.hwpx --spec $S --allow-estimate
```

| 게이트 | 본다 |
|---|---|
| `gate_form` | 글자 크기·굵기·개조식·표 열 수·**골격(리드·슬롯)** |
| `gate_hwpx` | HWPX 구조 무결성 |
| `gate_pages` | **한컴 실측 쪽수** |

**`gate_pages` 가 「미측정」을 내면 실패가 아니다** — 한컴 COM 이 죽은 것이고
거짓 FAIL 을 피하려는 설계다. 잔류 `Hwp` 프로세스를 정리하거나
한글을 GUI 로 한 번 열었다 닫으면 풀린다.

## 양식 명세를 고쳐야 할 때

양식마다 상한이 다르다. 기본 양식은 **그림 1장 · 표 7개 · 10쪽**이다.
더 필요하면 워크스페이스의 `50_form_spec.json` 에서 고치고 **사유를 적는다.**

```json
"limits": { "figures": 3, "figures_note": "시연용 3장. 제출본은 0장." },
"page_budget": { "hard_max": 15 }
```

> **게이트 판정 기준은 사람이 소유한다.** AI 가 임의로 올리지 않는다.

---

# 12. 안 될 때

| 증상 | 원인 · 조치 |
|---|---|
| `python` 을 못 찾음 | 설치 시 **Add to PATH** 누락 |
| `pytest` 가 `188 passed` 가 아님 | §3 `pip install` 누락 또는 Python 버전 |
| 게이트가 아무 출력 없이 죽음 | **§6 패치 미적용** (`cp949` 크래시) |
| `gate_pages` 가 `WinError 2` | 같음 |
| `rfp-proposal-harness 가 설치돼 있지 않다` | §5 플러그인 설치 |
| 조립이 쪽수를 **「미측정」** | 한컴 잔류 프로세스. 한글을 GUI 로 열었다 닫는다 |
| **그림이 안 들어감** (`BinData 0`) | **파일명이 한글**이다. ASCII 로 바꾼다 |
| 쪽수가 원본과 다름 | `kordoc` 을 **4.12.3** 에서 바꾸지 마라 |
| S1 이 exit 2 | **정상**. 역할 매핑은 사람이 승인한다 |
| Chrome MCP 붙여넣기가 안 먹음 | 클립보드가 덮였는지 먼저 확인. 좌표 대신 JS `.focus()` |

## 조립 후 반드시 세는 것

```bash
python -c "
import zipfile
z = zipfile.ZipFile(r'workspace/<과제>/30_proposal.hwpx')
print('그림', len([n for n in z.namelist() if n.startswith('BinData/')]))"
```

**0 이면 그림이 안 들어간 것이다.** 이 실패는 **오류를 내지 않는다.**

---

# 13. 무엇이 재현되고 무엇이 안 되는지

**정직하게 적는다.** 실측값이다.

| 층 | 재현성 |
|---|---|
| 양식 추출 · 조립 · 게이트 · 그림 엔진 | **완전** |
| **조립 산출물 바이트** | **완전** — 같은 원고면 sha256 이 같다 |
| 문서 **구조** | **완전** (L2 = 1.00) |
| 문서 **결론·수치** | **미달** (L6 = 0.83, 목표 0.90) |

## 다른 PC 에서 받는 인상 — 구체적으로

> **같은 계획서의 다른 원고**다. 다른 계획서가 아니다.

**안 바뀌는 것**: 주제·과제명·연구기간·최종목표·절 구성·글자크기·여백·띄어쓰기.
서식은 `header.xml` 을 **바이트 그대로** 쓰므로 무너질 수 없다.

**갈리는 것** (3회 실행 실측):

| 종류 | 예 |
|---|---|
| 표 헤더 이름·행 나눔 | `\| 구분 \|` ↔ `\| 항목 \|` · 요약문 표 12/15/13행 |
| 자유 서술 | 영문 과제명이 회차마다 다른 문장 |
| **★ 입력에 없는 수치** | 기술분류 비중 `50/30/20` ↔ `총액만` ↔ `미정` |

마지막 것이 L6 를 끌어내린 **유일한 원인**이고, **`check_numbers.py` 가 이제 그것을 센다**(§10-2).

## 주장할 수 있는 것

> **「양식이 바뀌어도 형태가 무너지지 않는다」** — 기계가 증명한다.
>
> **「같은 계획서가 나온다」** — 아직 아니다. 구조는 같고 결론이 갈린다.
