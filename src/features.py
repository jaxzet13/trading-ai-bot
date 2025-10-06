import pandas as pd

def add_moving_averages(df):
    df["ma_3"] = df["close"].rolling(window=3).mean()
    df["ma_5"] = df["close"].rolling(window=5).mean()
    return df
