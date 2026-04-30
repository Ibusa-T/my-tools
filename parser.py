
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
 