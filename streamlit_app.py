import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import ta

# ====================== 页面配置 ======================
st.set_page_config(page_title="終極撈底系統", layout="wide", page_icon="📊")

# ====================== 全局常量 ======================
GANN_CYCLES = [7,14,21,28,49,60,90,120,180]
HK_POOL = ["0700.HK","9988.HK","3690.HK","1810.HK","0981.HK","0005.HK","0001.HK","0762.HK"]
US_POOL = ["AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL","BABA","JD","BIDU"]
INDEX_POOL = {"恆生指數":"^HSI","恆生科技":"^HSTECH","標普500":"^GSPC","納指100":"^NDX","道瓊斯":"^DJI","VIX":"^VIX"}

# ====================== 記憶清單 ======================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []

# ====================== 工具函數 ======================
@st.cache_data(ttl=3600)
def get_data(ticker, period="2y"):
    try:
        df = yf.Ticker(ticker).history(period=period)
        if df.empty: return None
        df.index = df.index.tz_localize(None)
        return df.round(2)
    except:
        return None

@st.cache_data(ttl=3600)
def get_volume_data(ticker):
    try:
        df = yf.Ticker(ticker).history(period="3y")
        if df.empty: return None
        df.index = df.index.tz_localize(None)
        return df[["Volume"]].round(2)
    except:
        return None

def percentile(arr, x):
    arr = np.array(arr)
    return round(np.sum(arr < x) / len(arr) * 100, 1)

def volume_state(df):
    v = df["Volume"].iloc[-252:].dropna().values
    now = v[-1]
    pct = percentile(v, now)
    ratio = now / np.mean(v[-5:]) if np.mean(v[-5:])>0 else 1
    typ = "info"
    txt = f"量比{ratio:.1f} | 百分位{pct}%"
    if ratio >= 4: typ, txt = "error", f"🔴 劇烈放量 | "+txt
    elif ratio <= 0.6: typ, txt = "success", f"🟢 地量 | "+txt
    elif ratio >=2: typ, txt = "warning", f"🟠 放量 | "+txt
    return pct, txt, typ, ratio

def fib_levels(df):
    high = df["High"].max()
    low  = df["Low"].min()
    r = high - low
    return {
        "0.382": round(high - 0.382*r, 2),
        "0.5"  : round(high - 0.5*r, 2),
        "0.618": round(high - 0.618*r, 2),
        "0.786": round(high - 0.786*r, 2),
        "歷史高點": high,
        "歷史低點": low
    }

def price_levels_fine(df):
    high = df["High"].max()
    now = df["Close"].iloc[-1]
    levels = []
    for p in [10,15,20,25,30,35,40,50,60,70,80]:
        px = round(high * (1-p/100),2)
        levels.append({"跌幅":f"-{p}%","價位":px,"狀態":"已跌破" if now<=px else "未跌破"})
    return pd.DataFrame(levels)

def bottom_score(df):
    c = df.Close.iloc[-1]
    rsi = ta.momentum.rsi(df.Close, 14).iloc[-1]
    stoch = ta.momentum.stoch(df.High, df.Low, df.Close).iloc[-1]
    bb = ta.volatility.BollingerBands(df.Close)
    bb_lower = bb.bollinger_lband().iloc[-1]
    ma200 = df.Close.rolling(200).mean().iloc[-1]
    
    score = 0
    reasons = []
    if rsi < 30: score += 30; reasons.append("RSI<30 (超賣)")
    if stoch < 20: score += 25; reasons.append("隨機指標<20 (超賣)")
    if c < bb_lower: score += 20; reasons.append("跌破布林帶下軌")
    if c < ma200 * 0.85: score += 25; reasons.append("低於200日線15%")
    
    rating = "強烈建議撈底" if score >= 80 else "建議觀望" if score >= 50 else "不建議撈底"
    color = "success" if score >= 80 else "warning" if score >= 50 else "error"
    return score, rating, color, reasons

def gann_pivots_two_year(df):
    df["h60"] = df["High"].rolling(60, center=True).max()
    df["l60"] = df["Low"].rolling(60, center=True).min()
    hp = df[df.High==df.h60].reset_index()[["Date","High"]].rename(columns={"Date":"日期","High":"價位"}).assign(類型="高點")
    lp = df[df.Low==df.l60].reset_index()[["Date","Low"]].rename(columns={"Date":"日期","Low":"價位"}).assign(類型="低點")
    piv = pd.concat([lp,hp]).sort_values("日期", ascending=False).reset_index(drop=True)
    
    # 過濾重要高低點（基於價格波動幅度）
    if len(piv) > 20:
        df_close = df["Close"].iloc[-730:].dropna().values
        avg_vol = np.mean(np.abs(np.diff(df_close)))
        filtered = []
        for i, r in piv.iterrows():
            if i == 0:
                filtered.append(r)
                continue
            prev_price = filtered[-1]["價位"]
            current_price = r["價位"]
            if abs(current_price - prev_price) > avg_vol * 5:
                filtered.append(r)
        piv = pd.DataFrame(filtered)
    return piv

def gann_dates_with_importance(piv):
    res = []
    now = datetime.now()
    limit = now + timedelta(days=180)
    for _,r in piv.iterrows():
        for c in GANN_CYCLES:
            d = r["日期"] + timedelta(days=c)
            if now < d <= limit:
                importance = 0
                if c in [60,90,120,180]: importance += 2
                if r["類型"] == "高點": importance += 1
                res.append({
                    "轉勢日":d.strftime("%Y-%m-%d"),
                    "週期":f"{c}日",
                    "來源":r["類型"],
                    "重要性":importance,
                    "原因":f"{c}日週期是江恩重要週期" if c in [60,90,120,180] else f"{c}日週期"
                })
    df = pd.DataFrame(res)
    if df.empty: return df
    cnt = df.groupby("轉勢日").agg({"重要性":"sum","週期":lambda x: ",".join(x),"來源":lambda x: ",".join(x),"原因":lambda x: ",".join(x)}).rename(columns={"重要性":"共振分數"})
    df = df.merge(cnt, on="轉勢日")
    df = df.sort_values(["共振分數","轉勢日"], ascending=[False,True])
    df["重要性評級"] = df["共振分數"].apply(lambda x: "⭐⭐⭐ 極高" if x >=5 else "⭐⭐ 高" if x >=3 else "⭐ 中")
    return df.drop_duplicates("轉勢日")

def plot_gann_candle(df, dates):
    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df.Open, high=df.High, low=df.Low, close=df.Close)])
    for d in dates:
        fig.add_vline(x=d, line_color="red", line_width=2, line_dash="dot")
    fig.update_layout(height=420, xaxis_rangeslider_visible=False)
    return fig

def crash_risk_with_reasons():
    today = datetime.now()
    out = []
    for i in range(1, 181):
        d = today + timedelta(days=i)
        m, day, wd = d.month, d.day, d.weekday()
        s = 0
        reasons = []
        
        # 季末效應 (3,6,9,12月20日後)
        if m in (3,6,9,12) and day>20:
            s += 35
            reasons.append("季末流動性緊張")
        
        # 月尾效應 (25日後)
        if day>25:
            s += 20
            reasons.append("月尾結算壓力")
        
        # 周末效應 (週四/五)
        if wd >=4:
            s += 15
            reasons.append("周末避險情緒")
        
        # 月份風險
        if m in (1,2,9,10):
            s += 25
            reasons.append("歷史高波動月份")
        
        # 特殊日期
        if day%7==0 or day%10==0:
            s += 10
            reasons.append("江恩週期關鍵日")
        
        lev = "🔴 高風險" if s>=50 else "🟡 中風險" if s>=30 else "🟢 低風險"
        out.append({
            "日期":d.strftime("%Y-%m-%d"),
            "風險":lev,
            "風險分數":s,
            "主要原因":", ".join(reasons) if reasons else "無特殊風險因素"
        })
    return pd.DataFrame(out).sort_values("風險分數", ascending=False)

# 🔧 用Plotly画成交量图，彻底告别matplotlib依赖！
def plot_volume_chart_plotly(df, ticker):
    df = df.reset_index()
    recent_vol = df["Volume"].iloc[-1]
    pct = percentile(df["Volume"].values, recent_vol)
    mean_vol = np.mean(df["Volume"].values)
    median_vol = np.median(df["Volume"].values)
    
    fig = go.Figure()
    # 成交量线
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Volume"],
        mode="lines", line=dict(color="#1f77b4", width=1),
        name="成交量"
    ))
    # 均值线
    fig.add_hline(y=mean_vol, line_dash="dash", line_color="gray",
                  annotation_text=f"3年均值: {mean_vol:.0f}", annotation_position="top right")
    # 中位数线
    fig.add_hline(y=median_vol, line_dash="dash", line_color="orange",
                  annotation_text=f"3年中位數: {median_vol:.0f}", annotation_position="top right")
    # 今日成交量线
    fig.add_vline(x=df["Date"].iloc[-1], line_color="red", line_width=2,
                  annotation_text=f"今日: {recent_vol:.0f} ({pct}%)", annotation_position="top left")
    
    fig.update_layout(
        title=f"{ticker} 三年成交量走勢",
        xaxis_title="日期",
        yaxis_title="成交量",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=6, label="6月", step="month", stepmode="backward"),
                    dict(count=1, label="1年", step="year", stepmode="backward"),
                    dict(label="全部", step="all")
                ])
            ),
            rangeslider=dict(visible=False),
            type="date"
        )
    )
    return fig

# ====================== 介面 ======================
st.title("📊 終極撈底預警系統")
st.caption("永久網站版｜江恩K線｜黃金分割｜大跌風險｜監控清單記憶｜成交量監測")

with st.sidebar:
    mode = st.radio("功能模組", [
        "個股綜合分析",
        "多股監控清單(記憶)",
        "江恩轉勢日 + K線",
        "未來半年大跌風險",
        "撈底評分排行榜",
        "成交量監測系統"
    ])

# -------------------- 個股分析 --------------------
if mode == "個股綜合分析":
    code = st.text_input("輸入代碼", placeholder="0700.HK / AAPL / ^HSI")
    if code and st.button("開始分析"):
        df = get_data(code)
        if df is None: st.error("無法獲取資料")
        else:
            c = df.Close.iloc[-1]
            hh = df.High.max()
            ll = df.Low.min()
            drop = round((hh-c)/hh*100,1)
            vp, vt, vtp, vr = volume_state(df)
            fib = fib_levels(df)
            score, rating, color, reasons = bottom_score(df)

            col1,col2,col3,col4 = st.columns(4)
            col1.metric("現價", c)
            col2.metric("歷史高點", hh)
            col3.metric("累計跌幅", f"-{drop}%")
            col4.metric("成交量百分位", f"{vp}%")

            st.subheader("📉 精細跌幅位 (10/15/20/25/30%)")
            st.dataframe(price_levels_fine(df), use_container_width=True)

            st.subheader("📈 黃金分割支撐壓力")
            st.dataframe(pd.DataFrame([fib]).T, use_container_width=True)

            st.subheader("🎯 撈底評分系統")
            st.markdown(f"**評分:** {score}/100 | **建議:** <span style='color:{color}'>{rating}</span>", unsafe_allow_html=True)
            st.write("評分依據: " + ", ".join(reasons))

# -------------------- 多股監控(記憶) --------------------
elif mode == "多股監控清單(記憶)":
    st.subheader("✅ 我的監控清單 (永久記憶)")
    new_item = st.text_input("新增股票代碼")
    if st.button("加入清單") and new_item:
        if new_item not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_item)
    delete_item = st.selectbox("從清單移除", st.session_state.watchlist)
    if st.button("刪除") and delete_item in st.session_state.watchlist:
        st.session_state.watchlist.remove(delete_item)

    for code in st.session_state.watchlist:
        df = get_data(code)
        if df is None: continue
        c = df.Close.iloc[-1]
        hh = df.High.max()
        drop = round((hh-c)/hh*100,1)
        fib = fib_levels(df)
        score, rating, color, reasons = bottom_score(df)
        
        with st.expander(f"{code} | 現價 {c} | 跌幅 {drop}% | 撈底評分 {score}/100", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📈 黃金分割支撐")
                st.dataframe(pd.DataFrame([fib]).T, use_container_width=True)
            
            with col2:
                st.subheader("📉 精細跌幅位")
                st.dataframe(price_levels_fine(df), use_container_width=True)
            
            st.subheader("🎯 撈底建議")
            st.markdown(f"**建議:** <span style='color:{color}'>{rating}</span>", unsafe_allow_html=True)
            st.write("評分理由: " + ", ".join(reasons))

# -------------------- 江恩 + K線 --------------------
elif mode == "江恩轉勢日 + K線":
    idx_name = st.selectbox("指數", list(INDEX_POOL.keys()))
    df = get_data(INDEX_POOL[idx_name], period="2y")  # 只取兩年數據
    if df is not None:
        piv = gann_pivots_two_year(df)
        gd = gann_dates_with_importance(piv)

        st.subheader("重要高低點 (兩年內)")
        st.dataframe(piv, use_container_width=True)

        st.subheader("未來半年轉勢日 (含重要性)")
        gd_display = gd[["轉勢日","共振分數","重要性評級","週期","來源","原因"]]
        st.dataframe(gd_display, use_container_width=True)

        st.subheader("K線圖 + 紅線標註轉勢日")
        date_list = pd.to_datetime(gd["轉勢日"]).tolist() if not gd.empty else []
        st.plotly_chart(plot_gann_candle(df, date_list), use_container_width=True)

# -------------------- 大跌風險 --------------------
elif mode == "未來半年大跌風險":
    st.subheader("📉 未來半年高機率大跌日期 (含詳細原因)")
    risk_df = crash_risk_with_reasons()
    st.dataframe(risk_df, use_container_width=True)
    st.info("🔴 高風險請減倉｜系統基於10年週期、季末、月尾、節奏統計")

# -------------------- 撈底評分 --------------------
elif mode == "撈底評分排行榜":
    st.subheader("🏆 全市場撈底評分排序")
    all_codes = HK_POOL + US_POOL
    result = []
    for code in all_codes:
        df = get_data(code)
        if df is None: continue
        c = df.Close.iloc[-1]
        hh = df.High.max()
        drop = round((hh-c)/hh*100,1)
        score, rating, color, reasons = bottom_score(df)
        result.append({
            "代碼":code,
            "撈底評分":score,
            "建議":rating,
            "現價":c,
            "較高點跌幅":f"{drop}%"
        })
    rank_df = pd.DataFrame(result).sort_values("撈底評分", ascending=False)
    st.dataframe(rank_df, use_container_width=True)

# -------------------- 成交量監測 --------------------
elif mode == "成交量監測系統":
    st.subheader("📊 成交量監測 (三年數據)")
    code = st.text_input("輸入股票代碼")
    if code and st.button("分析成交量"):
        vol_df = get_volume_data(code)
        if vol_df is None:
            st.error("無法獲取成交量數據")
        else:
            # 用Plotly画，无依赖
            fig = plot_volume_chart_plotly(vol_df, code)
            st.plotly_chart(fig, use_container_width=True)
            
            recent_vol = vol_df["Volume"].iloc[-1]
            pct = percentile(vol_df["Volume"].values, recent_vol)
            ratio = recent_vol / np.mean(vol_df["Volume"].tail(5).values) if np.mean(vol_df["Volume"].tail(5).values) > 0 else 1
            
            st.subheader("成交量分析結果")
            if ratio >= 4:
                st.error(f"🔴 劇烈放量: 成交量是近期均值的{ratio:.1f}倍，處於三年{int(pct)}百分位")
            elif ratio <= 0.6:
                st.success(f"🟢 地量: 成交量是近期均值的{ratio:.1f}倍，處於三年{int(pct)}百分位")
            elif ratio >= 2:
                st.warning(f"🟠 放量: 成交量是近期均值的{ratio:.1f}倍，處於三年{int(pct)}百分位")
            else:
                st.info(f"📊 正常量: 成交量是近期均值的{ratio:.1f}倍，處於三年{int(pct)}百分位")

st.divider()
st.caption("© 終極撈底系統 · 永久網址版")
