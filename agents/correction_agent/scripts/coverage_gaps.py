"""목차에는 있는데 본문 청크가 없는 조항을 찾아 `coverage_gaps.json` 으로 낸다.

리포트의 `coverage_gap` 필드 근거다. "언더컷 RT 기준이 없다" 가 아니라
**"MIL-STD 5.2.1.9 Undercut(p12) 조항은 존재하나 본문을 확보하지 못했다"** 라고
말할 수 있어야 연구원이 다음 행동을 정할 수 있다.

목차 행을 지우지 않고 `toc_entry` 로 재분류해 둔 것이 이 진단을 가능하게 한다.
"""

from __future__ import annotations

import json
import re
import sqlite3

from agents.correction_agent.rag import config

HERE = config.DATA
ROW = re.compile(
    r"(?:Paragraph:\s*|:\s*)([\d.]+\d)\s*\|\s*(?:Paragraph:\s*|:\s*)([^|]+?)\s*\|\s*Page:\s*(\d+)"
)


def main() -> int:
    con = sqlite3.connect(f"file:{HERE}/chroma.sqlite3?mode=ro", uri=True)
    rows = list(
        con.execute("""
        select em.string_value,
         (select string_value from embedding_metadata where id=em.id and key='doc_id'),
         (select string_value from embedding_metadata where id=em.id and key='chunk_type'),
         (select string_value from embedding_metadata where id=em.id and key='section')
        from embedding_metadata em where em.key='chroma:document'""")
    )

    have = {s for _, d, ct, s in rows if d == "milstd-2035a" and ct != "toc_entry" and s}
    listed: dict[str, tuple[str, int]] = {}
    for txt, d, ct, _ in rows:
        if d != "milstd-2035a" or ct != "toc_entry":
            continue
        m = ROW.search((txt or "").split("\n", 1)[-1])
        if m:
            sec, title, page = m.group(1).rstrip("."), m.group(2).strip(" .·"), int(m.group(3))
            if re.fullmatch(r"\d+(\.\d+)+", sec):
                listed[sec] = (title, page)

    # 절 번호가 다른 청크 본문 안에 남아 있는지 본다. 남아 있으면 "주소만 없는" 것이고,
    # 아예 없으면 OCR 이 그 줄을 통째로 놓친 것이다. 대응 방법이 완전히 다르다.
    bodies = "\n".join(
        (t or "") for t, d, ct, _ in rows if d == "milstd-2035a" and ct != "toc_entry"
    )

    gaps = []
    for sec, (title, page) in sorted(
        listed.items(), key=lambda x: [int(i) for i in x[0].split(".")]
    ):
        if sec in have:
            continue
        in_body = f"{sec} " in bodies or f"{sec}." in bodies
        gaps.append(
            {
                "standard": "MIL-STD-2035A(SH)",
                "section": sec,
                "title": title,
                "page": page,
                "kind": "unaddressable" if in_body else "absent",
                "status": (
                    "본문은 페이지 단위 청크에 있으나 절 번호로 인용할 수 없음 "
                    "— 재청킹으로 복구 가능"
                    if in_body
                    else "OCR 원본에 해당 줄이 없음 — 재청킹으로는 복구 불가. "
                    "해당 쪽 재OCR 또는 수기 전사 필요"
                ),
            }
        )

    out = {
        "_meta": {
            "note": "목차에는 있으나 본문 청크가 없는 조항. 리포트 coverage_gap 근거.",
            "listed": len(listed),
            "missing": len(gaps),
        },
        "gaps": gaps,
    }
    (HERE / "coverage_gaps.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    absent = [g for g in gaps if g["kind"] == "absent"]
    unaddr = [g for g in gaps if g["kind"] == "unaddressable"]
    print(f"목차 등재 {len(listed)}절 중 본문 청크 없음 {len(gaps)}절")
    print(f"  ├ 재청킹으로 복구 가능 (주소만 없음) : {len(unaddr)}절")
    print(f"  └ 복구 불가 (OCR 원본에 없음)        : {len(absent)}절\n")
    for label, group in (("복구 불가 ★", absent), ("재청킹 가능", unaddr)):
        print(f"[{label}]")
        for g in group:
            print(f"  {g['section']:<10} {g['title'][:50]:<52} p{g['page']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
