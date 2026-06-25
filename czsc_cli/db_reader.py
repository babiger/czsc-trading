"""czsc_cli.db_reader — 从本地 SQLite 数据库读数据 (v5.4+)

跟 data.py 的区别:
- data.py: 走网络 (tushare / akshare / 腾讯) — 慢, 限流
- db_reader: 走本地 SQLite (~/.openclaw/data/czsc_market.db) — 快, 无网络

策略:
- 默认优先 DB (czsc_market.db 有数据就用)
- DB 缺数据时 fallback 到 data.py 网络拉
- 用户可强制 use_db=False 走网络

支持的查询:
- get_stock_basic(ts_code=None) — 股票列表/单只详情
- get_daily_bars(ts_code, start_date, end_date) — K 线 OHLCV
- get_adj_factor(ts_code, start_date, end_date) — 复权因子
- get_daily_basic(ts_code, start_date, end_date) — PE/PB/换手率
- get_top_list(trade_date) — 龙虎榜
- get_block_trade(trade_date) — 大宗交易

设计原则:
- czsc-trading skill 不感知 DB 存在 (data.py 内部优先 DB, 网络兜底)
- DB 路径来自环境变量 CZCSC_DB_PATH 或默认 ~/.openclaw/data/czsc_market.db
- 所有日期统一 YYYYMMDD 字符串
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# DB 路径
DEFAULT_DB_PATH = os.path.expanduser("~/.openclaw/data/czsc_market.db")
DB_PATH = os.environ.get("CZCSC_DB_PATH", DEFAULT_DB_PATH)


def _conn():
    """获取 DB 连接 (短连接, 避免长时间持有锁)"""
    if not Path(DB_PATH).exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_db_available() -> bool:
    """DB 是否可用 (文件存在 + 有数据)"""
    conn = _conn()
    if not conn:
        return False
    try:
        cur = conn.execute("SELECT COUNT(*) FROM stock_basic")
        n = cur.fetchone()[0]
        return n > 0
    except Exception:
        return False
    finally:
        conn.close()


def get_db_stats() -> Dict:
    """DB 健康度报告 (rows per table)"""
    if not is_db_available():
        return {"available": False}
    conn = _conn()
    try:
        stats = {"available": True, "db_path": DB_PATH, "tables": {}}
        for table in ["stock_basic", "daily", "adj_factor", "daily_basic",
                      "top_list", "block_trade", "holder_number", "trade_cal"]:
            try:
                cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
                n = cur.fetchone()[0]
                # 不同表的日期列名不一样
                if table == "stock_basic":
                    cur = conn.execute(f"SELECT MIN(list_date), MAX(list_date) FROM {table}")
                elif table == "trade_cal":
                    cur = conn.execute(f"SELECT MIN(cal_date), MAX(cal_date) FROM {table}")
                elif table == "holder_number":
                    cur = conn.execute(f"SELECT MIN(end_date), MAX(end_date) FROM {table}")
                else:
                    cur = conn.execute(f"SELECT MIN(trade_date), MAX(trade_date) FROM {table}")
                r = cur.fetchone()
                date_range = f"{r[0]}~{r[1]}" if r[0] else "N/A"
                stats["tables"][table] = {"rows": n, "range": date_range}
            except Exception as e:
                stats["tables"][table] = {"error": str(e)}
        # meta
        try:
            cur = conn.execute("SELECT key, value FROM meta")
            stats["meta"] = dict(cur.fetchall())
        except Exception:
            stats["meta"] = {}
        return stats
    finally:
        conn.close()


# ============================================================
# 业务查询
# ============================================================
def get_stock_basic(ts_code: Optional[str] = None, list_status: str = "L",
                    industry: Optional[str] = None, exchange: Optional[str] = None) -> List[Dict]:
    """股票列表/单只详情

    Args:
        ts_code: 单只 (e.g. "000001.SZ") 或 None=全部
        list_status: L=上市 D=退市
        industry: 申万行业过滤
        exchange: SSE/SZSE/BSE
    """
    conn = _conn()
    if not conn:
        return []
    try:
        sql = "SELECT * FROM stock_basic WHERE list_status=?"
        params = [list_status]
        if ts_code:
            sql += " AND ts_code=?"
            params.append(ts_code)
        if industry:
            sql += " AND industry=?"
            params.append(industry)
        if exchange:
            sql += " AND exchange=?"
            params.append(exchange)
        sql += " ORDER BY ts_code"
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_daily_bars(ts_code: str, start_date: str, end_date: str,
                   adj: str = "qfq") -> List[Dict]:
    """K 线 OHLCV

    Args:
        ts_code: e.g. "000001.SZ"
        start_date/end_date: YYYYMMDD
        adj: qfq (前复权) | hfq (后复权) | none (不复权)
    """
    conn = _conn()
    if not conn:
        return []
    try:
        sql = """
            SELECT trade_date, open, high, low, close, pre_close, change, pct_chg,
                   vol, amount
            FROM daily
            WHERE ts_code=? AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date
        """
        cur = conn.execute(sql, (ts_code, start_date, end_date))
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            return []
        # 复权处理
        if adj in ("qfq", "hfq"):
            # 拉复权因子
            cur = conn.execute(
                "SELECT trade_date, adj_factor FROM adj_factor WHERE ts_code=? AND trade_date BETWEEN ? AND ?",
                (ts_code, start_date, end_date)
            )
            factors = {r["trade_date"]: r["adj_factor"] for r in cur.fetchall()}
            if factors:
                # 取最近一天的因子作基准
                last_factor = max(factors.values())
                for r in rows:
                    f = factors.get(r["trade_date"])
                    if f and f > 0:
                        if adj == "qfq":
                            ratio = f / last_factor
                        else:  # hfq
                            ratio = f
                        r["open"] = r["open"] * ratio
                        r["high"] = r["high"] * ratio
                        r["low"] = r["low"] * ratio
                        r["close"] = r["close"] * ratio
        return rows
    finally:
        conn.close()


def get_daily_basic(ts_code: str, start_date: str, end_date: str) -> List[Dict]:
    """每日指标 PE/PB/换手率/市值"""
    conn = _conn()
    if not conn:
        return []
    try:
        cur = conn.execute(
            """SELECT trade_date, close, turnover_rate, turnover_rate_f, volume_ratio,
                      pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm,
                      total_share, float_share, free_share, total_mv, circ_mv
               FROM daily_basic
               WHERE ts_code=? AND trade_date BETWEEN ? AND ?
               ORDER BY trade_date""",
            (ts_code, start_date, end_date)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_top_list(trade_date: str) -> List[Dict]:
    """龙虎榜某日上榜股"""
    conn = _conn()
    if not conn:
        return []
    try:
        cur = conn.execute(
            """SELECT * FROM top_list WHERE trade_date=? ORDER BY net_amount DESC""",
            (trade_date,)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_block_trade(trade_date: str) -> List[Dict]:
    """大宗交易某日"""
    conn = _conn()
    if not conn:
        return []
    try:
        cur = conn.execute(
            """SELECT * FROM block_trade WHERE trade_date=? ORDER BY amount DESC""",
            (trade_date,)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_latest_trade_date() -> Optional[str]:
    """最近一个交易日"""
    conn = _conn()
    if not conn:
        return None
    try:
        cur = conn.execute(
            "SELECT MAX(cal_date) FROM trade_cal WHERE is_open=1 AND exchange='SSE'"
        )
        r = cur.fetchone()
        return r[0] if r and r[0] else None
    finally:
        conn.close()
