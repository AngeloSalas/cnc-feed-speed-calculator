from flask import Flask, request, render_template_string
from cnc.formulas import sfm_from_rpm, rpm_from_sfm, ipm_from_ipr, ipr_from_ipm
from cnc.data import MATERIALS, INSERTS

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CNC Calculator</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 18px; }
    .card { max-width: 640px; margin: 0 auto; padding: 18px; border: 1px solid #ddd; border-radius: 14px; }
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
  <div class="card">
    <h1>Shop CNC Calculator (Lathe)</h1>

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

def to_float(s: str):
    s = (s or "").strip()
    if s == "":
        return None
    return float(s)

@app.route("/", methods=["GET", "POST"])
def home():
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

            # Build recommendation object if selected
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
        TEMPLATE,
        diameter=diameter, sfm=sfm, rpm=rpm, ipr=ipr, ipm=ipm,
        material=material, insert=insert,
        materials=list(MATERIALS.keys()),
        inserts=list(INSERTS.keys()),
        results=results,
        warnings=warnings,
        rec=rec,
        error=error
    )

if __name__ == "__main__":
    app.run(debug=True)
