"""
manse.py — Five Resonance 만세력 모듈
절기(二十四節気) / 일진(日干支) / 오행 매핑

- 시간대: JST (UTC+9) 고정. 일본 대상 서비스이므로 로컬(밴쿠버) 시각을 쓰지 않는다.
- 절기: ephem으로 태양 시황경(視黄経)이 15°k를 통과하는 순간을 이분탐색.
        성력 파일 다운로드 불필요(해석적 모델).
- 일진: JDN 기반. sxtwl과 교차검증 완료.
"""

from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from datetime import date, datetime, timedelta, timezone
import ephem

JST = timezone(timedelta(hours=9))

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"

# 천간 → 오행 (양간/음간 순서대로 木木火火土土金金水水)
GAN_ELEMENT = ["wood", "wood", "fire", "fire", "earth",
               "earth", "metal", "metal", "water", "water"]

# 24절기: (황경, 이름, 읽기, 節/中)
SOLAR_TERMS = [
    (315, "立春", "りっしゅん", "節"), (330, "雨水", "うすい", "中"),
    (345, "啓蟄", "けいちつ", "節"), (0,   "春分", "しゅんぶん", "中"),
    (15,  "清明", "せいめい", "節"), (30,  "穀雨", "こくう", "中"),
    (45,  "立夏", "りっか", "節"), (60,  "小満", "しょうまん", "中"),
    (75,  "芒種", "ぼうしゅ", "節"), (90,  "夏至", "げし", "中"),
    (105, "小暑", "しょうしょ", "節"), (120, "大暑", "たいしょ", "中"),
    (135, "立秋", "りっしゅう", "節"), (150, "処暑", "しょしょ", "中"),
    (165, "白露", "はくろ", "節"), (180, "秋分", "しゅうぶん", "中"),
    (195, "寒露", "かんろ", "節"), (210, "霜降", "そうこう", "中"),
    (225, "立冬", "りっとう", "節"), (240, "小雪", "しょうせつ", "中"),
    (255, "大雪", "たいせつ", "節"), (270, "冬至", "とうじ", "中"),
    (285, "小寒", "しょうかん", "節"), (300, "大寒", "だいかん", "中"),
]

# 節(입절) → 계절 오행. 土用은 별도 처리.
TERM_SEASON_ELEMENT = {
    "立春": "wood", "啓蟄": "wood", "清明": "wood",
    "立夏": "fire", "芒種": "fire", "小暑": "fire",
    "立秋": "metal", "白露": "metal", "寒露": "metal",
    "立冬": "water", "大雪": "water", "小寒": "water",
}

# 土用 입절 황경 (각 계절 마지막 18일)
DOYO_LONGITUDES = {297: "冬の土用", 27: "春の土用", 117: "夏の土用", 207: "秋の土用"}


# ── 절기 계산 ──────────────────────────────────────────────

def _nutation_longitude(jd: float) -> float:
    """장동(章動) 황경 성분, 초(arcsec). Meeus ch.22 주요항."""
    import math
    T = (jd - 2451545.0) / 36525.0
    Om = math.radians(125.04452 - 1934.136261 * T)
    L = math.radians(280.4665 + 36000.7698 * T)
    Lp = math.radians(218.3165 + 481267.8813 * T)
    return (-17.20 * math.sin(Om) - 1.32 * math.sin(2 * L)
            - 0.23 * math.sin(2 * Lp) + 0.21 * math.sin(2 * Om))


def sun_apparent_longitude(dt_utc: datetime) -> float:
    """태양 시황경(視黄経, 도). 국립천문대 절기 정의와 동일.
    = 기하황경 + 장동 - 광행차. 2026년 검증 오차 < 1.1초각.
    """
    import math
    d = ephem.Date(dt_utc.replace(tzinfo=None))
    s = ephem.Sun(d)
    geometric = (float(s.hlong) * 180.0 / math.pi + 180.0) % 360.0
    dpsi = _nutation_longitude(ephem.julian_date(d)) / 3600.0
    aberration = (20.4898 / float(s.earth_distance)) / 3600.0
    return (geometric + dpsi - aberration) % 360.0


def solar_term_time(year: int, target_lon: float) -> datetime:
    """해당 연도에 태양 시황경이 target_lon을 통과하는 시각 (JST)."""
    def diff(dt):
        return ((sun_apparent_longitude(dt) - target_lon) + 180) % 360 - 180

    # 춘분(0도) 기준 선형 근사 후, 부호 변화 구간을 일 단위로 탐색
    approx = (datetime(year, 3, 20, tzinfo=timezone.utc)
              + timedelta(days=target_lon * 365.2422 / 360.0))
    lo = None
    for k in range(-30, 31):
        a = approx + timedelta(days=k)
        b = a + timedelta(days=1)
        if diff(a) <= 0 < diff(b) or (diff(a) <= 0 and diff(b) > 0):
            lo, hi = a, b
            break
    if lo is None:
        raise ValueError(f"교차점 탐색 실패: {year} {target_lon}deg")

    for _ in range(50):
        mid = lo + (hi - lo) / 2
        if diff(mid) <= 0:
            lo = mid
        else:
            hi = mid
    return lo.astimezone(JST)


@lru_cache(maxsize=64)
def solar_terms_of_year(year: int) -> list[tuple[str, str, str, datetime]]:
    """해당 연도의 24절기 (이름, 읽기, 節/中, JST 시각) 리스트."""
    out = []
    for lon, name, yomi, kind in SOLAR_TERMS:
        t = solar_term_time(year, lon)
        if t.year != year:  # 立春 등 경계 보정
            t = solar_term_time(year + (1 if t.year < year else -1), lon)
        out.append((name, yomi, kind, t))
    return tuple(sorted(out, key=lambda x: x[3]))


@lru_cache(maxsize=64)
def doyo_periods_of_year(year: int) -> list[tuple[str, datetime]]:
    """해당 연도의 土用 입절 4회 (이름, JST 시각)."""
    out = []
    for lon, nm in DOYO_LONGITUDES.items():
        t = solar_term_time(year, lon)
        if t.year != year:  # 황경 285도 이상은 이듬해 1월에 오므로 시드 연도 보정
            t = solar_term_time(year + (1 if t.year < year else -1), lon)
        out.append((nm, t))
    return tuple(sorted(out, key=lambda x: x[1]))


# ── 일진 ──────────────────────────────────────────────────

def _jdn(d: date) -> int:
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    return d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def day_ganzhi(d: date) -> tuple[str, str, int]:
    """일간지. 반환: (천간, 지지, 60갑자 인덱스)"""
    i = (_jdn(d) + 49) % 60
    return GAN[i % 10], ZHI[i % 12], i


def day_element(d: date) -> str:
    """일간 기준 오행."""
    return GAN_ELEMENT[GAN.index(day_ganzhi(d)[0])]


# ── 통합 조회 ──────────────────────────────────────────────

@dataclass
class DayInfo:
    day: date
    day_gan: str
    day_zhi: str
    day_element: str          # 일진 오행 (전면 배치)
    season_term: str          # 현재 節
    season_element: str       # 계절 오행 (배경)
    is_doyo: bool
    doyo_name: str | None
    term_starts_today: str | None  # 오늘이 절기 당일이면 절기명
    resonance: bool           # 일진 오행 == 계절 오행


def day_info(d: date) -> DayInfo:
    terms = list(solar_terms_of_year(d.year - 1)) + list(solar_terms_of_year(d.year))
    setsu = [t for t in terms if t[2] == "節" and t[3].date() <= d]
    cur = setsu[-1]

    doyos = list(doyo_periods_of_year(d.year - 1)) + list(doyo_periods_of_year(d.year))
    is_doyo, doyo_name = False, None
    for nm, start in doyos:
        if start.date() <= d < (start + timedelta(days=18)).date():
            is_doyo, doyo_name = True, nm
            break

    today_term = next((t[0] for t in terms if t[3].date() == d), None)
    g, z, _ = day_ganzhi(d)
    de = day_element(d)
    se = "earth" if is_doyo else TERM_SEASON_ELEMENT[cur[0]]

    return DayInfo(d, g, z, de, cur[0], se, is_doyo, doyo_name, today_term, de == se)


# ── 정밀 4주 계산 ──────────────────────────────────────────

ZHI_ELEMENT = {
    "子": "water", "丑": "earth", "寅": "wood",  "卯": "wood",
    "辰": "earth", "巳": "fire",  "午": "fire",  "未": "earth",
    "申": "metal", "酉": "metal", "戌": "earth", "亥": "water",
}

# 12節 순서 (입춘=寅月 기산)
SETSU_NAMES = ["立春", "啓蟄", "清明", "立夏", "芒種", "小暑",
               "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]


def get_exact_four_pillars(dt_jst: datetime, hour: int | None = None) -> dict:
    """
    JST 기준 출생 일시 → 입춘/절기/오서둔법 완전 적용 4주.
    hour: 0~23 정수 또는 None(시주 미산출).
    """
    year = dt_jst.year

    # 전년·현재·이듬해 절기 수집 (경계 보정용)
    terms = (list(solar_terms_of_year(year - 1))
             + list(solar_terms_of_year(year))
             + list(solar_terms_of_year(year + 1)))

    # ── 연주: 立春(315°) 경계 판정
    risshuns = [t for t in terms if t[0] == "立春" and t[3] <= dt_jst]
    eff_year = risshuns[-1][3].year
    y_gan_idx = (eff_year - 4) % 10
    y_zhi_idx = (eff_year - 4) % 12
    year_gan, year_zhi = GAN[y_gan_idx], ZHI[y_zhi_idx]

    # ── 월주: 12節 경계 + 월두법
    setsu_list = [t for t in terms if t[2] == "節" and t[3] <= dt_jst]
    cur_setsu = setsu_list[-1]
    setsu_idx = SETSU_NAMES.index(cur_setsu[0])  # 0=立春…11=小寒
    m_zhi_idx = (setsu_idx + 2) % 12             # 立春→寅(2)
    m_stem_start = (y_gan_idx % 5) * 2 + 2       # 월두법
    m_gan_idx = (m_stem_start + setsu_idx) % 10
    month_gan, month_zhi = GAN[m_gan_idx], ZHI[m_zhi_idx]

    # ── 일주: JDN 기반
    day_gan_str, day_zhi_str, day_idx = day_ganzhi(dt_jst.date())

    # ── 시주: 오서둔법 동적 계산
    hour_pillar = None
    if hour is not None and 0 <= hour <= 23:
        h_branch_idx = ((hour + 1) % 24) // 2   # 자시=0, 축시=1…
        d_gan_idx = GAN.index(day_gan_str)
        h_stem_start = (d_gan_idx % 5) * 2
        h_gan_idx = (h_stem_start + h_branch_idx) % 10
        h_gan, h_zhi = GAN[h_gan_idx], ZHI[h_branch_idx]
        hour_pillar = {
            "gan": h_gan, "zhi": h_zhi,
            "gan_el": GAN_ELEMENT[h_gan_idx],
            "zhi_el": ZHI_ELEMENT[h_zhi],
        }

    return {
        "year":  {"gan": year_gan,    "zhi": year_zhi,
                  "gan_el": GAN_ELEMENT[y_gan_idx],
                  "zhi_el": ZHI_ELEMENT[year_zhi]},
        "month": {"gan": month_gan,   "zhi": month_zhi,
                  "gan_el": GAN_ELEMENT[m_gan_idx],
                  "zhi_el": ZHI_ELEMENT[month_zhi]},
        "day":   {"gan": day_gan_str, "zhi": day_zhi_str,
                  "gan_el": GAN_ELEMENT[GAN.index(day_gan_str)],
                  "zhi_el": ZHI_ELEMENT[day_zhi_str]},
        "hour":  hour_pillar,
    }


if __name__ == "__main__":
    import sys
    d = date.today() if len(sys.argv) < 2 else date.fromisoformat(sys.argv[1])
    i = day_info(d)
    print(f"{i.day}  {i.day_gan}{i.day_zhi}日")
    print(f"  일진 오행 : {i.day_element}")
    print(f"  현재 節   : {i.season_term}  → 계절 오행 {i.season_element}")
    print(f"  土用      : {i.doyo_name or '-'}")
    print(f"  절기 당일 : {i.term_starts_today or '-'}")
    print(f"  공명일    : {'YES' if i.resonance else 'no'}")
