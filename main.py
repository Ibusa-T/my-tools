import os
import io
import asyncio
import time
import json
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from groq import Groq
import edge_tts
import cgi
from difflib import get_close_matches
#プロンプト

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
# RAG
"""インメモリDB"""
INTENTS_DB = {
    "playMusic": {
        "summary": "ミュージックアプリで楽曲やプレイリストを再生する",
        "parameters": [
            {
                "name": "song_name",
                "type": "string",
                "description": "再生したい曲名（例: CRICIS）"
            },
            {
                "name": "artist_name",
                "type": "string",
                "description": "再生したいアーティスト名やグループ名（例: acidBlackCherry）"
            },
            {
                "name": "playlist_name",
                "type": "string",
                "description": "再生したいプレイリスト名（例: トップ25）"
            }
        ],
        "usage_example": [
            "音楽をかけて",
            "L'Arc~en~Cielの曲を再生して",
            "リラックスできるプレイリストを流して"
        ],
        "swift_action": "PlayMusicIntent"
    },
    "setReminder": {
        "summary": "リマインダーに予定を追加する",
        "parameters": [
            {
                "name": "title",
                "type": "string",
                "description": "リマインダーの内容やタイトル"
            },
            {
                "name": "target_time",
                "type": "string",
                "description": "リマインダーを設定する日時や時刻（例: 15:00、明日）"
            }
        ],
        "usage_example": [
            "リマインダーに予定を入れて"
        ],
        "swift_action": "SetReminderIntent"
    }
}
class FileUtil:
    @staticmethod
    def temp_file():
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        in_file = f"in_{timestamp}.m4a"
        out_file = f"out_{timestamp}.mp3"
        
        return {'in':in_file,'out':out_file}
    @staticmethod
    def rm_f(in_file, out_file):
        # 一時ファイルの削除
        for f in [in_file, out_file]:
            if os.path.exists(f):
                os.remove(f)


# 環境変数の読み込み
load_dotenv()

# クライアントの初期化
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class VoiceAgentHandler(BaseHTTPRequestHandler):
    
    """インメモリでのあいまい検索処理（使用例を利用）"""
    def search_intent(self, query: str) -> dict:
        for intent_key, intent_data in INTENTS_DB.items():
            for example in intent_data.get("usage_example", []):
                # ユーザーのクエリが使用例に含まれているか、使用例がクエリに含まれているか判定
                if example in query or query in example:
                    return intent_data
        return {}
    
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

                temp_file = FileUtil.temp_file()
                #送られてきた音声データ
                in_file = temp_file['in']
                # 読み上げ音声を保存するファイル
                out_file = temp_file['out']

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
                FileUtil.rm_f(in_file, out_file)
            
            except Exception as e:
                print(f"❌ Server Error: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                error_json = json.dumps({
                    "user_text": "Error",
                    "ai_text": f"Server Error: {str(e)}",
                    "audio_data": "",
                    "swift_action": "",
                    "parameters": {}
                })
                self.wfile.write(error_json.encode('utf-8'))
    
    """送られてきた音声を処理する"""
    def parse_voice_request(body, boundary):
        # boundaryを区切り文字として分割
        parts = body.split(b'--' + boundary)
        history = "{}"
        audio = None
        
        for part in parts:
            if b'name="history"' in part:
                # ヘッダーとボディの間の空行(\r\n\r\n)で分割して中身を取る
                history = part.split(b'\r\n\r\n')[1].strip(b'\r\n--').decode('utf-8')
            elif b'name="audio"' in part:
                audio = part.split(b'\r\n\r\n')[1].rstrip(b'\r\n--')
                
        return history, audio
 

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
            # あいまい検索
            matched_intent = self.search_intent(user_text)

            # B.初期プロンプト組み立て
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_text})

            tools = []
            if matched_intent:
                properties = {}
                for p in matched_intent.get("parameters", []):
                    p_type = p.get("type", "string").lower()
                    if p_type not in ["string", "number", "integer", "boolean", "array", "object"]:
                        p_type = "string"
                    properties[p["name"]] = {
                        "type": p_type,
                        "description": p.get("description", "")
                    }
                
                tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": matched_intent.get("swift_action", "IntentAction"),
                            "description": matched_intent.get("summary", ""),
                            "parameters": {
                                "type": "object",
                                "properties": properties
                            }
                        }
                    }
                ]

            # C. Llamaによる回答生成
            chat_kwargs = {
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
            }
            if tools:
                chat_kwargs["tools"] = tools
                chat_kwargs["tool_choice"] = "auto"

            chat = groq_client.chat.completions.create(**chat_kwargs)
            message = chat.choices[0].message
            
            ai_text = message.content or ""
            swift_action = ""
            extracted_parameters = {}

            if message.tool_calls:
                tool_call = message.tool_calls[0]
                swift_action = tool_call.function.name
                try:
                    extracted_parameters = json.loads(tool_call.function.arguments)
                except:
                    print("エラーだよ〜〜〜")
                if not ai_text:
                    ai_text = "承知いたしました。操作を実行します。"

            # AIの回答も履歴に追加
            history.append({"role": "assistant", "content": ai_text})

            # D. Edge TTSによる音声合成
            await edge_tts.Communicate(ai_text, "ja-JP-NanamiNeural").save(out_file)
            
            # E. 音声バイナリをBase64文字列に変換
            with open(out_file, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode('utf-8')
            
            # Swift側がデコードできるJSONを返す
            return json.dumps({
                "user_text": user_text,
                "ai_text": ai_text,
                "audio_data": audio_b64,
                "swift_action": swift_action,
                "parameters": extracted_parameters
            })
        except Exception as e:
            return json.dumps({
                "user_text": "Error",
                "ai_text": f"AI Error: {str(e)}",
                "audio_data": "",
                "swift_action": "",
                "parameters": {}
            })

def run_server():
    port = int(os.environ.get("PORT", 8000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, VoiceAgentHandler)
    print(f"🚀 Server running on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
