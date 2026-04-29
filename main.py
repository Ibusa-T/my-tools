import os
import asyncio
import time
import json
import base64
import cgi
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from groq import Groq
import edge_tts

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class VoiceAgentHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/voice':
            # Multipartフォームの解析
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST'}
            )

            history_json = form.getvalue("history") or "[]"
            audio_field = form["audio"]
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            in_file = f"in_{timestamp}.m4a"
            out_file = f"out_{timestamp}.mp3"

            with open(in_file, "wb") as f:
                f.write(audio_field.file.read())

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response_json = loop.run_until_complete(self.process_ai(in_file, out_file, history_json))
            loop.close()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(response_json.encode('utf-8'))

            for f in [in_file, out_file]:
                if os.path.exists(f): os.remove(f)

    async def process_ai(self, in_file, out_file, history_json):
        try:
            history = json.loads(history_json)
            # A. Whisper
            with open(in_file, "rb") as f:
                user_text = groq_client.audio.transcriptions.create(
                    file=(in_file, f.read()),
                    model="whisper-large-v3-turbo",
                    language="ja"
                ).text

            # B. Llama (履歴の注入)
            messages = [{"role": "system", "content": "あなたは投資アシスタントGuardianです。簡潔に1-2文で回答してください。"}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_text})

            chat = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages
            )
            ai_text = chat.choices[0].message.content

            # C. TTS
            communicate = edge_tts.Communicate(ai_text, "ja-JP-NanamiNeural")
            await communicate.save(out_file)
            
            with open(out_file, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode('utf-8')
            
            return json.dumps({"user_text": user_text, "ai_text": ai_text, "audio_data": audio_b64})
        except Exception as e:
            return json.dumps({"user_text": "Error", "ai_text": str(e), "audio_data": ""})

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Guardian is Running")

def run():
    port = int(os.environ.get("PORT", 8000))
    HTTPServer(('', port), VoiceAgentHandler).serve_forever()

if __name__ == "__main__":
    run()
