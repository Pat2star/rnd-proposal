# 양식 추출 리포트 — kimm-basic

- 문단 12개, 표 0개
- paraPr 20 / charPr 12 / borderFill 2 (id 1~2) / style 23
- 본문폭: 계산 42520 / **실측 42520** (실측 우선)
- 목차 항목 0개, 안내문 0건, 형광펜 0건, 메모 0건

## 역할 매핑

| 역할 | paraPr | charPr | style | 신뢰도 | 근거 |
|---|---:|---:|---:|:---:|---|
| `heading_1` | 2 | 0 | 2 | low | 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 1'(engName=Outline 1, id=2)의 문단모양 2 / 글자모양 0을 후보로 제안한다 |
| `heading_2` | 3 | 0 | 3 | low | 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 2'(engName=Outline 2, id=3)의 문단모양 3 / 글자모양 0을 후보로 제안한다 |
| `heading_3` | 4 | 0 | 4 | low | 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 3'(engName=Outline 3, id=4)의 문단모양 4 / 글자모양 0을 후보로 제안한다 |
| `bullet_level_0` | 4 | 1 | — | medium | heading.type=OUTLINE, margin.left=3000 (본문 사용 2회) → 오름차순 0번째. 본문 미사용 BULLET paraPr ['2', '3', '5', '6', '7', ' |
| `bullet_level_1` | 6 | 0 | 6 | low | 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 5'(engName=Outline 5, id=6)의 문단모양 6 / 글자모양 0을 후보로 제안한다 |
| `bullet_level_2` | 7 | 0 | 7 | low | 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 6'(engName=Outline 6, id=7)의 문단모양 7 / 글자모양 0을 후보로 제안한다 |
| `bullet_level_3` | 7 | 0 | 7 | none | 양식에 대응 서식이 없어 'bullet_level_2' 설정을 전용함 |
| `body` | 0 | 0 | 0 | medium | 제목/글머리/앵커로 배정되지 않은 평문단 중 최빈 (heading=NONE, indent=0, intent=0) |
| `table_header` | 0 | 0 | 0 | low | 이 양식에는 표 사례가 없다. 표준 스타일 '바탕글'(engName=Normal, id=0)의 문단모양 0 / 글자모양 0을 후보로 제안한다 |
| `table_cell` | 0 | 0 | 0 | low | 이 양식에는 표 사례가 없다. 표준 스타일 '바탕글'(engName=Normal, id=0)의 문단모양 0 / 글자모양 0을 후보로 제안한다 |
| `figure_anchor` | 4 | 1 | 0 | medium | hp:pic을 직접 담은 문단 (텍스트 run이 없어 첫 run charPr로 폴백) |
| `table_anchor` | 0 | 0 | 0 | none | 양식에 대응 서식이 없어 'body' 설정을 전용함 |
| `figure_caption` | 0 | 0 | 0 | low | 이 양식에는 그림 캡션 사례가 없다. 표준 스타일 '바탕글'(engName=Normal, id=0)의 문단모양 0 / 글자모양 0을 후보로 제안한다 |
| `table_caption` | 0 | 0 | 0 | none | 양식에 대응 서식이 없어 'figure_caption' 설정을 전용함 |
| `bold` | — | 30 | — | medium | 본문 높이(1000)와 같은 bold charPr ['30', '32'] 발견 |

## 확인 질문 10개

> 답을 `profile.override.yaml`에 적으면 재추출해도 살아남는다.

**Q1. figure_anchor에 OUTLINE 문단모양 4를 쓰면 개요 번호가 자동으로 붙습니다. 그래도 이걸 쓰시겠습니까?**
- 근거: hp:pic을 직접 담은 문단 (텍스트 run이 없어 첫 run charPr로 폴백)

**Q2. bullet_level_0에 OUTLINE 문단모양 4를 쓰면 개요 번호가 자동으로 붙습니다. 그래도 이걸 쓰시겠습니까?**
- 근거: heading.type=OUTLINE, margin.left=3000 (본문 사용 2회) → 오름차순 0번째. 본문 미사용 BULLET paraPr ['2', '3', '5', '6', '7', '8'] 제외함

**Q3. heading_1을 표준 스타일 '개요 1'(paraPr 2 / charPr 0)로 잡았습니다. 본문에 이 역할의 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 1'(engName=Outline 1, id=2)의 문단모양 2 / 글자모양 0을 후보로 제안한다

**Q4. heading_2을 표준 스타일 '개요 2'(paraPr 3 / charPr 0)로 잡았습니다. 본문에 이 역할의 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 2'(engName=Outline 2, id=3)의 문단모양 3 / 글자모양 0을 후보로 제안한다

**Q5. heading_3을 표준 스타일 '개요 3'(paraPr 4 / charPr 0)로 잡았습니다. 본문에 이 역할의 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 3'(engName=Outline 3, id=4)의 문단모양 4 / 글자모양 0을 후보로 제안한다

**Q6. bullet_level_1을 표준 스타일 '개요 5'(paraPr 6 / charPr 0)로 잡았습니다. 본문에 이 역할의 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 5'(engName=Outline 5, id=6)의 문단모양 6 / 글자모양 0을 후보로 제안한다

**Q7. bullet_level_2을 표준 스타일 '개요 6'(paraPr 7 / charPr 0)로 잡았습니다. 본문에 이 역할의 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 본문에 이 역할의 사례가 없다. 표준 스타일 '개요 6'(engName=Outline 6, id=7)의 문단모양 7 / 글자모양 0을 후보로 제안한다

**Q8. table_header을 표준 스타일 '바탕글'(paraPr 0 / charPr 0)로 잡았습니다. 이 양식에는 표 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 이 양식에는 표 사례가 없다. 표준 스타일 '바탕글'(engName=Normal, id=0)의 문단모양 0 / 글자모양 0을 후보로 제안한다

**Q9. table_cell을 표준 스타일 '바탕글'(paraPr 0 / charPr 0)로 잡았습니다. 이 양식에는 표 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 이 양식에는 표 사례가 없다. 표준 스타일 '바탕글'(engName=Normal, id=0)의 문단모양 0 / 글자모양 0을 후보로 제안한다

**Q10. figure_caption을 표준 스타일 '바탕글'(paraPr 0 / charPr 0)로 잡았습니다. 이 양식에는 그림 캡션 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 이 양식에는 그림 캡션 사례가 없다. 표준 스타일 '바탕글'(engName=Normal, id=0)의 문단모양 0 / 글자모양 0을 후보로 제안한다

## borderFill 존 규칙 자기검증

> 존 규칙은 우리가 생성할 stub 없는 표용이다. 원본 재현율이 낮은 것은 정상이며, stub 열과 수작업 편집 때문이다.

| 표 | 크기 | 규칙 일치 | stub 열 |
|---|---|---|---|

## 미배정 ID

- paraPr: {}
- charPr: {}

## 경고

- BULLET paraPr ['2', '3', '5', '6', '7', '8']는 본문에서 쓰이지 않아(표 전용) 글머리 수준 후보에서 제외했다. 이 필터가 없으면 수준이 한 칸씩 밀린다.
- figure_anchor: paraPr 4는 heading=OUTLINE이라 한글이 개요 번호를 자동으로 붙인다. BULLET 또는 NONE 문단모양이 안전하다.
- bullet_level_0: paraPr 4는 heading=OUTLINE이라 한글이 개요 번호를 자동으로 붙인다. BULLET 또는 NONE 문단모양이 안전하다.
- heading_1: heading_1: 관측 사례 없음 → 스타일 이름으로 추정
- heading_2: heading_2: 관측 사례 없음 → 스타일 이름으로 추정
- heading_3: heading_3: 관측 사례 없음 → 스타일 이름으로 추정
- bullet_level_1: bullet_level_1: 관측 사례 없음 → 스타일 이름으로 추정 / paraPr 6는 heading=OUTLINE이라 한글이 개요 번호를 자동으로 붙인다. BULLET 또는 NONE 문단모양이 안전하다.
- bullet_level_2: bullet_level_2: 관측 사례 없음 → 스타일 이름으로 추정 / paraPr 7는 heading=OUTLINE이라 한글이 개요 번호를 자동으로 붙인다. BULLET 또는 NONE 문단모양이 안전하다.
- table_header: table_header: 관측 사례 없음 → 스타일 이름으로 추정
- table_cell: table_cell: 관측 사례 없음 → 스타일 이름으로 추정
- figure_caption: figure_caption: 관측 사례 없음 → 스타일 이름으로 추정
- bullet_level_3: bullet_level_3 미검출 → bullet_level_2 폴백 / paraPr 7는 heading=OUTLINE이라 한글이 개요 번호를 자동으로 붙인다. BULLET 또는 NONE 문단모양이 안전하다.
- table_anchor: table_anchor 미검출 → body 폴백
- table_caption: table_caption 미검출 → figure_caption 폴백
