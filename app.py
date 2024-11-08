from app import create_app, socketio
import os

app = create_app()

if __name__ == '__main__':
   
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=app.config.get("DEBUG", False))
