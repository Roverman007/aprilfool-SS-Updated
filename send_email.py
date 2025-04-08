import os
import smtplib
import json
import datetime
import yfinance as yf
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === Email 設定 ===
FROM_EMAIL = "roverpoonhkg@gmail.com"
TO_EMAIL = "klauspoon@gmail.com"
APP_PASSWORD = "rbmk opks bdex ajzr"
POSITION_FILE = "position.json"

def send_email(subject, body, to_email):
    if not FROM_EMAIL or not TO_EMAIL or not APP_PASSWORD:
        print("❌ Missing email credentials. Email not sent.")
        return

    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(FROM_EMAIL, APP_PASSWORD)
        server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        server.quit()
        print("✅ Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")

# === 技術指標計算 ===
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = -delta.clip(upper=0).rolling(window=period).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).astype(float)

def compute_macd(series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd.astype(float), signal.astype(float)

def compute_adx(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']

    plus_dm = high.diff()
    minus_dm = low.diff()

    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0

    tr1 = (high - low).abs()
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = plus_dm.rolling(window=period).mean()
    minus_di = minus_dm.rolling(window=period).mean()

    sum_di = plus_di + minus_di
    sum_di[sum_di == 0] = 1e-10
    dx = 100 * (plus_di - minus_di).abs() / sum_di
    adx = dx.rolling(window=period).mean()
    return pd.Series(adx.values.ravel(), index=df.index, name='ADX').astype(float)

# === 主策略 ===
def check_intraday_strategy():
    df = yf.download("SQQQ", period="2d", interval="5m", prepost=True)

    if df.empty or len(df) < 50:
        send_email("SQQQ 策略錯誤", "無足夠資料執行策略（5分鐘級別）。", TO_EMAIL)
        return

    df["EMA5"] = df["Close"].ewm(span=5).mean()
    df["EMA10"] = df["Close"].ewm(span=10).mean()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["RSI"] = compute_rsi(df["Close"])
    df["MACD"], df["Signal"] = compute_macd(df["Close"])
    df["ADX"] = compute_adx(df)

    df = df.dropna().copy()
    if df.empty:
        send_email("SQQQ 策略錯誤", "指標計算後資料為空（可能過早執行）。", TO_EMAIL)
        return

    row = df.iloc[-1]
    timestamp = row.name

    def safe_scalar(val):
        return val.item() if isinstance(val, pd.Series) else val

    rsi = safe_scalar(row["RSI"])
    macd = safe_scalar(row["MACD"])
    signal = safe_scalar(row["Signal"])
    ema5 = safe_scalar(row["EMA5"])
    ema10 = safe_scalar(row["EMA10"])
    ema20 = safe_scalar(row["EMA20"])
    close = safe_scalar(row["Close"])
    adx = safe_scalar(row["ADX"])

    signals = []
    if rsi > 60:
        signals.append("RSI > 60")
    if macd < signal:
        signals.append("MACD < Signal")
    if ema5 < ema10:
        signals.append("EMA5 < EMA10")
    if close < ema20:
        signals.append("Close < EMA20 (即時)")
    if adx > 20:
        signals.append("ADX > 20")

    # === 檢查持倉紀錄 ===
    position = None
    if os.path.exists("position.json"):
        with open("position.json") as f:
            position = json.load(f)

    # === 賣出邏輯 ===
    if position:
        buy_price = position["buy_price"]
        gain = (close - buy_price) / buy_price

        prev_close = df["Close"].iloc[-2]
        prev_ema20 = df["EMA20"].iloc[-2]

        if gain <= -0.075:
            send_email("❌ SQQQ 止損賣出",
                       f"❌【止損】\n🕒 時間：{timestamp}\n💰 價格：{close:.2f}\n📉 損失：{gain*100:.1f}%",
                       TO_EMAIL)
            os.remove("position.json")
            return

        elif gain >= 0.10:
            send_email("✅ SQQQ 止盈賣出",
                       f"✅【止盈】\n🕒 時間：{timestamp}\n💰 價格：{close:.2f}\n📈 獲利：{gain*100:.1f}%",
                       TO_EMAIL)
            os.remove("position.json")
            return

        elif prev_close > prev_ema20 and close > ema20:
            send_email("📈 SQQQ EMA20 連續突破賣出",
                       f"📈【連續兩根K線突破 EMA20 賣出】\n🕒 時間：{timestamp}\n💰 價格：{close:.2f}",
                       TO_EMAIL)
            os.remove("position.json")
            return

    # === 買入策略 ===
    if not position and len(signals) >= 2:
        new_position = {
            "symbol": "SQQQ",
            "buy_price": close,
            "buy_time": str(timestamp),
            "reason": ", ".join(signals)
        }
        with open("position.json", "w") as f:
            json.dump(new_position, f)

        send_email("📈 SQQQ 即時買入訊號",
                   f"✅【5分鐘級別 買入訊號】\n🕒 時間：{timestamp}\n💰 價格：{close:.2f}\n📌 訊號條件：{new_position['reason']}",
                   TO_EMAIL)
    elif not position:
        send_email("SQQQ 無即時訊號", f"📋 {timestamp} 沒有觸發任何買入或賣出訊號。", TO_EMAIL)

# === 執行策略 ===
check_intraday_strategy()
