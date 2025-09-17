#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, asyncio, math, time
from collections import deque
from dotenv import load_dotenv
import aiohttp
from aiohttp import resolver
from PIL import Image, ImageDraw

# === .env ===
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
HTML_OUTPUT_DIR    = os.getenv("HTML_OUTPUT_DIR", "/data/data/com.termux/files/home/www")
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError("В .env должны быть TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")

# === ВКЛ/ВЫКЛ блоки ===
ENABLE_PATTERNS = True
ENABLE_INDICATORS = True
ENABLE_ATR_ANOMALY = True
ENABLE_VOLUME_FILTER = True
ENABLE_ORDERBOOK_ANOMALY = True

# === НАСТРОЙКИ ===
SYMBOLS = ["SOLUSDT","INJUSDT","WIFUSDT","ADAUSDT"]
TF_LIST = ["5","15","60","240"]

INIT_CANDLES = 50
MAX_CANDLES  = 200
CHART_BARS   = 120

RSI_PERIOD = 14
RSI_LOW, RSI_HIGH = 23.0, 77.0
STOCH_K, STOCH_D, STOCH_SMOOTH = 14, 3, 3

THREE_TOUCH_LOOKBACK = 120
THREE_TOUCH_SPACING  = 5

ATR_PERIOD_DAILY = 14
ANOMALY_ATR_RATIO = 0.65

MIN_CANDLE_PCT = 0.013
VOL_GROWTH_FACTOR = 2.0
VOL_GROWTH_WINDOW = 50

ORDERBOOK_WINDOW = 30
ORDERBOOK_FACTOR = 2.0

POLL_SEC_FAST = 60
POLL_SEC_SLOW = 180

BASE_URL = "https://api.bybit.com"

# === УТИЛИТЫ ===
def ensure_dir(p): os.makedirs(p, exist_ok=True)

def compute_rsi(close, period=14):
    n = len(close)
    if n < period + 1: return [math.nan]*n
    gains=[0.0]; losses=[0.0]
    for i in range(1,n):
        ch=close[i]-close[i-1]
        gains.append(max(ch,0.0)); losses.append(max(-ch,0.0))
    ag=sum(gains[1:period+1])/period; al=sum(losses[1:period+1])/period
    rsi=[math.nan]*period
    rsi.append(100.0 if al==0 else 100.0 - (100.0/(1.0+ag/al)))
    for i in range(period+1,n):
        ag=(ag*(period-1)+gains[i])/period
        al=(al*(period-1)+losses[i])/period
        rsi.append(100.0 if al==0 else 100.0 - (100.0/(1.0+ag/al)))
    return rsi

def compute_stoch(h,l,c,k=14,d=3,s=3):
    n=len(c)
    if n<k: return [math.nan]*n, [math.nan]*n
    raw=[math.nan]*n
    for i in range(k-1,n):
        hh=max(h[i-k+1:i+1]); ll=min(l[i-k+1:i+1])
        raw[i]=50.0 if hh==ll else (c[i]-ll)/(hh-ll)*100.0
    ksm=[math.nan]*n
    for i in range(k-1+s-1,n):
        ksm[i]=sum(raw[i-s+1:i+1])/s
    dsm=[math.nan]*n
    for i in range(k-1+s-1+d-1,n):
        dsm[i]=sum(ksm[i-d+1:i+1])/d
    return ksm,dsm

def true_range(h,l,prev_close): return max(h-l, abs(h-prev_close), abs(l-prev_close))
def compute_atr(h,l,c,period):
    n=len(c)
    if n<period+1: return [math.nan]*n
    trs=[math.nan]+[true_range(h[i],l[i],c[i-1]) for i in range(1,n)]
    atr=[math.nan]*period
    atr.append(sum(trs[1:period+1])/period)
    for i in range(period+1,n):
        atr.append((atr[-1]*(period-1)+trs[i])/period)
    return atr

def three_touches(binary_series, lookback, spacing):
    idxs=[i for i,v in enumerate(binary_series[-lookback:]) if v]
    if len(idxs)<3: return False
    cnt,last=1,idxs[0]
    for i in idxs[1:]:
        if i-last>=spacing:
            cnt+=1; last=i
            if cnt>=3: return True
    return False

def candle_effective_size(c):
    o,h,l,cl = c["open"], c["high"], c["low"], c["close"]
    return (h - o) if cl >= o else (o - l)

def candle_big_enough(c):
    size = candle_effective_size(c)
    cl = c["close"]
    denom = abs(cl) if cl != 0 else max(abs(c["open"]), 1e-9)
    return (size / denom) >= MIN_CANDLE_PCT

def volume_growth_passed(candles):
    if len(candles) < VOL_GROWTH_WINDOW + 1:
        window = min(VOL_GROWTH_WINDOW, max(0, len(candles)-1))
        if window < 10: return False
    else:
        window = VOL_GROWTH_WINDOW
    vols = [c["volume"] for c in candles[-(window+1):-1]]
    avg = (sum(vols)/len(vols)) if vols else 0.0
    return avg>0 and candles[-1]["volume"] >= VOL_GROWTH_FACTOR * avg

# === BYBIT ===
async def fetch_kline(s,symbol,interval,limit):
    url=f"{BASE_URL}/v5/market/kline"
    params={"category":"linear","symbol":symbol,"interval":interval,"limit":str(limit)}
    async with s.get(url,params=params,timeout=20) as r:
        data=await r.json()
        lst=sorted(data["result"]["list"], key=lambda x:int(x[0]))
        return [{"ts":int(x[0]),"open":float(x[1]),"high":float(x[2]),"low":float(x[3]),"close":float(x[4]),"volume":float(x[5])} for x in lst]

async def fetch_orderbook(s, symbol, limit=50):
    url=f"{BASE_URL}/v5/market/orderbook"
    params={"category":"linear","symbol":symbol,"limit":str(limit)}
    async with s.get(url,params=params,timeout=20) as r:
        data=await r.json()
        ob=data["result"]
        return float(ob["b"][0][1]), float(ob["a"][0][1])  # bid1, ask1

async def fetch_daily_atr_prev(s,symbol,period=14):
    kl=await fetch_kline(s,symbol,"D",max(period+2,20))
    if len(kl)<period+1: return None
    h=[x["high"] for x in kl]; l=[x["low"] for x in kl]; c=[x["close"] for x in kl]
    atr=compute_atr(h,l,c,period)
    return atr[-2] if len(atr)>=2 and not math.isnan(atr[-2]) else None

# === TELEGRAM ===
async def tg_photo(s,caption,image_path):
    with open(image_path,"rb") as f:
        form=aiohttp.FormData()
        form.add_field("chat_id",TELEGRAM_CHAT_ID)
        form.add_field("caption",caption)
        form.add_field("parse_mode","HTML")
        form.add_field("photo",f,filename=os.path.basename(image_path),content_type="image/png")
        await s.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",data=form)

# === ГРАФИК ===
def plot_png(sym,tf,cand,levs,save):
    ensure_dir(save)
    d=cand[-CHART_BARS:]
    W,H=1100,500; L,R,T,B=70,30,30,60
    img=Image.new("RGB",(W,H),(20,20,24)); drw=ImageDraw.Draw(img)

    h=[c["high"] for c in d]; l=[c["low"] for c in d]
    extra=list(levs.values()) if levs else []
    vmin=min(l+extra) if extra else min(l)
    vmax=max(h+extra) if extra else max(h)
    if vmax==vmin: vmax+=1e-6

    def x(i): return int(L+(W-L-R)*(i/max(len(d)-1,1)))
    def y(v): return int(T+(H-T-B)*(1-(v-vmin)/(vmax-vmin)))

    for i,C in enumerate(d):
        drw.line([(x(i),y(C["low"])),(x(i),y(C["high"]))],fill=(180,180,190))
        y0 = y(min(C["open"], C["close"]))
        y1 = y(max(C["open"], C["close"]))
        if y0>y1: y0,y1=y1,y0
        drw.rectangle([x(i)-2,y0,x(i)+2,y1],
                      fill=(90,180,90) if C["close"]>=C["open"] else (200,100,100))

    if levs:
        for k,v in levs.items():
            drw.line([(L,y(v)),(W-R,y(v))],fill=(120,120,200))
            drw.text((W-R-140,y(v)-12),f"{k} {v:.6g}",fill=(220,220,230))
    drw.text((L,8),f"{sym} TF {tf}",fill=(230,230,240))
    path=os.path.join(save,f"{sym}_{tf}_{int(time.time())}.png")
    img.save(path,"PNG")
    return path

# === УРОВНИ ===
def pick_biggest_candle(candles):
    if not candles: return None
    best_idx=0; best_size=-1.0
    for i,c in enumerate(candles):
        sz=candle_effective_size(c)
        if sz>best_size:
            best_size=sz; best_idx=i
    return candles[best_idx]

def build_levels_from_candle(c):
    o,h,l,cl = c["open"], c["high"], c["low"], c["close"]
    if cl >= o:  # зелёная
        A = o; C = h
    else:        # красная
        A = l; C = o
    rng = C - A
    D = C + rng
    F = A - rng
    return {"A":A,"C":C,"D":D,"F":F}

def fmt_levels_human(levels):
    return ("A={A:.6g} | C={C:.6g} | D={D:.6g} | F={F:.6g}"
           ).format(**{k:float(v) for k,v in levels.items()})

# === ПАТТЕРНЫ ===
def detect_patterns(candles):
    if len(candles)<4: return None
    c1,c2,c3,c4 = candles[-4],candles[-3],candles[-2],candles[-1]
    out=[]
    body=lambda c: abs(c["close"]-c["open"])
    rng=lambda c: c["high"]-c["low"]
    if rng(c4)>0 and body(c4)/rng(c4) < 0.1:
        out.append("Doji")
    if c3["close"]<c3["open"] and c4["close"]>c4["open"] and c4["close"]>c3["open"] and c4["open"]<c3["close"]:
        out.append("Bullish Engulfing")
    if c3["close"]>c3["open"] and c4["close"]<c4["open"] and c4["close"]<c3["open"] and c4["open"]>c3["close"]:
        out.append("Bearish Engulfing")
    if all(c["close"]>c["open"] for c in [c2,c3,c4]):
        out.append("Three White Soldiers")
    if all(c["close"]<c["open"] for c in [c2,c3,c4]):
        out.append("Three Black Crows")
    return out if out else None

# === STATE ===
class State:
    def __init__(self):
        self.candles=deque(maxlen=MAX_CANDLES)
        self.last_ts=None
        self.levels=None
        self.ob_bids=deque(maxlen=ORDERBOOK_WINDOW)
        self.ob_asks=deque(maxlen=ORDERBOOK_WINDOW)

# === WORKER ===
async def worker(sym,tf,poll,sess):
    st=State()
    initial=await fetch_kline(sess,sym,tf,INIT_CANDLES)
    for c in initial: st.candles.append(c)
    st.last_ts=initial[-1]["ts"] if initial else None

    ref = pick_biggest_candle(list(st.candles))
    if ref:
        st.levels = build_levels_from_candle(ref)
        png=plot_png(sym,tf,list(st.candles),st.levels,HTML_OUTPUT_DIR)
        await tg_photo(sess, f"<b>{sym} {tf}m</b>\nСтартовые уровни:\n{fmt_levels_human(st.levels)}", png)

    atr_prev = await fetch_daily_atr_prev(sess, sym, ATR_PERIOD_DAILY)

    while True:
        latest = await fetch_kline(sess,sym,tf,2)
        if not latest: 
            await asyncio.sleep(poll); continue
        closed = latest[-2] if len(latest)>=2 else latest[-1]

        if st.last_ts is None or closed["ts"] > st.last_ts:
            st.candles.append(closed)
            st.last_ts = closed["ts"]

            closes=[x["close"] for x in st.candles]
            highs =[x["high"]  for x in st.candles]
            lows  =[x["low"]   for x in st.candles]

            last_bar = st.candles[-1]

            if ENABLE_VOLUME_FILTER and (not candle_big_enough(last_bar) or not volume_growth_passed(list(st.candles))):
                await asyncio.sleep(poll); continue

            # RSI / Stoch
            if ENABLE_INDICATORS:
                rsi = compute_rsi(closes, RSI_PERIOD)
                st_k, _ = compute_stoch(highs, lows, closes, STOCH_K, STOCH_D, STOCH_SMOOTH)

                if len(rsi)>1 and not math.isnan(rsi[-1]):
                    if rsi[-2] >= RSI_LOW and rsi[-1] < RSI_LOW:
                        png=plot_png(sym,tf,list(st.candles),st.levels,HTML_OUTPUT_DIR)
                        await tg_photo(sess, f"{sym} {tf}m RSI < {RSI_LOW}: {rsi[-1]:.6g}", png)
                    if rsi[-2] <= RSI_HIGH and rsi[-1] > RSI_HIGH:
                        png=plot_png(sym,tf,list(st.candles),st.levels,HTML_OUTPUT_DIR)
                        await tg_photo(sess, f"{sym} {tf}m RSI > {RSI_HIGH}: {rsi[-1]:.6g}", png)

                rsi_bin=[(v<RSI_LOW or v>RSI_HIGH) if not math.isnan(v) else False for v in rsi]
                if three_touches(rsi_bin,THREE_TOUCH_LOOKBACK,THREE_TOUCH_SPACING):
                    png=plot_png(sym,tf,list(st.candles),st.levels,HTML_OUTPUT_DIR)
                    await tg_photo(sess, f"{sym} {tf}m Три касания RSI", png)

                stoch_bin=[(k<20 or k>80) if not math.isnan(k) else False for k in st_k]
                if three_touches(stoch_bin,THREE_TOUCH_LOOKBACK,THREE_TOUCH_SPACING):
                    png=plot_png(sym,tf,list(st.candles),st.levels,HTML_OUTPUT_DIR)
                    await tg_photo(sess, f"{sym} {tf}m Три касания Stoch", png)

            # ATR аномалия
            if ENABLE_ATR_ANOMALY and atr_prev:
                prev_close = st.candles[-2]["close"] if len(st.candles)>=2 else last_bar["close"]
                tr = true_range(last_bar["high"], last_bar["low"], prev_close)
                if tr >= ANOMALY_ATR_RATIO * atr_prev:
                    png=plot_png(sym,tf,list(st.candles),st.levels,HTML_OUTPUT_DIR)
                    await tg_photo(sess, f"{sym} {tf}m ATR anomaly {tr:.6g}", png)

            # Паттерны
            if ENABLE_PATTERNS:
                pats=detect_patterns(list(st.candles))
                if pats:
                    png=plot_png(sym,tf,list(st.candles),st.levels,HTML_OUTPUT_DIR)
                    await tg_photo(sess, f"{sym} {tf}m Pattern(s): {', '.join(pats)}", png)

            # Стакан
            if ENABLE_ORDERBOOK_ANOMALY:
                ob = await fetch_orderbook(sess, sym)
                if ob:
                    bid1, ask1 = ob
                    st.ob_bids.append(bid1)
                    st.ob_asks.append(ask1)
                    if len(st.ob_bids) >= 5 and len(st.ob_asks) >= 5:
                        avg_b = sum(list(st.ob_bids)[:-1]) / max(1, len(st.ob_bids) - 1)
                        avg_a = sum(list(st.ob_asks)[:-1]) / max(1, len(st.ob_asks) - 1)
                        ob_alerts = []
                        if avg_b > 0 and bid1 >= ORDERBOOK_FACTOR * avg_b:
                            ob_alerts.append(f"bid1 qty {bid1:.6g} (avg {avg_b:.6g}, ×{bid1/max(1e-12,avg_b):.2f})")
                        if avg_a > 0 and ask1 >= ORDERBOOK_FACTOR * avg_a:
                            ob_alerts.append(f"ask1 qty {ask1:.6g} (avg {avg_a:.6g}, ×{ask1/max(1e-12,avg_a):.2f})")
                        if ob_alerts:
                            png = plot_png(sym, tf, list(st.candles), st.levels, HTML_OUTPUT_DIR)
                            caption = f"{sym} {tf}m Orderbook anomaly\n" + "\n".join(ob_alerts) + f"\n{fmt_levels_human(st.levels)}"
                            await tg_photo(sess, caption, png)

        await asyncio.sleep(poll)

# === MAIN ===
async def main():
    # DNS fix для Termux
    conn = aiohttp.TCPConnector(limit=50, resolver=resolver.ThreadedResolver())
    async with aiohttp.ClientSession(connector=conn) as sess:
        tasks = []
        for sym in SYMBOLS:
            for tf in TF_LIST:
                poll = POLL_SEC_FAST if tf in ("5", "15") else POLL_SEC_SLOW
                tasks.append(asyncio.create_task(worker(sym, tf, poll, sess)))
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
       