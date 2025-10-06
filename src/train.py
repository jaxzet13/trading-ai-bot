import pandas as pd
from sklearn.linear_model import LinearRegression
import joblib
import os

# Load data
data_path = os.path.join("..", "data", "train.csv")
df = pd.read_csv(data_path)

# Simple features: previous close price
df["prev_close"] = df["close"].shift(1)
df = df.dropna()

# Train model
X = df[["prev_close"]]
y = df["close"]
model = LinearRegression()
model.fit(X, y)

# Save model
os.makedirs("../models", exist_ok=True)
joblib.dump(model, "../models/trading_model.pkl")

print("✅ Model trained and saved!")
