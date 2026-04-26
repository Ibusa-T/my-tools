# Guardian Voice API (my-tools)

このプロジェクトは、Groq (Whisper/Llama) と Edge-TTS を使用した音声対話エージェントのAPIサーバーです。

## Render へのデプロイ設定

Render にデプロイする際は、以下の設定を使用してください。

### 1. Web Service の作成
Render のダッシュボードから **New > Web Service** を選択し、このリポジトリを連携してください。

### 2. ビルド設定 (Build Command)
依存関係をインストールします。

```bash
pip install -r requirements.txt
```

### 3. 起動設定 (Start Command)
サーバーを起動します。

```bash
python main.py
```

### 4. 環境変数 (Environment Variables)
以下の環境変数を Render のダッシュボードで設定してください。
*   `GROQ_API_KEY`: Groq の API キー

### 5. その他の設定
*   **Runtime**: Python
*   **Plan**: Free または任意のプラン
*   **PORT**: 自動的に割り当てられます（コード側で `os.environ.get("PORT")` を使用しています）

## ローカルでの実行方法

1.  `uv` がインストールされていることを確認してください。
2.  依存関係の同期:
    ```bash
    uv sync
    ```
3.  `.env` ファイルの作成:
    ```text
    GROQ_API_KEY=あなたのキー
    ```
4.  サーバー起動:
    ```bash
    uv run python main.py
    ```

## API の使用方法

-   **Endpoint**: `POST /voice`
-   **Content-Type**: `audio/mpeg` または `audio/m4a`
-   **Response**: `audio/mpeg` (AIの返答音声)
