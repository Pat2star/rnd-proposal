# -*- coding: utf-8 -*-
"""조직도 — 주관·공동·위탁·협력 기관과 담당 영역을 계층으로.

레이아웃은 **선언한 층(tier)** 이 정한다. 층 안의 상자는 균등 분할된다.
부속 상자(협력기관·운영위원회)만 `nodes:` 로 자유 배치한다.

상자 하나에 `label`(기관명, 굵게)과 `body`(담당 영역)를 함께 넣을 수 있다.
matplotlib 텍스트 하나는 굵기를 섞지 못하므로 **칸을 나눠 두 개**를 놓고,
둘 사이 겹침은 검사기가 글자↔글자 규칙으로 잡는다.
"""
from __future__ import annotations

from . import shapes
from .textbox import fit_text


def _rect(cx, cy, w, h):
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def render(ax, spec, t, cc, fitter):
    a = spec.get("area", {})
    L, R = float(a.get("left", 0.02)), float(a.get("right", 0.98))

    placed: dict[str, dict] = {}

    def put(nd, cx, cy, w, h):
        role = t.roles.get(nd.get("role", "plain"), t.roles["plain"])
        rect = _rect(cx, cy, w, h)
        shapes.box(ax, rect, fill=role["fill"], edge=role["edge"], ls=role["ls"],
                   lw=t.lw_box_strong if role["strong"] else t.lw_box)
        nid = nd["id"]
        placed[nid] = shapes.anchors(rect)
        cc.add_box(nid, rect)

        body = nd.get("body")
        if body:
            split = float(nd.get("split", 0.44))
            ysep = rect[3] - (rect[3] - rect[1]) * split
            ax.plot([rect[0], rect[2]], [ysep, ysep], color=role["edge"],
                    lw=t.lw_grid, zorder=4)
            head_box = (rect[0], ysep, rect[2], rect[3])
            body_box = (rect[0], rect[1], rect[2], ysep)
        else:
            head_box, body_box = rect, None

        if nd.get("label"):
            tt, ok = fit_text(ax, fitter, head_box, nd["label"], t,
                              fs=nd.get("fs", t.fs_node), weight="bold")
            cc.add_text(tt, nd["label"].replace("\n", " "), owner=nid, fitted=ok)
        if body:
            tt, ok = fit_text(ax, fitter, body_box, body, t,
                              fs=nd.get("fs_body", t.fs_small), weight="normal")
            cc.add_text(tt, body.replace("\n", " ")[:26], owner=nid, fitted=ok)

    for tier in spec.get("tiers", []):
        ns = tier.get("nodes", [])
        if not ns:
            continue
        y = float(tier.get("y", 0.5))
        h = float(tier.get("h", 0.14))
        gap = float(tier.get("gap", 0.14))
        colw = (R - L) / len(ns)
        for i, nd in enumerate(ns):
            cx = nd["at"][0] if "at" in nd else L + (i + 0.5) * colw
            cy = nd["at"][1] if "at" in nd else y
            put(nd, cx, cy, float(nd.get("w", colw * (1 - gap))),
                float(nd.get("h", h)))

    for nd in spec.get("nodes", []):
        cx, cy = nd["at"]
        put(nd, float(cx), float(cy), float(nd["w"]), float(nd["h"]))

    for e in spec.get("edges", []):
        src, dst = placed.get(e["from"]), placed.get(e["to"])
        if src is None or dst is None:
            raise ValueError(f"조직도 연결선의 노드를 찾을 수 없다: {e}")
        shapes.connect(ax, src, dst, route=e.get("route", "VHV"),
                       color=t.edge, lw=t.lw_edge,
                       ls=e.get("style", "solid"), mid=e.get("mid"),
                       arrow=bool(e.get("arrow", False)))
