import os
from Pillow import Image
import imagehash

def find_duplicate_images(folder1, folder2):
    """
    2つのフォルダ内の画像を比較し、同一の画像（ハッシュ一致）を特定します。
    """
    
    def get_image_hashes(folder_path):
        """フォルダ内の画像から {ハッシュ値: ファイル名} の辞書を作成"""
        hashes = {}
        # 対応する拡張子
        valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
        
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(valid_extensions):
                img_file = os.path.join(folder_path, filename)
                try:
                    with Image.open(img_file) as img:
                        # 知覚ハッシュ（dhash）を使用。リサイズや圧縮に強い
                        h = str(imagehash.dhash(img))
                        hashes[h] = filename
                except Exception as e:
                    print(f"エラー（スキップ）: {filename} - {e}")
        return hashes

    print(f"フォルダ1 をスキャン中...")
    hashes1 = get_image_hashes(folder1)
    
    print(f"フォルダ2 をスキャン中...")
    hashes2 = get_image_hashes(folder2)

    # 共通するハッシュ値（＝同じ画像）を特定
    duplicates = []
    common_hashes = set(hashes1.keys()) & set(hashes2.keys())

    for h in common_hashes:
        duplicates.append((hashes1[h], hashes2[h]))

    return duplicates

# --- 設定と実行 ---
dir_a = "C:\\Users\\User\\Desktop\\写真データ"  # 1つ目のフォルダパス
dir_b = "C:\\Users\\User\\Desktop\\指定画像-20260401T140103Z-1-001"  # 2つ目のフォルダパス

if __name__ == "__main__":
    results = find_duplicate_images(dir_a, dir_b)

    if results:
        print(f"\n--- 同一画像が見つかりました ({len(results)}件) ---")
        for file_a, file_b in results:
            print(f"フォルダA: {file_a}  <==>  フォルダB: {file_b}")
    else:
        print("\n同一画像は見つかりませんでした。")