import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import yfinance as yf
import pandas as pd
import datetime

# === Load Environment Variables ===
load_dotenv()

FROM_EMAIL = os.getenv("FROM_EMAIL")
TO_EMAIL = os.getenv("TO_EMAIL")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

def send_email(subject, body, to_email):
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
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")

# === RSI ===
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = -delta.clip(upper=0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# === MACD ===
def compute_macd(series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

# === ADX ===
def compute_adx(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']

    plus_dm = high.diff()
    minus_dm = low.diff()

    tr1 = (high - low).abs()
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()

    return pd.Series(adx, index=df.index, name="ADX")

# === Main Strategy ===
def check_strategy():
    df = yf.download("SQQQ", period="90d", interval="1d", auto_adjust=False)

    if df.empty or len(df) < 30:
        send_email("SQQQ 策略錯誤", "無足夠資料執行策略。", TO_EMAIL)
        return

    df["EMA5"] = df["Close"].ewm(span=5).mean()
    df["EMA10"] = df["Close"].ewm(span=10).mean()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["RSI"] = compute_rsi(df["Close"])
    df["MACD"], df["Signal"] = compute_macd(df["Close"])
    df["ADX"] = compute_adx(df)

    position = None
    no_trigger = True

    for i in range(20, len(df)):
        row = df.iloc[i]
        date = row.name.date()

        signals = []
        if row["RSI"] > 60:
            signals.append("RSI > 60")
        if row["MACD"] < row["Signal"]:
            signals.append("MACD < Signal")
        if row["EMA5"] < row["EMA10"]:
            signals.append("EMA5 < EMA10")
        if row["Close"] < row["EMA20"]:
            signals.append("Close < EMA20")
        if pd.notna(row["ADX"]) and row["ADX"] > 20:
            signals.append("ADX > 20")

        if position is None and len(signals) >= 2:
            position = {
                "Buy Price": row["Close"],
                "Buy Date": date,
                "Buy Reason": ", ".join(signals)
            }
            send_email("SQQQ 買入訊號",
                       f"✅【買入】\n📅 日期：{date}\n💰 價格：{row['Close']:.2f}\n📌 原因：{position['Buy Reason']}",
                       TO_EMAIL)
            no_trigger = False
            continue

        if position is not None:
            buy_price = position["Buy Price"]
            gain = (row["Close"] - buy_price) / buy_price

            if gain <= -0.075:
                send_email("SQQQ 賣出訊號",
                           f"❌【止損】\n📅 日期：{date}\n💰 價格：{row['Close']:.2f}\n📉 損失：{gain * 100:.1f}%",
                           TO_EMAIL)
                position = None
                no_trigger = False
                continue

            if gain >= 0.10:
                send_email("SQQQ 賣出訊號",
                           f"✅【止盈】\n📅 日期：{date}\n💰 價格：{row['Close']:.2f}\n📈 獲利：{gain * 100:.1f}%",
                           TO_EMAIL)
                position = None
                no_trigger = False
                continue

            if (
                i >= 1 and
                df["Close"].iloc[i - 1] > df["EMA20"].iloc[i - 1] and
                row["Close"] > df["EMA20"].iloc[i]
            ):
                send_email("SQQQ 賣出訊號",
                           f"📈【EMA20突破賣出】\n📅 日期：{date}\n💰 價格：{row['Close']:.2f}\n📌 原因：連續兩日收盤 > EMA20",
                           TO_EMAIL)
                position = None
                no_trigger = False

    if no_trigger:
        today = datetime.date.today()
        send_email("SQQQ 無訊號", f"📋 今天（{today}）未觸發任何買入或賣出訊號。", TO_EMAIL)

# === Execute ===
check_strategy()
