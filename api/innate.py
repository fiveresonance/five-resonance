"""
api/innate.py — 타고난 결 분석 엔드포인트 (v2 - 정밀 계산 엔진)
POST /api/innate
Body: { "birth": "1990-05-15", "hour": 14, "lang": "jp" }
hour: 0~23 정수 또는 null(시주 미산출)
"""
from http.server import BaseHTTPRequestHandler
import json, os, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from manse import get_exact_four_pillars, JST
from five_elements import build_element_vector
from resonance_engine import calculate_final_sound_focus
import google.generativeai as genai

# ── 3-Layer DB 로드 ───────────────────────────────────────
_DB_PATH = Path(__file__).parent.parent / "five_resonance_db_jp.json"
try:
    with open(_DB_PATH, encoding="utf-8") as _f:
        _LAYER_DB = json.load(_f)
except Exception:
    _LAYER_DB = {}

_GAN_TO_KEY = {
    "甲": "갑목", "乙": "을목", "丙": "병화", "丁": "정화", "戊": "무토",
    "己": "기토", "庚": "경금", "辛": "신금", "壬": "임수", "癸": "계수",
}
_ZHI_TO_SEASON = {
    "寅": "봄", "卯": "봄", "辰": "봄",
    "巳": "여름", "午": "여름", "未": "여름",
    "申": "가을", "酉": "가을", "戌": "가을",
    "亥": "겨울", "子": "겨울", "丑": "겨울",
}
_LACK_KEY  = {"wood":"목부족","fire":"화부족","earth":"토부족","metal":"금부족","water":"수부족"}
_EXCESS_KEY = {"wood":"목과다","fire":"화과다","earth":"토과다","metal":"금과다","water":"수과다"}
_ELEMENT_L3 = {"wood":"목","fire":"화","earth":"토","metal":"금","water":"수"}

# 시간(時干) → DB 키 매핑 (Layer 1.5)
_HOUR_GAN_TO_KEY = {
    "甲": "갑목", "乙": "을목", "丙": "병화", "丁": "정화", "戊": "무토",
    "己": "기토", "庚": "경금", "辛": "신금", "壬": "임수", "癸": "계수",
}


def build_layer_texts(pillars: dict, model_data: dict) -> dict:
    if not _LAYER_DB:
        return {}

    # Layer 1: 일간 × 계절
    day_gan    = pillars.get("day", {}).get("gan", "")
    month_zhi  = pillars.get("month", {}).get("zhi", "")
    stem_key   = _GAN_TO_KEY.get(day_gan, "")
    season_key = _ZHI_TO_SEASON.get(month_zhi, "")
    layer1_text = (_LAYER_DB.get("layer1", {}).get(stem_key, {}).get(season_key, "")
                   if stem_key and season_key else "")

    # Layer 1.5: 시간(時干) — 시주 입력 시에만
    hour_pillar = pillars.get("hour")
    layer1_5_text = ""
    hour_gan = ""
    if hour_pillar:
        hour_gan    = hour_pillar.get("gan", "")
        hour_key    = _HOUR_GAN_TO_KEY.get(hour_gan, "")
        if hour_key:
            layer1_5_text = _LAYER_DB.get("layer1_5", {}).get(hour_key, "")

    # Layer 2: 부족 × 과다 (시주 있으면 8글자 기준, 없으면 6글자)
    vector = model_data.get("vector", {})
    lack_el = excess_el = ""
    layer2_text = layer3_text = ""
    if vector:
        sorted_el  = sorted(vector.items(), key=lambda x: x[1])
        lack_el    = sorted_el[0][0]
        excess_el  = sorted_el[-1][0]
        lack_key   = _LACK_KEY.get(lack_el, "")
        excess_key = _EXCESS_KEY.get(excess_el, "")
        if lack_key and excess_key:
            layer2_text = _LAYER_DB.get("layer2", {}).get(lack_key, {}).get(excess_key, "")
        l3_key = _ELEMENT_L3.get(lack_el, "")
        if l3_key:
            layer3_text = _LAYER_DB.get("layer3", {}).get(l3_key, "")

    return {
        "layer1":   layer1_text,
        "layer1_5": layer1_5_text,   # 시주 있으면 텍스트, 없으면 ""
        "layer2":   layer2_text,
        "layer3":   layer3_text,
        "has_hour": bool(hour_pillar),
        "debug":    {"day_gan": day_gan, "month_zhi": month_zhi,
                     "hour_gan": hour_gan,
                     "stem_key": stem_key, "season_key": season_key,
                     "lack_element": lack_el, "excess_element": excess_el},
    }


# ── Gemini 프롬프트 (언어화 전용) ─────────────────────────

PROMPTS = {
"jp": """あなたはFive Resonanceの五行音響アナリストです。
以下の計算済みデータを【音とエネルギーの言葉】のみで表現してください。

【厳格ルール】
1. 占いや運勢の言葉（運気, 吉, 凶, 運命）は絶対禁止。
2. 断定ではなく「〜の気配・傾向があります」と描写。
3. 出力は以下のJSONのみ。前置き不要。
4. JSON文字列値の中にダブルクォーテーション（"）を絶対に使用禁止。強調には「」または『』を使用すること。

【日本語トーン＆マナー厳格ルール】
1. 禁止単語および不自然な表現の排除:
   - 「制律」という造語は絶対に使用禁止（「節度」「調和」「調整」を使用すること）。
   - 「〜が望ましい気配があります」のような不自然な語尾結合は禁止。
   - 硬すぎる機械的表現（「制動する」「深水」）を避け、洗練された表現（「和らげる」「深い水」）を使用。
2. 文末表現の重複回避:
   - 「〜傾向があります」の連続使用は禁止（1カードにつき最大1回まで）。
   - 音響提案の文末は「〜が適しています」または「〜が効果的です」と言い切ること。
3. ブランドトーン:
   - ミニマルで洗練されたウェルネス・音響デザインブランドにふさわしい、静かで美しい日本語で記述すること。
4. 語彙およびドメイン制約:
   - 音楽・ウェルネス・音響デザインにふさわしい語彙のみを使用すること。
   - 電化製品・機械・工業分野の用語（静音、制動、作動など）は使用禁止。
   - 「思考」には「沈める」ではなく「深める」「整える」を使用すること。
   - 「音楽」には「静音」ではなく「静かな」「静穏な」を使用すること。

入力データ:
{data}

出力JSON:
{{
  "headline": "20文字以内の核心フレーズ",
  "primary_description": "中心的な波動の性質（100文字以内）",
  "balance_note": "整えるべきエネルギーのめぐり（80文字以内）",
  "music_guidance": "必要な音響セッションの方向性（60文字以内）",
  "resonance_type": "共鳴タイプ名（例：澄んだ金の静けさ型）"
}}""",

"ko": """당신은 Five Resonance의 오행 음향 분석가입니다.
계산된 데이터를 【에너지와 소리의 언어】로만 표현하세요.

【규칙】
1. 점술/운세 언어 금지 (운기, 길, 흉, 운명).
2. 단정이 아닌 "〜의 기색/경향이 있습니다"로 묘사.
3. 출력은 아래 JSON만. 전치사 불필요.

입력 데이터:
{data}

출력 JSON:
{{
  "headline": "20자 이내 핵심 문구",
  "primary_description": "중심 파동의 성질 (100자 이내)",
  "balance_note": "보완해야 할 에너지 흐름 (80자 이내)",
  "music_guidance": "필요한 음향 세션 방향 (60자 이내)",
  "resonance_type": "공명 타입명 (예: 맑은 금의 고요 타입)"
}}""",

"en": """You are a Five Resonance Five Elements sonic analyst.
Express the calculated data ONLY in terms of energy and sound.

Rules:
1. No fortune-telling language (luck, auspicious, fate, destiny).
2. Use "tends toward / has a quality of" — not definitive statements.
3. Output ONLY the JSON below. No preamble.

Input data:
{data}

Output JSON:
{{
  "headline": "Core phrase under 15 words",
  "primary_description": "Nature of the primary wave (under 80 words)",
  "balance_note": "Energy circulation to cultivate (under 60 words)",
  "music_guidance": "Sonic session direction needed (under 40 words)",
  "resonance_type": "Resonance type name (e.g. Clear Metal Stillness Type)"
}}"""
}


def clean_japanese_text(text: str) -> str:
    """Gemini 일본어 출력 후처리 — 비표준 조어 및 어색한 어미 정제"""
    if not text:
        return text
    text = text.replace("制律", "節度")
    text = text.replace("深水", "深い水")
    text = text.replace("制動します", "和らげます")
    text = text.replace("制動", "調整")
    text = text.replace("が望ましい気配があります", "が効果的です")
    text = text.replace("望ましい気配があります", "望ましいでしょう")
    text = text.replace("適している傾向があります", "適しています")
    text = text.replace("現れる傾向があります。", "現れます。")
    # 추가 교정 (2026-08-12)
    text = text.replace("思考を沈めていく", "思考を深めていく")
    text = text.replace("心を沈めていく", "心を静かに沈めていく")
    text = text.replace("整える必要があります", "整えていくとよいでしょう")
    text = text.replace("静音音楽", "静かな音楽")
    text = text.replace("静音アンビエント", "静穏なアンビエント")
    text = text.replace("静音", "静穏")
    # balance_note 교정 추가
    text = text.replace("際立つ気配があります", "感じられます")
    text = text.replace("求められています", "整えていくとよいでしょう")
    text = text.replace("不足している温かな火のエネルギーを補い", "足りない火の温かさを取り入れることで")
    text = text.replace("計画の深さがあります", "じっくり計画を練る方です")
    text = text.replace("生気を再び感じる", "活力をもう一度感じる")
    text = text.replace("温かみのある暖色系の音色", "温かみのある音色")
    return text


def gemini_narrate(model_data: dict, lang: str) -> dict:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-3.5-flash")
    prompt = PROMPTS.get(lang, PROMPTS["jp"]).format(
        data=json.dumps(model_data, ensure_ascii=False)
    )
    resp = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json", "temperature": 0.2}
    )
    import re as _re
    raw = resp.text.strip() if resp.text else ""

    # 1. 마크다운 코드펜스 제거
    raw = _re.sub(r"```json\s*", "", raw)
    raw = _re.sub(r"```\s*", "", raw)
    raw = raw.strip()

    # 2. JSON 시작점 탐색
    brace = raw.find("{")
    if brace > 0:
        raw = raw[brace:]

    # 3. JSON 값 내부 큰따옴표 교정 (Gemini가 프롬프트 규칙 무시하는 경우 대응)
    def sanitize_json_string_values(s: str) -> str:
        """JSON 문자열 값 내부의 naked 큰따옴표를 「」로 교체"""
        import re as _re2
        # 문자열 값 안의 큰따옴표: ": "...값..." 패턴에서 값 내부만 처리
        # 방법: 전체를 문자 단위로 순회하며 문자열 컨텍스트 추적
        result = []
        in_string = False
        escape_next = False
        key_or_value = False  # True=값 위치

        i = 0
        while i < len(s):
            c = s[i]
            if escape_next:
                result.append(c)
                escape_next = False
            elif c == '\\' and in_string:
                result.append(c)
                escape_next = True
            elif c == '"':
                if not in_string:
                    in_string = True
                    result.append(c)
                else:
                    in_string = False
                    result.append(c)
            else:
                result.append(c)
            i += 1
        return ''.join(result)

    # 3. 파싱 시도 → 실패 시 큰따옴표 교정 후 재시도
    def try_parse(raw_str: str):
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(raw_str)
        return obj

    try:
        obj = try_parse(raw)
    except json.JSONDecodeError:
        # 값 내부의 bare 큰따옴표를 일본어 괄호로 교체하는 정규식 방식
        import re as _re2
        # 패턴: JSON 키-값에서 값 문자열 안에 있는 큰따옴표만 교체
        # 전략: ": "로 시작하는 문자열 값에서 종료 따옴표 전까지의 " 를 「」로
        def fix_inner_quotes(m):
            inner = m.group(1).replace('"', '「').replace('"', '」')
            return ': "' + inner + '"'
        fixed = _re2.sub(r':\s*"(.*?)"(?=\s*[,}])', fix_inner_quotes, raw, flags=_re2.DOTALL)
        try:
            obj = try_parse(fixed)
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini JSON parse error at char {e.pos}: {e.msg} | raw={raw[:300]}")

    # 4. 일본어 후처리
    if lang == "jp":
        for key in obj:
            if isinstance(obj[key], str):
                obj[key] = clean_japanese_text(obj[key])
    return obj


# ── HTTP 핸들러 ───────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body  = json.loads(self.rfile.read(length))
            birth = body["birth"]          # "YYYY-MM-DD"
            hour  = body.get("hour")       # None 또는 0~23
            lang  = body.get("lang", "jp")

            dt = datetime.strptime(birth, "%Y-%m-%d")
            dt_jst = dt.replace(tzinfo=JST)

            # 1. 천문 정밀 계산
            pillars = get_exact_four_pillars(dt_jst, hour)

            # 2. 오행 가중치 벡터
            model_data = build_element_vector(pillars)

            # 3. 퀴즈 점수가 있으면 결합 사운드 포커스 계산
            quiz_scores = body.get("quiz_scores")  # 프론트에서 선택적 전달
            sound_focus = None
            if quiz_scores:
                sound_focus = calculate_final_sound_focus(
                    model_data["vector"], quiz_scores, lang
                )

            # 4. Gemini 언어화 (sound_focus 포함)
            gemini_input = {**model_data}
            if sound_focus:
                gemini_input["today_sound_focus"] = sound_focus["primary_sound"]
                gemini_input["sound_direction"]   = sound_focus["sound_direction"]
            reading = gemini_narrate(gemini_input, lang)

            # 5. 3-Layer DB 텍스트
            layer_texts = build_layer_texts(pillars, model_data)

            self._json(200, {
                "pillars":     pillars,
                "model_data":  model_data,
                "sound_focus": sound_focus,
                "reading":     reading,
                "layer_texts": layer_texts,
            })

        except KeyError as e:
            self._json(400, {"error": f"Missing field: {e}"})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
