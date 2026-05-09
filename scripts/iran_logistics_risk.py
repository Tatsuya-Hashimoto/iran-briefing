"""
Iran Logistics Risk Analyzer - Basic Edition
イラン関連物流リスク分析スクリプト（基本版）

Usage:
    python iran_logistics_risk.py
    python iran_logistics_risk.py --format csv
    python iran_logistics_risk.py --format both
    python iran_logistics_risk.py --output-dir ../data --scenario worst
"""

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── 定数 ──────────────────────────────────────────────────────────────────────

RISK_LEVELS: List[Tuple[float, float, str, str]] = [
    (0,  30,  "LOW",      "低リスク（通常運航可）"),
    (30, 60,  "MEDIUM",   "中リスク（要注意・追加保険推奨）"),
    (60, 80,  "HIGH",     "高リスク（迂回ルート検討）"),
    (80, 100, "CRITICAL", "危機的（運航停止レベル）"),
]

# ホルムズ海峡リスク因子の重み付け
HORMUZ_FACTORS: Dict[str, Dict] = {
    "military_activity": {
        "label": "軍事活動・作戦行動",
        "weight": 0.30,
        "description": "攻撃・封鎖・機雷敷設等のリスク",
    },
    "sanctions_intensity": {
        "label": "制裁強度",
        "weight": 0.25,
        "description": "米国・EU制裁による航行制限・保険問題",
    },
    "shipping_incidents": {
        "label": "海上事案",
        "weight": 0.25,
        "description": "拿捕・妨害・臨検の発生頻度",
    },
    "oil_price_volatility": {
        "label": "原油価格ボラティリティ",
        "weight": 0.20,
        "description": "WTI/Brent価格の急変動（30日σ）",
    },
}

# 地域別ベースラインリスク（平時比）
REGION_BASELINE: Dict[str, float] = {
    "ホルムズ海峡":   0,  # 0–100 で入力
    "ペルシャ湾":     0,
    "オマーン湾":     0,
    "アラビア海":     0,
    "紅海・バブエルマンデブ海峡": 0,
}

# 原油価格と輸送コスト増加の相関係数（簡易モデル）
OIL_COST_CORRELATION = 0.72   # 実績値の近似
BASE_OIL_PRICE_USD  = 75.0    # 基準原油価格（WTI $/bbl）
BASE_FREIGHT_RATE   = 30000   # 基準傭船料（$/day, VLCC想定）


# ── データクラス ───────────────────────────────────────────────────────────────

@dataclass
class RiskFactor:
    name: str
    label: str
    score: float          # 0–10
    weight: float
    weighted_score: float = field(init=False)
    description: str = ""

    def __post_init__(self):
        self.weighted_score = round(self.score * self.weight * 10, 2)


@dataclass
class RegionRisk:
    region: str
    base_score: float           # 0–100
    hormuz_multiplier: float    # ホルムズ情勢による増幅係数
    final_score: float = field(init=False)
    level: str = field(init=False)
    level_description: str = field(init=False)

    def __post_init__(self):
        self.final_score = round(min(self.base_score * self.hormuz_multiplier, 100), 1)
        self.level, self.level_description = classify_level(self.final_score)


@dataclass
class TransportCostImpact:
    oil_price_usd: float
    price_change_pct: float         # 基準比 %変化
    freight_rate_usd_per_day: float
    freight_change_pct: float
    war_risk_premium_pct: float     # 戦争リスク割増保険料（対船価%）
    total_cost_index: float         # 総コスト指数（基準=100）


@dataclass
class AnalysisResult:
    timestamp: str
    scenario: str
    hormuz_risk_score: float
    hormuz_risk_level: str
    hormuz_risk_description: str
    risk_factors: List[Dict]
    region_risks: List[Dict]
    transport_cost: Dict
    mitigation: List[str]
    summary: str


# ── 計算関数 ───────────────────────────────────────────────────────────────────

def classify_level(score: float) -> Tuple[str, str]:
    for lo, hi, level, desc in RISK_LEVELS:
        if lo <= score < hi:
            return level, desc
    return "CRITICAL", RISK_LEVELS[-1][3]


def calc_hormuz_risk_score(factor_scores: Dict[str, float]) -> Tuple[float, List[RiskFactor]]:
    """因子スコア（各0–10）からホルムズ海峡総合リスクスコア（0–100）を算出"""
    factors = []
    for name, cfg in HORMUZ_FACTORS.items():
        score = factor_scores.get(name, 0.0)
        factors.append(RiskFactor(
            name=name,
            label=cfg["label"],
            score=score,
            weight=cfg["weight"],
            description=cfg["description"],
        ))
    total = sum(f.weighted_score for f in factors)
    return round(total, 1), factors


def calc_hormuz_multiplier(hormuz_score: float) -> float:
    """ホルムズリスクスコアから地域増幅係数を算出（1.0 = 変化なし）"""
    return round(1.0 + (hormuz_score / 100) * 1.5, 3)


def calc_transport_cost_impact(
    oil_price: float,
    war_risk_premium: float,
) -> TransportCostImpact:
    """原油価格と戦争リスク保険料から輸送コスト影響を算出"""
    price_change_pct = (oil_price - BASE_OIL_PRICE_USD) / BASE_OIL_PRICE_USD * 100
    freight_change_pct = price_change_pct * OIL_COST_CORRELATION
    freight_rate = BASE_FREIGHT_RATE * (1 + freight_change_pct / 100)

    # 総コスト指数：傭船料 + 燃料 + 戦争リスク保険
    total_cost_index = 100 + freight_change_pct * 0.5 + war_risk_premium * 200
    return TransportCostImpact(
        oil_price_usd=round(oil_price, 1),
        price_change_pct=round(price_change_pct, 1),
        freight_rate_usd_per_day=round(freight_rate),
        freight_change_pct=round(freight_change_pct, 1),
        war_risk_premium_pct=round(war_risk_premium * 100, 3),
        total_cost_index=round(total_cost_index, 1),
    )


def build_region_risks(
    base_scores: Dict[str, float],
    multiplier: float,
) -> List[RegionRisk]:
    return [
        RegionRisk(region=region, base_score=score, hormuz_multiplier=multiplier)
        for region, score in base_scores.items()
    ]


def generate_mitigation(hormuz_score: float, level: str) -> List[str]:
    """リスクレベルに応じた対策アクションを返す"""
    actions = [
        "積荷保険の保険条件・除外事項を再確認する",
        "主要バイヤー・サプライヤーへのリスク状況を共有する",
    ]
    if hormuz_score >= 30:
        actions += [
            "喜望峰迂回ルートの費用・日程を試算する",
            "戦争リスク保険（War Risk Premium）の追加手配を検討する",
            "予備調達先（UAEまたは東南アジア経由）をリストアップする",
        ]
    if hormuz_score >= 60:
        actions += [
            "既存LCの延長・期限変更をバイヤーと事前協議する",
            "FOB条件から CIF/DAP への条件変更を検討する",
            "プラント納期への影響をエンドユーザーへ事前通知する",
        ]
    if hormuz_score >= 80:
        actions += [
            "ホルムズ経由貨物の出荷を一時停止し代替手配を優先する",
            "フォースマジュール条項の適用可否を法務確認する",
        ]
    return actions


def generate_summary(hormuz_score: float, level: str, cost: TransportCostImpact) -> str:
    return (
        f"ホルムズ海峡リスクスコア {hormuz_score}/100（{level}）。"
        f"輸送コストは基準比 {cost.total_cost_index - 100:+.1f}% の変動。"
        f"原油 {cost.oil_price_usd} $/bbl、傭船料 {cost.freight_rate_usd_per_day:,} $/day。"
    )


# ── シナリオ定義 ───────────────────────────────────────────────────────────────

def get_scenario(name: str) -> Dict:
    """
    シナリオ別の入力値を返す。
    実運用では API や手動入力でこの値を更新すること。
    """
    scenarios = {
        "base": {
            "label": "ベースケース（現状維持）",
            "factor_scores": {
                "military_activity":    6.5,
                "sanctions_intensity":  7.0,
                "shipping_incidents":   5.0,
                "oil_price_volatility": 5.5,
            },
            "region_base_scores": {
                "ホルムズ海峡":              65,
                "ペルシャ湾":               55,
                "オマーン湾":              50,
                "アラビア海":              35,
                "紅海・バブエルマンデブ海峡": 60,
            },
            "oil_price":         82.0,
            "war_risk_premium":  0.025,   # 船価に対する割合（2.5%）
        },
        "best": {
            "label": "ベストケース（停戦・緊張緩和）",
            "factor_scores": {
                "military_activity":    2.0,
                "sanctions_intensity":  4.0,
                "shipping_incidents":   1.5,
                "oil_price_volatility": 2.0,
            },
            "region_base_scores": {
                "ホルムズ海峡":              20,
                "ペルシャ湾":               18,
                "オマーン湾":              15,
                "アラビア海":              12,
                "紅海・バブエルマンデブ海峡": 25,
            },
            "oil_price":         68.0,
            "war_risk_premium":  0.005,
        },
        "worst": {
            "label": "ワーストケース（海峡封鎖・全面衝突）",
            "factor_scores": {
                "military_activity":    9.5,
                "sanctions_intensity":  9.0,
                "shipping_incidents":   9.0,
                "oil_price_volatility": 8.5,
            },
            "region_base_scores": {
                "ホルムズ海峡":              95,
                "ペルシャ湾":               88,
                "オマーン湾":              80,
                "アラビア海":              60,
                "紅海・バブエルマンデブ海峡": 75,
            },
            "oil_price":         130.0,
            "war_risk_premium":  0.075,
        },
    }
    if name not in scenarios:
        raise ValueError(f"シナリオ名が不正です。有効値: {list(scenarios.keys())}")
    return scenarios[name]


# ── 出力関数 ───────────────────────────────────────────────────────────────────

def export_json(result: AnalysisResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"iran_risk_{result.scenario}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2)
    return path


def export_csv(result: AnalysisResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"iran_risk_{result.scenario}_{ts}.csv"

    rows = []
    # ホルムズ海峡総合
    rows.append({
        "category":      "ホルムズ海峡総合",
        "item":          "総合リスクスコア",
        "score":         result.hormuz_risk_score,
        "level":         result.hormuz_risk_level,
        "description":   result.hormuz_risk_description,
    })
    # 因子別
    for f in result.risk_factors:
        rows.append({
            "category":    "リスク因子",
            "item":        f["label"],
            "score":       f["weighted_score"],
            "level":       f"生スコア={f['score']}",
            "description": f["description"],
        })
    # 地域別
    for r in result.region_risks:
        rows.append({
            "category":    "地域リスク",
            "item":        r["region"],
            "score":       r["final_score"],
            "level":       r["level"],
            "description": r["level_description"],
        })

    fieldnames = ["category", "item", "score", "level", "description"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def print_report(result: AnalysisResult) -> None:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  イラン物流リスク分析レポート")
    print(f"  生成日時: {result.timestamp}")
    print(f"  シナリオ: {result.scenario}")
    print(sep)

    print(f"\n【ホルムズ海峡 総合リスクスコア】")
    print(f"  {result.hormuz_risk_score} / 100  →  {result.hormuz_risk_level}")
    print(f"  {result.hormuz_risk_description}")

    print(f"\n【リスク因子別スコア】")
    for f in result.risk_factors:
        bar = "█" * int(f["score"])
        print(f"  {f['label']:<28} {bar:<10} {f['score']:>4.1f}/10  (加重: {f['weighted_score']})")

    print(f"\n【地域別リスク】")
    for r in result.region_risks:
        bar = "█" * int(r["final_score"] / 10)
        print(f"  {r['region']:<30} {bar:<10} {r['final_score']:>5.1f}  [{r['level']}]")

    tc = result.transport_cost
    print(f"\n【輸送コスト影響】")
    print(f"  原油価格:         {tc['oil_price_usd']} $/bbl  ({tc['price_change_pct']:+.1f}%)")
    print(f"  傭船料:           {tc['freight_rate_usd_per_day']:,} $/day  ({tc['freight_change_pct']:+.1f}%)")
    print(f"  戦争リスク保険料:  {tc['war_risk_premium_pct']:.3f}% (対船価)")
    print(f"  総コスト指数:      {tc['total_cost_index']}  (基準=100)")

    print(f"\n【推奨対策アクション】")
    for i, m in enumerate(result.mitigation, 1):
        print(f"  {i}. {m}")

    print(f"\n【サマリー】")
    print(f"  {result.summary}")
    print(f"\n{sep}\n")


# ── メイン ─────────────────────────────────────────────────────────────────────

def analyze(scenario_name: str) -> AnalysisResult:
    sc = get_scenario(scenario_name)

    hormuz_score, factors = calc_hormuz_risk_score(sc["factor_scores"])
    hormuz_level, hormuz_desc = classify_level(hormuz_score)
    multiplier = calc_hormuz_multiplier(hormuz_score)
    regions = build_region_risks(sc["region_base_scores"], multiplier)
    cost = calc_transport_cost_impact(sc["oil_price"], sc["war_risk_premium"])
    mitigation = generate_mitigation(hormuz_score, hormuz_level)
    summary = generate_summary(hormuz_score, hormuz_level, cost)

    return AnalysisResult(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        scenario=f"{scenario_name} — {sc['label']}",
        hormuz_risk_score=hormuz_score,
        hormuz_risk_level=hormuz_level,
        hormuz_risk_description=hormuz_desc,
        risk_factors=[asdict(f) for f in factors],
        region_risks=[asdict(r) for r in regions],
        transport_cost=asdict(cost),
        mitigation=mitigation,
        summary=summary,
    )


def main():
    parser = argparse.ArgumentParser(
        description="イラン関連物流リスク分析スクリプト（基本版）"
    )
    parser.add_argument(
        "--scenario",
        choices=["base", "best", "worst"],
        default="base",
        help="分析シナリオ（default: base）",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "both"],
        default="json",
        help="出力フォーマット（default: json）",
    )
    parser.add_argument(
        "--output-dir",
        default="../data",
        help="出力先ディレクトリ（default: ../data）",
    )
    parser.add_argument(
        "--no-print",
        action="store_true",
        help="コンソール出力を抑制する",
    )
    args = parser.parse_args()

    result = analyze(args.scenario)
    output_dir = Path(args.output_dir)

    if not args.no_print:
        print_report(result)

    saved = []
    if args.format in ("json", "both"):
        p = export_json(result, output_dir)
        saved.append(str(p))
        print(f"JSON出力: {p}")
    if args.format in ("csv", "both"):
        p = export_csv(result, output_dir)
        saved.append(str(p))
        print(f"CSV出力:  {p}")

    return result


if __name__ == "__main__":
    main()
