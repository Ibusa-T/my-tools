import os
import io
import asyncio
import json
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from groq import Groq
# Google の新世代公式SDKをインポート
from google import genai
from google.genai import types
import edge_tts
import cgi

# --- 1. プロンプト設定 ---
SYSTEM_BASE = "あなたはユーザーの思考を深めるインタビュアーです。"

CONSTRAINTS = """
- 1〜2文で簡潔に話してください。
- オウム返しするより、あなたの意見や感想を述べることに集中してください。
- 相手の話が長くても、最後まで話を聞いてください
"""

BEHAVIOR_LOGIC = """
# 相手の話題に対して、必ず以下のいずれかを行ってください
-「相手が答えやすくなる具体的な質問」
-「独自の視点」から新しい提案

# 相手が明確に以下のキーワードを使ったとき、「本日の会話は以上です。お疲れ様でした。」と一言添えて終了してください。
- 「終わり」
- 「終了」
- 「また明日」
- 「もう良いよ」
"""

def get_system_prompt():
    return f"{SYSTEM_BASE}\n\n【制約】{CONSTRAINTS}\n\n【思考プロセス】{BEHAVIOR_LOGIC}"

system_prompt = get_system_prompt()

# --- 2. INTENTS_DB (RAG/Function Calling用) ---
INTENTS_DB = {
    "LocationIntent": {
        "summary": "現在地や周辺の施設などの位置情報を確認・検索する",
        "parameters": [
            {"name": "query", "type": "String", "description": "検索したい場所や施設名（例：ここから一番近い、近くのコンビニ）"}
        ],
        "usage_example": ["ここから一番近い", "どこ", "近くの"],
        "swift_action": "LocationIntent"
    },
    "CalendarIntent": {
        "summary": "カレンダーからリマインダの予定を確認する",
        "parameters": [
            {"name": "time_frame", "type": "String", "description": "確認したい期間（今日の予定、今週の予定など）"}
        ],
        "usage_example": ["今日の予定", "今週の予定", "今月の予定"],
        "swift_action": "CalendarIntent"
    },
    "ReminderIntent": {
        "summary": "リマインダーに予定を追加、削除、または編集する",
        "parameters": [
            {"name": "action_type", "type": "String", "description": "実行する操作（追加、削除、編集）"},
            {"name": "title", "type": "String", "description": "予定の内容"},
            {"name": "target_time", "type": "String", "description": "時刻"}
        ],
        "usage_example": ["リマインダーに予定を入れて", "予定を削除して", "予定を編集して"],
        "swift_action": "ReminderIntent"
    },
    "HealthcareIntent": {
        "summary": "ヘルスケアのデータ（歩数や心拍数）を確認する",
        "parameters": [
            {"name": "data_type", "type": "String", "description": "確認したいデータ（歩数、心拍数など）"}
        ],
        "usage_example": ["歩数を確認", "心拍数を確認"],
        "swift_action": "HealthcareIntent"
    },
    "MusicIntent": {
        "summary": "ミュージックアプリで楽曲やプレイリストを再生、または停止する",
        "parameters": [
            {"name": "action_type", "type": "String", "description": "実行する操作（再生、停止）"},
            {"name": "song_name", "type": "String", "description": "再生したい曲名"},
            {"name": "artist_name", "type": "String", "description": "再生したいアーティスト名"},
            {"name": "playlist_name", "type": "String", "description": "再生したいプレイリスト名"}
        ],
        "usage_example": ["音楽をかけて", "再生して", "流して", "音楽を止めて"],
        "swift_action": "MusicIntent"
    }
}

# --- 3. クライアント初期化 ---
load_dotenv()

# 音声認識(STT)は引き続き爆速のGroq(Whisper)を維持
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# 思考エンジン(LLM)はGoogle公式クライアントを生成（.env の GEMINI_API_KEY を自動参照）
google_client = genai.Client()


class AnalyzerUtil:
    @staticmethod
    def multipart_field_storage(headers, rfile):
        ctype, pdict = cgi.parse_header(headers['content-type'])
        if ctype == 'multipart/form-data':
            if isinstance(pdict['boundary'], str):
                pdict['boundary'] = pdict['boundary'].encode('utf-8')
            return cgi.FieldStorage(fp=rfile, headers=headers, environ={'REQUEST_METHOD': 'POST'})
        else:
            raise ValueError("Content-Type is not multipart/form-data")

    @staticmethod
    def search_intent(query: str) -> dict:
        for intent_key, intent_data in INTENTS_DB.items():
            for example in intent_data.get("usage_example", []):
                if example in query or query in example:
                    return intent_data
        return {}

    @staticmethod
    def whisper_transcription(audio_buffer):
        return groq_client.audio.transcriptions.create(
                file=audio_buffer,
                model="whisper-large-v3-turbo",
                language="ja"
        )
    
    @staticmethod
    def gemma_intent_tool(matched_intent):
        """INTENTS_DBの定義をGoogle SDKのTool(Function Calling)形式に動的変換"""
        properties = {}
        required_fields = []
        
        for p in matched_intent.get("parameters", []):
            p_name = p["name"]
            properties[p_name] = types.Schema(
                type=types.Type.STRING,  # 引数は一律String型として定義
                description=p.get("description", "")
            )
            required_fields.append(p_name)
            
        return types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=matched_intent.get("swift_action", "IntentAction"),
                    description=matched_intent.get("summary", ""),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties=properties,
                        required=required_fields
                    )
                )
            ]
        )


class VoiceAgentHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("Service is Running".encode('utf-8'))

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()

    def do_POST(self):
        if self.path == '/voice':
            try:
                form = AnalyzerUtil.multipart_field_storage(self.headers, self.rfile)
                history_json = form.getvalue("history") or "[]"
                audio_field = form["audio"]
                audio_data = audio_field.file.read()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response_json_str = loop.run_until_complete(
                    self.process_ai(audio_data, history_json)
                )
                loop.close()

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(response_json_str.encode('utf-8'))
            
            except Exception as e:
                print(f"❌ Server Error: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
    
    async def process_ai(self, audio_data, history_json):
        try:
            history = json.loads(history_json)

            audio_buffer = io.BytesIO(audio_data)
            audio_buffer.name = "input.m4a"

            # --- B. Whisper Transcription ---
            user_text = AnalyzerUtil.whisper_transcription(audio_buffer).text
            
            # --- C. Intent Search & Tool Setup ---
            matched_intent = AnalyzerUtil.search_intent(user_text)
            google_tools = None
            
            if matched_intent:
                google_tools = [AnalyzerUtil.gemma_intent_tool(matched_intent)]
           
            # --- D. Gemma 4 推論 ---
            contents = []
            for msg in history:
                contents.append(
                    types.Content(
                        role="user" if msg["role"] == "user" else "model",
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                tools=google_tools if google_tools else None
            )

            response = google_client.models.generate_content(
                model='gemma-4-31b-it',
                contents=contents,
                config=config
            )
            
            ai_text = response.text or ""
            swift_action = ""
            extracted_parameters = {}

            if response.function_calls:
                tool_call = response.function_calls[0]
                swift_action = tool_call.name
                
                if tool_call.args:
                    # 💡【重要デバッグポイント】
                    # Gemmaがパラメータの値を配列（例：["今日"]）や別のオブジェクトとして返してきた場合、
                    # Swift側の [String: String] のデコードが失敗してクラッシュ（解析エラー）するため、
                    # すべての値を文字列型（String）に強制変換・フラット化してSwiftへパスします。
                    for k, v in dict(tool_call.args).items():
                        if isinstance(v, list):
                            extracted_parameters[k] = str(v[0]) if v else ""
                        else:
                            extracted_parameters[k] = str(v)
                
                if not ai_text:
                    ai_text = "承知いたしました。実行しますね。"

            # 履歴の更新
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": ai_text})

            # --- E. Edge TTS (音声合成) ---
            tts_buffer = io.BytesIO()
            communicate = edge_tts.Communicate(ai_text, "ja-JP-NanamiNeural")
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    tts_buffer.write(chunk["data"])
            
            audio_b64 = base64.b64encode(tts_buffer.getvalue()).decode('utf-8')
            
            return json.dumps({
                "user_text": user_text,
                "ai_text": ai_text,
                "audio_data": audio_b64,
                "swift_action": swift_action,
                "parameters": extracted_parameters
            })
        except Exception as e:
            print(f"❌ process_ai error: {e}")
            return json.dumps({"user_text": "Error", "ai_text": str(e), "audio_data": ""})


def run_server():
    port = int(os.environ.get("PORT", 8000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, VoiceAgentHandler)
    print(f"🚀 Server running on port {port} (Gemma 4 Pipeline Activated)")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()