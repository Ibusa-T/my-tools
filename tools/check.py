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

def main():
    app_name = 'polls'
    project_dir = 'mysite'
    # ここが修正ポイント：Pythonプロセス自体のカレントディレクトリを変更する
    if os.path.exists(project_dir):
        os.chdir(project_dir)
        print(f"Moved to {os.getcwd()}")
    else:
        print(f"Error: {project_dir} directory not found.")
        sys.exit(1)
    
    run_command(" uv run python manage.py check")
    run_command(" uv run python manage.py runserver")
    
   
if __name__ == "__main__":
    main()