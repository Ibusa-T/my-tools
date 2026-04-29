import os
import io
import asyncio
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from groq import Groq
import edge_tts
import json
import base64
import cgi  # 【追加】Multipart解析用

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class VoiceAgentHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/voice':
            # --- [改修箇所] Multipartの解析 ---
            # cgiモジュールを使って、履歴(text)と音声(file)を分離します
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST'}
            )

            # Swift側で指定したname="history"とname="audio"で取得
            history_json = form.getvalue("history") or "[]"
            audio_field = form["audio"]
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            input_filename = f"input_{timestamp}.m4a"
            output_filename = f"response_{timestamp}.mp3"

            # 音声バイナリをファイルに保存
            with open(input_filename, "wb") as f:
                f.write(audio_field.file.read())

            print(f">> 受信完了: {input_filename} / 履歴: {history_json}")

            # 非同期処理を実行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # 履歴(history_json)も引数に渡す
            response_json_str = loop.run_until_complete(
                self.process_ai(input_filename, output_filename, history_json)
            )
            loop.close()

            # --- [改修箇所] JSONレスポンスの送信 ---
            if response_json_str:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json') # Content-TypeをJSONに変更
                self.end_headers()
                self.wfile.write(response_json_str.encode('utf-8'))
            else:
                self.send_error(500, "Processing Error")

            self.cleanup_files([input_filename, output_filename])

    # --- 他の do_GET, do_HEAD, cleanup_files はそのまま ---

    async def process_ai(self, in_file, out_file, history_json):
        """履歴を考慮して推論し、JSONを返す"""
        try:
            # 1. 履歴のパース
            history = json.loads(history_json)

            # 2. Groq Whisper (文字起こし)
            with open(in_file, "rb") as file:
                user_text = groq_client.audio.transcriptions.create(
                    file=(in_file, file.read()),
                    model="whisper-large-v3-turbo",
                    response_format="text",
                    language="ja"
                )
            
            # 3. Llamaへのメッセージ構築 (履歴を注入)
            # システムプロンプト + 過去の履歴 + 今回の発言
            messages = [{"role": "system", "content": "あなたは投資アシスタントのGuardianです。簡潔に1-2文で回答してください。"}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_text})

            # 4. Groq LLM 推論
            chat_completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages
            )
            ai_text = chat_completion.choices[0].message.content

            # 5. Edge TTS (音声生成)
            communicate = edge_tts.Communicate(ai_text, "ja-JP-NanamiNeural")
            await communicate.save(out_file)
            
            # 6. 音声データをBase64にエンコード
            with open(out_file, "rb") as f:
                audio_bytes = f.read()
                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # 7. Swift側が期待する形式の辞書を作成
            result = {
                "user_text": user_text,
                "ai_text": ai_text,
                "audio_data": audio_base64
            }
            return json.dumps(result)
        
        except Exception as e:
            print(f"❌ 処理エラー: {e}")
            error_result = {"user_text": "Error", "ai_text": f"エラーが発生しました: {str(e)}", "audio_data": ""}
            return json.dumps(error_result)

    # 既存のメソッド（cleanup_files, run_server等）をここに追加
