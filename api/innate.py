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

# ── Gemini 프롬프트 (언어화 전용) ─────────────────────────

PROMPTS = {
"jp": """あなたはFive Resonanceの五行音響アナリストです。
以下の計算済みデータを【音とエネルギーの言葉】のみで表現してください。

【厳格ルール】
1. 占いや運勢の言葉（運気, 吉, 凶, 運命）は絶対禁止。
2. 断定ではなく「〜の気配・傾向があります」と描写。
3. 出力は以下のJSONのみ。前置き不要。

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


def gemini_narrate(model_data: dict, lang: str) -> dict:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = PROMPTS.get(lang, PROMPTS["jp"]).format(
        data=json.dumps(model_data, ensure_ascii=False)
    )
    resp = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    return json.loads(resp.text)


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

            self._json(200, {
                "pillars":     pillars,
                "model_data":  model_data,
                "sound_focus": sound_focus,
                "reading":     reading,
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
