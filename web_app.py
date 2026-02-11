from __future__ import annotations

import math
from flask import Flask, request, render_template_string, url_for, session

from cnc.formulas import (
    sfm_from_rpm, rpm_from_sfm,
    ipm_from_ipr, ipr_from_ipm,
    ipm_from_chipload, chipload_from_ipm
)
from cnc.data import (
    MATERIALS,
    INSERTS,
    MILL_MATERIALS,
    DRILL_MATERIALS,
    MACHINES,
    ALL_MATERIAL_NAMES
)


app = Flask(__name__)
app.secret_key = "change-me-to-any-random-string"


# ----------------------------
# Helpers
# ----------------------------
def to_float(s: str):
    s = (s or "").strip()
    if s == "":
        return None
    return float(s)

def to_int(s: str):
    s = (s or "").strip()
    if s == "":
        return None
    return int(s)

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def machine_list(machine_type: str) -> list[str]:
    # machine_type: "lathe" or "mill"
    return [k for k, v in MACHINES.items() if v.get("type") == machine_type]

def get_machine_maxload(machine_name: str, default_pct: int = 60) -> int:
    # shared across all ops for that machine
    key = f"maxload::{machine_name}"
    val = session.get(key, default_pct)
    try:
        val = int(val)
    except Exception:
        val = default_pct
    return int(clamp(val, 1, 100))

def set_machine_maxload(machine_name: str, pct: int):
    key = f"maxload::{machine_name}"
    session[key] = int(clamp(pct, 1, 100))

def compute_lathe_style(diameter_in: float, sfm_val, rpm_val, ipr_val, ipm_val):
    """
    Shared calc used by turning & drilling style math:
    returns (rpm, sfm, ipr, ipm) as floats
    """
    if rpm_val is None and sfm_val is None:
        raise ValueError("Enter either Target SFM or RPM.")
    if rpm_val is None:
        rpm_val = rpm_from_sfm(diameter_in, sfm_val)
    if sfm_val is None:
        sfm_val = sfm_from_rpm(diameter_in, rpm_val)

    if ipr_val is None and ipm_val is None:
        raise ValueError("Enter either IPR or IPM.")
    if ipm_val is None:
        ipm_val = ipm_from_ipr(ipr_val, rpm_val)
    if ipr_val is None:
        ipr_val = ipr_from_ipm(ipm_val, rpm_val)

    return rpm_val, sfm_val, ipr_val, ipm_val

def clamp_rpm_to_machine(machine: str, rpm_val: float, use_live_tool: bool) -> tuple[float, str | None]:
    spec = MACHINES.get(machine, {})
    if use_live_tool and spec.get("has_live_tool", False):
        max_rpm = float(spec.get("live_tool_max_rpm", 0) or 0)
        label = "Live Tool"
    else:
        max_rpm = float(spec.get("spindle_max_rpm", 0) or 0)
        label = "Spindle"

    if max_rpm > 0 and rpm_val > max_rpm:
        return max_rpm, f"{label} RPM limited to machine max ({max_rpm:.0f})."
    return rpm_val, None

def available_hp(machine: str, use_live_tool: bool) -> float:
    spec = MACHINES.get(machine, {})
    if use_live_tool and spec.get("has_live_tool", False):
        return float(spec.get("live_tool_hp", 0.0) or 0.0)
    return float(spec.get("spindle_hp", 0.0) or 0.0)

def drill_hp_required(material: str, drill_dia_in: float, ipm: float) -> float:
    """
    HP estimate for drilling:
      HP = unit_hp(material) * MRR
      MRR = area * feed_ipm
    Your DRILL_MATERIALS already contains unit_hp. :contentReference[oaicite:1]{index=1}
    """
    mat = DRILL_MATERIALS.get(material, {})
    unit = float(mat.get("unit_hp", 0.7))  # hp / (in^3/min), fallback
    area = math.pi * (drill_dia_in / 2.0) ** 2
    mrr = area * ipm  # in^3/min
    return unit * mrr

def suggest_drill_feed_for_hp_limit(material: str, drill_dia_in: float, rpm: float, hp_limit: float) -> tuple[float, float]:
    """
    Given an HP limit, suggest max IPR and IPM for drilling.
    Reverse of HP equation:
      hp_limit = unit_hp * area * ipm
      ipm = hp_limit / (unit_hp * area)
      ipr = ipm / rpm
    """
    mat = DRILL_MATERIALS.get(material, {})
    unit = float(mat.get("unit_hp", 0.7))
    area = math.pi * (drill_dia_in / 2.0) ** 2
    if unit <= 0 or area <= 0 or rpm <= 0:
        return (0.0, 0.0)
    ipm_max = hp_limit / (unit * area)
    ipr_max = ipm_max / rpm
    return (ipr_max, ipm_max)


# ----------------------------
# Templates
# ----------------------------
HOME_TEMPLATE = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shop CNC Calculator</title>
<style>
  body { font-family: Arial, sans-serif; margin:18px; }
  .card { max-width:720px; margin:0 auto; padding:18px; border:1px solid #ddd; border-radius:14px; }
  h1 { font-size:24px; margin:0 0 14px; }
  label { display:block; margin-top:12px; font-size:14px; }
  select, button {
    width:100%;
    padding:18px;
    font-size:20px;
    margin-top:8px;
    border-radius:12px;
    border:1px solid #ccc;
  }
  button { cursor:pointer; background:#f6f6f6; }
  .small { font-size:13px; color:#444; margin-top:10px; }
</style>

<script>
  // Operation options by machine type
  const OPS = {
    lathe: [
      { value: "turning",   label: "Turning (OD/ID)" },
      { value: "drilling",  label: "Drilling (Spindle)" },
      { value: "live_tool", label: "Live Tooling (Drilling/Milling)" }
    ],
    mill: [
      { value: "milling",   label: "Milling" },
      { value: "drilling",  label: "Drilling" }
    ]
  };

  function setOperations() {
    const machine = document.getElementById("machine_select").value;
    const opSel = document.getElementById("op_select");

    // Reset ops dropdown
    opSel.innerHTML = '<option value="">-- Select Operation --</option>';

    if (!machine || !OPS[machine]) {
      opSel.disabled = true;
      return;
    }

    OPS[machine].forEach(o => {
      const opt = document.createElement("option");
      opt.value = o.value;
      opt.textContent = o.label;
      opSel.appendChild(opt);
    });

    opSel.disabled = false;
  }

  function goToCalc() {
    const machine = document.getElementById("machine_select").value;
    const op = document.getElementById("op_select").value;

    if (!machine) { alert("Select Lathe or Mill."); return; }
    if (!op) { alert("Select an operation."); return; }

    // Route + querystring so the page can auto-select the section
    if (machine === "lathe") window.location = "{{ url_for('lathe') }}" + "?op=" + encodeURIComponent(op);
    if (machine === "mill")  window.location = "{{ url_for('mill') }}"  + "?op=" + encodeURIComponent(op);
  }
</script>
</head>

<body>
<div class="card">
  <h1>Shop CNC Calculator</h1>

  <label>Machine Type</label>
  <select id="machine_select" onchange="setOperations()">
    <option value="">-- Select --</option>
    <option value="lathe">Lathe</option>
    <option value="mill">Mill</option>
  </select>

  <label>Operation</label>
  <select id="op_select" disabled>
    <option value="">-- Select Operation --</option>
  </select>

  <button onclick="goToCalc()">Open</button>

  <div class="small">
    Tip: Bookmark Lathe/Mill pages on the shop PC.
  </div>
</div>
</body>
</html>
"""

LATHE_TEMPLATE = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lathe - Shop CNC Calculator</title>
<style>
  body { font-family: Arial, sans-serif; margin: 18px; }
  .topbar { max-width: 820px; margin: 0 auto 10px; display:flex; justify-content:space-between; align-items:center; }
  .topbar a { text-decoration:none; font-size: 14px; }
  .card { max-width: 820px; margin: 0 auto; padding: 18px; border: 1px solid #ddd; border-radius: 14px; }
  h1 { font-size: 22px; margin: 0 0 10px; }
  .tabs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
  .tab { padding:10px 12px; border:1px solid #ccc; border-radius:999px; text-decoration:none; color:#111; background:#f6f6f6; font-size:14px; }
  .tab.active { background:#111; color:#fff; border-color:#111; }
  label { display:block; margin-top: 12px; font-size: 14px; }
  input, select { width: 100%; padding: 14px; font-size: 18px; margin-top: 6px; border-radius: 10px; border: 1px solid #ccc; }
  button { width: 100%; padding: 16px; font-size: 18px; margin-top: 14px; border-radius: 12px; border: none; cursor: pointer; background:#f6f6f6; }
  .row { display:flex; gap: 12px; }
  .row > div { flex:1; }
  .out { margin-top: 14px; padding: 12px; border-radius: 12px; background:#f6f6f6; font-size: 18px; }
  .warn { margin-top: 10px; padding: 10px; border-radius: 12px; background:#fff6d6; border:1px solid #ffe08a; }
  .small { font-size: 13px; color:#444; margin-top: 8px; }
  .pill { display:inline-block; padding: 6px 10px; border-radius: 999px; background:#eee; font-size: 13px; margin-right: 6px; }
  .danger { background:#ffecec; border:1px solid #ffb3b3; }
</style>
</head>
<body>

<div class="topbar">
  <a href="{{ url_for('home') }}">← Home</a>
  <a href="{{ url_for('mill') }}">Go to Mill →</a>
</div>

<div class="card">
  <h1>Lathe Calculator</h1>

  <div class="tabs">
    <a class="tab {% if op=='turning' %}active{% endif %}" href="{{ url_for('lathe') }}?op=turning">Turning</a>
    <a class="tab {% if op=='drilling' %}active{% endif %}" href="{{ url_for('lathe') }}?op=drilling">Spindle Drilling</a>
    <a class="tab {% if op=='live_tool' %}active{% endif %}" href="{{ url_for('lathe') }}?op=live_tool">Live Tool Drilling</a>
  </div>

  <form method="post">
    <input type="hidden" name="op" value="{{ op }}">

    <div class="row">
      <div>
        <label>Machine</label>
        <select name="machine">
          {% for m in machines %}
            <option value="{{m}}" {% if m==machine %}selected{% endif %}>{{m}}</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label>Max Load % (shared for this machine)</label>
        <input name="max_load_pct" inputmode="numeric" value="{{ max_load_pct }}">
      </div>
    </div>

    {% if op == 'turning' %}
      <input type="hidden" name="mode" value="lathe_turning">

      <div class="row">
        <div>
          <label>Material</label>
          <select name="material">
            <option value="">-- Select --</option>
            {% for m in materials %}
              <option value="{{m}}" {% if m==material %}selected{% endif %}>{{m}}</option>
            {% endfor %}
          </select>
        </div>
        <div>
          <label>Insert Type</label>
          <select name="insert">
            <option value="">-- Select --</option>
            {% for i in inserts %}
              <option value="{{i}}" {% if i==insert %}selected{% endif %}>{{i}}</option>
            {% endfor %}
          </select>
        </div>
      </div>

      {% if rec %}
        <div class="small">
          <span class="pill">SFM: {{rec.sfm_min}}–{{rec.sfm_max}}</span>
          <span class="pill">IPR: {{rec.ipr_min}}–{{rec.ipr_max}}</span>
        </div>
      {% endif %}

      <label>Tool Diameter (inches)</label>
      <input name="diameter" inputmode="decimal" value="{{diameter}}">

      <div class="row">
        <div>
          <label>Target SFM (optional)</label>
          <input name="sfm" inputmode="decimal" value="{{sfm}}">
        </div>
        <div>
          <label>RPM (optional)</label>
          <input name="rpm" inputmode="decimal" value="{{rpm}}">
        </div>
      </div>

      <div class="row">
        <div>
          <label>Feed IPR (optional)</label>
          <input name="ipr" inputmode="decimal" value="{{ipr}}">
        </div>
        <div>
          <label>Feed IPM (optional)</label>
          <input name="ipm" inputmode="decimal" value="{{ipm}}">
        </div>
      </div>

      <button type="submit">Calculate Turning</button>

      <div class="small">
        Note: Load limiting for turning needs DOC/WOC to estimate HP. Max load is still saved for this machine.
      </div>

    {% else %}
      <input type="hidden" name="mode" value="lathe_drill">

      <div class="row">
        <div>
          <label>Drill Material</label>
          <select name="drill_material">
            <option value="">-- Select --</option>
            {% for m in drill_materials %}
              <option value="{{m}}" {% if m==drill_material %}selected{% endif %}>{{m}}</option>
            {% endfor %}
          </select>
        </div>
        <div>
          <label>Drill Diameter (inches)</label>
          <input name="drill_diameter" inputmode="decimal" value="{{drill_diameter}}">
        </div>
      </div>

      <div class="row">
        <div>
          <label>Use Live Tool?</label>
          <select name="live_tool">
            <option value="no" {% if live_tool=='no' %}selected{% endif %}>No (Spindle)</option>
            <option value="yes" {% if live_tool=='yes' %}selected{% endif %}>Yes (Live Tool)</option>
          </select>
        </div>
        <div>
          <label>Auto-limit Feed to Load?</label>
          <select name="auto_limit">
            <option value="no" {% if auto_limit=='no' %}selected{% endif %}>No</option>
            <option value="yes" {% if auto_limit=='yes' %}selected{% endif %}>Yes</option>
          </select>
        </div>
      </div>

      {% if drill_rec %}
        <div class="small">
          <span class="pill">SFM: {{drill_rec.sfm_min}}–{{drill_rec.sfm_max}}</span>
          <span class="pill">IPR: {{drill_rec.ipr_min}}–{{drill_rec.ipr_max}}</span>
        </div>
      {% endif %}

      <div class="row">
        <div>
          <label>Target SFM (optional)</label>
          <input name="drill_sfm" inputmode="decimal" value="{{drill_sfm}}">
        </div>
        <div>
          <label>RPM (optional)</label>
          <input name="drill_rpm" inputmode="decimal" value="{{drill_rpm}}">
        </div>
      </div>

      <div class="row">
        <div>
          <label>Feed IPR (optional)</label>
          <input name="drill_ipr" inputmode="decimal" value="{{drill_ipr}}">
        </div>
        <div>
          <label>Feed IPM (optional)</label>
          <input name="drill_ipm" inputmode="decimal" value="{{drill_ipm}}">
        </div>
      </div>

      <button type="submit">Calculate Drilling</button>

    {% endif %}
  </form>

  {% if results %}
    <div class="out">
      {% if results.title %}<div><b>{{results.title}}</b></div>{% endif %}
      {% for k,v in results.items() %}
        {% if k!='title' %}
          <div><b>{{k}}:</b> {{v}}</div>
        {% endif %}
      {% endfor %}
    </div>
  {% endif %}

  {% if warnings %}
    <div class="warn">
      <b>Notes / Warnings:</b>
      <ul>
        {% for w in warnings %}
          <li>{{w}}</li>
        {% endfor %}
      </ul>
    </div>
  {% endif %}

  {% if error %}
    <div class="out danger">
      <b>Error:</b> {{error}}
    </div>
  {% endif %}

</div>
</body>
</html>
"""

MILL_TEMPLATE = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mill - Shop CNC Calculator</title>
<style>
  body { font-family: Arial, sans-serif; margin: 18px; }
  .topbar { max-width: 820px; margin: 0 auto 10px; display:flex; justify-content:space-between; align-items:center; }
  .topbar a { text-decoration:none; font-size: 14px; }
  .card { max-width: 820px; margin: 0 auto; padding: 18px; border: 1px solid #ddd; border-radius: 14px; }
  h1 { font-size: 22px; margin: 0 0 10px; }
  .tabs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
  .tab { padding:10px 12px; border:1px solid #ccc; border-radius:999px; text-decoration:none; color:#111; background:#f6f6f6; font-size:14px; }
  .tab.active { background:#111; color:#fff; border-color:#111; }
  label { display:block; margin-top: 12px; font-size: 14px; }
  input, select { width: 100%; padding: 14px; font-size: 18px; margin-top: 6px; border-radius: 10px; border: 1px solid #ccc; }
  button { width: 100%; padding: 16px; font-size: 18px; margin-top: 14px; border-radius: 12px; border: none; cursor: pointer; background:#f6f6f6; }
  .row { display:flex; gap: 12px; }
  .row > div { flex:1; }
  .out { margin-top: 14px; padding: 12px; border-radius: 12px; background:#f6f6f6; font-size: 18px; }
  .warn { margin-top: 10px; padding: 10px; border-radius: 12px; background:#fff6d6; border:1px solid #ffe08a; }
  .small { font-size: 13px; color:#444; margin-top: 8px; }
  .pill { display:inline-block; padding: 6px 10px; border-radius: 999px; background:#eee; font-size: 13px; margin-right: 6px; }
  .danger { background:#ffecec; border:1px solid #ffb3b3; }
</style>
</head>
<body>

<div class="topbar">
  <a href="{{ url_for('home') }}">← Home</a>
  <a href="{{ url_for('lathe') }}">Go to Lathe →</a>
</div>

<div class="card">
  <h1>Mill Calculator</h1>

  <div class="tabs">
    <a class="tab {% if op=='milling' %}active{% endif %}" href="{{ url_for('mill') }}?op=milling">Milling</a>
    <a class="tab {% if op=='drilling' %}active{% endif %}" href="{{ url_for('mill') }}?op=drilling">Drilling</a>
  </div>

  <form method="post">
    <input type="hidden" name="op" value="{{ op }}">

    <div class="row">
      <div>
        <label>Machine</label>
        <select name="machine">
          {% for m in machines %}
            <option value="{{m}}" {% if m==machine %}selected{% endif %}>{{m}}</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label>Max Load % (shared for this machine)</label>
        <input name="max_load_pct" inputmode="numeric" value="{{ max_load_pct }}">
      </div>
    </div>

    {% if op == 'milling' %}
      <input type="hidden" name="mode" value="mill_milling">

      <label>Material</label>
      <select name="material">
        <option value="">-- Select --</option>
        {% for m in mill_materials %}
          <option value="{{m}}" {% if m==material %}selected{% endif %}>{{m}}</option>
        {% endfor %}
      </select>

      {% if mill_rec %}
        <div class="small">
          <span class="pill">SFM: {{mill_rec.sfm_min}}–{{mill_rec.sfm_max}}</span>
          <span class="pill">Chipload: {{mill_rec.chip_min}}–{{mill_rec.chip_max}}</span>
        </div>
      {% endif %}

      <label>Tool Diameter (inches)</label>
      <input name="diameter" inputmode="decimal" value="{{diameter}}">

      <div class="row">
        <div>
          <label>Target SFM (optional)</label>
          <input name="sfm" inputmode="decimal" value="{{sfm}}">
        </div>
        <div>
          <label>RPM (optional)</label>
          <input name="rpm" inputmode="decimal" value="{{rpm}}">
        </div>
      </div>

      <div class="row">
        <div>
          <label>Flutes</label>
          <input name="flutes" inputmode="numeric" value="{{flutes}}">
        </div>
        <div>
          <label>Chipload IPT (optional)</label>
          <input name="chipload" inputmode="decimal" value="{{chipload}}">
        </div>
      </div>

      <label>Feed IPM (optional)</label>
      <input name="ipm" inputmode="decimal" value="{{ipm}}">

      <button type="submit">Calculate Milling</button>

      <div class="small">
        Note: Milling load limiting needs DOC/WOC to estimate HP. Max load is still saved for this machine.
      </div>

    {% else %}
      <input type="hidden" name="mode" value="mill_drill">

      <div class="row">
        <div>
          <label>Drill Material</label>
          <select name="drill_material">
            <option value="">-- Select --</option>
            {% for m in drill_materials %}
              <option value="{{m}}" {% if m==drill_material %}selected{% endif %}>{{m}}</option>
            {% endfor %}
          </select>
        </div>
        <div>
          <label>Drill Diameter (inches)</label>
          <input name="drill_diameter" inputmode="decimal" value="{{drill_diameter}}">
        </div>
      </div>

      <div class="row">
        <div>
          <label>Auto-limit Feed to Load?</label>
          <select name="auto_limit">
            <option value="no" {% if auto_limit=='no' %}selected{% endif %}>No</option>
            <option value="yes" {% if auto_limit=='yes' %}selected{% endif %}>Yes</option>
          </select>
        </div>
        <div>
          <label>(Mill) uses Spindle HP</label>
          <div class="small">Live tool does not apply on mills.</div>
        </div>
      </div>

      {% if drill_rec %}
        <div class="small">
          <span class="pill">SFM: {{drill_rec.sfm_min}}–{{drill_rec.sfm_max}}</span>
          <span class="pill">IPR: {{drill_rec.ipr_min}}–{{drill_rec.ipr_max}}</span>
        </div>
      {% endif %}

      <div class="row">
        <div>
          <label>Target SFM (optional)</label>
          <input name="drill_sfm" inputmode="decimal" value="{{drill_sfm}}">
        </div>
        <div>
          <label>RPM (optional)</label>
          <input name="drill_rpm" inputmode="decimal" value="{{drill_rpm}}">
        </div>
      </div>

      <div class="row">
        <div>
          <label>Feed IPR (optional)</label>
          <input name="drill_ipr" inputmode="decimal" value="{{drill_ipr}}">
        </div>
        <div>
          <label>Feed IPM (optional)</label>
          <input name="drill_ipm" inputmode="decimal" value="{{drill_ipm}}">
        </div>
      </div>

      <button type="submit">Calculate Drilling</button>

    {% endif %}
  </form>

  {% if results %}
    <div class="out">
      {% if results.title %}<div><b>{{results.title}}</b></div>{% endif %}
      {% for k,v in results.items() %}
        {% if k!='title' %}
          <div><b>{{k}}:</b> {{v}}</div>
        {% endif %}
      {% endfor %}
    </div>
  {% endif %}

  {% if warnings %}
    <div class="warn">
      <b>Notes / Warnings:</b>
      <ul>
        {% for w in warnings %}
          <li>{{w}}</li>
        {% endfor %}
      </ul>
    </div>
  {% endif %}

  {% if error %}
    <div class="out danger">
      <b>Error:</b> {{error}}
    </div>
  {% endif %}

</div>
</body>
</html>
"""


# ----------------------------
# Routes
# ----------------------------
@app.route("/")
def home():
    return render_template_string(HOME_TEMPLATE)


@app.route("/lathe", methods=["GET", "POST"])
def lathe():
    error = None
    results = None
    warnings: list[str] = []

    # operation from querystring or hidden input
    op = (request.args.get("op") or request.form.get("op") or "turning").strip()
    if op not in ("turning", "drilling", "live_tool"):
        op = "turning"

    machines = machine_list("lathe")
    if not machines:
        machines = list(MACHINES.keys())

    # machine + max load
    machine = request.form.get("machine") if request.method == "POST" else None
    if not machine:
        machine = session.get("lathe_machine") or machines[0]
    if machine not in MACHINES:
        machine = machines[0]

    # max load pct shared across ops for that machine
    max_load_pct = request.form.get("max_load_pct") if request.method == "POST" else str(get_machine_maxload(machine, 60))
    try:
        max_load_int = int(float(max_load_pct))
    except Exception:
        max_load_int = get_machine_maxload(machine, 60)
    max_load_int = int(clamp(max_load_int, 1, 100))
    max_load_pct = str(max_load_int)

    # Save machine selection + max load
    session["lathe_machine"] = machine
    set_machine_maxload(machine, max_load_int)

    # Turning fields
    diameter = ""
    sfm = ""
    rpm = ""
    ipr = ""
    ipm = ""
    material = ""
    insert = ""
    rec = None

    # Drilling fields
    drill_material = ""
    drill_diameter = ""
    drill_sfm = ""
    drill_rpm = ""
    drill_ipr = ""
    drill_ipm = ""
    drill_rec = None
    live_tool = "no"
    auto_limit = "no"

    # Prefill from session (per operation)
    if request.method == "GET":
        if op == "turning":
            last = session.get("lathe_turning_last", {})
            diameter = last.get("diameter", "")
            sfm = last.get("sfm", "")
            rpm = last.get("rpm", "")
            ipr = last.get("ipr", "")
            ipm = last.get("ipm", "")
            material = last.get("material", "")
            insert = last.get("insert", "")
        else:
            last = session.get("lathe_drill_last", {})
            drill_material = last.get("drill_material", "")
            drill_diameter = last.get("drill_diameter", "")
            drill_sfm = last.get("drill_sfm", "")
            drill_rpm = last.get("drill_rpm", "")
            drill_ipr = last.get("drill_ipr", "")
            drill_ipm = last.get("drill_ipm", "")
            live_tool = "yes" if op == "live_tool" else last.get("live_tool", "no")
            auto_limit = last.get("auto_limit", "no")

    if request.method == "POST":
        mode = request.form.get("mode", "lathe_turning" if op == "turning" else "lathe_drill")

        if mode == "lathe_turning":
            diameter = request.form.get("diameter", "")
            sfm = request.form.get("sfm", "")
            rpm = request.form.get("rpm", "")
            ipr = request.form.get("ipr", "")
            ipm = request.form.get("ipm", "")
            material = request.form.get("material", "")
            insert = request.form.get("insert", "")

            try:
                d = to_float(diameter)
                s = to_float(sfm)
                r = to_float(rpm)
                f_ipr = to_float(ipr)
                f_ipm = to_float(ipm)

                if not d or d <= 0:
                    raise ValueError("Tool diameter is required and must be > 0.")

                # Recommendations
                sfm_min = sfm_max = ipr_min = ipr_max = None
                if material in MATERIALS:
                    sfm_min = MATERIALS[material]["sfm_min"]
                    sfm_max = MATERIALS[material]["sfm_max"]
                if insert in INSERTS:
                    ipr_min = INSERTS[insert]["ipr_min"]
                    ipr_max = INSERTS[insert]["ipr_max"]

                if sfm_min is not None or ipr_min is not None:
                    rec = {
                        "sfm_min": sfm_min if sfm_min is not None else "-",
                        "sfm_max": sfm_max if sfm_max is not None else "-",
                        "ipr_min": f"{ipr_min:.3f}" if ipr_min is not None else "-",
                        "ipr_max": f"{ipr_max:.3f}" if ipr_max is not None else "-",
                    }

                rr, ss, ipr_out, ipm_out = compute_lathe_style(d, s, r, f_ipr, f_ipm)

                # Clamp by machine spindle max rpm (turning always uses spindle)
                rr, note = clamp_rpm_to_machine(machine, rr, use_live_tool=False)
                if note:
                    warnings.append(note)

                # Range warnings
                if sfm_min is not None and ss < sfm_min:
                    warnings.append("SFM is below the typical range (may rub / poor finish).")
                if sfm_max is not None and ss > sfm_max:
                    warnings.append("SFM is above the typical range (may wear/burn edge).")
                if ipr_min is not None and ipr_out < ipr_min:
                    warnings.append("IPR is below typical range (may rub depending on insert/nose radius).")
                if ipr_max is not None and ipr_out > ipr_max:
                    warnings.append("IPR is above typical range (watch power, chatter, edge).")

                results = {
                    "title": "Turning Results",
                    "RPM": f"{rr:.0f}",
                    "SFM": f"{ss:.1f}",
                    "IPR": f"{ipr_out:.4f}",
                    "IPM": f"{ipm_out:.3f}",
                    "Machine": machine,
                    "Max Load %": f"{max_load_int}%",
                }

                session["lathe_turning_last"] = {
                    "diameter": diameter,
                    "sfm": sfm,
                    "rpm": rpm,
                    "ipr": ipr,
                    "ipm": ipm,
                    "material": material,
                    "insert": insert,
                }

            except Exception as e:
                error = str(e)

        elif mode == "lathe_drill":
            # drilling operation (spindle or live tool)
            drill_material = request.form.get("drill_material", "")
            drill_diameter = request.form.get("drill_diameter", "")
            drill_sfm = request.form.get("drill_sfm", "")
            drill_rpm = request.form.get("drill_rpm", "")
            drill_ipr = request.form.get("drill_ipr", "")
            drill_ipm = request.form.get("drill_ipm", "")
            live_tool = request.form.get("live_tool", "no")
            auto_limit = request.form.get("auto_limit", "no")

            # If user chose op via home tabs, enforce live tool mode automatically
            if op == "live_tool":
                live_tool = "yes"
            elif op == "drilling":
                live_tool = "no"

            try:
                dd = to_float(drill_diameter)
                ds = to_float(drill_sfm)
                dr = to_float(drill_rpm)
                dipr = to_float(drill_ipr)
                dipm = to_float(drill_ipm)

                if not dd or dd <= 0:
                    raise ValueError("Drill diameter is required and must be > 0.")

                use_live = (live_tool == "yes")

                # Drill presets
                sfm_min = sfm_max = ipr_min = ipr_max = None
                if drill_material in DRILL_MATERIALS:
                    sfm_min = DRILL_MATERIALS[drill_material]["sfm_min"]
                    sfm_max = DRILL_MATERIALS[drill_material]["sfm_max"]
                    ipr_min = DRILL_MATERIALS[drill_material]["ipr_min"]
                    ipr_max = DRILL_MATERIALS[drill_material]["ipr_max"]
                    drill_rec = {
                        "sfm_min": sfm_min,
                        "sfm_max": sfm_max,
                        "ipr_min": f"{ipr_min:.4f}",
                        "ipr_max": f"{ipr_max:.4f}",
                    }

                rr, ss, ipr_out, ipm_out = compute_lathe_style(dd, ds, dr, dipr, dipm)

                # Clamp rpm by machine (spindle vs live tool)
                rr, note = clamp_rpm_to_machine(machine, rr, use_live_tool=use_live)
                if note:
                    warnings.append(note)

                # HP check
                hp_avail = available_hp(machine, use_live_tool=use_live)
                hp_limit = hp_avail * (max_load_int / 100.0)

                hp_req = drill_hp_required(drill_material, dd, ipm_out) if drill_material else 0.0

                if drill_material:
                    if sfm_min is not None and ss < sfm_min:
                        warnings.append("SFM is below typical range (may rub).")
                    if sfm_max is not None and ss > sfm_max:
                        warnings.append("SFM is above typical range (may burn/wear drill).")
                    if ipr_min is not None and ipr_out < ipr_min:
                        warnings.append("IPR is light (may rub/work-harden depending on material).")
                    if ipr_max is not None and ipr_out > ipr_max:
                        warnings.append("IPR is heavy (watch load/chip packing).")

                if hp_avail > 0 and hp_req > 0:
                    if hp_req > hp_limit:
                        warnings.append(
                            f"Load risk: estimated drilling HP {hp_req:.2f} > allowed {hp_limit:.2f} "
                            f"({max_load_int}% of {hp_avail:.1f} HP)."
                        )

                        # Suggest reduced feed
                        ipr_sug, ipm_sug = suggest_drill_feed_for_hp_limit(drill_material, dd, rr, hp_limit)
                        if ipr_sug > 0:
                            warnings.append(
                                f"Suggestion to stay under load: ≤ {ipr_sug:.4f} IPR (≈ {ipm_sug:.2f} IPM) at {rr:.0f} RPM."
                            )

                        # Optional auto-limit
                        if auto_limit == "yes" and ipr_sug > 0:
                            ipr_out = ipr_sug
                            ipm_out = ipm_sug
                            hp_req = drill_hp_required(drill_material, dd, ipm_out)
                            warnings.append("Auto-limit applied: feed reduced to meet load limit.")

                results = {
                    "title": "Lathe Drilling Results",
                    "Mode": "Live Tool" if use_live else "Spindle",
                    "RPM": f"{rr:.0f}",
                    "SFM": f"{ss:.1f}",
                    "IPR": f"{ipr_out:.4f}",
                    "IPM": f"{ipm_out:.3f}",
                    "Est HP": f"{hp_req:.2f}" if hp_req else "-",
                    "Allowed HP": f"{hp_limit:.2f}" if hp_avail else "-",
                    "Machine": machine,
                    "Max Load %": f"{max_load_int}%",
                }

                session["lathe_drill_last"] = {
                    "drill_material": drill_material,
                    "drill_diameter": drill_diameter,
                    "drill_sfm": drill_sfm,
                    "drill_rpm": drill_rpm,
                    "drill_ipr": drill_ipr,
                    "drill_ipm": drill_ipm,
                    "live_tool": live_tool,
                    "auto_limit": auto_limit,
                }

            except Exception as e:
                error = str(e)

    return render_template_string(
        LATHE_TEMPLATE,
        op=op,
        machines=machines,
        machine=machine,
        max_load_pct=max_load_pct,
        


        # turning vars
        diameter=diameter, sfm=sfm, rpm=rpm, ipr=ipr, ipm=ipm,
        material=material, insert=insert,
        materials=list(ALL_MATERIAL_NAMES()),
        inserts=list(INSERTS.keys()),
        rec=rec,

        # drilling vars
        drill_materials=list(ALL_MATERIAL_NAMES()),
        drill_material=drill_material,
        drill_diameter=drill_diameter,
        drill_sfm=drill_sfm,
        drill_rpm=drill_rpm,
        drill_ipr=drill_ipr,
        drill_ipm=drill_ipm,
        drill_rec=drill_rec,
        live_tool=live_tool,
        auto_limit=auto_limit,

        # output
        results=results,
        warnings=warnings,
        error=error
    )


@app.route("/mill", methods=["GET", "POST"])
def mill():
    error = None
    results = None
    warnings: list[str] = []
    mill_rec = None

    op = (request.args.get("op") or request.form.get("op") or "milling").strip()
    if op not in ("milling", "drilling"):
        op = "milling"

    machines = machine_list("mill")
    if not machines:
        machines = list(MACHINES.keys())

    machine = request.form.get("machine") if request.method == "POST" else None
    if not machine:
        machine = session.get("mill_machine") or machines[0]
    if machine not in MACHINES:
        machine = machines[0]

    max_load_pct = request.form.get("max_load_pct") if request.method == "POST" else str(get_machine_maxload(machine, 60))
    try:
        max_load_int = int(float(max_load_pct))
    except Exception:
        max_load_int = get_machine_maxload(machine, 60)
    max_load_int = int(clamp(max_load_int, 1, 100))
    max_load_pct = str(max_load_int)

    session["mill_machine"] = machine
    set_machine_maxload(machine, max_load_int)

    # Milling fields
    diameter = ""
    sfm = ""
    rpm = ""
    flutes = "4"
    chipload = ""
    ipm = ""
    material = ""

    # Drilling fields
    drill_material = ""
    drill_diameter = ""
    drill_sfm = ""
    drill_rpm = ""
    drill_ipr = ""
    drill_ipm = ""
    drill_rec = None
    auto_limit = "no"

    if request.method == "GET":
        if op == "milling":
            last = session.get("mill_milling_last", {})
            diameter = last.get("diameter", "")
            sfm = last.get("sfm", "")
            rpm = last.get("rpm", "")
            flutes = last.get("flutes", "4")
            chipload = last.get("chipload", "")
            ipm = last.get("ipm", "")
            material = last.get("material", "")
        else:
            last = session.get("mill_drill_last", {})
            drill_material = last.get("drill_material", "")
            drill_diameter = last.get("drill_diameter", "")
            drill_sfm = last.get("drill_sfm", "")
            drill_rpm = last.get("drill_rpm", "")
            drill_ipr = last.get("drill_ipr", "")
            drill_ipm = last.get("drill_ipm", "")
            auto_limit = last.get("auto_limit", "no")

    if request.method == "POST":
        mode = request.form.get("mode", "mill_milling" if op == "milling" else "mill_drill")

        if mode == "mill_milling":
            material = request.form.get("material", "")
            diameter = request.form.get("diameter", "")
            sfm = request.form.get("sfm", "")
            rpm = request.form.get("rpm", "")
            flutes = request.form.get("flutes", "4")
            chipload = request.form.get("chipload", "")
            ipm = request.form.get("ipm", "")

            try:
                d = to_float(diameter)
                s = to_float(sfm)
                r = to_float(rpm)
                n_flutes = to_int(flutes)
                c = to_float(chipload)
                feed_ipm = to_float(ipm)

                if not d or d <= 0:
                    raise ValueError("Tool diameter is required and must be > 0.")
                if not n_flutes or n_flutes <= 0:
                    raise ValueError("Flutes must be a whole number > 0.")

                # Material recommendations
                sfm_min = sfm_max = chip_min = chip_max = None
                if material in MILL_MATERIALS:
                    sfm_min = MILL_MATERIALS[material]["sfm_min"]
                    sfm_max = MILL_MATERIALS[material]["sfm_max"]
                    chip_min = MILL_MATERIALS[material]["chip_min"]
                    chip_max = MILL_MATERIALS[material]["chip_max"]
                    mill_rec = {
                        "sfm_min": sfm_min,
                        "sfm_max": sfm_max,
                        "chip_min": f"{chip_min:.4f}",
                        "chip_max": f"{chip_max:.4f}",
                    }

                if r is None and s is None:
                    raise ValueError("Enter either Target SFM or RPM.")
                if r is None:
                    r = rpm_from_sfm(d, s)
                if s is None:
                    s = sfm_from_rpm(d, r)

                # Clamp RPM to machine spindle max
                r, note = clamp_rpm_to_machine(machine, r, use_live_tool=False)
                if note:
                    warnings.append(note)

                if c is None and feed_ipm is None:
                    raise ValueError("Enter either Chipload (IPT) or Feed (IPM).")
                if feed_ipm is None:
                    feed_ipm = ipm_from_chipload(c, n_flutes, r)
                if c is None:
                    c = chipload_from_ipm(feed_ipm, n_flutes, r)

                if sfm_min is not None and s < sfm_min:
                    warnings.append("SFM is below typical range (may rub).")
                if sfm_max is not None and s > sfm_max:
                    warnings.append("SFM is above typical range (may wear tool fast).")
                if chip_min is not None and c < chip_min:
                    warnings.append("Chipload is light (risk of rubbing).")
                if chip_max is not None and c > chip_max:
                    warnings.append("Chipload is heavy (watch chatter/tool load).")

                results = {
                    "title": "Milling Results",
                    "RPM": f"{r:.0f}",
                    "SFM": f"{s:.1f}",
                    "Chipload (IPT)": f"{c:.4f}",
                    "Feed (IPM)": f"{feed_ipm:.2f}",
                    "Machine": machine,
                    "Max Load %": f"{max_load_int}%",
                }

                session["mill_milling_last"] = {
                    "diameter": diameter,
                    "sfm": sfm,
                    "rpm": rpm,
                    "flutes": flutes,
                    "chipload": chipload,
                    "ipm": ipm,
                    "material": material,
                }

            except Exception as e:
                error = str(e)

        elif mode == "mill_drill":
            drill_material = request.form.get("drill_material", "")
            drill_diameter = request.form.get("drill_diameter", "")
            drill_sfm = request.form.get("drill_sfm", "")
            drill_rpm = request.form.get("drill_rpm", "")
            drill_ipr = request.form.get("drill_ipr", "")
            drill_ipm = request.form.get("drill_ipm", "")
            auto_limit = request.form.get("auto_limit", "no")

            try:
                dd = to_float(drill_diameter)
                ds = to_float(drill_sfm)
                dr = to_float(drill_rpm)
                dipr = to_float(drill_ipr)
                dipm = to_float(drill_ipm)

                if not dd or dd <= 0:
                    raise ValueError("Drill diameter is required and must be > 0.")

                # Presets
                sfm_min = sfm_max = ipr_min = ipr_max = None
                if drill_material in DRILL_MATERIALS:
                    sfm_min = DRILL_MATERIALS[drill_material]["sfm_min"]
                    sfm_max = DRILL_MATERIALS[drill_material]["sfm_max"]
                    ipr_min = DRILL_MATERIALS[drill_material]["ipr_min"]
                    ipr_max = DRILL_MATERIALS[drill_material]["ipr_max"]
                    drill_rec = {
                        "sfm_min": sfm_min,
                        "sfm_max": sfm_max,
                        "ipr_min": f"{ipr_min:.4f}",
                        "ipr_max": f"{ipr_max:.4f}",
                    }

                rr, ss, ipr_out, ipm_out = compute_lathe_style(dd, ds, dr, dipr, dipm)

                rr, note = clamp_rpm_to_machine(machine, rr, use_live_tool=False)
                if note:
                    warnings.append(note)

                hp_avail = available_hp(machine, use_live_tool=False)
                hp_limit = hp_avail * (max_load_int / 100.0)
                hp_req = drill_hp_required(drill_material, dd, ipm_out) if drill_material else 0.0

                if drill_material:
                    if sfm_min is not None and ss < sfm_min:
                        warnings.append("SFM is below typical range (may rub).")
                    if sfm_max is not None and ss > sfm_max:
                        warnings.append("SFM is above typical range (may burn/wear drill).")
                    if ipr_min is not None and ipr_out < ipr_min:
                        warnings.append("IPR is light (may rub/work-harden depending on material).")
                    if ipr_max is not None and ipr_out > ipr_max:
                        warnings.append("IPR is heavy (watch load/chip packing).")

                if hp_avail > 0 and hp_req > 0:
                    if hp_req > hp_limit:
                        warnings.append(
                            f"Load risk: estimated drilling HP {hp_req:.2f} > allowed {hp_limit:.2f} "
                            f"({max_load_int}% of {hp_avail:.1f} HP)."
                        )

                        ipr_sug, ipm_sug = suggest_drill_feed_for_hp_limit(drill_material, dd, rr, hp_limit)
                        if ipr_sug > 0:
                            warnings.append(
                                f"Suggestion to stay under load: ≤ {ipr_sug:.4f} IPR (≈ {ipm_sug:.2f} IPM) at {rr:.0f} RPM."
                            )
                        if auto_limit == "yes" and ipr_sug > 0:
                            ipr_out = ipr_sug
                            ipm_out = ipm_sug
                            hp_req = drill_hp_required(drill_material, dd, ipm_out)
                            warnings.append("Auto-limit applied: feed reduced to meet load limit.")

                results = {
                    "title": "Mill Drilling Results",
                    "RPM": f"{rr:.0f}",
                    "SFM": f"{ss:.1f}",
                    "IPR": f"{ipr_out:.4f}",
                    "IPM": f"{ipm_out:.3f}",
                    "Est HP": f"{hp_req:.2f}" if hp_req else "-",
                    "Allowed HP": f"{hp_limit:.2f}" if hp_avail else "-",
                    "Machine": machine,
                    "Max Load %": f"{max_load_int}%",
                }

                session["mill_drill_last"] = {
                    "drill_material": drill_material,
                    "drill_diameter": drill_diameter,
                    "drill_sfm": drill_sfm,
                    "drill_rpm": drill_rpm,
                    "drill_ipr": drill_ipr,
                    "drill_ipm": drill_ipm,
                    "auto_limit": auto_limit,
                }

            except Exception as e:
                error = str(e)

    return render_template_string(
        MILL_TEMPLATE,
        op=op,
        machines=machines,
        machine=machine,
        max_load_pct=max_load_pct,

        # milling vars
        diameter=diameter, sfm=sfm, rpm=rpm, flutes=flutes, chipload=chipload, ipm=ipm,
        material=material,
        mill_materials=list(ALL_MATERIAL_NAMES()),
        mill_rec=mill_rec,

        # drilling vars
        drill_materials=list(ALL_MATERIAL_NAMES()),
        drill_material=drill_material,
        drill_diameter=drill_diameter,
        drill_sfm=drill_sfm,
        drill_rpm=drill_rpm,
        drill_ipr=drill_ipr,
        drill_ipm=drill_ipm,
        drill_rec=drill_rec,
        auto_limit=auto_limit,

        # output
        results=results,
        warnings=warnings,
        error=error
    )


if __name__ == "__main__":
    app.run(debug=True)
