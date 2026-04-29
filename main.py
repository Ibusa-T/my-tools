import os
import io
import asyncio
import time  # タイムスタンプ用
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from groq import Groq
import edge_tts
import json
import base64

# 環境変数の読み込み
load_dotenv()

# クライアントの初期化
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class VoiceAgentHandler(BaseHTTPRequestHandler):
    def do_POST(self):
          # これはrenderのパスに置き換え
        if self.path == '/voice':
            # 1. 現在時刻からタイムスタンプを生成 (例: 20260426_220505)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            input_filename = f"input_{timestamp}.m4a"
            output_filename = f"response_{timestamp}.mp3"
    

            # 2. iPhoneから送られてきた音声バイナリを取得
            content_length = int(self.headers.get('Content-Length', 0))
            audio_bytes = self.rfile.read(content_length)
            
            with open(input_filename, "wb") as f:
                f.write(audio_bytes)

            print(f">> 受信完了: {input_filename} (サイズ: {content_length} bytes)")

            # 3. 非同期処理を同期的に実行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response_audio_data = loop.run_until_complete(
                self.process_ai(input_filename, output_filename)
            )
            loop.close()

            # 4. レスポンス送信
            if response_audio_data:
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.end_headers()
                self.wfile.write(response_audio_data)
            else:
                self.send_error(500, "Processing Error")

            # 5. 【重要】処理が終わった一時ファイルを削除（ストレージ圧迫防止）
            self.cleanup_files([input_filename, output_filename])

    def do_GET(self):
        """ヘルスチェック用 (Renderなどの監視サービスに対応)"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("<h1>Guardian Voice API</h1><p>Status: Running</p>".encode('utf-8'))

    def do_HEAD(self):
        """ヘルスチェック用 (Renderなどの監視サービスに対応)"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

    async def process_ai(self, in_file, out_file):
        """タイムスタンプ付きファイルを使用して推論"""
        try:
            # A. Groq Whisper
            with open(in_file, "rb") as file:
                user_text = groq_client.audio.transcriptions.create(
                    file=(in_file, file.read()),
                    model="whisper-large-v3-turbo",
                    response_format="text",
                    language="ja"
                )
            print(f"[{in_file}] あなた: {user_text}")
            response_body['user_text'] = user_text
            # B. Groq LLM (Guardian)
            chat_completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "あなたは投資アシスタントのGuardianです。簡潔に1-2文で回答してください。"},
                    {"role": "user", "content": user_text}
                ]
            )
            ai_text = chat_completion.choices[0].message.content
            print(f"[{out_file}] AI: {ai_text}")
            response_body['ai_text'] = ai_text
            # C. Edge TTS
            communicate = edge_tts.Communicate(ai_text, "ja-JP-NanamiNeural")
            await communicate.save(out_file)
            
            with open(out_file, "rb") as f:
                audio_data = f.read()
                audio_base64=b64.encode(audio_data)
                print(f"[{out_file}] 音声データ取得完了 ({len(audio_data)} bytes)")
                response_body={'user_text':user_text
                                     ,'ai_text':ai_text
                                     ,'audio_data':audio_data}
                return json.dumps(result)
        except Exception as e:
            response_body={'tesult':'❌ 処理エラー'
                                     ,'err_text':e}
                
            print(f"❌ 処理エラー: {e}")
            return json.dumps(result)

    def cleanup_files(self, files):
        """使用済みのファイルを削除"""
        for f in files:
            if os.path.exists(f):
                os.remove(f)
                print(f"🗑 削除済み: {f}")

def run_server():
    port = int(os.environ.get("PORT", 8000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, VoiceAgentHandler)
    print(f"🚀 Guardian Voice API (Timestamp Mode) running on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
