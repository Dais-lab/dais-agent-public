"""치수 허용 한계를 **코드로** 계산한다. LLM 산술에 맡기지 않는다.

근거 — 실측(2026-08-19):
    질문: "1/64 inch 는 몇 mm 인가?"
    dais-llm 답: 1.5875     (정답 0.3969 — 1/16인치 값을 답했다)
그 결과 언더컷 깊이 0.3mm / 두께 12mm / Class 1 케이스에서
허용(0.3 ≤ 0.397)인데 **불허**로 판정했다. 조항은 정확히 찾아왔는데 산술에서 틀렸다.
변환값을 주면 곧바로 맞힌다 → 추론이 아니라 **단위 변환**이 실패 지점이다.

그래서 조항의 한계식을 기계가 읽을 수 있는 형태로 따로 둔다
(설계문서의 `limit_expression` 제안을 그대로 구현한 것).
`variables` 가 곧 `missing_info` 이므로 부족 정보도 하드코딩 없이 나온다.
"""

from __future__ import annotations

from dataclasses import dataclass

MM_PER_INCH = 25.4


@dataclass
class LimitRule:
    citation_path: str
    applies_to: str  # our_code
    quality_class: str  # MIL-STD 의 Class 1 / 2 / 3
    raw: str
    variables: tuple[str, ...]  # 계산에 필요한 입력 = missing_info 후보

    def evaluate(self, m: dict) -> dict: ...


class UndercutLimit(LimitRule):
    """MIL-STD-2035A 4.2.16 — 언더컷 깊이 상한.

    Class 1      : min(1/64 inch, 두께의 10%)
    Class 2 and 3: min(1/32 inch, 두께의 10%)  ※ 두께 1/2인치 이상이면 1/16인치까지
    """

    def evaluate(self, m: dict) -> dict:
        t = m.get("base_thickness_mm")
        h = m.get("defect_depth_mm")
        missing = [n for n, v in (("모재 두께(t, mm)", t), ("결함 깊이(h, mm)", h)) if v is None]
        if missing:
            return {"computable": False, "missing": missing}

        inch = (1 / 64) if self.quality_class == "1" else (1 / 32)
        cap_mm = inch * MM_PER_INCH
        pct_mm = 0.10 * t
        limit = min(cap_mm, pct_mm)
        return {
            "computable": True,
            "limit_mm": round(limit, 4),
            "measured_mm": h,
            "within_limit": h <= limit,
            "work": (
                f"min({inch:.5g} inch = {cap_mm:.4f} mm, 10% × {t} mm = {pct_mm:.4f} mm)"
                f" = {limit:.4f} mm  vs  측정 {h} mm"
            ),
        }


RULES: tuple[LimitRule, ...] = (
    UndercutLimit(
        citation_path="milstd-2035a#4.2.16",
        applies_to="UC",
        quality_class="1",
        raw="shall not exceed 1/64-inch or 10 percent of the minimum thickness, whichever is less",
        variables=("base_thickness_mm", "defect_depth_mm"),
    ),
    UndercutLimit(
        citation_path="milstd-2035a#4.2.16.2",
        applies_to="UC",
        quality_class="2",
        raw=(
            "the maximum undercut shall be 1/32-inch, or 10 percent of "
            "the minimum thickness, whichever is less"
        ),
        variables=("base_thickness_mm", "defect_depth_mm"),
    ),
)


def check(our_code: str, quality_class: str | None, measurements: dict) -> dict | None:
    """해당 결함·Class 의 한계식을 찾아 계산한다. 규칙이 없으면 None."""
    for r in RULES:
        if r.applies_to == our_code and (quality_class or "1") == r.quality_class:
            out = r.evaluate(measurements)
            out.update(
                {"citation_path": r.citation_path, "rule": r.raw, "quality_class": r.quality_class}
            )
            return out
    return None
