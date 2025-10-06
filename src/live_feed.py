import requests
import time
from serve import predict_signal

prices = []

def get_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    try:
        response = requests.get(url)
        data = response.json()
        return float(data["bitcoin"]["usd"])
    except:
        return None

print("📡 Starting live BTC feed...")
for _ in range(10):  # fetch 10 times
    price = get_price()
    if price:
        prices.append(price)
        print(f"Current BTC price: {price}")
        if len(prices) >= 5:
            signal = predict_signal(prices)
            print("Signal:", signal)
    time.sleep(10)
