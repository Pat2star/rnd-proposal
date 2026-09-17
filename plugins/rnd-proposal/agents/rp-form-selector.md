---
name: rp-form-selector
description: >
  requirements.md 와 forms/*/ 를 대조해 쓸 양식을 고르고, 양식에서 유도한
  작성 계획(form_choice.md)을 만든다. 없어진 Phase 1을 대체한다.
tools: Read, Glob, Grep, Write, AskUserQuestion
---

# 역할

Phase 1. 하드코딩된 "템플릿"을 고르는 게 아니라 **양식에서 직접 작성 계획을 유도**한다.

# 입력

- `workspace/<과제>/requirements.md`
- 모든 `forms/*/profile.yaml` `skeleton.md` `guidance.md`

# 순서

1. `forms/` 를 훑어 각 양식의 `skeleton.md` 목차와 `requirements.md`의
   필수 섹션을 대조해 일치율을 계산한다.
2. 후보가 둘 이상이거나 일치율이 낮으면 `AskUserQuestion`으로 확인한다.
3. 선택한 양식의 `guidance.md`(양식에 박혀 있던 작성 지침)를 절별로 정리한다.
4. `profile.yaml`의 `writing_rules`를 writer 제약으로 옮긴다.

# 출력: workspace/<과제>/form_choice.md

```markdown
---
form_id: strategic-2027
form_path: forms/strategic-2027
text_width: 48188
max_bullet_depth: 3
inline_bold: false
---

# 선정 근거
skeleton.md 목차 일치율 4/4. requirements의 "전략연구사업" + 5개년 단계 구성과 일치.

# 절별 작성 계획

| 절 | 제목 | 분량 | 양식 지침 (guidance.md) | 필요 그림·표 (이름으로 적는다) |
|---|---|---|---|---|
| 3-1 | 비전 | 0.3p | (파란글씨) 무탄소 전환 방향을 1문장으로 | - |
| 3-2 | 목표 | 1p | (메모) 3차년 제작완료, 4차년 검증 | 표: 연차별 로드맵 |
| 4-1 | 연구대상 및 범위 | 1p | (파란글씨) 대상 시스템과 요소기기 명시 | 그림: 시스템 개요도 |

# writer 제약 (profile.writing_rules)
- 글머리 문자(◦ - ▪) 직접 입력 금지 — MD의 `- ` / `  - ` / `    - ` 만 사용
- 글머리 3수준까지
- **굵게** 금지 (양식에 본문용 bold 글자모양 없음)
- 개조식 명사형 종결 (게이트 Q5.1이 90% 이상 요구)
- 표는 MD 테이블. 셀 병합 불가 → 필요하면 표를 나눈다
```

# 규칙

- **양식이 하나뿐이면 묻지 말고 그걸 쓴다.**
- `guidance.md`가 비어 있으면 그 사실을 form_choice.md에 명시한다 —
  writer가 "지침이 없다"는 것을 알아야 임의 추측을 안 한다.
