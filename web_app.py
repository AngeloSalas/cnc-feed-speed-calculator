from flask import Flask, request, render_template_string, redirect, url_for
from cnc.formulas import (
    sfm_from_rpm, rpm_from_sfm, ipm_from_ipr, ipr_from_ipm,
    ipm_from_chipload, chipload_from_ipm
)
from cnc.data import MATERIALS, INSERTS

app = Flask(__name__)

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
    .topbar { max-width: 740px; margin: 0 auto 10px; display:flex; justify-content:space-between; align-items:center; }
    .topbar a { text-decoration:none; font-size: 14px; }
    .card { max-width: 740px; margin: 0 auto; padding: 18px; border: 1px solid #ddd; border-radius: 14px; }
    h1 { font-size: 22px; margin: 0 0 14px; }
    label { display:block; margin-top: 12px; font-size: 14px; }
    input, select { width: 100%; padding: 14px; font-size: 18px; margin-top: 6px; border-radius: 10px; border: 1px solid #ccc; }
    button { width: 100%; padding: 16px; font-size: 18px; margin-top: 14px; border-radius: 12px; border: none; cursor: pointer; }
    .row { display:flex; gap: 12px; }
    .row > div { flex:1; }
    .out { margin-top: 14px; padding: 12px; border-radius: 12px; background:#f6f6f6; font-size: 18px; }
    .warn { margin-top: 10px; padding: 10px; border-radius: 12px; background:#fff6d6; border:1px solid #ffe08a; }
    .small { font-size: 13px; color:#444; margin-top: 8px; }
    .pill { display:inline-block; padding: 6px 10px; border-radius: 999px; background:#eee; font-size: 13px; margin-right: 6px; }
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
          {% for w in warnings %}
            <li>{{w}}</li>
          {% endfor %}
        </ul>
      </div>
    {% endif %}

    {% if error %}
      <div class="out" style="background:#ffecec;border:1px solid #ffb3b3;">
        <b>Error:</b> {{error}}
      </div>
    {% endif %}

    <div class="small">
      Tip: Enter either SFM or RPM. Enter either IPR or IPM. Material/Insert gives recommended ranges.
    </div>
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
    .topbar { max-width: 740px; margin: 0 auto 10px; display:flex; justify-content:space-between; align-items:center; }
    .topbar a { text-decoration:none; font-size: 14px; }
    .card { max-width: 740px; margin: 0 auto; padding: 18px; border: 1px solid #ddd; border-radius: 14px; }
    h1 { font-size: 22px; margin: 0 0 14px; }
    label { display:block; margin-top: 12px; font-size: 14px; }
    input, select { width: 100%; padding: 14px; font-size: 18px; margin-top: 6px; border-radius: 10px; border: 1px solid #ccc; }
    button { width: 100%; padding: 16px; font-size: 18px; margin-top: 14px; border-radius: 12px; border: none; cursor: pointer; }
    .row { display:flex; gap: 12px; }
    .row > div { flex:1; }
    .out { margin-top: 14px; padding: 12px; border-radius: 12px; background:#f6f6f6; font-size: 18px; }
    .small { font-size: 13px; color:#444; margin-top: 8px; }
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

      <button type="submit">Calculate</button>
    </form>

    {% if results %}
      <div class="out">
        <div><b>RPM:</b> {{results.rpm}}</div>
        <div><b>SFM:</b> {{results.sfm}}</div>
        <div><b>Chipload (IPT):</b> {{results.chipload}}</div>
        <div><b>Feed (IPM):</b> {{results.ipm}}</div>
      </div>
    {% endif %}

    {% if error %}
      <div class="out" style="background:#ffecec;border:1px solid #ffb3b3;">
        <b>Error:</b> {{error}}
      </div>
    {% endif %}

    <div class="small">
      Tip: Enter either SFM or RPM. Then enter either Chipload (IPT) or Feed (IPM). We compute the rest.
    </div>
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

    diameter = ""
    sfm = ""
    rpm = ""
    ipr = ""
    ipm = ""
    material = ""
    insert = ""
    rec = None

    if request.method == "POST":
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

            # Recommendations (optional)
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

            # SFM/RPM resolution
            if r is None and s is None:
                raise ValueError("Enter either Target SFM or RPM.")
            if r is None:
                r = rpm_from_sfm(d, s)
            if s is None:
                s = sfm_from_rpm(d, r)

            # Feed resolution
            if f_ipr is None and f_ipm is None:
                raise ValueError("Enter either IPR or IPM.")
            if f_ipm is None:
                f_ipm = ipm_from_ipr(f_ipr, r)
            if f_ipr is None:
                f_ipr = ipr_from_ipm(f_ipm, r)

            # Range warnings
            if sfm_min is not None and (s < sfm_min):
                warnings.append("SFM is below the typical range (may rub / poor finish).")
            if sfm_max is not None and (s > sfm_max):
                warnings.append("SFM is above the typical range (may wear/burn edge).")
            if ipr_min is not None and (f_ipr < ipr_min):
                warnings.append("IPR is below typical range (may rub depending on insert/nose radius).")
            if ipr_max is not None and (f_ipr > ipr_max):
                warnings.append("IPR is above typical range (watch power, chatter, edge).")

            results = {
                "rpm": f"{r:.0f}",
                "sfm": f"{s:.1f}",
                "ipr": f"{f_ipr:.4f}",
                "ipm": f"{f_ipm:.3f}",
            }

        except Exception as e:
            error = str(e)

    return render_template_string(
        LATHE_TEMPLATE,
        diameter=diameter, sfm=sfm, rpm=rpm, ipr=ipr, ipm=ipm,
        material=material, insert=insert,
        materials=list(MATERIALS.keys()),
        inserts=list(INSERTS.keys()),
        results=results,
        warnings=warnings,
        rec=rec,
        error=error
    )

@app.route("/mill", methods=["GET", "POST"])
def mill():
    error = None
    results = None

    diameter = ""
    sfm = ""
    rpm = ""
    flutes = "4"
    chipload = ""
    ipm = ""

    if request.method == "POST":
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

            # SFM/RPM resolution
            if r is None and s is None:
                raise ValueError("Enter either Target SFM or RPM.")
            if r is None:
                r = rpm_from_sfm(d, s)
            if s is None:
                s = sfm_from_rpm(d, r)

            # Chipload/Feed resolution
            if c is None and feed_ipm is None:
                raise ValueError("Enter either Chipload (IPT) or Feed (IPM).")
            if feed_ipm is None:
                feed_ipm = ipm_from_chipload(c, n_flutes, r)
            if c is None:
                c = chipload_from_ipm(feed_ipm, n_flutes, r)

            results = {
                "rpm": f"{r:.0f}",
                "sfm": f"{s:.1f}",
                "chipload": f"{c:.4f}",
                "ipm": f"{feed_ipm:.2f}",
            }

        except Exception as e:
            error = str(e)

    return render_template_string(
        MILL_TEMPLATE,
        diameter=diameter, sfm=sfm, rpm=rpm,
        flutes=flutes, chipload=chipload, ipm=ipm,
        results=results, error=error
    )

if __name__ == "__main__":
    app.run(debug=True)
