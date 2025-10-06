from flask import Flask, request, jsonify
import os
import joblib
from src.serve import predict_signal

app = Flask(__name__)
model = joblib.load(os.path.join("models", "trading_model.pkl"))

@app.route("/predict", methods=["POST"])
def predict():
    data = request.json
    prices = data.get("prices")
    if not prices:
        return jsonify({"error": "Missing 'prices' list"}), 400
    signal = predict_signal(prices)
    return jsonify({"signal": signal})

@app.route("/")
def home():
    return "Trading bot API running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
