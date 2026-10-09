import os

from flask import Flask, jsonify
from flask_cors import CORS

from groq_client import call_groq_json

app = Flask(__name__)
CORS(app)


@app.get("/api/health")
def health():
    return jsonify(status="ok")


# Temporary route to confirm the AI connection. Remove later.
@app.get("/api/test-groq")
def test_groq():
    try:
        out = call_groq_json(
            [{"role": "user", "content": 'Reply with JSON only: {"status":"connected"}'}]
        )
        return jsonify(out)
    except Exception as e:
        return jsonify(error=str(e)), 500


# TODO: POST /api/analyze

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5000)), debug=True)
