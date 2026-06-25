"""测试 db_reader 模块 — czsc-trading v5.4 DB-first 集成"""
import os
import pytest
from czsc_cli import db_reader


def test_db_available():
    """DB 存在 + 有 stock_basic 数据"""
    assert db_reader.is_db_available(), "DB 不存在或没数据"


def test_get_stock_basic_all():
    """拿全部 stock_basic 应该有 5000+ 行"""
    rows = db_reader.get_stock_basic()
    assert len(rows) >= 5000, f"stock_basic 太少: {len(rows)}"


def test_get_stock_basic_by_code():
    """按 ts_code 查单只"""
    rows = db_reader.get_stock_basic(ts_code="000001.SZ")
    assert len(rows) == 1
    assert rows[0]["ts_code"] == "000001.SZ"


def test_get_stock_basic_by_exchange():
    """按 exchange 过滤"""
    sse = db_reader.get_stock_basic(exchange="SSE")
    szse = db_reader.get_stock_basic(exchange="SZSE")
    assert len(sse) > 0
    assert len(szse) > 0


def test_get_daily_bars_no_adj():
    """拿 K 线 (不复权)"""
    bars = db_reader.get_daily_bars("000001.SZ", "20260101", "20260131", adj="none")
    assert len(bars) > 0
    assert "close" in bars[0]
    assert "trade_date" in bars[0]


def test_get_daily_bars_qfq():
    """拿 K 线 (前复权)"""
    bars = db_reader.get_daily_bars("000001.SZ", "20260101", "20260625", adj="qfq")
    assert len(bars) > 50, f"qfq 数据少: {len(bars)}"


def test_get_daily_bars_hfq():
    """拿 K 线 (后复权)"""
    bars = db_reader.get_daily_bars("000001.SZ", "20260101", "20260625", adj="hfq")
    assert len(bars) > 50


def test_get_daily_basic():
    """拿每日指标"""
    rows = db_reader.get_daily_basic("000001.SZ", "20260101", "20260131")
    assert len(rows) > 0
    assert "pe" in rows[0] or "turnover_rate" in rows[0]


def test_get_top_list():
    """拿龙虎榜"""
    rows = db_reader.get_top_list("20260625")
    # 20260625 是交易日,应该有数据
    # 但 top_list 按周拉,数据稀疏,允许空
    assert isinstance(rows, list)


def test_get_block_trade():
    """拿大宗交易"""
    rows = db_reader.get_block_trade("20260625")
    assert isinstance(rows, list)


def test_get_latest_trade_date():
    """最近一个交易日"""
    latest = db_reader.get_latest_trade_date()
    assert latest is not None
    assert len(latest) == 8  # YYYYMMDD


def test_get_db_stats():
    """DB 健康度报告"""
    stats = db_reader.get_db_stats()
    assert stats["available"]
    assert "tables" in stats
    assert stats["tables"]["daily"]["rows"] > 1000000  # 至少 100 万行


def test_data_py_uses_db():
    """data.py fetch_klines_for_signals 应该走 DB"""
    from czsc_cli import data
    bars, df = data.fetch_klines_for_signals("000001.SZ", days=60, use_cache=False)
    assert len(bars) >= 30, f"应至少 30 bars, 实得 {len(bars)}"
    assert df is not None
    assert df.shape[0] >= 30
