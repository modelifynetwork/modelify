import threading
import app
import bot_manager

def run_flask():
    app.app.run(host="0.0.0.0", port=8080)

def run_bots():
    # Se bot_manager já inicia os bots ao importar, pode deixar vazio.
    pass

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    bots_thread = threading.Thread(target=run_bots)
    flask_thread.start()
    bots_thread.start()
    flask_thread.join()
    bots_thread.join()
