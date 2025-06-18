import subprocess
import sys
import threading

def run_app():
    subprocess.run([sys.executable, "app.py"])

def run_bots():
    subprocess.run([sys.executable, "bot_manager.py"])

if __name__ == "__main__":
    t1 = threading.Thread(target=run_app)
    t2 = threading.Thread(target=run_bots)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
