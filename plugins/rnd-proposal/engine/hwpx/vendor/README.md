# vendor/ — 외부 코드 복사본 (수정 금지)

## 출처

| 항목 | 값 |
|---|---|
| 이름 | `hwpx-generator` |
| 버전 | 3.11.0 |
| 저자 | Baekdong Cha (orientpine@gmail.com) |
| 라이선스 | **MIT** |
| 원본 경로 | `~/.claude/plugins/cache/honeypot/hwpx-generator/3.11.0/skills/hwpx-core/scripts/` |
| 복사일 | 2026-08-12 |

## 왜 복사해 두는가

플러그인 캐시 경로를 직접 참조하면 안 되는 이유 3가지:

1. **재현자료 제출 요건** — 경진대회 제출물에 Agent 재현자료(zip)가 포함된다. 심사자 PC에 이 플러그인이 없으면 파이프라인이 돌지 않는다.
2. **플러그인 업데이트 시 깨짐** — 캐시는 버전이 바뀌면 경로가 통째로 바뀐다.
3. **선례** — `.claude/settings.local.json`이 이미 이 캐시를 `C:/Users/hrkim/...` 경로로 참조하다 PC가 바뀌면서 깨져 있었다.

## 규칙

- **이 폴더의 `.py` 파일을 수정하지 않는다.** 동작을 바꿔야 하면 `engine/hwpx/` 상위 층에서 래핑한다.
- 업스트림을 갱신할 때는 폴더 전체를 다시 복사하고 이 README의 버전·복사일을 갱신한다.

## 파일 역할

| 파일 | 하는 일 | 우리가 쓰는 방식 |
|---|---|---|
| `zip_surgery.py` | ZIP 엔트리 순서·압축타입·XML 선언을 바이트 보존하며 `section0.xml`만 교체 | `package.py`가 래핑 |
| `xml_writer.py` | `styles["heading_1"]["paraPrIDRef"]` 형태의 dict를 받아 `hp:p`/`hp:tbl` 생성 | `profile.py`가 profile.yaml → 이 dict로 변환 |
| `md_parser.py` | Markdown → block IR (표·이미지·글머리 레벨·인라인 bold) | 그대로 사용 |
| `image_embedder.py` | `hp:pic` 생성 (`dim = px×75`, `scaMatrix = curSz/orgSz` 내장) | `figure.py`가 래핑 |
| `cell_writer.py` | `linesegarray` 생성 + 표 행높이 조정 | ⚠️ `zip_surgery` 산출물에 실행 금지 (아래 참조) |
| `page_guard.py` | 페이지 넘침 추정 | 그림/표 배치 시 사용 |
| `validate.py` | 기본 검증 | 우리 `validate_hwpx.py`가 L2/L4를 추가 |
| `analyze_template.py` | HWPX 구조를 사람이 읽는 리포트로 출력 | 참고용 |
| `section_transplant.py`, `proofread.py`, `md_merger.py`, `text_extract.py`, `build_hwpx.py` | 섹션 이식·교정·병합·텍스트 추출·빌드 | 선택적 |

## 원저자가 남긴 중요한 경고

`zip_surgery.py` 도크스트링:

> `NEVER run cell_writer.py on surgery output (Hangul recalculates layout)`

→ **한글이 `linesegarray`를 열 때 재계산한다**는 것을 원저자가 실험으로 확인했다는 뜻이다.
우리 `build_hwpx.py`는 근사값 `linesegarray`를 넣되 `profile.lineseg.emit: false` 스위치를 남겨 A/B 검증이 가능하게 한다.
