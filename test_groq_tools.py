import os
import json
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

matched_intent = {
    "intent_name": "playMusic",
    "summary": "ミュージックアプリで楽曲やプレイリストを再生する",
    "parameters": [
      {"name": "song_name", "type": "String", "description": "CRICIS"},
      {"name": "artist_name", "type": "String", "description": "acidBlackCherry"},
      {"name": "playlist_name", "type": "String", "description": "トップ25"}
    ],
    "usage_example": ["音楽をかけて"],
    "swift_action": "PlayMusicIntent"
}

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

messages = [{"role": "user", "content": "L'Arc~en~Cielの曲を再生して"}]

print("Tools schema:", json.dumps(tools, indent=2))

try:
    chat = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    msg = chat.choices[0].message
    print("Content:", msg.content)
    if msg.tool_calls:
        for tc in msg.tool_calls:
            print("Tool call:", tc.function.name, tc.function.arguments)
except Exception as e:
    print("API Error:", str(e))
