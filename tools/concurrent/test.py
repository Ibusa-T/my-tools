import typing
import threading
import concurrent.futures
import time

"""プロセスはヒープメモリや静的データ領域を共有する。
スレッドを管理下に置いているので実質スタック・レジスタも保有
"""
"""スレッドはスタック（ローカル変数）とレジスタを保持する"""



class Monitor:
    shared_data = {}
    # プロセスには必ず一つのGILが存在する
    def __init__(self):
        self._gil_lock = threading.Lock()
        self.name = threading.current_thread().name
    def read(self):
        key:str = time.time()
        with self._gil_lock:
            Monitor.shared_data[key] = self.name
    
    @property
    def value(self):
        with self._gil_lock:
            return Monitor.shared_data[self.name]


if __name__ == "__main__":
    process =[]
    process.append(Monitor())
    process.append(Monitor())
    process.append(Monitor())

    threadpool =concurrent.futures.ThreadPoolExecutor(max_workers=len(process))
    # GILがあるのでスレッドは並列に動かない、よってタイムスタンプキーが上書きされることはない

    for i in range(len(process)):
       futures =  threadpool.submit(process[i].read)
    # すべて終わるのを待機
    concurrent.futures.wait([futures])
    print(Monitor.shared_data)
