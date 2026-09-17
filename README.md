# hyerim-skills

부처 연구계획서 **양식(.hwpx)을 넣으면 코드 수정 없이** 그 양식에 맞는
연구계획서를 만드는 Claude Code 플러그인 묶음.

## 설치

```
/plugin marketplace add Pat2star/rnd-proposal
/plugin install rnd-proposal@hyerim-skills
```

그림과 특허는 **필요할 때 꺼내 쓴다** — 안 깔아도 계획서는 만들어진다.

```
/plugin install rnd-figure@hyerim-skills     # 개요도·조직도·진도표
/plugin install rnd-patent@hyerim-skills     # 선행특허·회피설계
```

## 플러그인

| 이름 | 무엇 |
|---|---|
| `rnd-proposal` | 부처 연구계획서 양식(.hwpx)을 넣으면 코드 수정 없이 그 양식에 맞춰 조립한다. |
| `rnd-figure` | 연구계획서 그림. |
| `rnd-patent` | 선행특허 조사와 회피설계 축 정리. |

## 함께 필요한 것

| | 왜 |
|---|---|
| **Node.js 18+** | HWPX 조립을 `kordoc` 으로 한다(`npx` 가 받아온다) |
| **Python 3.10+** | 게이트와 검사기. `pip install -r requirements.txt` |
| **한컴오피스 한글** | 쪽수를 **실측**한다. 없으면 「미측정」으로 남고 통과를 발급하지 않는다 |
| `rfp-proposal-harness@jinwoo-skills` | 조사 4축·평가위원단 6인. 조립 스크립트가 이 플러그인의 kordoc 설정을 쓴다 |

자세한 사용법은 `plugins/rnd-proposal/SETUP.md`.

## 이 저장소는 손으로 고치지 않는다

비공개 원본에서 `scripts/build_marketplace.py` 로 **생성**한다.
여기서 고치면 다음 생성 때 사라진다.

MIT License
