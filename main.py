import os
import io
import asyncio
import time
import json
import base64
import cgi  # Multipart解析用（Python 3.13で廃止予定だが現時点では必須）
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from groq import Groq
import edge_tts

# 環境変数の読み込み
load_dotenv()

# クライアントの初期化
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class VoiceAgentHandler(BaseHTTPRequestHandler):
    
    # 1. ヘルスチェック・ブラウザアクセス用
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("Guardian Service is Running".encode('utf-8'))

    # 2. Render等の監視サービス用
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()

    # 3. メインの音声・履歴処理
    def do_POST(self):
        if self.path == '/voice':
            try:
                # Multipartデータの解析
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST'}
                )

                # Swift側で指定したキー名で取得
                history_json = form.getvalue("history") or "[]"
                audio_field = form["audio"]
                
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                in_file = f"in_{timestamp}.m4a"
                out_file = f"out_{timestamp}.mp3"

                # 送られてきた音声バイナリを一時ファイルに保存
                with open(in_file, "wb") as f:
                    f.write(audio_field.file.read())

                # 非同期イベントループの作成と実行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response_json_str = loop.run_until_complete(
                    self.process_ai(in_file, out_file, history_json)
                )
                loop.close()

                # SwiftへJSONとして返却
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(response_json_str.encode('utf-8'))

                # 一時ファイルの削除
                for f in [in_file, out_file]:
                    if os.path.exists(f):
                        os.remove(f)
            
            except Exception as e:
                print(f"❌ Server Error: {e}")
                self.send_error(500, str(e))

    async def process_ai(self, in_file, out_file, history_json):
        """履歴を考慮した推論ロジック"""
        try:
            # 履歴のパース
            history = json.loads(history_json)

            # A. Whisperによる文字起こし
            with open(in_file, "rb") as f:
                user_text = groq_client.audio.transcriptions.create(
                    file=(in_file, f.read()),
                    model="whisper-large-v3-turbo",
                    language="ja"
                ).text

            # B. Llamaへのプロンプト組み立て
            messages = [{"role": "system", "content": "あなたは投資アシスタントです。簡潔に回答してください。"}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_text})

            # C. Llamaによる回答生成
            chat = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages
            )
            ai_text = chat.choices[0].message.content

            # D. Edge TTSによる音声合成
            await edge_tts.Communicate(ai_text, "ja-JP-NanamiNeural").save(out_file)
            
            # E. 音声バイナリをBase64文字列に変換
            with open(out_file, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode('utf-8')
            
            # Swift側がデコードできるJSONを返す
            return json.dumps({
                "user_text": user_text,
                "ai_text": ai_text,
                "audio_data": audio_b64
            })
        except Exception as e:
            return json.dumps({"user_text": "Error", "ai_text": str(e), "audio_data": ""})

def run_server():
    port = int(os.environ.get("PORT", 8000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, VoiceAgentHandler)
    print(f"🚀 Server running on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
