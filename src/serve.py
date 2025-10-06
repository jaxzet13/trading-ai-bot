import pandas as pd
import joblib
import os

# Load model
model_path = os.path.join("..", "models", "trading_model.pkl")
model = joblib.load(model_path)

def predict_signal(close_prices):
    df = pd.DataFrame({"close": close_prices})
    df["ma_3"] = df["close"].rolling(window=3).mean()
    df["ma_5"] = df["close"].rolling(window=5).mean()
    df = df.dropna()
    last_row = df.tail(1)[["ma_3", "ma_5"]]
    prediction = model.predict(last_row)[0]
    last_close = df["close"].iloc[-1]
    return "BUY" if prediction > last_close else "SELL"

if __name__ == "__main__":
    sample_prices = [50000, 50010, 50020, 50015, 50025, 50030, 50040]
    signal = predict_signal(sample_prices)
    print("Signal:", signal)
