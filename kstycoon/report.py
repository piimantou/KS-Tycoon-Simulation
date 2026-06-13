"""Render the handoff report — the one artifact that crosses into the tactical
Kriegsspiel. Plain Markdown so it can be pasted anywhere (Discord, a doc, etc.).
"""

from __future__ import annotations

from .resolve import TickResult


def render(res: TickResult) -> str:
    s = res.state
    L: list[str] = []
    L.append(f"# {s.nation} — End of FY{s.year - 1} → FY{s.year}")
    L.append("")

    g = s.government
    L.append("## Economy")
    L.append(f"- GDP: ${s.gdp:,.0f}  (per capita ${s.gdp / s.manpower.population:,.0f})")
    L.append(f"- Stability: {s.stability:.2f}")
    L.append(f"- Treasury: ${g.treasury:,.0f}   Debt: ${g.debt:,.0f}")
    L.append("")

    L.append("## Public finance")
    L.append(f"- Tax revenue (income tax {g.income_tax_rate:.0%}): ${g.revenue:,.0f}")
    L.append(f"- Civilian budget ({g.civilian_share:.0%}): ${g.civilian_budget:,.0f}")
    L.append(f"- Defense budget ({g.defense_share:.0%}): ${g.defense_budget:,.0f}")
    L.append("")

    L.append("## Population")
    L.append("| Stratum | Size | Income/capita | SoL | Loyalty |")
    L.append("|---|--:|--:|--:|--:|")
    for p in s.pops.values():
        pc = p.income / p.size if p.size else 0.0
        L.append(
            f"| {p.name} | {p.size:,.0f} | ${pc:,.0f} | {p.sol:.2f} | {p.loyalty:.2f} |"
        )
    L.append("")
    L.append("| Good | Price | Base | Supply |")
    L.append("|---|--:|--:|--:|")
    for gid, g in s.goods.items():
        L.append(
            f"| {g.name} | {g.price:,.2f} | {g.base_price:,.2f} "
            f"| {res.sector_output.get(gid, 0.0):,.0f} |"
        )
    L.append("")

    L.append("## Budget this year")
    L.append(f"- Project (development) spend: ${res.project_cost:,.0f}")
    L.append(f"- Procurement spend: ${res.procurement_cost:,.0f}")
    L.append(f"- Personnel (wages): ${res.personnel_cost:,.0f}")
    L.append("")

    L.append("## Manpower")
    L.append(f"- Callable pool (readiness {s.manpower.readiness}): {res.manpower_available:,.0f}")
    L.append(f"- Manning operational forces: {res.manpower_operational:,.0f}")
    L.append("")

    L.append("## Procurement delivered")
    if res.delivered:
        L.append("| Token | Domestic | Import | Cost |")
        L.append("|---|--:|--:|--:|")
        for tid, rec in res.delivered.items():
            name = s.units[tid].name if tid in s.units else tid
            L.append(
                f"| {name} | {rec['domestic']} | {rec['import']} | ${rec['cost']:,.0f} |"
            )
    else:
        L.append("_No procurement orders this year._")
    L.append("")

    L.append("## Force handoff → tactical layer")
    L.append("| Token | Operational | In training | Men/token | Upkeep |")
    L.append("|---|--:|--:|--:|--:|")
    keys = set(res.operational_tokens) | set(res.training_tokens)
    for tid in keys:
        u = s.units.get(tid)
        name = u.name if u else tid
        L.append(
            f"| {name} | {res.operational_tokens.get(tid, 0)} "
            f"| {res.training_tokens.get(tid, 0)} "
            f"| {u.men_per_token if u else '?'} "
            f"| {u.maintenance_tokens if u else '?'} |"
        )
    L.append(f"\nTotal maintenance load: {res.maintenance_load:,.1f} tokens")
    L.append("")

    if res.warnings:
        L.append("## Umpire notes / warnings")
        for warn in res.warnings:
            L.append(f"- {warn}")
        L.append("")
    return "\n".join(L)
