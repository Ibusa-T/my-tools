import os
import io
import asyncio
import json
import base64
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from groq import Groq
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
- 「もう大丈夫」
- 「今日は終わり」

"""

def get_system_prompt():
    return f"{SYSTEM_BASE}\n\n【制約】{CONSTRAINTS}\n\n【思考プロセス】{BEHAVIOR_LOGIC}"

system_prompt = get_system_prompt()

# --- 2. INTENTS_DB (RAG/Function Calling用) ---
# 元のファイルから継承
INTENTS_DB = {
    "playMusic": {
        "summary": "ミュージックアプリで楽曲やプレイリストを再生する",
        "parameters": [
            {"name": "song_name", "type": "string", "description": "再生したい曲名"},
            {"name": "artist_name", "type": "string", "description": "再生したいアーティスト名"},
            {"name": "playlist_name", "type": "string", "description": "再生したいプレイリスト名"}
        ],
        "usage_example": ["音楽をかけて", "再生して", "流して"],
        "swift_action": "PlayMusicIntent"
    },
    "setReminder": {
        "summary": "リマインダーに予定を追加する",
        "parameters": [
            {"name": "title", "type": "string", "description": "内容"},
            {"name": "target_time", "type": "string", "description": "時刻"}
        ],
        "usage_example": ["リマインダーに予定を入れて"],
        "swift_action": "SetReminderIntent"
    }
}

# --- 3. サーバーハンドラー ---
load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class VoiceAgentHandler(BaseHTTPRequestHandler):
    
    def search_intent(self, query: str) -> dict:
        """インメモリでのあいまい検索処理"""
        for intent_key, intent_data in INTENTS_DB.items():
            for example in intent_data.get("usage_example", []):
                if example in query or query in example:
                    return intent_data
        return {}
        # 1. ヘルスチェック・ブラウザアクセス用
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("Service is Running".encode('utf-8'))

    # 2. Render等の監視サービス用
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
    
    def do_POST(self):
        if self.path == '/voice':
            try:
                # 1. マルチパートデータの解析
                ctype, pdict = cgi.parse_header(self.headers['content-type'])
                if ctype == 'multipart/form-data':
                    # pdict['boundary'] を bytes に変換する必要がある場合があるため修正
                    if isinstance(pdict['boundary'], str):
                        pdict['boundary'] = pdict['boundary'].encode('utf-8')
                    
                    form = cgi.FieldStorage(
                        fp=self.rfile,
                        headers=self.headers,
                        environ={'REQUEST_METHOD': 'POST'}
                    )
             
                history_json = form.getvalue("history") or "[]"
                audio_field = form["audio"]
                
                # iOSから送られてきたM4Aデータそのもの
                audio_data = audio_field.file.read()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # 修正: raw_pcm ではなく audio_data (M4A) を渡す
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
                # エラー詳細をJSONで返すとiOS側でデバッグしやすい
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        async def process_ai(self, audio_data, history_json):
            try:
                history = json.loads(history_json)

                # A. Audio Data -> BytesIO (WhisperはM4Aを直接受け取れます)
                audio_buffer = io.BytesIO(audio_data)
                audio_buffer.name = "input.m4a" # 拡張子を明示するのがコツ

                # B. Whisper Transcription (修正箇所)
                # waveモジュールを使わず、bufferをそのまま渡します
                transcription = groq_client.audio.transcriptions.create(
                    file=audio_buffer,
                    model="whisper-large-v3-turbo",
                    language="ja"
                )
                user_text = transcription.text

                # --- C, D (LLM推論) は元のロジックを維持 ---
                # ... (中略) ...

                # E. Edge TTS
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
    print(f"🚀 Server running on port {port} (Full Memory Mode)")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()