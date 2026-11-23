"""Single-file offline HTML dashboard: national, Admin1 and Admin2 views."""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import numpy as np
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

from .charts import CODE_COLORS
from .thresholds import MEASURES, STATUS

CSS = """
.viz-root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--line:#e6e5e1;--tile:#f3f2ef;
--cases:#2a78d6;--band:#e6e5e1;color-scheme:light}
@media (prefers-color-scheme: dark){.viz-root{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;
--line:#383835;--tile:#242422;--cases:#3987e5;--band:#383835;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.viz-root{background:var(--surface);color:var(--ink);min-height:100vh;padding:24px 32px}
h1{font-size:24px;margin:0}h2{font-size:17px;margin:26px 0 10px}.sub{color:var(--ink2);margin:4px 0 0}
.banner{margin:16px 0;padding:12px 16px;border-radius:8px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}
.kpi{background:var(--tile);border-radius:8px;padding:14px}.kpi b{font-size:26px;display:block}.kpi span{color:var(--ink2);font-size:13px}
.row{display:grid;grid-template-columns:minmax(0,0.9fr) minmax(0,1.1fr);gap:24px;align-items:start}
select{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink);margin-right:8px}
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
.heat{border-collapse:separate;border-spacing:1px;font-size:10px;width:auto}.heat td{padding:0;width:16px;height:14px;border:none;text-align:center;color:#0b0b0b}
.heat td.name{width:auto;padding-right:8px;color:var(--ink2);white-space:nowrap;text-align:left;font-size:11px}.heat th{font-size:10px;padding:0 0 2px;color:var(--muted);font-weight:400;text-align:center}
.scroll{overflow:auto}.note{color:var(--muted);font-size:12px;margin-top:24px;line-height:1.5}
#chart text{fill:var(--ink2);font-size:11px}#chart .grid{stroke:var(--line)}
@media (max-width:900px){.row{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}}
"""

JS = """
const D=JSON.parse(document.getElementById('data').textContent);
const lv=document.getElementById('level'),un=document.getElementById('unit'),tip=document.getElementById('tip');
const SL={N:'Normal',A:'Alert',E:'Epidemic',NA:'Not reported'};
function fill(){un.innerHTML=Object.keys(D.units[lv.value]).sort().map(u=>`<option>${u}</option>`).join('')}
function line(pts,sx,sy){return pts.filter(p=>p[1]!=null).map((p,i)=>(i?'L':'M')+sx(p[0]).toFixed(1)+','+sy(p[1]).toFixed(1)).join('')}
function draw(){const d=D.units[lv.value][un.value];const W=640,H=300,L=58,R=12,T=12,B=32;
 const vals=[...d.cases,...d.max,...d.epi].filter(v=>v!=null);const ymax=Math.max(1,...vals)*1.08;
 const sx=w=>L+(w-1)/52*(W-L-R),sy=v=>T+(1-v/ymax)*(H-T-B);
 let s='';for(let i=0;i<=4;i++){const v=ymax*i/4,y=sy(v);s+=`<line class="grid" x1="${L}" x2="${W-R}" y1="${y}" y2="${y}"/><text x="${L-6}" y="${y+4}" text-anchor="end">${Math.round(v).toLocaleString()}</text>`}
 for(let w=1;w<=53;w+=4)s+=`<text x="${sx(w)}" y="${H-12}" text-anchor="middle">${w}</text>`;
 const wk=[...Array(53).keys()].map(i=>i+1);
 const up=wk.map((w,i)=>[w,d.max[i]]).filter(p=>p[1]!=null),lo=wk.map((w,i)=>[w,d.min[i]]).filter(p=>p[1]!=null).reverse();
 s+=`<path d="${line(up,sx,sy)}${line(lo,sx,sy).replace('M','L')}Z" fill="var(--band)"/>`;
 s+=`<line x1="${sx(D.week)}" x2="${sx(D.week)}" y1="${T}" y2="${H-B}" stroke="var(--muted)" stroke-dasharray="2 3"/>`;
 s+=`<path d="${line(wk.map((w,i)=>[w,d.alert[i]]),sx,sy)}" fill="none" stroke="#b77400" stroke-width="1.5" stroke-dasharray="5 3"/>`;
 s+=`<path d="${line(wk.map((w,i)=>[w,d.epi[i]]),sx,sy)}" fill="none" stroke="#d03b3b" stroke-width="1.8"/>`;
 s+=`<path d="${line(wk.map((w,i)=>[w,d.cases[i]]),sx,sy)}" fill="none" stroke="var(--cases)" stroke-width="2.2"/>`;
 d.cases.forEach((v,i)=>{if(v!=null){const c=d.code[i],col=c==='E'?'#d03b3b':c==='A'?'#b77400':'transparent';
  s+=`<circle cx="${sx(i+1)}" cy="${sy(v)}" r="${c==='E'||c==='A'?4:8}" fill="${col}" stroke="${col==='transparent'?'none':'var(--surface)'}" data-i="${i}"/>`}});
 const svg=document.getElementById('chart');svg.innerHTML=s;
 svg.querySelectorAll('circle').forEach(c=>{c.addEventListener('mousemove',e=>{const i=+c.dataset.i;
  tip.innerHTML=`<b>${un.value}</b>, week ${i+1}<br>Cases: ${d.cases[i].toLocaleString()}<br>Alert threshold: ${Math.round(d.alert[i]).toLocaleString()}<br>Epidemic threshold: ${Math.round(d.epi[i]).toLocaleString()}<br>Status: ${SL[d.code[i]]}`;
  tip.style.display='block';tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px'});
  c.addEventListener('mouseleave',()=>tip.style.display='none')});
 document.getElementById('ctitle').textContent=`${un.value}: ${SL[d.code[D.week-1]]||'Not reported'} at week ${D.week}`;}
lv.addEventListener('change',()=>{fill();draw()});un.addEventListener('change',draw);
document.querySelectorAll('path.d').forEach(p=>{p.addEventListener('click',()=>{lv.value='district';fill();un.value=p.dataset.d;draw()});
 p.addEventListener('mousemove',e=>{const d=D.units.district[p.dataset.d];tip.innerHTML=`<b>${p.dataset.d}</b> · ${d.region}<br>Week ${D.week}: ${SL[d.code[D.week-1]]}<br>Click to see the curve`;
 tip.style.display='block';tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px'});
 p.addEventListener('mouseleave',()=>tip.style.display='none')});
fill();un.value='National';draw();
"""


def _svg_map(geometry: dict, codes: dict, region_of: dict, width=520) -> str:
    b = np.array([g.bounds for g in geometry.values()])
    minx, miny, maxx, maxy = b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()
    k = width / (maxx - minx)

    def path(geom):
        polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
        return "".join("M" + "L".join(f"{(x - minx) * k:.1f},{(maxy - y) * k:.1f}"
                                      for x, y in p.exterior.coords) + "Z" for p in polys)

    parts = [f'<path class="d" data-d="{html.escape(d)}" fill="{CODE_COLORS[codes.get(d, "NA")]}" '
             f'd="{path(g)}"/>' for d, g in geometry.items()]
    for r in sorted(set(region_of.values())):
        parts.append(f'<path class="r" d="{path(unary_union([g for d, g in geometry.items() if region_of.get(d) == r]))}"/>')
    return (f'<svg viewBox="0 0 {width} {(maxy - miny) * k:.0f}" width="100%" role="img" '
            f'aria-label="District status map">{"".join(parts)}</svg>')


def _num(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 1)


def build_dashboard(path: Path, r: dict) -> Path:
    week, year, alert, epi = r["last_week"], r["year"], r["alert"], r["epidemic"]
    units = {}
    for lv, st in r["status"].items():
        thr = r["thresholds"][lv]
        units[lv] = {}
        for u, g in thr.groupby("unit"):
            g = g.set_index("week").reindex(range(1, 54))
            s = st[st.unit == u].set_index("week").reindex(range(1, 54))
            units[lv][u] = {
                "region": r["region_of"].get(u, ""),
                "cases": [None if c == "NA" or c != c else _num(v) for v, c in zip(s.value, s.code, strict=True)],
                "code": [c if isinstance(c, str) else "" for c in s.code],
                "alert": [_num(v) for v in g[alert]], "epi": [_num(v) for v in g[epi]],
                "min": [_num(v) for v in g["min"]], "max": [_num(v) for v in g["max"]]}
    lt = r["latest"]
    codes = lt.set_index("unit").code.to_dict()
    nat_code = r["status"]["national"].query("week == @week").code.iloc[0]
    banner_col = CODE_COLORS[nat_code]
    n_e, n_a = int((lt.code == "E").sum()), int((lt.code == "A").sum())
    pct = r["share"].set_index("week").pct_above_alert.get(week, np.nan)
    tiles = [(STATUS[nat_code], "national status"), (n_e, "districts in epidemic"),
             (n_a, "districts on alert"),
             (f"{pct:.0f}%", f"districts above alert (critical {r['critical_pct']}%)")]
    kpis = "".join(f'<div class="kpi"><b>{v}</b><span>{lab}</span></div>' for v, lab in tiles)
    flagged = lt[lt.code.isin(["E", "A"])]
    rows = "".join(
        f"<tr><td><span class='badge' style='background:{CODE_COLORS[x.code]}'>{STATUS[x.code]}</span></td>"
        f"<td>{html.escape(x.unit)}</td><td>{html.escape(x.region)}</td><td class='n'>{x.value:,.0f}</td>"
        f"<td class='n'>{x.alert_threshold:,.0f}</td><td class='n'>{x.epidemic_threshold:,.0f}</td>"
        f"<td class='n'>{x.ratio:.2f}</td><td class='n'>{x.weeks_a_or_e}</td></tr>"
        for x in flagged.itertuples())
    sd = r["status"]["district"]
    order = lt.sort_values(["region", "unit"])
    weeks = list(range(1, week + 1))
    head = "<tr><th></th>" + "".join(f"<th>{w if w % 4 == 1 or w == week else ''}</th>" for w in weeks) + "</tr>"
    body = []
    for x in order.itertuples():
        st = sd[sd.unit == x.unit].set_index("week").code
        cells = "".join(f'<td title="Week {w}: {STATUS[st.get(w, "NA")]}" style="background:{CODE_COLORS[st.get(w, "NA")]}">'
                        f'{"" if st.get(w, "NA") in ("N", "NA") else st.get(w)}</td>' for w in weeks)
        body.append(f'<tr><td class="name">{html.escape(x.unit)}</td>{cells}</tr>')
    share_png = base64.b64encode(Path(r["charts"]["share"]).read_bytes()).decode()
    legend = "".join(f'<span><i style="background:{c}"></i>{k} = {STATUS[k]}</span>' for k, c in CODE_COLORS.items())
    chart_legend = (f'<span><i style="background:var(--band)"></i>Baseline range ({min(r["baseline_years"])}-{max(r["baseline_years"])})</span>'
                    f'<span><i class="l" style="background:#b77400"></i>Alert: {MEASURES[alert]}</span>'
                    f'<span><i class="l" style="background:#d03b3b"></i>Epidemic: {MEASURES[epi]}</span>'
                    f'<span><i class="l" style="background:var(--cases)"></i>{r["indicator"].capitalize()} {year}</span>')
    abn = ", ".join(map(str, r["abnormal_years"])) or "none"
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Malaria epidemic thresholds - {html.escape(r['country'])}</title>
<style>{CSS}</style></head><body><div class="viz-root">
<h1>Malaria epidemic thresholds - {html.escape(r['country'])}</h1>
<p class="sub">Malaria {r['indicator']} · week {week} of {year} · baseline years {', '.join(map(str, r['baseline_years']))}
(abnormal years excluded: {abn}) · generated {r['generated']} · synthetic demonstration data</p>
<div class="banner" style="background:{banner_col};color:#0b0b0b">{html.escape(r['headline'])}</div>
<div class="kpis">{kpis}</div>
<div class="row"><div><h2>District status, week {week}</h2>{_svg_map(r['geometry'], codes, r['region_of'])}
<div class="legend">{legend}</div><p class="sub">Click a district to show its curve.</p></div>
<div><h2 id="ctitle"></h2><select id="level" aria-label="Level"><option value="national">National</option>
<option value="region">Admin1 (region)</option><option value="district">Admin2 (district)</option></select>
<select id="unit" aria-label="Unit"></select>
<svg id="chart" viewBox="0 0 640 300" width="100%" role="img" aria-label="Weekly cases and thresholds"></svg>
<div class="legend">{chart_legend}</div></div></div>
<h2>Districts in epidemic or alert at week {week} ({len(flagged)})</h2>
<table><thead><tr><th>Status</th><th>District</th><th>Region</th><th>Cases</th><th>Alert threshold</th>
<th>Epidemic threshold</th><th>Cases / epidemic threshold</th><th>Weeks A or E this year</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Weekly summary, all districts</h2><div class="scroll"><table class="heat">{head}{''.join(body)}</table></div>
<div class="legend">{legend}</div>
<h2>Share of districts above their alert threshold</h2><img style="max-width:100%;border-radius:8px" alt="Share of districts above alert" src="data:image/png;base64,{share_png}">
<p class="note">Each week of {year} is compared with the same week of the baseline years: {MEASURES[alert]} = alert threshold,
{MEASURES[epi]} = epidemic threshold. Zero values are treated as not reported. All figures are synthetic.</p>
<div id="tip"></div></div><script type="application/json" id="data">{json.dumps({"units": units, "week": week})}</script>
<script>{JS}</script></body></html>"""
    path.write_text(page, encoding="utf-8")
    return path
