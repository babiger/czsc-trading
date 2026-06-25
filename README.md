# czsc-trading

缠论技术分析 OpenClaw skill — Python wrapper for `waditu/czsc` + `akshare`.

## 装机状态

- 安装日期: 2026-06-23
- czsc 版本: 1.0.0rc8 (Rust 加速)
- akshare 版本: 1.18.64
- Python: 3.11.2

## 文件清单

```
czsc-trading/
├── SKILL.md                          # 触发场景 + CLI 用法 + 安全声明
├── README.md                         # 本文件
├── runtime.conf                      # python3 entry
├── .gitignore                        # __pycache__, output/*.html, .env
├── scripts/
│   └── czsc_trading.py               # 主 CLI (analyze/signals/report/doc)
├── examples/
│   └── demo_mock.py                  # 用 mock 数据 demo (不需联网)
├── references/
│   └── cheatsheet.md                 # 常用 API 速查
└── output/                           # HTML 输出目录 (默认 .gitignore)
```

## 一句话总结

```bash
python3 scripts/czsc_trading.py analyze --ts-code 000001.SZ --output /tmp/x.html
```

## 安全 / 来源

- GitHub: <https://github.com/waditu/czsc> (Apache-2.0 / BSD, 6K+ stars)
- pip: tuna 镜像 (国内加速)
- 数据源: akshare (东方财富免费接口)
- **无外部脚本下载**,**无 API token**,**无自动修改任何全局配置**
