"""Single-file offline HTML dashboard for weekly epidemic monitoring."""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

from .charts import METHOD_LABEL, STATUS_COLORS

CSS = """
.viz-root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--line:#e6e5e1;--tile:#f3f2ef;
--cases:#2a78d6;--band:#e6e5e1;color-scheme:light}
@media (prefers-color-scheme: dark){.viz-root{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;
--line:#383835;--tile:#242422;--cases:#3987e5;--band:#383835;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.viz-root{background:var(--surface);color:var(--ink);min-height:100vh;padding:24px 32px}
h1{font-size:24px;margin:0}h2{font-size:17px;margin:26px 0 10px}.sub{color:var(--ink2);margin:4px 0 0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}
.kpi{background:var(--tile);border-radius:8px;padding:14px}.kpi b{font-size:28px;display:block}.kpi span{color:var(--ink2);font-size:13px}
.row{display:grid;grid-template-columns:minmax(0,0.9fr) minmax(0,1.1fr);gap:24px;align-items:start}
select{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink)}
svg path.d{stroke:var(--surface);stroke-width:1;cursor:pointer}svg path.d:hover{stroke:var(--ink);stroke-width:2}
svg path.r{fill:none;stroke:var(--ink);stroke-width:1.6;pointer-events:none}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--ink2);margin-top:6px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.legend i.l{height:3px;border-radius:2px;vertical-align:3px;width:16px}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);padding:8px 10px;border-radius:6px;
font-size:13px;display:none;line-height:1.4;z-index:5}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--ink2);font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;color:#0b0b0b}
.heat{border-collapse:separate;border-spacing:1px;font-size:11px;width:auto}.heat td{padding:0;width:14px;height:13px;border:none}
.heat td.name{width:auto;padding-right:8px;color:var(--ink2);white-space:nowrap}.heat th{font-size:10px;padding:0 0 2px;color:var(--muted);font-weight:400;text-align:center}
.scroll{overflow:auto}.note{color:var(--muted);font-size:12px;margin-top:24px}
#chart text{fill:var(--ink2);font-size:11px}#chart .grid{stroke:var(--line)}
@media (max-width:900px){.row{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}}
"""

JS = """
const D=JSON.parse(document.getElementById('data').textContent);
const sel=document.getElementById('dist'),tip=document.getElementById('tip');
function line(pts,sx,sy){return pts.filter(p=>p[1]!=null).map((p,i)=>(i?'L':'M')+sx(p[0]).toFixed(1)+','+sy(p[1]).toFixed(1)).join('')}
function draw(){const d=D.dist[sel.value];const W=640,H=300,L=52,R=12,T=12,B=32;
 const vals=[...d.cases,...d.max,...d.epi].filter(v=>v!=null);const ymax=Math.max(1,...vals)*1.08;
 const sx=w=>L+(w-1)/52*(W-L-R),sy=v=>T+(1-v/ymax)*(H-T-B);
 let s='';for(let i=0;i<=4;i++){const v=ymax*i/4,y=sy(v);s+=`<line class="grid" x1="${L}" x2="${W-R}" y1="${y}" y2="${y}"/><text x="${L-6}" y="${y+4}" text-anchor="end">${Math.round(v).toLocaleString()}</text>`}
 for(let w=1;w<=53;w+=4)s+=`<text x="${sx(w)}" y="${H-12}" text-anchor="middle">${w}</text>`;
 const wk=[...Array(53).keys()].map(i=>i+1);
 const up=wk.map((w,i)=>[w,d.max[i]]).filter(p=>p[1]!=null),lo=wk.map((w,i)=>[w,d.min[i]]).filter(p=>p[1]!=null).reverse();
 s+=`<path d="${line(up,sx,sy)}${line(lo,sx,sy).replace('M','L')}Z" fill="var(--band)"/>`;
 s+=`<path d="${line(wk.map((w,i)=>[w,d.alert[i]]),sx,sy)}" fill="none" stroke="#b77400" stroke-width="1.5" stroke-dasharray="5 3"/>`;
 s+=`<path d="${line(wk.map((w,i)=>[w,d.epi[i]]),sx,sy)}" fill="none" stroke="#d03b3b" stroke-width="1.8"/>`;
 s+=`<path d="${line(wk.map((w,i)=>[w,d.cases[i]]),sx,sy)}" fill="none" stroke="var(--cases)" stroke-width="2.2"/>`;
 d.cases.forEach((v,i)=>{if(v!=null){const st=d.status[i];
  s+=`<circle cx="${sx(i+1)}" cy="${sy(v)}" r="${st==='Epidemic'?4:9}" fill="${st==='Epidemic'?'#d03b3b':'transparent'}" stroke="${st==='Epidemic'?'var(--surface)':'none'}" data-i="${i}"/>`}});
 const svg=document.getElementById('chart');svg.innerHTML=s;
 svg.querySelectorAll('circle').forEach(c=>{c.addEventListener('mousemove',e=>{const i=+c.dataset.i;
  tip.innerHTML=`<b>${sel.value}</b>, week ${i+1}<br>Cases: ${d.cases[i].toLocaleString()}<br>Alert threshold: ${Math.round(d.alert[i]).toLocaleString()}<br>Epidemic threshold: ${Math.round(d.epi[i]).toLocaleString()}<br>Status: ${d.status[i]}`;
  tip.style.display='block';tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px'});
  c.addEventListener('mouseleave',()=>tip.style.display='none')});
 document.getElementById('ctitle').textContent=sel.value+' ('+d.region+'): '+d.latest;}
sel.addEventListener('change',draw);
document.querySelectorAll('path.d').forEach(p=>{p.addEventListener('click',()=>{sel.value=p.dataset.d;draw()});
 p.addEventListener('mousemove',e=>{const d=D.dist[p.dataset.d];tip.innerHTML=`<b>${p.dataset.d}</b> · ${d.region}<br>Status: ${d.latest}<br>Click to see the curve`;
 tip.style.display='block';tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px'});
 p.addEventListener('mouseleave',()=>tip.style.display='none')});
draw();
"""


def _svg_map(geometry: dict, summary: pd.DataFrame, width=520) -> str:
    st = summary.set_index("district").status
    b = np.array([g.bounds for g in geometry.values()])
    minx, miny, maxx, maxy = b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()
    k = width / (maxx - minx)

    def path(geom):
        polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
        return "".join("M" + "L".join(f"{(x - minx) * k:.1f},{(maxy - y) * k:.1f}"
                                      for x, y in p.exterior.coords) + "Z" for p in polys)

    parts = [f'<path class="d" data-d="{html.escape(d)}" fill="{STATUS_COLORS[st.get(d, "No data")]}" '
             f'd="{path(g)}"/>' for d, g in geometry.items()]
    for _, g in summary.groupby("region"):
        parts.append(f'<path class="r" d="{path(unary_union([geometry[x] for x in g.district]))}"/>')
    return (f'<svg viewBox="0 0 {width} {(maxy - miny) * k:.0f}" width="100%" role="img" '
            f'aria-label="District status map">{"".join(parts)}</svg>')


def _clean(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 1)


def build_dashboard(path: Path, ctx: dict) -> Path:
    s, st, thr = ctx["summary"], ctx["status"], ctx["thresholds"]
    alert, epi = ctx["alert_method"], ctx["epidemic_method"]
    data = {}
    for d, g in thr.groupby("district"):
        g = g.set_index("week").reindex(range(1, 54))
        c = st[st.district == d].set_index("week").reindex(range(1, 54))
        data[d] = {"region": s.set_index("district").region[d],
                   "latest": s.set_index("district").status[d],
                   "cases": [_clean(v) for v in c.value], "status": list(c.status.fillna("")),
                   "alert": [_clean(v) for v in g[alert]], "epi": [_clean(v) for v in g[epi]],
                   "min": [_clean(v) for v in g["min"]], "max": [_clean(v) for v in g["max"]]}
    first = s.district.iloc[0]
    opts = "".join(f'<option{" selected" if d == first else ""}>{html.escape(d)}</option>'
                   for d in sorted(data))
    order = s.sort_values(["region", "district"])
    weeks = list(range(1, ctx["last_week"] + 1))
    heat_head = "<tr><th></th>" + "".join(f"<th>{w if w % 4 == 1 else ''}</th>" for w in weeks) + "</tr>"
    heat_rows = []
    for r in order.itertuples():
        stat = st[st.district == r.district].set_index("week").status
        cells = "".join(f'<td title="Week {w}: {stat.get(w, "No data")}" '
                        f'style="background:{STATUS_COLORS.get(stat.get(w, "No data"))}"></td>'
                        for w in weeks)
        heat_rows.append(f'<tr><td class="name">{html.escape(r.district)}</td>{cells}</tr>')
    flagged = s[s.status.isin(["Epidemic", "Alert"])]
    alert_rows = "".join(
        f"<tr><td><span class='badge' style='background:{STATUS_COLORS[r.status]}'>{r.status}</span></td>"
        f"<td>{html.escape(r.district)}</td><td>{html.escape(r.region)}</td>"
        f"<td class='n'>{r.cases_latest_week:,.0f}</td><td class='n'>{r.epidemic_threshold:,.0f}</td>"
        f"<td class='n'>{'' if pd.isna(r.episode_start_week) else int(r.episode_start_week)}</td>"
        f"<td class='n'>{r.weeks_alert_or_epidemic}</td></tr>" for r in flagged.itertuples())
    k = ctx["kpis"]
    tiles = [(k["epidemic"], "districts in epidemic"), (k["alert"], "districts on alert"),
             (f"{k['cases_4w']:,.0f}", f"cases, weeks {ctx['last_week'] - 3}-{ctx['last_week']}"),
             (f"{k['completeness']:.0f}%", "reporting completeness")]
    kpis = "".join(f'<div class="kpi"><b>{v}</b><span>{lab}</span></div>' for v, lab in tiles)
    nat = base64.b64encode(Path(ctx["charts"]["national"]).read_bytes()).decode()
    legend = ("".join(f'<span><i style="background:{c}"></i>{s_}</span>' for s_, c in STATUS_COLORS.items()))
    chart_legend = (f'<span><i style="background:var(--band)"></i>Baseline range</span>'
                    f'<span><i class="l" style="background:#b77400"></i>Alert: {METHOD_LABEL[alert]}</span>'
                    f'<span><i class="l" style="background:#d03b3b"></i>Epidemic: {METHOD_LABEL[epi]}</span>'
                    f'<span><i class="l" style="background:var(--cases)"></i>Cases {ctx["year"]}</span>')
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Malaria epidemic thresholds - {html.escape(ctx['country'])}</title>
<style>{CSS}</style></head><body><div class="viz-root">
<h1>Malaria epidemic monitoring - {html.escape(ctx['country'])}</h1>
<p class="sub">Week {ctx['last_week']} of {ctx['year']} · baseline {ctx['baseline_label']} · generated {ctx['generated']} · synthetic demonstration data</p>
<div class="kpis">{kpis}</div>
<div class="row"><div><h2>Status at week {ctx['last_week']}</h2>{_svg_map(ctx['geometry'], s)}
<div class="legend">{legend}</div><p class="sub">Click a district to show its curve.</p></div>
<div><h2 id="ctitle"></h2><label for="dist">District </label><select id="dist">{opts}</select>
<svg id="chart" viewBox="0 0 640 300" width="100%" role="img" aria-label="District weekly cases and thresholds"></svg>
<div class="legend">{chart_legend}</div></div></div>
<h2>Districts in alert or epidemic ({len(flagged)})</h2>
<table><thead><tr><th>Status</th><th>District</th><th>Region</th><th>Cases, week {ctx['last_week']}</th>
<th>Epidemic threshold</th><th>Above alert since week</th><th>Weeks above alert</th></tr></thead><tbody>{alert_rows}</tbody></table>
<h2>Weekly status, all districts</h2><div class="scroll"><table class="heat">{heat_head}{''.join(heat_rows)}</table></div>
<div class="legend">{legend}</div>
<h2>National trend</h2><img style="max-width:100%;border-radius:8px" alt="National weekly cases" src="data:image/png;base64,{nat}">
<p class="note">Alert threshold: {METHOD_LABEL[alert]}. Epidemic: cases above the {METHOD_LABEL[epi]} threshold for
{ctx['consecutive']} consecutive weeks. Past epidemic years are excluded from the baseline. All figures are synthetic.</p>
<div id="tip"></div></div><script type="application/json" id="data">{json.dumps({"dist": data})}</script>
<script>{JS}</script></body></html>"""
    path.write_text(page, encoding="utf-8")
    return path
