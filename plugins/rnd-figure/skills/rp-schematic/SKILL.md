---
name: rp-schematic
description: 에너지 시스템 사이클 개괄도를 코드로 그린다. "시스템 개요도", "개괄도", "사이클도", "사이클 구성도", "히트펌프 구성도", "공정 계통도", "P&ID 풍 도면"을 요청하면 사용한다. 압축기·열교환기·밸브·팽창기가 배관으로 연결되는 그림이 대상이다. 조직도·진도표·기대효과 그림은 이 스킬이 아니라 rp-figure-ai 를 쓴다.
---

# 사이클 개괄도 스킬 (코드 · 결정적)

## 0. 이 스킬이 맡는 것 — 사이클 하나뿐이다

**압축기·열교환기·밸브·팽창기가 배관으로 연결되는가?** 그렇다면 여기다.
행과 열이 있는 격자(조직도·진도표·매트릭스)나 회화적 표현은 **`rp-figure-ai`** 로 간다.

> **왜 이것만 코드인가.** 사이클은 **위상(topology)이 곧 연구 내용**이다.
> 배관 하나가 잘못 연결되면 그림이 못생긴 게 아니라 **틀린 것**이다.
> AI 이미지는 위상을 정확히 그리지 못하고, 틀려도 그럴듯해 보인다.

## 1. 실행

```bash
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" python -m engine.figure.schematic --spec specs/<이름>.yaml \
       --out <워크스페이스>/figures/fig1_system.png --assert-no-overlap
```

**`--assert-no-overlap` 을 빼지 마라.** 라벨이 겹치면 exit 2 를 낸다.
이 프로젝트에서 `generation_report.md` 가 *"All component labels rendered correctly"*
PASS 를 선언했는데 실제 겹침이 8건 이상이었다. matplotlib stderr 가 비었다는 뜻일 뿐이었다.

## 2. 스펙 (선언적 YAML)

기존 것을 본뜬다.

| 스펙 | 무엇 |
|---|---|
| `specs/airef_system_fig1.yaml` | 단순 증기압축 사이클 (가장 최근, 가장 단순) |
| `specs/hthp_mvr_fig4.yaml` | MVR 연계 |
| `specs/hp_cascade_fig1.yaml` | 캐스케이드 4패널 |

### 문법 함정 둘 (실측)

**① 열원·열침은 `to` + `direction` 형식이다.** `from` 만 쓰면 `KeyError: 'to'`.

```yaml
- {to: evap.bottom, fluid: heat_source, direction: down, length: 0.09, dx: -0.07,
   into: true, label: "저온 열원"}
```

**② 열이 들어오는 쪽은 `into: true` 를 넣는다.** 안 넣으면 화살촉이 **밖으로** 향해
증발기에서 열이 나가는 그림이 된다(2026-09-10 실측: 이걸로 한 번 틀렸다).

## 3. 목표 기준선 — 사용자가 PowerPoint 로 직접 만든 그림

```
~/Desktop/실적/저널/IJ/2. (2026) HP cascade/2. 파일/26.07.22/paper/figures/
    Fig1_schematic.png     ← 목표물
    Fig1_source.pptx       ← 원본 (저장소 밖, 대외 공개 금지)
```

재현본을 원본과 나란히 놓고 「이 정도면 쓰겠다」가 나와야 한다.

## 4. 시각 문법 — 사람이 소유한다 (변경 금지)

```
상태점 번호 ✗   도면 내 수치 ✗   그룹 박스 ✗   범례 ✗
```

*「수치는 표로, 도면은 위상만」* 이 원칙이다. 사용자 논문 3편의 공통 철학이고,
어기면 사용자 스타일이 아니게 된다.

> ⚠️ 조사 중 나온 18KB matplotlib 스크립트를 목표로 삼지 마라. 그것은 이미지 생성
> 실패 후의 **일회용 폴백**이고 상태점·그룹박스·온도배지로 과잉 장식했다.

## 5. 자가검증 (필수)

1. `Read` 로 PNG 를 **직접 열어** 본다
   - **배관 방향(화살촉)이 사이클 순서와 맞는가** ← 가장 중요하다
   - 열원이 **들어오고** 열침이 **나가는가**
   - 배경이 흰색인가 (네 모서리)
   - 라벨이 도형·선과 겹치지 않는가
2. 네 모서리 기계 검사

```bash
python -c "
from PIL import Image
im=Image.open('<파일>.png').convert('RGB'); w,h=im.size
print([im.getpixel(p) for p in [(10,10),(w-11,10),(10,h-11),(w-11,h-11)]])"
```

## 6. 본문에 넣기

**마크다운 이미지 참조**가 정식 경로다. **파일명은 ASCII.**

```markdown
**[그림 1] 시스템 개요도**

![시스템 개요도](fig1_system.png)
```

조립기가 `<워크스페이스>/figures/` 를 `--image-dir` 로 자동 전달한다.
조립 후 `BinData/` 를 세라 — **0 이면 안 들어간 것**이고 오류는 나지 않는다.
