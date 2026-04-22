# -*- coding: utf-8 -*-
"""
投资仪表盘 - Supabase PostgreSQL 版
数据存储在云端 Supabase 数据库，重启不会丢失
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta
import random

st.set_page_config(page_title="投资仪表盘", layout="wide", page_icon="📊")

# 配色常量（中国股市：涨红跌绿）
RED = "#E74C3C"
GREEN = "#27AE60"
BLUE = "#3498DB"
ORANGE = "#F39C12"
PURPLE = "#9B59B6"

# ─── 数据库配置（从环境变量读取）───────────────────────────
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres"
)


# ─── 建表 SQL（PostgreSQL 语法）───────────────────────────
TABLES_SQL = """
CREATE TABLE IF NOT EXISTS stocks (
    ts_code TEXT PRIMARY KEY, name TEXT, industry TEXT, market TEXT,
    list_date TEXT, updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS daily (
    id SERIAL PRIMARY KEY, ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL, open REAL DEFAULT 0, high REAL DEFAULT 0,
    low REAL DEFAULT 0, close REAL DEFAULT 0, volume REAL DEFAULT 0,
    amount REAL DEFAULT 0, pct_chg REAL DEFAULT 0, turnover REAL DEFAULT 0,
    UNIQUE(ts_code, trade_date)
);
CREATE TABLE IF NOT EXISTS positions (
    ts_code TEXT PRIMARY KEY, shares REAL NOT NULL, cost_price REAL NOT NULL,
    current_price REAL DEFAULT 0, buy_date TEXT, notes TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY, ts_code TEXT NOT NULL,
    direction TEXT NOT NULL, price REAL NOT NULL, shares REAL NOT NULL,
    trade_date TEXT, fee REAL DEFAULT 0, notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS watchlist (
    ts_code TEXT PRIMARY KEY, group_name TEXT DEFAULT '默认',
    notes TEXT, added_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS financials (
    id SERIAL PRIMARY KEY, ts_code TEXT NOT NULL,
    period TEXT NOT NULL, end_date TEXT, revenue REAL DEFAULT 0,
    net_profit REAL DEFAULT 0, gross_margin REAL DEFAULT 0,
    roe REAL DEFAULT 0, pe REAL DEFAULT 0, pb REAL DEFAULT 0,
    total_mv REAL DEFAULT 0, UNIQUE(ts_code, period)
);
CREATE TABLE IF NOT EXISTS briefings (
    trade_date TEXT PRIMARY KEY, summary TEXT, market_view TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """初始化数据库，如果是首次则写入演示数据"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(TABLES_SQL)
    conn.commit()

    # 检查是否已有数据
    cur.execute("SELECT COUNT(*) AS cnt FROM stocks")
    count = cur.fetchone()["cnt"]
    if count == 0:
        _seed_demo_data(conn)

    return conn


def _seed_demo_data(conn):
    """首次启动时写入演示数据"""
    cur = conn.cursor()
    portfolio = [
        ("00700.HK", "腾讯控股", "互联网", "HK"),
        ("600519.SH", "贵州茅台", "白酒", "SH"),
        ("002027.SZ", "分众传媒", "传媒", "SZ"),
        ("600036.SH", "招商银行", "银行", "SH"),
        ("002415.SZ", "海康威视", "安防", "SZ"),
        ("000333.SZ", "美的集团", "家电", "SZ"),
        ("2359.HK",  "药明康德", "医疗", "HK"),
        ("300144.SZ", "宋城演艺", "文旅", "SZ"),
    ]
    for ts_code, name, industry, market in portfolio:
        cur.execute(
            "INSERT INTO stocks (ts_code, name, industry, market) VALUES (%s, %s, %s, %s) ON CONFLICT (ts_code) DO UPDATE SET name=%s, industry=%s, market=%s",
            (ts_code, name, industry, market, name, industry, market)
        )

    positions = [
        ("00700.HK", 500, 320.0, 348.0, "2025-01-15", "长期持有"),
        ("600519.SH", 100, 1650.0, 1720.0, "2024-11-20", "核心仓位"),
        ("002027.SZ", 5000, 5.80, 6.35, "2025-03-10", "低位布局"),
        ("600036.SH", 2000, 32.50, 35.80, "2025-02-28", "银行股配置"),
        ("002415.SZ", 1500, 30.20, 28.60, "2024-12-05", "观察仓"),
        ("000333.SZ", 1000, 58.00, 62.50, "2025-01-22", "家电龙头"),
        ("2359.HK", 3000, 45.00, 42.30, "2025-04-01", "抄底中"),
        ("300144.SZ", 3000, 12.50, 11.80, "2025-03-18", "文旅复苏"),
    ]
    for ts_code, shares, cost, current, buy_date, notes in positions:
        cur.execute(
            """INSERT INTO positions (ts_code, shares, cost_price, current_price, buy_date, notes, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (ts_code) DO UPDATE SET shares=%s, cost_price=%s, current_price=%s, buy_date=%s, notes=%s, updated_at=%s""",
            (ts_code, shares, cost, current, buy_date, notes, datetime.now().isoformat(),
             shares, cost, current, buy_date, notes, datetime.now().isoformat())
        )

    # 模拟行情数据
    random.seed(42)
    base_prices = {
        "00700.HK": 320, "600519.SH": 1650, "002027.SZ": 5.8,
        "600036.SH": 32.5, "002415.SZ": 30.2, "000333.SZ": 58.0,
        "2359.HK": 45.0, "300144.SZ": 12.5
    }
    base_date = datetime(2026, 2, 1)
    for ts_code, base_p in base_prices.items():
        price = base_p
        for i in range(60):
            d = base_date + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            change = random.uniform(-0.03, 0.03)
            price = max(price * (1 + change), base_p * 0.8)
            open_p = round(price * (1 + random.uniform(-0.01, 0.01)), 2)
            close_p = round(price, 2)
            high_p = round(max(open_p, close_p) * (1 + random.uniform(0, 0.015)), 2)
            low_p = round(min(open_p, close_p) * (1 - random.uniform(0, 0.015)), 2)
            volume = round(random.uniform(50000, 500000), 0)
            pct = round((close_p - (price / (1 + change))) / (price / (1 + change)) * 100, 2) if change != 0 else 0
            cur.execute(
                """INSERT INTO daily (ts_code, trade_date, open, high, low, close, volume, pct_chg)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (ts_code, trade_date) DO UPDATE SET open=%s, high=%s, low=%s, close=%s, volume=%s, pct_chg=%s""",
                (ts_code, d.strftime("%Y%m%d"), open_p, high_p, low_p, close_p, volume, pct,
                 open_p, high_p, low_p, close_p, volume, pct)
            )

    demo_trades = [
        ("00700.HK", "buy", 320.0, 500, "2025-01-15", 50.0, "建仓"),
        ("600519.SH", "buy", 1650.0, 100, "2024-11-20", 80.0, "建仓"),
        ("002027.SZ", "buy", 5.80, 5000, "2025-03-10", 30.0, "低位布局"),
        ("600036.SH", "buy", 32.50, 2000, "2025-02-28", 35.0, "银行配置"),
        ("000333.SZ", "buy", 58.00, 1000, "2025-01-22", 25.0, "买入"),
    ]
    for ts_code, d, p, s, tdate, fee, notes in demo_trades:
        cur.execute(
            """INSERT INTO trades (ts_code, direction, price, shares, trade_date, fee, notes, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (ts_code, d, p, s, tdate, fee, notes, datetime.now().isoformat())
        )

    watchlist = [
        ("000858.SZ", "白酒", "关注中"),
        ("601318.SH", "保险", "龙头"),
        ("002475.SZ", "新能源", "长期关注"),
    ]
    for ts_code, group, notes in watchlist:
        cur.execute(
            "INSERT INTO watchlist (ts_code, group_name, notes, added_at) VALUES (%s, %s, %s, %s) ON CONFLICT (ts_code) DO UPDATE SET group_name=%s, notes=%s, added_at=%s",
            (ts_code, group, notes, datetime.now().isoformat(), group, notes, datetime.now().isoformat())
        )

    conn.commit()


# ─── 查询封装 ─────────────────────────────────────────
def query_df(sql, params=None):
    """执行查询，返回 pandas DataFrame"""
    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    finally:
        conn.close()


def execute_sql(sql, params=None):
    """执行写入操作（INSERT/UPDATE/DELETE）"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def query_one(sql, params=None):
    """查询单个值"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row
    finally:
        conn.close()


# ─── 初始化 ──────────────────────────────────────────
@st.cache_resource
def init_app():
    """初始化数据库并返回状态"""
    conn = init_db()
    conn.close()
    return True

init_app()


# ─── 侧边栏：数据管理 ────────────────────────────────
with st.sidebar:
    st.header("数据管理")
    tab_mgmt = st.selectbox("管理类型", ["股票信息", "持仓管理", "交易记录", "自选股"], key="mgmt_tab")

    stocks_df = query_df("SELECT * FROM stocks ORDER BY ts_code")

    if tab_mgmt == "股票信息":
        with st.expander("添加股票", expanded=True):
            with st.form("add_stock_form"):
                ts_code = st.text_input("证券代码", placeholder="如 000001.SZ 或 00700.HK")
                name = st.text_input("股票名称")
                industry = st.text_input("所属行业")
                market = st.selectbox("市场", ["SH", "SZ", "HK", "US"])
                submitted = st.form_submit_button("添加")
                if submitted and ts_code and name:
                    execute_sql(
                        "INSERT INTO stocks (ts_code, name, industry, market) VALUES (%s, %s, %s, %s) ON CONFLICT (ts_code) DO UPDATE SET name=%s, industry=%s, market=%s",
                        (ts_code, name, industry, market, name, industry, market)
                    )
                    st.success(f"{name} 已添加")
                    st.rerun()

        st.divider()
        with st.expander("现有股票列表"):
            for _, row in stocks_df.iterrows():
                st.text(f"{row['ts_code']}  {row['name']}  {row['industry']}  {row['market']}")

        st.divider()
        with st.expander("删除股票"):
            del_code = st.selectbox("选择要删除的", stocks_df["ts_code"].tolist(), key="del_stock")
            if st.button("确认删除", type="secondary"):
                execute_sql("DELETE FROM stocks WHERE ts_code=%s", (del_code,))
                st.success("已删除")
                st.rerun()

    elif tab_mgmt == "持仓管理":
        with st.expander("添加/更新持仓", expanded=True):
            with st.form("add_pos_form"):
                code = st.selectbox("股票", stocks_df["ts_code"].tolist(),
                    format_func=lambda x: f"{stocks_df[stocks_df['ts_code']==x].iloc[0]['name']} ({x})",
                    key="pos_code")
                shares = st.number_input("持仓股数", min_value=0.0, step=100.0, key="pos_shares")
                cost = st.number_input("成本价", min_value=0.0, step=0.01, key="pos_cost")
                current = st.number_input("当前价", min_value=0.0, step=0.01, key="pos_current")
                buy_date = st.date_input("买入日期", key="pos_date")
                notes = st.text_input("备注", key="pos_notes")
                submitted = st.form_submit_button("保存持仓")
                if submitted and shares > 0 and cost > 0:
                    execute_sql(
                        """INSERT INTO positions (ts_code, shares, cost_price, current_price, buy_date, notes, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (ts_code) DO UPDATE SET shares=%s, cost_price=%s, current_price=%s, buy_date=%s, notes=%s, updated_at=%s""",
                        (code, shares, cost, current, buy_date.strftime("%Y-%m-%d"), notes, datetime.now().isoformat(),
                         shares, cost, current, buy_date.strftime("%Y-%m-%d"), notes, datetime.now().isoformat())
                    )
                    st.success("持仓已保存")
                    st.rerun()

        st.divider()
        with st.expander("删除持仓"):
            pos_list = query_df("SELECT ts_code FROM positions")
            if len(pos_list) > 0:
                del_pos = st.selectbox("选择", pos_list["ts_code"].tolist(), key="del_pos")
                if st.button("清仓删除", type="secondary"):
                    execute_sql("DELETE FROM positions WHERE ts_code=%s", (del_pos,))
                    st.success("已清仓")
                    st.rerun()

    elif tab_mgmt == "交易记录":
        with st.expander("记录新交易", expanded=True):
            with st.form("add_trade_form"):
                t_code = st.selectbox("股票", stocks_df["ts_code"].tolist(),
                    format_func=lambda x: f"{stocks_df[stocks_df['ts_code']==x].iloc[0]['name']} ({x})",
                    key="trade_code")
                t_dir = st.selectbox("方向", ["buy", "sell"],
                    format_func=lambda x: "买入" if x == "buy" else "卖出", key="trade_dir")
                t_price = st.number_input("成交价", min_value=0.0, step=0.01, key="trade_price")
                t_shares = st.number_input("成交量", min_value=0.0, step=100.0, key="trade_shares")
                t_date = st.date_input("交易日期", key="trade_date")
                t_fee = st.number_input("手续费", min_value=0.0, step=1.0, key="trade_fee")
                t_notes = st.text_input("备注", key="trade_notes")
                submitted = st.form_submit_button("记录交易")
                if submitted and t_price > 0 and t_shares > 0:
                    execute_sql(
                        """INSERT INTO trades (ts_code, direction, price, shares, trade_date, fee, notes, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (t_code, t_dir, t_price, t_shares, t_date.strftime("%Y-%m-%d"), t_fee, t_notes, datetime.now().isoformat())
                    )
                    st.success("交易已记录")
                    st.rerun()

        st.divider()
        with st.expander("最近交易"):
            trades = query_df("SELECT * FROM trades ORDER BY trade_date DESC LIMIT 10")
            if len(trades) > 0:
                st.dataframe(trades[["ts_code", "direction", "price", "shares", "trade_date", "fee"]],
                           use_container_width=True, hide_index=True)

    elif tab_mgmt == "自选股":
        with st.expander("添加自选", expanded=True):
            with st.form("add_watch_form"):
                w_code = st.selectbox("股票", stocks_df["ts_code"].tolist(),
                    format_func=lambda x: f"{stocks_df[stocks_df['ts_code']==x].iloc[0]['name']} ({x})",
                    key="watch_code")
                w_group = st.text_input("分组", value="默认", key="watch_group")
                w_notes = st.text_input("备注", key="watch_notes")
                submitted = st.form_submit_button("添加关注")
                if submitted:
                    execute_sql(
                        "INSERT INTO watchlist (ts_code, group_name, notes, added_at) VALUES (%s, %s, %s, %s) ON CONFLICT (ts_code) DO UPDATE SET group_name=%s, notes=%s, added_at=%s",
                        (w_code, w_group, w_notes, datetime.now().isoformat(), w_group, w_notes, datetime.now().isoformat())
                    )
                    st.success("已添加自选")
                    st.rerun()

        st.divider()
        with st.expander("当前自选"):
            wl = query_df("""
                SELECT w.ts_code, s.name, s.industry, w.group_name, w.notes
                FROM watchlist w LEFT JOIN stocks s ON w.ts_code = s.ts_code
                ORDER BY w.group_name
            """)
            if len(wl) > 0:
                st.dataframe(wl, use_container_width=True, hide_index=True)
            else:
                st.info("暂无自选股")


# ─── 主区域：图表展示 ──────────────────────────────────
st.title("投资仪表盘")

pos_row = query_one("SELECT COUNT(*) AS cnt FROM positions")
pos_count = pos_row["cnt"]
trade_row = query_one("SELECT COUNT(*) AS cnt FROM trades")
trade_count = trade_row["cnt"]
positions = query_df("""
    SELECT p.ts_code, s.name, s.industry,
           p.shares, p.cost_price, p.current_price,
           ROUND((p.current_price - p.cost_price) * p.shares::numeric, 2) AS profit,
           ROUND((p.current_price - p.cost_price) / p.cost_price::numeric * 100, 2) AS profit_pct,
           p.buy_date, p.notes
    FROM positions p LEFT JOIN stocks s ON p.ts_code = s.ts_code
    ORDER BY profit_pct DESC
""")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("持仓股票", f"{pos_count} 只")
with col2:
    total_profit = positions["profit"].sum() if len(positions) > 0 else 0
    st.metric("总盈亏", f"¥{total_profit:,.0f}")
with col3:
    avg_pct = positions["profit_pct"].mean() if len(positions) > 0 else 0
    st.metric("平均收益率", f"{avg_pct:.2f}%")
with col4:
    st.metric("交易笔数", f"{trade_count} 笔")

st.divider()

st.subheader("持仓明细")
if len(positions) > 0:
    def color_pct(val):
        return "color: red" if val > 0 else "color: green" if val < 0 else ""
    st.dataframe(
        positions.style.map(color_pct, subset=["profit_pct"]),
        use_container_width=True, hide_index=True
    )
else:
    st.info("暂无持仓，请在左侧添加")

tab_chart1, tab_chart2, tab_chart3 = st.tabs(["K线图", "走势对比", "行业分布"])

with tab_chart1:
    selected = st.selectbox("选择股票", stocks_df["ts_code"].tolist(),
        format_func=lambda x: f"{stocks_df[stocks_df['ts_code']==x].iloc[0]['name']} ({x})",
        key="chart1_select")

    daily = query_df("SELECT * FROM daily WHERE ts_code=%s ORDER BY trade_date", (selected,))
    if len(daily) > 0:
        daily["date_fmt"] = pd.to_datetime(daily["trade_date"], format="%Y%m%d")
        daily = daily.sort_values("date_fmt")
        daily["ma5"] = daily["close"].rolling(5).mean()
        daily["ma20"] = daily["close"].rolling(20).mean()

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                           row_heights=[0.7, 0.3], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(
            x=daily["date_fmt"], open=daily["open"], high=daily["high"],
            low=daily["low"], close=daily["close"],
            increasing_line_color=RED, decreasing_line_color=GREEN,
            increasing_fillcolor=RED, decreasing_fillcolor=GREEN, name="K线"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(x=daily["date_fmt"], y=daily["ma5"],
            mode="lines", name="MA5", line=dict(color=ORANGE, width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=daily["date_fmt"], y=daily["ma20"],
            mode="lines", name="MA20", line=dict(color=PURPLE, width=1.5)), row=1, col=1)
        vol_colors = [RED if daily.iloc[i]["close"] >= daily.iloc[i]["open"] else GREEN
                      for i in range(len(daily))]
        fig.add_trace(go.Bar(x=daily["date_fmt"], y=daily["volume"],
            marker_color=vol_colors, name="成交量", showlegend=False), row=2, col=1)
        fig.update_layout(height=480, template="plotly_white", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("暂无行情数据")

with tab_chart2:
    selected_cmp = st.multiselect("对比股票", stocks_df["ts_code"].tolist(),
        default=stocks_df["ts_code"].tolist()[:4],
        format_func=lambda x: f"{stocks_df[stocks_df['ts_code']==x].iloc[0]['name']}",
        key="chart2_select")
    if selected_cmp:
        all_daily = query_df("SELECT * FROM daily ORDER BY trade_date")
        all_daily["date_fmt"] = pd.to_datetime(all_daily["trade_date"], format="%Y%m%d")
        fig2 = go.Figure()
        palette = [RED, BLUE, GREEN, ORANGE, PURPLE, "#E67E22", "#1ABC9C"]
        for i, code in enumerate(selected_cmp):
            data = all_daily[all_daily["ts_code"] == code].sort_values("date_fmt")
            if len(data) > 0:
                base = data["close"].iloc[0]
                norm = (data["close"] / base * 100 - 100).round(2)
                name = stocks_df[stocks_df["ts_code"] == code].iloc[0]["name"]
                fig2.add_trace(go.Scatter(x=data["date_fmt"], y=norm,
                    mode="lines", name=name, line=dict(color=palette[i % len(palette)], width=2)))
        fig2.update_layout(height=400, template="plotly_white", yaxis_title="涨跌幅 (%)",
                          hovermode="x unified")
        fig2.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        st.plotly_chart(fig2, use_container_width=True)

with tab_chart3:
    if len(positions) > 0:
        col_p, col_t = st.columns([1, 1])
        with col_p:
            ind = positions.groupby("industry")["profit"].sum().reset_index()
            fig3 = go.Figure(go.Pie(labels=ind["industry"], values=ind["profit"], hole=0.45,
                marker_colors=[RED, BLUE, GREEN, ORANGE, PURPLE],
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>盈亏: ¥%{value:,.0f}<extra></extra>"))
            fig3.update_layout(height=350, showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)
        with col_t:
            ind_s = positions.groupby("industry").agg(
                stocks=("name", "count"), total_profit=("profit", "sum"),
                avg_pct=("profit_pct", "mean")).round(2).reset_index()
            ind_s.columns = ["行业", "股票数", "总盈亏", "平均收益率%"]
            st.dataframe(ind_s, use_container_width=True, hide_index=True)

st.caption("Supabase PostgreSQL 版 - 云端数据库，数据永久保存，重启不会丢失。")
