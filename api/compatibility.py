"""
api/compatibility.py — 관계 공명 분석 엔드포인트 (v2)
POST /api/compatibility
Body: { "birth_a": "1990-05-15", "hour_a": 14,
        "birth_b": "1995-11-03", "hour_b": 9, "lang": "jp" }
"""
from http.server import BaseHTTPRequestHandler
import json, os, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from manse import get_exact_four_pillars, JST
from five_elements import build_element_vector, element_relation
import google.generativeai as genai

RELATION_DESC = {
    "共鳴型": {"jp": "同じ波動が深く響き合う関係",    "ko": "같은 파동이 깊이 공명하는 관계",    "en": "Same frequencies resonating deeply"},
    "補完型": {"jp": "一方が他方を自然に育てる関係",  "ko": "한쪽이 다른 쪽을 자연스럽게 키우는 관계", "en": "One naturally nourishes the other"},
    "成長型": {"jp": "互いに引き出し合い成長する関係", "ko": "서로를 끌어내어 함께 성장하는 관계", "en": "Each draws out the other's growth"},
    "緊張型": {"jp": "緊張が変化のきっかけになる関係", "ko": "긴장이 변화의 계기가 되는 관계",    "en": "Tension becomes a catalyst for change"},
    "抑制型": {"jp": "強い波動が均衡を問い直す関係",  "ko": "강한 파동이 균형을 다시 묻는 관계",  "en": "Strong energy questions the balance"},
    "鏡型":   {"jp": "互いを映し出す鏡のような関係",  "ko": "서로를 비추는 거울 같은 관계",      "en": "Mirror-like reflection of each other"},
}

PROMPTS = {
"jp": """あなたはFive Resonanceの五行関係アナリストです。
以下の計算済みデータを【音とエネルギーの言葉】で表現してください。

【厳格ルール】
1. 占い・運命の言葉禁止（縁、運命、相性◎など）。
2. 出力は以下のJSONのみ。
3. JSON文字列値の中にダブルクォーテーション（"）を絶対に使用禁止。強調には「」または『』を使用すること。

【日本語トーン＆マナー厳格ルール】
1. 禁止単語および不自然な表現の排除:
   - 「制律」という造語は絶対に使用禁止（「節度」「調和」「調整」を使用すること）。
   - 硬すぎる機械的表現（「制動する」「深水」）を避け、洗練された表現を使用。
2. 文末表現の重複回避:
   - 「〜傾向があります」の連続使用は禁止（1カードにつき最大1回まで）。
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
  "relation_headline": "この関係を表す20文字以内のフレーズ",
  "relation_description": "関係性の本質（120文字以内）",
  "harmony_note": "調和のポイント（80文字以内）",
  "tension_note": "緊張のポイント（80文字以内）",
  "music_suggestion": "二人で聴くべき五行音楽の方向性（60文字以内）"
}}""",

"ko": """당신은 Five Resonance의 오행 관계 분석가입니다.
계산된 데이터를 【에너지와 소리의 언어】로 표현하세요.

【규칙】
1. 점술·운명 언어 금지 (인연, 운명, 궁합◎ 등).
2. 출력은 아래 JSON만.

입력 데이터:
{data}

출력 JSON:
{{
  "relation_headline": "이 관계를 표현하는 20자 이내 문구",
  "relation_description": "관계의 본질 (120자 이내)",
  "harmony_note": "조화 포인트 (80자 이내)",
  "tension_note": "긴장 포인트 (80자 이내)",
  "music_suggestion": "두 사람이 함께 들을 오행 음악 방향 (60자 이내)"
}}""",

"en": """You are a Five Resonance Five Elements relationship analyst.
Express the calculated data ONLY in terms of energy and sound.

Rules:
1. No fate/destiny language (soulmates, destined, compatibility score).
2. Output ONLY the JSON below.

Input data:
{data}

Output JSON:
{{
  "relation_headline": "Phrase under 15 words for this relationship",
  "relation_description": "Nature of the relationship (under 80 words)",
  "harmony_note": "Harmony point (under 50 words)",
  "tension_note": "Tension point (under 50 words)",
  "music_suggestion": "Five element music direction for both (under 40 words)"
}}"""
}


def clean_japanese_text(text: str) -> str:
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
    return text


def gemini_narrate(data: dict, lang: str) -> dict:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-3.5-flash")
    prompt = PROMPTS.get(lang, PROMPTS["jp"]).format(
        data=json.dumps(data, ensure_ascii=False)
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

    # 4. 파싱 시도
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini JSON parse error at char {e.pos}: {e.msg} | raw={raw[:200]}")

    # 4. 일본어 후처리
    if lang == "jp":
        for key in obj:
            if isinstance(obj[key], str):
                obj[key] = clean_japanese_text(obj[key])
    return obj


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
            lang = body.get("lang", "jp")

            def parse(birth_key, hour_key):
                dt = datetime.strptime(body[birth_key], "%Y-%m-%d")
                dt_jst = dt.replace(tzinfo=JST)
                hour = body.get(hour_key)
                pillars = get_exact_four_pillars(dt_jst, hour)
                return build_element_vector(pillars), pillars

            model_a, pillars_a = parse("birth_a", "hour_a")
            model_b, pillars_b = parse("birth_b", "hour_b")

            rel_type = element_relation(
                model_a["primary"], model_b["primary"],
                model_a["vector"],  model_b["vector"]
            )

            combined = {
                "person_a":        model_a,
                "person_b":        model_b,
                "relation_type":   rel_type,
                "relation_desc":   RELATION_DESC[rel_type][lang],
            }

            reading = gemini_narrate(combined, lang)

            self._json(200, {
                "pillars_a":     pillars_a,
                "pillars_b":     pillars_b,
                "model_a":       model_a,
                "model_b":       model_b,
                "relation_type": rel_type,
                "reading":       reading,
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
