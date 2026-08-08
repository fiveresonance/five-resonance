"""
resonance_engine.py — Born Vector + Today's Need Vector 결합 엔진
Five Resonance 고유 사운드 포커스 계산

가중치 상수:
  W_TODAY = 0.7  (오늘의 즉각적 필요)
  W_BORN  = 0.3  (타고난 체질적 결핍 보정)

→ 실사용 데이터 쌓이면 상수만 조정하여 모델 튜닝 가능.
"""
from __future__ import annotations

# ── 조정 가능한 상수 ──────────────────────────────────────
W_TODAY = 0.7   # 오늘 퀴즈 가중치
W_BORN  = 0.3   # 타고난 결핍 가중치
BALANCE_BASE = 20.0


ELEMENTS = ["water", "wood", "fire", "earth", "metal"]

# 오행 × 음악 추천 방향 (3개 언어)
SOUND_DIRECTION = {
    "water": {
        "jp": "深い静寂と流れるような水音のセッション",
        "ko": "깊은 고요와 흐르는 물소리 세션",
        "en": "Deep stillness and flowing water soundscapes",
    },
    "wood": {
        "jp": "芽吹きの生命力と上昇するリズムのセッション",
        "ko": "새싹의 생명력과 상승하는 리듬 세션",
        "en": "Vital growth energy with rising rhythmic momentum",
    },
    "fire": {
        "jp": "温もりと鼓動する光のセッション",
        "ko": "온기와 고동치는 빛의 세션",
        "en": "Warmth and pulsing luminous energy",
    },
    "earth": {
        "jp": "大地の安定と包み込む厚みのセッション",
        "ko": "대지의 안정과 포근한 두께감 세션",
        "en": "Grounded stability with enveloping depth",
    },
    "metal": {
        "jp": "澄んだ輪郭と研ぎ澄まされた静けさのセッション",
        "ko": "맑은 윤곽과 정제된 고요 세션",
        "en": "Clear contours and refined sonic precision",
    },
}


def calculate_final_sound_focus(
    born_vector: dict,
    quiz_scores: dict,
    lang: str = "jp",
) -> dict:
    """
    Born Vector + Today's Quiz 점수를 결합하여 오늘의 최종 사운드 포커스를 반환.

    born_vector: build_element_vector()의 vector 필드
                 {"water": 12.5, "wood": 37.5, ...}  (합계 100%)
    quiz_scores: 퀴즈 원점수 {"water": 6, "wood": 3, ...}
    """
    # 1. Today Quiz 백분율 정규화
    total_quiz = sum(quiz_scores.values()) or 1
    today_vector = {e: (quiz_scores.get(e, 0) / total_quiz) * 100
                    for e in ELEMENTS}

    # 2. Born Vector 결핍도 (균형선 20%에서 모자란 만큼)
    born_deficit = {e: max(0.0, BALANCE_BASE - born_vector.get(e, 0))
                    for e in ELEMENTS}

    # 3. 가중치 결합
    final_scores = {
        e: round(today_vector[e] * W_TODAY + born_deficit[e] * W_BORN, 1)
        for e in ELEMENTS
    }

    # 4. 정렬 (동률 시 순환 순서로 안정 정렬)
    cycle = ELEMENTS
    sorted_final = sorted(
        final_scores.items(),
        key=lambda x: (-x[1], cycle.index(x[0]))
    )

    primary_sound   = sorted_final[0][0]
    secondary_sound = sorted_final[1][0]

    # 5. 결합 근거 텍스트
    born_primary = max(born_vector, key=born_vector.get)
    born_deficient = min(born_vector, key=born_vector.get)
    today_primary  = max(today_vector, key=today_vector.get)

    return {
        "primary_sound":    primary_sound,
        "secondary_sound":  secondary_sound,
        "final_scores":     final_scores,
        "today_vector":     {e: round(v, 1) for e, v in today_vector.items()},
        "born_deficit":     {e: round(v, 1) for e, v in born_deficit.items()},
        "weights":          {"today": W_TODAY, "born": W_BORN},
        "sound_direction":  SOUND_DIRECTION[primary_sound][lang],
        "context": {
            "born_primary":   born_primary,
            "born_deficient": born_deficient,
            "today_primary":  today_primary,
        },
    }
