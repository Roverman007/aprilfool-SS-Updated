import os
import smtplib
import datetime
import yfinance as yf
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === Email Settings ===
FROM_EMAIL = "roverpoonhkg@gmail.com"
TO_EMAIL = "klauspoon@gmail.com"
APP_PASSWORD = "rbmk opks bdex ajzr"

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

# === Technical Indicators ===
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

# === Today's Strategy ===
def check_today_signal():
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

    df = df.dropna().copy()
    if len(df) == 0:
        send_email("SQQQ 策略錯誤", "技術指標計算後資料為空。", TO_EMAIL)
        return

    today_row = df.iloc[[-1]]  # always returns a DataFrame with one row
    date = today_row.index[0].date()

    # Extract all values as scalars using .iloc[0]
    rsi = today_row["RSI"].iloc[0]
    macd = today_row["MACD"].iloc[0]
    signal = today_row["Signal"].iloc[0]
    ema5 = today_row["EMA5"].iloc[0]
    ema10 = today_row["EMA10"].iloc[0]
    ema20 = today_row["EMA20"].iloc[0]
    close = today_row["Close"].iloc[0]
    adx = today_row["ADX"].iloc[0]

    signals = []
    if rsi > 60:
        signals.append("RSI > 60")
    if macd < signal:
        signals.append("MACD < Signal")
    if ema5 < ema10:
        signals.append("EMA5 < EMA10")
    if close < ema20:
        signals.append("Close < EMA20")
    if adx > 20:
        signals.append("ADX > 20")

    if len(signals) >= 2:
        subject = "SQQQ 買入訊號"
        body = (
            f"✅【今日買入訊號】\n"
            f"📅 日期：{date}\n"
            f"💰 價格：{close:.2f}\n"
            f"📌 訊號條件：{', '.join(signals)}"
        )
    else:
        subject = "SQQQ 無訊號"
        body = f"📋 今天（{date}）未觸發任何買入或賣出訊號。"

    send_email(subject, body, TO_EMAIL)

# === Run Today's Strategy ===
check_today_signal()
