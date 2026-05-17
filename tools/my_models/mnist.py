# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "scikit-learn",
#     "scipy",
# ]
# ///

import sklearn
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split
from sklearn.svm import LinearSVC
# 分析用の機能を新しく追加インポート
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
# --------------------------------------------------
# 1. データの読み込み
# --------------------------------------------------
print("データを読み込んでいます...")
# 軽量版MNIST（手書き数字データ）をロード
digits = load_digits()
# ここは自前で用意しても良いデータ
# X: 画像のデータ（各ピクセルの濃さ）, y: ラベル（今回は0～9の数字）

X = digits.data
y = digits.target


# 並び替えパターン
shuffle_pattern = 12

# --------------------------------------------------
# 2. モデルの学習プロセスに使うデータセットの準備
# --------------------------------------------------
# random_stateというのはデータのシャッフル方法を切り換えるインデックス

"""ここでは、学習用データとテスト用データにラベルをマッピングしています。"""
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=shuffle_pattern
)

# --------------------------------------------------
# 3. AIモデルの作成と学習
# --------------------------------------------------
print("AIの学習を開始します...")
# 低スペックPCでも高速に動く「LinearSVC」というモデルを選択
# max_iterは学習の最大反復回数です。警告が出る場合は数値を増やします。
model = LinearSVC(max_iter=10000, random_state=shuffle_pattern)

# trainデータを使ってAIに学習させる
model.fit(X_train, y_train)
print("学習が完了しました！")

# --------------------------------------------------
# 4. AIの実力をテスト（予測と評価）
# --------------------------------------------------
# テスト用の画像を使って、AIに数字を予測させる
y_pred = model.predict(X_test)

# 予測結果と、実際の正解を比較して正解率を計算
accuracy = accuracy_score(y_test, y_pred)

print("--- 結果発表 ---")
result = accuracy * 100
print(f"予測の正解率: {result:.2f}%")


# --------------------------------------------------
# 4. AIの実力をテスト（予測と詳細評価）
# --------------------------------------------------
y_pred = model.predict(X_test)

# 全体の正解率
accuracy = accuracy_score(y_test, y_pred)

print("\n================ 結果発表 ================")
print(f"全体の正解率: {accuracy * 100:.2f}%\n")

# 新機能①：数字ごとの詳しい正解率レポート
print("--- 数字ごとの詳細レポート ---")
print(classification_report(y_test, y_pred))

# 新機能②：どの数字を何と間違えたかの表（混同行列）
print("--- 混同行列（縦軸：正解 / 横軸：AIの予測） ---")
print(confusion_matrix(y_test, y_pred))
print("==========================================")