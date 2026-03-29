
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
