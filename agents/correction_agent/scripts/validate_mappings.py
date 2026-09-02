"""defect_mappings.json 의 모든 citation_path 가 컬렉션에 실재하는지 검증한다.

인용주소를 손으로 적으면 조용히 틀린다. 리포트의 evidence 가 여기서 나오므로
존재하지 않는 조항을 매핑에 넣어두면 그대로 환각이 된다. sqlite 직접 조회라 의존성이 없다.

  python validate_mappings.py
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from agents.correction_agent.rag import config

HERE = config.DATA
SLOTS = ("definition", "visual_acceptance", "rt_acceptance", "general", "requirement")


def load_citations(db: pathlib.Path) -> set[str]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    return {
        r[0]
        for r in con.execute(
            "select string_value from embedding_metadata where key='citation_path'"
        )
    }


def main() -> int:
    known = load_citations(HERE / "chroma.sqlite3")
    data = json.loads((HERE / "defect_mappings.json").read_text(encoding="utf-8"))

    missing, total, empty = [], 0, []
    for d in data["defects"]:
        n = 0
        for doc in ("milstd-2035a", "49cfr192", "nasa-std-5006a"):
            for slot in SLOTS:
                for cite in d.get(doc, {}).get(slot, []):
                    total += 1
                    n += 1
                    if cite not in known:
                        missing.append((d["our_code"], doc, slot, cite))
        if n == 0:
            empty.append(d["our_code"])

    print(f"인용주소 {total}건 검사")
    if missing:
        print(f"\n❌ 컬렉션에 없는 인용주소 {len(missing)}건:")
        for code, doc, slot, cite in missing:
            print(f"   {code} · {doc} · {slot} · {cite!r}")
    else:
        print("✅ 전부 실재")

    if empty:
        print(f"\n⚠️  매핑 0건인 결함: {', '.join(empty)} — abstain 대상으로 다뤄야 함")

    # 슬롯별 커버리지
    print("\n슬롯별 커버리지 (결함 15종 중 조항이 붙은 종 수)")
    for slot in SLOTS:
        have = [
            d["our_code"]
            for d in data["defects"]
            if any(
                d.get(doc, {}).get(slot) for doc in ("milstd-2035a", "49cfr192", "nasa-std-5006a")
            )
        ]
        print(f"  {slot:<20} {len(have):>2}/15   {' '.join(have)}")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
