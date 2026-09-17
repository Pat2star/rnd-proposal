# -*- coding: utf-8 -*-
"""form profile 로더 — profile.yaml + profile.override.yaml deep-merge.

**이 병합이 재현성의 핵심이다.** 양식을 재추출하면 profile.yaml은 덮어써지지만
사람이 정정한 profile.override.yaml은 그대로 살아남아 항상 위에 얹힌다.
그래서 "추출기를 고쳐서 다시 돌려도 내 확인 결과가 안 날아간다"가 성립한다.

또한 vendor/xml_writer.py 가 기대하는 styles dict 로 변환하는 어댑터를 제공한다.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import yaml


def deep_merge(base: dict, over: dict) -> dict:
    """over가 이긴다. dict는 재귀 병합, 그 외는 교체."""
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Profile:
    data: dict
    dir: str
    rederived: list = None      # 병합 후 재계산으로 바뀐 파생값 (리포트용)

    # ── 접근자 ──
    @property
    def form_id(self) -> str:
        return self.data["form"]["id"]

    @property
    def template(self) -> str:
        return os.path.join(self.dir, self.data["form"].get("template", "template.hwpx"))

    @property
    def template_sha256(self) -> str | None:
        return self.data["form"].get("template_sha256")

    @property
    def text_width(self) -> int:
        return int(self.data["page"]["text_width"])

    @property
    def roles(self) -> dict:
        return self.data.get("roles", {})

    @property
    def table(self) -> dict:
        return self.data.get("table", {})

    @property
    def figure(self) -> dict:
        return self.data.get("figure", {})

    @property
    def budget(self) -> dict:
        """분량 예산 — **양식별 실측값**이지 상수가 아니다.

        ★ 이 값을 코드에 상수로 굳히면 안 된다. 실측 대조(2026-08-19):
          이 저장소 strategic-2027-dist  12pt / 130% / 개조식 → 약 800자/쪽
          rfp-proposal-harness 기본양식  11pt / 160% / 개조식 → 약 1,000자/쪽
          같은 개조식인데도 25% 차이가 난다. 글자 크기·줄간격·말머리 들여쓰기가
          모두 다르기 때문이다.
        `PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.quality.budget --calibrate` 로 양식마다 다시 잰다.
        """
        return self.data.get("budget", {})

    @property
    def limits(self) -> dict:
        """작성 상한 — 표 열수·굵기 비율 등. rfp-proposal-harness 규율 F에서 가져왔다."""
        return self.data.get("limits", {})

    @property
    def writing_rules(self) -> dict:
        return self.data.get("writing_rules", {})

    def role(self, key: str) -> dict:
        r = self.roles.get(key) or {}
        if not r.get("para") and r.get("fallback_of"):
            return self.roles.get(r["fallback_of"], r)
        return r

    def prologue_run(self) -> str | None:
        p = os.path.join(self.dir, self.data.get("section_prologue", {})
                         .get("raw_file", "prologue_run.xml"))
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
        return None

    # ── lineseg 계산 (consts와 같은 공식, profile 값으로) ──
    def lineseg(self, role_key: str, vertsize: int | None = None) -> dict:
        r = self.role(role_key)
        ch = int(r.get("char_height") or 1000)
        pct = int(r.get("line_spacing_pct") or 100)
        vs = vertsize if vertsize is not None else ch
        left = int(r.get("indent_left") or 0)
        has_bullet = bool((r.get("heading") or {}).get("type") in ("BULLET", "OUTLINE")
                          or r.get("bullet_char"))
        flags = self.data["lineseg"]["flags"]
        return {
            "vertsize": vs,
            "textheight": vs,
            "baseline": math.floor(vs * 0.85 + 0.5),
            "spacing": math.floor(ch * (pct - 100) / 100 + 0.5),
            "horzpos": left,
            "horzsize": self.text_width - left,
            "vertpos": 0,
            "flags": flags["with_bullet"] if has_bullet else flags["normal"],
        }

    # ── vendor/xml_writer.py 어댑터 ──
    def styles_dict(self) -> dict:
        """vendor 렌더러가 기대하는 {role: {paraPrIDRef, charPrIDRef, styleIDRef}}."""
        out = {}
        for key in self.roles:
            r = self.role(key)
            if not r.get("para"):
                continue
            out[key] = {
                "paraPrIDRef": str(r["para"]),
                "charPrIDRef": str(r["char"]) if r.get("char") else "0",
                "styleIDRef": str(r["style"]) if r.get("style") is not None else "0",
            }
        return out

    # ── 자기 점검 ──
    def unanswered_questions(self) -> list[str]:
        return [k for k, r in self.roles.items()
                if isinstance(r, dict) and r.get("review_question")
                and r.get("confidence") in ("medium", "low")]


_DERIVED_PARA = ("align", "line_spacing_pct", "indent_left", "intent")
_DERIVED_CHAR = ("char_height", "font", "bold")


def rederive(data: dict, template: str) -> list[str]:
    """병합 후 파생값을 template.hwpx에서 다시 읽어 덮어쓴다.

    override에서 para/char만 바꿔도 char_height·line_spacing_pct 같은 파생값이
    옛 ID 기준으로 남으면 lineseg 계산이 조용히 틀어진다. 사람이 override에
    파생값까지 손으로 적게 하는 건 실수를 부르므로, **항상 원본에서 재계산**한다.

    돌려주는 값: 실제로 값이 바뀐 항목 설명 리스트 (리포트용).
    """
    if not os.path.exists(template):
        return []
    from . import header_index
    hidx = header_index.from_hwpx(template)
    changed = []
    for key, r in (data.get("roles") or {}).items():
        if not isinstance(r, dict):
            continue
        pid = r.get("para")
        if pid is not None and str(pid) in hidx.para_pr:
            pp = hidx.para_pr[str(pid)]
            new = {"align": pp.align, "line_spacing_pct": pp.line_spacing_pct,
                   "indent_left": pp.indent_left, "intent": pp.intent}
            for k, v in new.items():
                if r.get(k) != v:
                    changed.append(f"{key}.{k}: {r.get(k)} → {v}")
                r[k] = v
        cid = r.get("char")
        if cid is not None and str(cid) in hidx.char_pr:
            cp = hidx.char_pr[str(cid)]
            new = {"char_height": cp.height, "font": cp.font_hangul, "bold": cp.bold}
            for k, v in new.items():
                if r.get(k) != v:
                    changed.append(f"{key}.{k}: {r.get(k)} → {v}")
                r[k] = v
    return changed


def load(form_dir: str, rederive_after_merge: bool = True) -> Profile:
    base_p = os.path.join(form_dir, "profile.yaml")
    if not os.path.exists(base_p):
        raise FileNotFoundError(f"profile.yaml 없음: {base_p}")
    with open(base_p, encoding="utf-8") as f:
        base = yaml.safe_load(f) or {}

    ovr_p = os.path.join(form_dir, "profile.override.yaml")
    over = {}
    if os.path.exists(ovr_p):
        with open(ovr_p, encoding="utf-8") as f:
            over = yaml.safe_load(f) or {}

    data = deep_merge(base, over)
    p = Profile(data=data, dir=form_dir)
    if rederive_after_merge:
        p.rederived = rederive(data, p.template)
    return p
