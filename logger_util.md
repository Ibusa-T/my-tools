# my-tools
Pythonスクリプトで使えそうな共通部品
# LoggerUtil

`LoggerUtil` は、Python/Djangoアプリケーションにおいて、リクエスト情報（ユーザー、IP、パス）を含めた構造化ログを、安全かつ簡潔に出力するためのユーティリティクラスです。

開発環境では `rich` による視覚的なデバッグを、本番環境（あるいはファイル出力）では `json-logging` による解析をサポートします。

## 1. 事前準備

### 依存パッケージのインストール

# 開発環境に合わせて、以下のパッケージをインストールしてください。
  1.rich
  1.python-json-logger


**uv を使用する場合:**
````
  uv add rich python-json-logger
````
**pip を使用する場合:**
````
   pip install rich python-json-logger
````


**Django settings.py の設定:**
LOGGING 設定を以下のように記述します。コンソール（RichHandler）とファイル（JSONL）で出力を分ける構成です。

````
from rich.logging import RichHandler

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%%(levelname)s %(asctime)s %(name)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'rich.logging.RichHandler',
            'formatter': 'json',
            'rich_tracebacks': True,          # トレースバックを美しく表示
            'tracebacks_show_locals': True,   # 異常終了時のローカル変数値を表示（超便利！）
        },
        'polls-file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': "polls.jsonl",
            'formatter': 'json',
        },
        'admin-file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': "django.jsonl",
            'formatter': 'json',
        },
    },
    'loggers': {
        'polls': {
            'handlers': ['console', 'polls-file'],
            'level': 'INFO',
        },
        'django': {
            'handlers': ['console', 'admin-file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
````

# LoggerUtil クラス
````
class LoggerUtil:
    """
    ロギングに関するユーティリティクラス
    """    
    @staticmethod
    def get_extra_data(request=None, **kwargs):
        """
        request が None でも壊れないように安全に抽出する
        """
        # 1. 基本となる空の辞書
        extra = {
            'user': 'anonymous',
            'ip': 'unknown',
            'path': 'unknown',
        }

        # 2. request が存在する場合のみ上書きを試みる
        if request:
            # user の取得（AttributeError を防ぐために getattr を使うのも手）
            if hasattr(request, 'user') and request.user.is_authenticated:
                extra['user'] = request.user.username
            
            # IPとパスの取得
            extra['ip'] = request.META.get('REMOTE_ADDR', 'unknown')
            extra['path'] = getattr(request, 'path', 'unknown')

        # 3. 呼び出し側の個別データをマージ
        extra.update(kwargs)
        return extra
    
    
    
    @staticmethod
    def get_extra_error(request, **kwargs):
        """
        ログ出力用の共通項目と個別項目をマージする
        """
        extra = {
            'user': request.user.username if request.user.is_authenticated else 'anonymous',
            'ip': request.META.get('REMOTE_ADDR'),
            'path': request.path,
        }
        extra.update(kwargs)
        return extra
````


# サンプルコード

````
import logging
from .utils import LoggerUtil

logger = logging.getLogger('polls')

def my_view(request):
    # 通常のログ出力
    logger.info(
        "処理を開始しました", 
        extra=LoggerUtil.get_extra_data(request)
    )

    # 任意のデータを追加して出力
    logger.info(
        "アイテムを購入しました", 
        extra=LoggerUtil.get_extra_data(request, item_id=101, amount=1)
    )
````