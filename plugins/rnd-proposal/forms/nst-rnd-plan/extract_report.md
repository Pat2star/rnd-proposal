# 양식 추출 리포트 — nst-rnd-plan

- 문단 269개, 표 4개
- paraPr 58 / charPr 86 / borderFill 98 (id 1~98) / style 38
- 본문폭: 계산 48190 / **실측 48188** (실측 우선)
- 목차 항목 6개, 안내문 25건, 형광펜 0건, 메모 1건

## 역할 매핑

| 역할 | paraPr | charPr | style | 신뢰도 | 근거 |
|---|---:|---:|---:|:---:|---|
| `heading_1` | 14 | 51 | 2 | high | heading=NONE, indent=0, 글자높이 1300(본문 1100 초과), 텍스트 ^N. , tabPr=0, 첫등장 #216, 본문 3회 — 일치 신호 3개(텍스트패턴/글자높이/등장순서) |
| `heading_2` | 41 | 50 | 3 | high | heading=NONE, indent=0, 글자높이 1200(본문 1100 초과), 텍스트 패턴없음, tabPr=1, 첫등장 #217, 본문 3회 — 일치 신호 3개(글자높이/탭설정/등장순서) |
| `heading_3` | 14 | 63 | 2 | low | 본문에 이 역할의 사례가 없다. 표준 스타일 '제목'(engName=Outline 3, id=2)의 문단모양 14 / 글자모양 63을 후보로 제안한다 |
| `bullet_level_0` | 39 | 54 | — | medium | heading.type=BULLET, margin.left=1500 (본문 사용 8회) → 오름차순 0번째. 본문 미사용 BULLET paraPr ['15', '19', '38'] 제외함 |
| `bullet_level_1` | 49 | 11 | — | medium | heading.type=BULLET, margin.left=2500 (본문 사용 13회) → 오름차순 1번째. 본문 미사용 BULLET paraPr ['15', '19', '38'] 제외함 |
| `bullet_level_2` | 39 | 54 | 4 | low | 본문에 이 역할의 사례가 없다. 표준 스타일 '◦ '(engName=Outline 6, id=4)의 문단모양 39 / 글자모양 54을 후보로 제안한다 |
| `bullet_level_3` | 39 | 54 | 4 | none | 양식에 대응 서식이 없어 'bullet_level_2' 설정을 전용함 |
| `body` | 16 | 8 | 0 | medium | 제목/글머리/앵커로 배정되지 않은 평문단 중 최빈 (heading=NONE, indent=0, intent=0) |
| `table_header` | 47 | 17 | 0 | high | 표 안 cellAddr.rowAddr==0 문단의 최빈 (paraPr, charPr, style) |
| `table_cell` | 13 | 33 | 0 | high | 표 안 rowAddr!=0 문단의 최빈 조합 |
| `figure_anchor` | 16 | 8 | 0 | none | 양식에 대응 서식이 없어 'body' 설정을 전용함 |
| `table_anchor` | 22 | 65 | 0 | medium | hp:tbl을 직접 담은 문단 (관측된 조합 4종) |
| `figure_caption` | 0 | 0 | 0 | low | 이 양식에는 그림 캡션 사례가 없다. 표준 스타일 '바탕글'(engName=Normal, id=0)의 문단모양 0 / 글자모양 0을 후보로 제안한다 |
| `table_caption` | 0 | 0 | 0 | none | 양식에 대응 서식이 없어 'figure_caption' 설정을 전용함 |
| `bold` | — | 10 | — | medium | 본문 높이(1000)와 같은 bold charPr ['10', '15', '67'] 발견 |

## 확인 질문 6개

> 답을 `profile.override.yaml`에 적으면 재추출해도 살아남는다.

**Q1. 표 앵커 문단이 4종 관측됐습니다. paraPr 22가 맞습니까?**
- 근거: hp:tbl을 직접 담은 문단 (관측된 조합 4종)

**Q2. bullet_level_0의 최빈 글자모양이 양식 안내문 색이라 검정 54로 바꿨습니다. 맞습니까?**
- 근거: heading.type=BULLET, margin.left=1500 (본문 사용 8회) → 오름차순 0번째. 본문 미사용 BULLET paraPr ['15', '19', '38'] 제외함
- 예시: ['(배경) 농업 기반 사회의 시간 관리 필요성 증', '과학적 기술력을 통한 국가 위상 제고', '(현안) 기존 시계의 제한적 활용 및 정보 불균']

**Q3. bullet_level_1의 최빈 글자모양이 양식 안내문 색이라 검정 11로 바꿨습니다. 맞습니까?**
- 근거: heading.type=BULLET, margin.left=2500 (본문 사용 13회) → 오름차순 1번째. 본문 미사용 BULLET paraPr ['15', '19', '38'] 제외함
- 예시: ['농사가 국가 경제의 중심이 되는 상황에서, 정확', '중국의 역법에 의존하던 방식에서 벗어나, 조선의', '기존의 보루각 물시계는 담당자가 밤낮으로 지켜보']

**Q4. heading_3을 표준 스타일 '제목'(paraPr 14 / charPr 63)로 잡았습니다. 본문에 이 역할의 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 본문에 이 역할의 사례가 없다. 표준 스타일 '제목'(engName=Outline 3, id=2)의 문단모양 14 / 글자모양 63을 후보로 제안한다

**Q5. bullet_level_2을 표준 스타일 '◦ '(paraPr 39 / charPr 54)로 잡았습니다. 본문에 이 역할의 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 본문에 이 역할의 사례가 없다. 표준 스타일 '◦ '(engName=Outline 6, id=4)의 문단모양 39 / 글자모양 54을 후보로 제안한다

**Q6. figure_caption을 표준 스타일 '바탕글'(paraPr 0 / charPr 0)로 잡았습니다. 이 양식에는 그림 캡션 사례가 없다라 관측으로는 확인할 수 없었습니다. 맞습니까?**
- 근거: 이 양식에는 그림 캡션 사례가 없다. 표준 스타일 '바탕글'(engName=Normal, id=0)의 문단모양 0 / 글자모양 0을 후보로 제안한다

## borderFill 존 규칙 자기검증

> 존 규칙은 우리가 생성할 stub 없는 표용이다. 원본 재현율이 낮은 것은 정상이며, stub 열과 수작업 편집 때문이다.

| 표 | 크기 | 규칙 일치 | stub 열 |
|---|---|---|---|
| 1 | 34x35 | 0/207 (0.0%) | 없음 |
| 2 | 2x2 | 1/3 (33.3%) | 없음 |
| 3 | 2x2 | 1/3 (33.3%) | 없음 |
| 4 | 2x2 | 1/3 (33.3%) | 없음 |

## 미배정 ID

- paraPr: {'4': {'body': 0, 'table': 2, 'caption': 0, 'memo': 1}, '15': {'body': 0, 'table': 2, 'caption': 0, 'memo': 0}, '29': {'body': 0, 'table': 14, 'caption': 0, 'memo': 0}, '30': {'body': 0, 'table': 7, 'caption': 0, 'memo': 0}, '31': {'body': 0, 'table': 28, 'caption': 0, 'memo': 0}, '32': {'body': 0, 'table': 28, 'caption': 0, 'memo': 0}, '25': {'body': 0, 'table': 3, 'caption': 0, 'memo': 0}, '33': {'body': 0, 'table': 28, 'caption': 0, 'memo': 0}, '48': {'body': 0, 'table': 3, 'caption': 0, 'memo': 0}, '42': {'body': 0, 'table': 8, 'caption': 0, 'memo': 0}}
- charPr: {'40': 30, '44': 30, '43': 20, '23': 17, '59': 13, '24': 10, '76': 9, '34': 9, '22': 8, '45': 8}

## 경고

- BULLET paraPr ['15', '19', '38']는 본문에서 쓰이지 않아(표 전용) 글머리 수준 후보에서 제외했다. 이 필터가 없으면 수준이 한 칸씩 밀린다.
- bullet_level_0: 최빈 charPr 55는 #0000FF 양식 안내문이라 같은 크기 검정 54로 치환함
- bullet_level_1: 최빈 charPr 59는 #0000FF 양식 안내문이라 같은 크기 검정 11로 치환함
- heading_3: heading_3: 관측 사례 없음 → 스타일 이름으로 추정
- bullet_level_2: bullet_level_2: 관측 사례 없음 → 스타일 이름으로 추정
- figure_caption: figure_caption: 관측 사례 없음 → 스타일 이름으로 추정
- bullet_level_3: bullet_level_3 미검출 → bullet_level_2 폴백
- figure_anchor: figure_anchor 미검출 → body 폴백
- table_caption: table_caption 미검출 → figure_caption 폴백
