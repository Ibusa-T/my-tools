import subprocess
import sys
import os

def run_command(command):
    """コマンドを実行し、エラーがあれば停止するヘルパー関数"""
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e}")
        sys.exit(1)

def virtualenv_init(project_name="mysite", app_name="polls"):

    print(f"--- 1. {project_name} ディレクトリを作成中 ---")
    if not os.path.exists(project_name):
        os.makedirs(project_name)
    os.chdir(project_name)
    
    print("--- 2. uv を初期化し、Django 3.2 を追加 ---")
    # uv プロジェクトの初期化    run_command("uv init --bare")
    # Pythonスクリプト内の修正イメージ
    # 修正ポイント：明示的に venv を作成する
    run_command("uv init --bare --python 3.11")
    run_command("uv venv --python 3.11")  # これで 3.11 の仮想環境を確定させる
    run_command("uv add django==3.2.*")
    
    print(f"--- 3. Django プロジェクト '{project_name}' を作成 ---")
    # チュートリアル1の構成：カレントディレクトリに展開
    run_command(f"uv run django-admin startproject {project_name} .")
    run_command(f"uv run python manage.py startapp {app_name}")
    print("\n--- セットアップ完了 ---")
    print(f"以下のコマンドでサーバーを起動できます:")
    print(f"cd {project_name}")
    print(f"uv run manage.py runserver")

def uv_init(project_name="mysite", app_name="polls"):

    print(f"--- 1. {project_name} ディレクトリを作成中 ---")
    if not os.path.exists(project_name):
        os.makedirs(project_name)
    os.chdir(project_name)

    print("--- 2. uv を初期化し、Django 3.2 を追加 ---")
    # uv プロジェクトの初期化    run_command("uv init --bare")
    # Pythonスクリプト内の修正イメージ
    # 修正ポイント：明示的に venv を作成する
    run_command("uv init --bare --python 3.11")
    run_command("uv venv --python 3.11")  # これで 3.11 の仮想環境を確定させる
    run_command("uv add django==3.2.*")
    
    print(f"--- 3. Django プロジェクト '{project_name}' を作成 ---")
    # チュートリアル1の構成：カレントディレクトリに展開
    run_command(f"uv run django-admin startproject {project_name} .")
    run_command(f"uv run python manage.py startapp {app_name}")
    print("\n--- セットアップ完了 ---")
    print(f"以下のコマンドでサーバーを起動できます:")
    print(f"cd {project_name}")
    print(f"uv run manage.py runserver")

if __name__ == "__main__":
    uv_init()