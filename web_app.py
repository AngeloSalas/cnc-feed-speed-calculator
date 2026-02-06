from flask import Flask, request, render_template_string, url_for, session
from cnc.formulas import (
    sfm_from_rpm, rpm_from_sfm, ipm_from_ipr, ipr_from_ipm,
    ipm_from_chipload, chipload_from_ipm
)
from cnc.data import MATERIALS, INSERTS, MILL_MATERIALS, DRILL_MATERIALS, MACHINES

app = Flask(__name__)
app.secret_key = "change-me-to-any-random-string"


# ---------- Shared helpers ----------
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

def default_machine_name(kind: str):
    # kind: "lathe" or "mill"
    for name, spec in MACHINES.items():
        if spec.get("type") == kind:
            return name
    return next(iter(MACHINES.keys()))  # fallback

def compute_lathe_style(diameter_in: float, sfm_val, rpm_val, ipr_val, ipm_val):
    if rpm_val is None and sfm_val is None:
        raise ValueError("Enter either SFM or RPM.")
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

def drilling_hp_required(diameter_in: float, ipm_val: float, material_name: str):
    """
    Simple shop-friendly estimate:
    MRR (in^3/min) = area * IPM, area = pi*(D^2)/4
    HPreq ≈ unit_hp * MRR
    """
    if ipm_val is None:
        return None
    mat = DRILL_MATERIALS.get(material_name) or {}
    unit_hp = mat.get("unit_hp", 0.60)  # fallback
    area = 3.1415926535 * (diameter_in ** 2) / 4.0
    mrr = area * ipm_val
    hp_req = unit_hp * mrr
    return hp_req


# ---------- Templates ----------
HOME_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Shop CNC Calculator</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 18px; }
    .card { max-width: 720px; margin: 0 auto; padding: 18px; border: 1px solid #ddd; border-radius: 14px; }
    h1 { font-size: 24px; margin: 0 0 14px; }
    .btnrow { display:flex; gap: 14px; margin-top: 14px; }
    a.btn {
      flex: 1;
      display:block;
      text-align:center;
      padding: 22px 16px;
      font-size: 22px;
      text-decoration:none;
      border-radius: 14px;
      border: 1px solid #ccc;
      background: #f6f6f6;
      color: #111;
    }
    .small { font-size: 13px; color:#444; margin-top: 10px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Shop CNC Calculator</h1>
    <div class="btnrow">
      <a class="btn" href="{{ url_for('lathe') }}">LATHE</a>
      <a class="btn" href="{{ url_for('mill') }}">MILL</a>
    </div>
    <div class="small">Tip: Bookmark Lathe/Mill pages on the shop PC.</div>
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
.topbar { max-width: 740px; margin: 0 auto 10px; display:flex; justify-content:space-between; }
.card { max-width: 740px; margin:0 auto; padding:18px; border:1px solid #ddd; border-radius:14px; }
label { display:block; margin-top:12px; font-size:14px; }
input, select { width:100%; padding:14px; font-size:18px; margin-top:6px; border-radius:10px; border:1px solid #ccc; }
button { width:100%; padding:16px; font-size:18px; margin-top:14px; border-radius:12px; border:none; cursor:pointer; }
.row { display:flex; gap:12px; }
.row > div { flex:1; }
.out { margin-top:14px; padding:12px; border-radius:12px; background:#f6f6f6; font-size:18px; }
.warn { margin-top:10px; padding:10px; border-radius:12px; background:#fff6d6; border:1px solid #ffe08a; }
.small { font-size:13px; color:#444; margin-top:8px; }
.pill { display:inline-block; padding:6px 10px; border-radius:999px; background:#eee; font-size:13px; margin-right:6px; }
hr { border:none; border-top:1px solid #ddd; margin:18px 0; }
h2 { margin: 8px 0 0; }
</style>
</head>

<body>
<div class="topbar">
  <a href="{{ url_for('home') }}">← Home</a>
  <a href="{{ url_for('mill') }}">Go to Mill →</a>
</div>

<div class="card">
  <h1>Lathe Calculator</h1>

  <form method="post">
    <input type="hidden" name="mode" value="lathe_main">

    <label>Machine</label>
    <select name="machine">
      {% for m in machines %}
        <option value="{{m}}" {% if m == machine %}selected{% endif %}>{{m}}</option>
      {% endfor %}
    </select>

    <div class="row">
      <div>
        <label>Material</label>
        <select name="material">
          <option value="">-- Select --</option>
          {% for m in materials %}
            <option value="{{m}}" {% if m == material %}selected{% endif %}>{{m}}</option>
          {% endfor %}
        </select>
      </div>

      <div>
        <label>Insert Type</label>
        <select name="insert">
          <option value="">-- Select --</option>
          {% for i in inserts %}
            <option value="{{i}}" {% if i == insert %}selected{% endif %}>{{i}}</option>
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
    <input name="diameter" value="{{diameter}}">

    <div class="row">
      <div>
        <label>Target SFM</label>
        <input name="sfm" value="{{sfm}}">
      </div>
      <div>
        <label>RPM</label>
        <input name="rpm" value="{{rpm}}">
      </div>
    </div>

    <div class="row">
      <div>
        <label>Feed IPR</label>
        <input name="ipr" value="{{ipr}}">
      </div>
      <div>
        <label>Feed IPM</label>
        <input name="ipm" value="{{ipm}}">
      </div>
    </div>

    <button type="submit">Calculate</button>
  </form>

  {% if results %}
    <div class="out">
      <div><b>RPM:</b> {{results.rpm}}</div>
      <div><b>SFM:</b> {{results.sfm}}</div>
      <div><b>IPR:</b> {{results.ipr}}</div>
      <div><b>IPM:</b> {{results.ipm}}</div>
    </div>
  {% endif %}

  {% if warnings %}
    <div class="warn">
      <b>Notes:</b>
      <ul>
        {% for w in warnings %}<li>{{w}}</li>{% endfor %}
      </ul>
    </div>
  {% endif %}

  {% if error %}
    <div class="out" style="background:#ffecec;border:1px solid #ffb3b3;">
      <b>Error:</b> {{error}}
    </div>
  {% endif %}

  <hr>

  <h2>Drilling (Lathe)</h2>

  <form method="post">
    <input type="hidden" name="mode" value="lathe_drill">

    <label>Machine</label>
    <select name="machine">
      {% for m in machines %}
        <option value="{{m}}" {% if m == machine %}selected{% endif %}>{{m}}</option>
      {% endfor %}
    </select>

    <label>Use Live Tool?</label>
    <select name="drill_drive">
      <option value="spindle" {% if drill_drive == "spindle" %}selected{% endif %}>No (Main Spindle)</option>
      <option value="live" {% if drill_drive == "live" %}selected{% endif %}>Yes (Live Tool)</option>
    </select>

    <div class="row">
      <div>
        <label>Material</label>
        <select name="drill_material">
          <option value="">-- Select --</option>
          {% for m in drill_materials %}
            <option value="{{m}}" {% if m == drill_material %}selected{% endif %}>{{m}}</option>
          {% endfor %}
        </select>
      </div>

      <div>
        <label>Drill Diameter</label>
        <input name="drill_diameter" value="{{drill_diameter}}">
      </div>
    </div>

    <div class="row">
      <div>
        <label>SFM</label>
        <input name="drill_sfm" value="{{drill_sfm}}">
      </div>
      <div>
        <label>RPM</label>
        <input name="drill_rpm" value="{{drill_rpm}}">
      </div>
    </div>

    <div class="row">
      <div>
        <label>IPR</label>
        <input name="drill_ipr" value="{{drill_ipr}}">
      </div>
      <div>
        <label>IPM</label>
        <input name="drill_ipm" value="{{drill_ipm}}">
      </div>
    </div>

    <button type="submit">Calculate Drill</button>
  </form>

  {% if drill_results %}
    <div class="out">
      <div><b>RPM:</b> {{drill_results.rpm}}</div>
      <div><b>SFM:</b> {{drill_results.sfm}}</div>
      <div><b>IPR:</b> {{drill_results.ipr}}</div>
      <div><b>IPM:</b> {{drill_results.ipm}}</div>
      {% if drill_results.hp_req %}
        <div style="margin-top:6px;"><b>Est. HP Required:</b> {{drill_results.hp_req}}</div>
        <div><b>Drive HP Available:</b> {{drill_results.hp_avail}}</div>
      {% endif %}
    </div>
  {% endif %}

  {% if drill_warnings %}
    <div class="warn">
      <b>Notes:</b>
      <ul>
        {% for w in drill_warnings %}<li>{{w}}</li>{% endfor %}
      </ul>
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
.topbar { max-width: 740px; margin: 0 auto 10px; display:flex; justify-content:space-between; }
.card { max-width:740px; margin:auto; padding:18px; border:1px solid #ddd; border-radius:14px; }
label { display:block; margin-top:12px; }
input, select { width:100%; padding:14px; margin-top:6px; border-radius:10px; border:1px solid #ccc; }
button { width:100%; padding:16px; margin-top:14px; border-radius:12px; border:none; cursor:pointer; }
.row { display:flex; gap:12px; }
.row > div { flex:1; }
.out { margin-top:14px; padding:12px; border-radius:12px; background:#f6f6f6; }
.warn { margin-top:10px; padding:10px; background:#fff6d6; border:1px solid #ffe08a; border-radius:12px; }
hr { border:none; border-top:1px solid #ddd; margin:18px 0; }
</style>
</head>

<body>
<div class="topbar">
  <a href="{{ url_for('home') }}">← Home</a>
  <a href="{{ url_for('lathe') }}">Go to Lathe →</a>
</div>

<div class="card">
<h1>Mill Calculator</h1>

<form method="post">
  <input type="hidden" name="mode" value="mill_main">

  <label>Machine</label>
  <select name="machine">
    {% for m in machines %}
      <option value="{{m}}" {% if m == machine %}selected{% endif %}>{{m}}</option>
    {% endfor %}
  </select>

  <label>Material</label>
  <select name="material">
    <option value="">-- Select --</option>
    {% for m in mill_materials %}
      <option value="{{m}}" {% if m == material %}selected{% endif %}>{{m}}</option>
    {% endfor %}
  </select>

  <label>Tool Diameter</label>
  <input name="diameter" value="{{diameter}}">

  <div class="row">
    <div>
      <label>SFM</label>
      <input name="sfm" value="{{sfm}}">
    </div>
    <div>
      <label>RPM</label>
      <input name="rpm" value="{{rpm}}">
    </div>
  </div>

  <div class="row">
    <div>
      <label>Flutes</label>
      <input name="flutes" value="{{flutes}}">
    </div>
    <div>
      <label>Chipload</label>
      <input name="chipload" value="{{chipload}}">
    </div>
  </div>

  <label>Feed IPM</label>
  <input name="ipm" value="{{ipm}}">

  <button type="submit">Calculate</button>
</form>

{% if results %}
  <div class="out">
    <div><b>RPM:</b> {{results.rpm}}</div>
    <div><b>SFM:</b> {{results.sfm}}</div>
    <div><b>Chipload:</b> {{results.chipload}}</div>
    <div><b>IPM:</b> {{results.ipm}}</div>
  </div>
{% endif %}

{% if warnings %}
  <div class="warn">
    <b>Notes:</b>
    <ul>{% for w in warnings %}<li>{{w}}</li>{% endfor %}</ul>
  </div>
{% endif %}

{% if error %}
  <div class="out" style="background:#ffecec;border:1px solid #ffb3b3;">
    <b>Error:</b> {{error}}
  </div>
{% endif %}

<hr>

<h2>Drilling (Mill)</h2>

<form method="post">
  <input type="hidden" name="mode" value="mill_drill">

  <label>Machine</label>
  <select name="machine">
    {% for m in machines %}
      <option value="{{m}}" {% if m == machine %}selected{% endif %}>{{m}}</option>
    {% endfor %}
  </select>

  <label>Material</label>
  <select name="drill_material">
    <option value="">-- Select --</option>
    {% for m in drill_materials %}
      <option value="{{m}}" {% if m == drill_material %}selected{% endif %}>{{m}}</option>
    {% endfor %}
  </select>

  <label>Drill Diameter</label>
  <input name="drill_diameter" value="{{drill_diameter}}">

  <div class="row">
    <div>
      <label>SFM</label>
      <input name="drill_sfm" value="{{drill_sfm}}">
    </div>
    <div>
      <label>RPM</label>
      <input name="drill_rpm" value="{{drill_rpm}}">
    </div>
  </div>

  <div class="row">
    <div>
      <label>IPR</label>
      <input name="drill_ipr" value="{{drill_ipr}}">
    </div>
    <div>
      <label>IPM</label>
      <input name="drill_ipm" value="{{drill_ipm}}">
    </div>
  </div>

  <button type="submit">Calculate Drill</button>
</form>

{% if drill_results %}
  <div class="out">
    <div><b>RPM:</b> {{drill_results.rpm}}</div>
    <div><b>SFM:</b> {{drill_results.sfm}}</div>
    <div><b>IPR:</b> {{drill_results.ipr}}</div>
    <div><b>IPM:</b> {{drill_results.ipm}}</div>
    {% if drill_results.hp_req %}
      <div style="margin-top:6px;"><b>Est. HP Required:</b> {{drill_results.hp_req}}</div>
      <div><b>Spindle HP Available:</b> {{drill_results.hp_avail}}</div>
    {% endif %}
  </div>
{% endif %}

{% if drill_warnings %}
  <div class="warn">
    <b>Notes:</b>
    <ul>{% for w in drill_warnings %}<li>{{w}}</li>{% endfor %}</ul>
  </div>
{% endif %}

</div>
</body>
</html>
"""


# ---------- Routes ----------
@app.route("/")
def home():
    return render_template_string(HOME_TEMPLATE)


@app.route("/lathe", methods=["GET", "POST"])
def lathe():
    error = None
    results = None
    warnings = []
    rec = None

    machines = [k for k, v in MACHINES.items() if v.get("type") == "lathe"]
    machine = default_machine_name("lathe")

    # main lathe fields
    diameter = ""
    sfm = ""
    rpm = ""
    ipr = ""
    ipm = ""
    material = ""
    insert = ""

    # drill fields (lathe drill section)
    drill_results = None
    drill_warnings = []
    drill_rec = None
    drill_material = ""
    drill_diameter = ""
    drill_sfm = ""
    drill_rpm = ""
    drill_ipr = ""
    drill_ipm = ""
    drill_drive = "spindle"  # spindle or live

    # Prefill from session
    if request.method == "GET":
        last = session.get("lathe_last", {})
        machine = last.get("machine", machine)
        diameter = last.get("diameter", "")
        sfm = last.get("sfm", "")
        rpm = last.get("rpm", "")
        ipr = last.get("ipr", "")
        ipm = last.get("ipm", "")
        material = last.get("material", "")
        insert = last.get("insert", "")

        dlast = session.get("lathe_drill_last", {})
        drill_drive = dlast.get("drill_drive", drill_drive)
        drill_material = dlast.get("drill_material", "")
        drill_diameter = dlast.get("drill_diameter", "")
        drill_sfm = dlast.get("drill_sfm", "")
        drill_rpm = dlast.get("drill_rpm", "")
        drill_ipr = dlast.get("drill_ipr", "")
        drill_ipm = dlast.get("drill_ipm", "")

    if request.method == "POST":
        mode = request.form.get("mode", "lathe_main")
        machine = request.form.get("machine", machine)

        if mode == "lathe_main":
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

                if sfm_min is not None and (ss < sfm_min):
                    warnings.append("SFM is below the typical range (may rub / poor finish).")
                if sfm_max is not None and (ss > sfm_max):
                    warnings.append("SFM is above the typical range (may wear/burn edge).")
                if ipr_min is not None and (ipr_out < ipr_min):
                    warnings.append("IPR is below typical range (may rub depending on insert/nose radius).")
                if ipr_max is not None and (ipr_out > ipr_max):
                    warnings.append("IPR is above typical range (watch power, chatter, edge).")

                results = {
                    "rpm": f"{rr:.0f}",
                    "sfm": f"{ss:.1f}",
                    "ipr": f"{ipr_out:.4f}",
                    "ipm": f"{ipm_out:.3f}",
                }

                session["lathe_last"] = {
                    "machine": machine,
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
            drill_drive = request.form.get("drill_drive", "spindle")
            drill_material = request.form.get("drill_material", "")
            drill_diameter = request.form.get("drill_diameter", "")
            drill_sfm = request.form.get("drill_sfm", "")
            drill_rpm = request.form.get("drill_rpm", "")
            drill_ipr = request.form.get("drill_ipr", "")
            drill_ipm = request.form.get("drill_ipm", "")

            try:
                dd = to_float(drill_diameter)
                ds = to_float(drill_sfm)
                dr = to_float(drill_rpm)
                dipr = to_float(drill_ipr)
                dipm = to_float(drill_ipm)

                if not dd or dd <= 0:
                    raise ValueError("Drill diameter is required and must be > 0.")

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

                # Machine limits based on drive selection
                mspec = MACHINES.get(machine, {})
                if drill_drive == "live" and mspec.get("has_live_tool"):
                    rpm_limit = mspec.get("live_tool_max_rpm", 0) or 0
                    hp_avail = mspec.get("live_tool_hp", 0.0) or 0.0
                    drive_name = "Live Tool"
                else:
                    rpm_limit = mspec.get("spindle_max_rpm", 0) or 0
                    hp_avail = mspec.get("spindle_hp", 0.0) or 0.0
                    drive_name = "Main Spindle"

                # Range warnings
                if sfm_min is not None and ss < sfm_min:
                    drill_warnings.append("SFM is below typical range (may rub).")
                if sfm_max is not None and ss > sfm_max:
                    drill_warnings.append("SFM is above typical range (may burn/wear drill).")
                if ipr_min is not None and ipr_out < ipr_min:
                    drill_warnings.append("IPR is light (may rub/work-harden depending on material).")
                if ipr_max is not None and ipr_out > ipr_max:
                    drill_warnings.append("IPR is heavy (watch load/chip packing).")

                # RPM limit warning
                if rpm_limit and rr > rpm_limit:
                    drill_warnings.append(
                        f"{drive_name} RPM limit is {rpm_limit:.0f}. Your drill RPM ({rr:.0f}) exceeds it."
                    )

                # Power/torque-style warning (HP required vs HP available)
                hp_req = drilling_hp_required(dd, ipm_out, drill_material)
                if hp_req is not None and hp_avail:
                    if hp_req > hp_avail * 0.90:
                        drill_warnings.append(
                            f"Estimated load is HIGH for {drive_name} (HP req ~{hp_req:.2f} vs avail {hp_avail:.2f}). "
                            "Expect high load/torque alarms. Reduce IPR, reduce SFM, or use spindle instead of live tool."
                        )

                drill_results = {
                    "rpm": f"{rr:.0f}",
                    "sfm": f"{ss:.1f}",
                    "ipr": f"{ipr_out:.4f}",
                    "ipm": f"{ipm_out:.3f}",
                    "hp_req": f"{hp_req:.2f}" if hp_req is not None else None,
                    "hp_avail": f"{hp_avail:.2f}" if hp_avail else None,
                }

                session["lathe_drill_last"] = {
                    "machine": machine,
                    "drill_drive": drill_drive,
                    "drill_material": drill_material,
                    "drill_diameter": drill_diameter,
                    "drill_sfm": drill_sfm,
                    "drill_rpm": drill_rpm,
                    "drill_ipr": drill_ipr,
                    "drill_ipm": drill_ipm,
                }

                # also keep machine sticky for main page
                session.setdefault("lathe_last", {})["machine"] = machine

            except Exception as e:
                error = str(e)

    return render_template_string(
        LATHE_TEMPLATE,
        machines=machines,
        machine=machine,
        # main
        diameter=diameter, sfm=sfm, rpm=rpm, ipr=ipr, ipm=ipm,
        material=material, insert=insert,
        materials=list(MATERIALS.keys()),
        inserts=list(INSERTS.keys()),
        results=results,
        warnings=warnings,
        rec=rec,
        error=error,
        # drill
        drill_drive=drill_drive,
        drill_materials=list(DRILL_MATERIALS.keys()),
        drill_material=drill_material,
        drill_diameter=drill_diameter,
        drill_sfm=drill_sfm,
        drill_rpm=drill_rpm,
        drill_ipr=drill_ipr,
        drill_ipm=drill_ipm,
        drill_rec=drill_rec,
        drill_results=drill_results,
        drill_warnings=drill_warnings,
    )


@app.route("/mill", methods=["GET", "POST"])
def mill():
    error = None
    results = None
    warnings = []
    mill_rec = None

    machines = [k for k, v in MACHINES.items() if v.get("type") == "mill"]
    machine = default_machine_name("mill")

    # main mill fields
    diameter = ""
    sfm = ""
    rpm = ""
    flutes = "4"
    chipload = ""
    ipm = ""
    material = ""

    # drill fields
    drill_results = None
    drill_warnings = []
    drill_material = ""
    drill_diameter = ""
    drill_sfm = ""
    drill_rpm = ""
    drill_ipr = ""
    drill_ipm = ""

    if request.method == "GET":
        last = session.get("mill_last", {})
        machine = last.get("machine", machine)
        diameter = last.get("diameter", "")
        sfm = last.get("sfm", "")
        rpm = last.get("rpm", "")
        flutes = last.get("flutes", "4")
        chipload = last.get("chipload", "")
        ipm = last.get("ipm", "")
        material = last.get("material", "")

        dlast = session.get("mill_drill_last", {})
        drill_material = dlast.get("drill_material", "")
        drill_diameter = dlast.get("drill_diameter", "")
        drill_sfm = dlast.get("drill_sfm", "")
        drill_rpm = dlast.get("drill_rpm", "")
        drill_ipr = dlast.get("drill_ipr", "")
        drill_ipm = dlast.get("drill_ipm", "")

    if request.method == "POST":
        mode = request.form.get("mode", "mill_main")
        machine = request.form.get("machine", machine)

        if mode == "mill_main":
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
                    "rpm": f"{r:.0f}",
                    "sfm": f"{s:.1f}",
                    "chipload": f"{c:.4f}",
                    "ipm": f"{feed_ipm:.2f}",
                }

                session["mill_last"] = {
                    "machine": machine,
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

            try:
                dd = to_float(drill_diameter)
                ds = to_float(drill_sfm)
                dr = to_float(drill_rpm)
                dipr = to_float(drill_ipr)
                dipm = to_float(drill_ipm)

                if not dd or dd <= 0:
                    raise ValueError("Drill diameter is required and must be > 0.")

                rr, ss, ipr_out, ipm_out = compute_lathe_style(dd, ds, dr, dipr, dipm)

                # machine spindle limits
                mspec = MACHINES.get(machine, {})
                rpm_limit = mspec.get("spindle_max_rpm", 0) or 0
                hp_avail = mspec.get("spindle_hp", 0.0) or 0.0

                if drill_material in DRILL_MATERIALS:
                    sfm_min = DRILL_MATERIALS[drill_material]["sfm_min"]
                    sfm_max = DRILL_MATERIALS[drill_material]["sfm_max"]
                    ipr_min = DRILL_MATERIALS[drill_material]["ipr_min"]
                    ipr_max = DRILL_MATERIALS[drill_material]["ipr_max"]

                    if ss < sfm_min:
                        drill_warnings.append("SFM is below typical range (may rub).")
                    if ss > sfm_max:
                        drill_warnings.append("SFM is above typical range (may burn/wear drill).")
                    if ipr_out < ipr_min:
                        drill_warnings.append("IPR is light (may rub/work-harden depending on material).")
                    if ipr_out > ipr_max:
                        drill_warnings.append("IPR is heavy (watch load/chip packing).")

                if rpm_limit and rr > rpm_limit:
                    drill_warnings.append(f"Spindle RPM limit is {rpm_limit:.0f}. Your drill RPM ({rr:.0f}) exceeds it.")

                hp_req = drilling_hp_required(dd, ipm_out, drill_material)
                if hp_req is not None and hp_avail:
                    if hp_req > hp_avail * 0.90:
                        drill_warnings.append(
                            f"Estimated load is HIGH (HP req ~{hp_req:.2f} vs avail {hp_avail:.2f}). "
                            "Reduce IPR/SFM or use a smaller drill / peck strategy."
                        )

                drill_results = {
                    "rpm": f"{rr:.0f}",
                    "sfm": f"{ss:.1f}",
                    "ipr": f"{ipr_out:.4f}",
                    "ipm": f"{ipm_out:.3f}",
                    "hp_req": f"{hp_req:.2f}" if hp_req is not None else None,
                    "hp_avail": f"{hp_avail:.2f}" if hp_avail else None,
                }

                session["mill_drill_last"] = {
                    "machine": machine,
                    "drill_material": drill_material,
                    "drill_diameter": drill_diameter,
                    "drill_sfm": drill_sfm,
                    "drill_rpm": drill_rpm,
                    "drill_ipr": drill_ipr,
                    "drill_ipm": drill_ipm,
                }

                session.setdefault("mill_last", {})["machine"] = machine

            except Exception as e:
                error = str(e)

    return render_template_string(
        MILL_TEMPLATE,
        machines=machines,
        machine=machine,
        diameter=diameter, sfm=sfm, rpm=rpm,
        flutes=flutes, chipload=chipload, ipm=ipm,
        material=material,
        mill_materials=list(MILL_MATERIALS.keys()),
        mill_rec=mill_rec,
        warnings=warnings,
        results=results,
        error=error,
        drill_materials=list(DRILL_MATERIALS.keys()),
        drill_material=drill_material,
        drill_diameter=drill_diameter,
        drill_sfm=drill_sfm,
        drill_rpm=drill_rpm,
        drill_ipr=drill_ipr,
        drill_ipm=drill_ipm,
        drill_results=drill_results,
        drill_warnings=drill_warnings,
    )


if __name__ == "__main__":
    app.run(debug=True)
