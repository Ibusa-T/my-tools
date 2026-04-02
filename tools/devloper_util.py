import subprocess
import sys
import os


class DeveloperUtil:
    """開発者向けのユーティリティクラス"""
    @classmethod
    def run_command(command):
        """コマンドを実行し、エラーがあれば停止するヘルパー関数"""
        try:
            subprocess.run(command, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error occurred: {e}")
            sys.exit(1)

    """""プロジェクトフォルダがないか確認する"""    
    def project_exists(project_name):
        print(f"--- 1. {project_name} ディレクトリを作成中 ---")
        #プロジェクトフォルダなければでぃれくとりを作成する
        if not os.path.exists(project_name):
            os.makedirs(project_name)
            os.chdir(project_name)
            
            return True
        return False
    
    
    def uv_init(project_name="mysite", app_name="polls",python_version="3.12",django_version="3.6.*"):

        print(f"--- 1. {project_name} ディレクトリを作成中 ---")
        if not os.path.exists(project_name):
            os.makedirs(project_name)
        os.chdir(project_name)

        print(f"--- 2. uv を初期化し、Django {django_version} を追加 ---")
        # uv プロジェクトの初期化    run_command("uv init --bare")
        # Pythonスクリプト内の修正イメージ
        # 修正ポイント：明示的に venv を作成する
        DeveloperUtil.run_command(f"uv init --bare --python {python_version}")
        DeveloperUtil.run_command(f"uv venv --python {python_version}")  # これで 3.11 の仮想環境を確定させる
        DeveloperUtil.run_command(f"uv add django=={django_version}")
        
        print(f"--- 3. Django プロジェクト '{project_name}' を作成 ---")
        # チュートリアル1の構成：カレントディレクトリに展開
        DeveloperUtil.run_command(f"uv run django-admin startproject {project_name} .")
        DeveloperUtil.run_command(f"uv run python manage.py startapp {app_name}")
        print("\n--- セットアップ完了 ---")
        print(f"以下のコマンドでサーバーを起動できます:")
        print(f"cd {project_name}")
        print(f"uv run manage.py runserver")
    
    def django_migrate(app_name='polls', project_dir='mysite'):

        # ここが修正ポイント：Pythonプロセス自体のカレントディレクトリを変更する
        if os.path.exists(project_dir):
            os.chdir(project_dir)
            print(f"Moved to {os.getcwd()}")
        else:
            print(f"Error: {project_dir} directory not found.")
            sys.exit(1)

        DeveloperUtil.run_command(f"uv run python manage.py makemigrations {app_name}")
        DeveloperUtil.run_command(" uv run python manage.py migrate")
        DeveloperUtil.run_command(" uv run python manage.py check")

        print("\n--- セットアップ完了 ---")
        print(f"以下のコマンドでサーバーを起動できます:")
        print(f"uv run manage.py runserver")