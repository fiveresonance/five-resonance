"""
five_elements.py — Five Resonance 오행 가중치 벡터 모듈
4주 데이터 → 계절 가중치 반영 오행 벡터 → primary/secondary/cultivate
"""
from __future__ import annotations

# ── 조정 가능한 상수 ──────────────────────────────────────
DEFICIENCY_THRESHOLD = 12.0   # 이 % 미만이면 결핍으로 판정
BALANCE_BASE = 20.0            # 5원소 완전 균형값


def analyze_deficiency(vector: dict) -> dict:
    """
    단순 최저치가 아닌, 절대 임계치(12%) 이하의 원소를 결핍으로 판정.
    모든 원소가 12% 이상이면 is_deficient=False (균형 사주).
    """
    sorted_els = sorted(vector.items(), key=lambda x: x[1])
    lowest_el, lowest_val = sorted_els[0]

    if lowest_val < DEFICIENCY_THRESHOLD:
        return {
            "cultivate":    lowest_el,
            "is_deficient": True,
            "gap":          round(BALANCE_BASE - lowest_val, 1),
        }
    return {
        "cultivate":    None,
        "is_deficient": False,
        "gap":          0.0,
    }


def build_element_vector(pillars: dict) -> dict:
    """
    4주 데이터 → 계절 가중치(월지 2.0) 반영 오행 백분율 벡터.
    pillars: get_exact_four_pillars() 반환값
    """
    scores = {"water": 0.0, "wood": 0.0, "fire": 0.0,
              "earth": 0.0, "metal": 0.0}

    def add(element: str, weight: float):
        if element and element in scores:
            scores[element] += weight

    p = pillars
    add(p["year"]["gan_el"],   1.0)
    add(p["year"]["zhi_el"],   1.0)
    add(p["month"]["gan_el"],  1.0)
    add(p["month"]["zhi_el"],  2.0)   # 월지 — 계절 핵심
    add(p["day"]["gan_el"],    1.0)
    add(p["day"]["zhi_el"],    1.0)

    total_weight = 7.0
    if p["hour"]:
        add(p["hour"]["gan_el"], 1.0)
        add(p["hour"]["zhi_el"], 1.0)
        total_weight += 2.0

    # 백분율 정규화
    vector = {k: round(v / total_weight * 100, 1) for k, v in scores.items()}

    # 동률 시 오행 순환 순서로 안정 정렬
    cycle = ["water", "wood", "fire", "earth", "metal"]
    sorted_els = sorted(vector.items(), key=lambda x: (-x[1], cycle.index(x[0])))

    primary   = sorted_els[0][0]
    secondary = sorted_els[1][0]

    # 결핍 판정
    deficiency = analyze_deficiency(vector)

    return {
        "vector":          vector,
        "primary":         primary,
        "secondary":       secondary,
        "cultivate":       deficiency["cultivate"],
        "is_deficient":    deficiency["is_deficient"],
        "deficiency_gap":  deficiency["gap"],
        "day_master":      p["day"]["gan_el"],
        "season_element":  p["month"]["zhi_el"],
        "is_four_pillars": p["hour"] is not None,
    }


def element_relation(primary_a: str, primary_b: str,
                     vector_a: dict, vector_b: dict) -> str:
    """
    두 사람의 주 오행 + 전체 벡터로 관계 유형 반환.
    6타입: 共鳴型 補完型 成長型 緊張型 抑制型 鏡型
    """
    SHENG = {("wood","fire"),("fire","earth"),("earth","metal"),
             ("metal","water"),("water","wood")}
    KE    = {("wood","earth"),("earth","water"),("water","fire"),
             ("fire","metal"),("metal","wood")}

    if primary_a == primary_b:
        return "共鳴型"

    pair, pair_r = (primary_a, primary_b), (primary_b, primary_a)

    if pair  in SHENG: return "補完型"
    if pair_r in SHENG: return "成長型"

    if pair in KE or pair_r in KE:
        diff = sum(abs(vector_a.get(e, 0) - vector_b.get(e, 0)) for e in vector_a)
        return "抑制型" if diff >= 40 else "緊張型"

    return "鏡型"
