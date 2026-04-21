# どこでも開発環境

# 使用ツール
- CLaude CLI
- Mobile Claude（ipadもしくはiphone）
- Open Router  CLaudeを無料で使うための無料モデルを提供している
- TailScale
- Uptime Robot

## npm でインストール
- npm install -g @anthropic-ai/claude-code

## claudeの起動テスト
-  claude
- もしくはpowershellにて$env:ANTHROPIC_BASE_URL="https://openrouter.ai/api/v1"; $env:ANTHROPIC_API_KEY="api-key";claude --model google/gemini-2.0-flash-001:free --dangerously-skip-tutorial
- api-keyはOpenRouterで取得したAPIkeyが入る

**cliの起動が確認出来たら閉じてよい**

## CLaude CLI以外の使用ツールを全てインストール
- 前述したclaudeの起動
- Claude Mobileからkeyを発行（画面右上から）
- npx.cmd claude-mobile-bridge@latest　起動することでモバイルとpcをつなぐ
- keyをブラウザで叩く
- 画面にある「接続する」ボタンを押下
- Connectedが出たらOK
## 


## 今回やりたいこと
- 上記だと電源を切ると接続が切れてしまう
- なので一連の手順をスクリプトにしてrenderにデプロイUptimeRobotで監視
- LINE Messaging APIを使用、トークでキーを送るとスクリプトが走り、Render上でプロセスを自動化できる

## 懸念点
- Renderの無料枠だとメモリの限界があるかも