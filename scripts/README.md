# scripts/

イラン関連の物流リスク分析・自動化スクリプト置き場。

---

## iran_logistics_risk.py — 物流リスク分析（基本版）

### 概要

ホルムズ海峡の地政学リスクを定量スコア化し、地域別リスクレベルと輸送コスト影響を算出するスクリプト。分析結果は JSON / CSV で `data/` フォルダに出力される。

### 動作環境

- Python 3.9 以上
- 追加ライブラリ不要（標準ライブラリのみ）

### 実行例

```bash
# ベースケース（現状維持）でJSON出力
python scripts/iran_logistics_risk.py

# ワーストケース（封鎖・全面衝突）でCSV出力
python scripts/iran_logistics_risk.py --scenario worst --format csv

# ベストケース、JSON+CSV両方出力、出力先指定
python scripts/iran_logistics_risk.py --scenario best --format both --output-dir data/

# コンソール出力なし（ファイル保存のみ）
python scripts/iran_logistics_risk.py --no-print
```

### オプション

| オプション | 選択肢 | デフォルト | 説明 |
|-----------|--------|-----------|------|
| `--scenario` | `base` / `best` / `worst` | `base` | 分析シナリオ |
| `--format` | `json` / `csv` / `both` | `json` | 出力フォーマット |
| `--output-dir` | パス | `../data` | 出力先ディレクトリ |
| `--no-print` | — | False | コンソール出力を抑制 |

### シナリオ定義

| シナリオ | 想定状況 | 原油価格 | 戦争リスク保険料 |
|---------|---------|---------|----------------|
| `base` | 現状維持（高緊張） | 82 $/bbl | 2.5% |
| `best` | 停戦・緊張緩和 | 68 $/bbl | 0.5% |
| `worst` | 海峡封鎖・全面衝突 | 130 $/bbl | 7.5% |

### リスクスコアの見方

| スコア | レベル | 目安 |
|-------|--------|------|
| 0–30 | LOW | 通常運航可 |
| 30–60 | MEDIUM | 要注意・追加保険推奨 |
| 60–80 | HIGH | 迂回ルート検討 |
| 80–100 | CRITICAL | 運航停止レベル |

### リスク因子と重み

| 因子 | 重み | 内容 |
|-----|------|------|
| 軍事活動・作戦行動 | 30% | 攻撃・封鎖・機雷敷設等 |
| 制裁強度 | 25% | 米国・EU制裁による航行制限・保険問題 |
| 海上事案 | 25% | 拿捕・妨害・臨検の発生頻度 |
| 原油価格ボラティリティ | 20% | WTI/Brent価格の急変動 |

### 出力ファイル

```
data/
├── iran_risk_base_20260509_120000.json   # JSON形式
└── iran_risk_base_20260509_120000.csv    # CSV形式（Excel対応・BOM付き）
```

### スコアのカスタマイズ

`iran_logistics_risk.py` 内の `get_scenario()` 関数を直接編集するか、
将来的にはAPIや手動入力フォームから動的に更新する予定。

---

## 今後追加予定のスクリプト

| ファイル名 | 内容 |
|-----------|------|
| `fetch_oil_price.py` | EIA/Alpha Vantage から原油価格を自動取得 |
| `gdelt_iran_events.py` | GDELT APIからイラン関連イベントデータを取得 |
| `daily_report_gen.py` | 毎朝の分析レポートを自動生成してreports/に保存 |
