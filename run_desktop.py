import webview
import threading
from app_flask import app 

def start_flask():
    app.run(port=8555, debug=False, use_reloader=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    webview.create_window(
        title="🎙️ ხმის ტექსტად გარდამქმნელი",
        url="http://127.0.0.1:8555",
        width=800,
        height=600,
        resizable=True
    )
 
    webview.start()
