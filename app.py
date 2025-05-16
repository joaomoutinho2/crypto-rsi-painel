from flask import Flask
import subprocess

app = Flask(__name__)

@app.route("/run-treino")
def run_treino():
    subprocess.Popen(["python3", "bot_treino.py"])
    return "✅ Treino e avaliação iniciados.", 200
