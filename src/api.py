from flask import Flask, request, jsonify
import joblib
import pandas as pd
import numpy as np

app = Flask(__name__)

# Load your trained model
model = joblib.load("model.pkl")

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    prices = np.array(data["prices"]).reshape(1, -1)
    prediction = model.predict(prices)
    signal = "BUY" if prediction[0] == 1 else "SELL"
    return jsonify({"signal": signal})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
