# Three-Panel Macro Monitor Design Logic

Date: 2026-05-26
Source: User conversation — Alpha-FICC Comparison workspace layout inference

## Panel Structure

| Panel | Content | Series |
|-------|---------|--------|
| 1 — 利率曲线 | 长端(10Y) + 短端(2Y) + 利差(T10Y2Y) | DGS10, DGS2, T10Y2Y |
| 2 — 多资产波动率 | 权益(VIX) / 科技(VXN) / 原油(OVX) / 黄金(GVZ) | VIXCLS, VXNCLS, OVXCLS, GVZCLS |
| 3 — 债市波动率 | MOVE 指数 | ^MOVE (yfinance) |

## Logical Chain (design intent inference)

The three panels form a risk transmission monitoring framework:

```
Panel 1 (利率方向/斜率)            ← 驱动力
    ↓
Panel 3 (MOVE: 债市是否stress)     ← 传导层
    ↓              ↘
    ↓         Panel 2 中 OVX(油价波动独立走高?)
    ↓              →
Panel 2 中 VIX(风险偏好是否受影响)  ← 终端效果
```

### What This Monitors

The design is looking for **disconnects** in the risk transmission chain:

- **利率上行 + MOVE同步升** → 债市正在stress
- **MOVE升 + VIX不动** → 债市波动尚未溢出到风险资产（链条断裂）
- **OVX极高 + VIX极低** → 原油和权益在定价不同风险（最值得关注的背离信号）
- **所有波动率同步升** → 广泛的风险规避（系统性事件）

### Current State (2026-05-26)

The transmission chain is broken: MOVE and OVX are elevated while VIX is low. The most anomalous signal is the OVX(75.97) / VIX(16.59) divergence.
