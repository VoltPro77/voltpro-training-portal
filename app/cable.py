"""Cable-sizing calculator engine + page, following the AS/NZS 3008.1.1 methodology.

Sizes a cable two ways and takes the larger required size:
  1. Current-carrying capacity — the derated table rating must carry the design current.
  2. Voltage drop — the volt-drop over the run must be within the allowable %.

Formulas (AS/NZS 3008.1.1):
  Design current  I_b:
    3-phase:  I = P / (√3 · V · pf)        (P in watts)   |  S / (√3 · V)  for kVA
    1-phase:  I = P / (V · pf)             |  S / V        for kVA
  Voltage drop:
    1-phase:  Vd = I · L · (mV/A/m)_1φ / 1000
    3-phase:  Vd = I · L · (mV/A/m)_3φ / 1000
  Current capacity: required base rating = I_b / (temp_factor · group_factor).

All numeric table values come from cable_data.py, which is DRAFT and must be verified
against AS/NZS 3008 — see the disclaimer shown on the page. This tool is a guide only.
"""
import math

from flask import Blueprint, render_template, request
from flask_login import login_required

from . import cable_data as cd

bp = Blueprint("cable", __name__)


def design_current(phases, voltage, rating_value, rating_unit, power_factor):
    """Return design current I_b in amps, or None if inputs are insufficient."""
    if voltage <= 0 or rating_value <= 0:
        return None
    unit = rating_unit.lower()

    if unit == "a":
        return rating_value

    # Normalise to watts (real) or VA (apparent).
    if unit == "kw":
        watts = rating_value * 1000.0
    elif unit == "hp":
        watts = rating_value * 746.0
    elif unit == "kva":
        va = rating_value * 1000.0
    else:
        return None

    if phases == "3":
        root3 = math.sqrt(3)
        if unit == "kva":
            return va / (root3 * voltage)
        pf = power_factor if power_factor and power_factor > 0 else 0.8
        return watts / (root3 * voltage * pf)
    else:  # single phase (and dc handled as 1-phase resistive)
        if unit == "kva":
            return va / voltage
        pf = power_factor if power_factor and power_factor > 0 else 0.8
        return watts / (voltage * pf)


def size_by_current(conductor, insulation, method, i_b, temp_factor, grp_factor):
    """Smallest size whose derated rating carries i_b. Returns (size, base_rating, derated)."""
    table = cd.CURRENT_RATINGS.get((conductor, insulation, method))
    if not table:
        return None, None, None
    k = temp_factor * grp_factor
    for size in cd.SIZES:
        base = table.get(size)
        if base is None:
            continue
        if base * k >= i_b:
            return size, base, round(base * k, 1)
    return None, None, None


def size_by_voltage_drop(conductor, phases, voltage, i_b, length_m, max_vd_pct):
    """Smallest size whose voltage drop is within max_vd_pct. Returns (size, vd_volts, vd_pct)."""
    table = cd.VOLTAGE_DROP_MVAM.get(conductor)
    if not table:
        return None, None, None
    key = "three" if phases == "3" else "single"
    limit_volts = voltage * max_vd_pct / 100.0
    for size in cd.SIZES:
        row = table.get(size)
        if not row or key not in row:
            continue
        mvam = row[key]
        vd = mvam * i_b * length_m / 1000.0
        if vd <= limit_volts:
            return size, round(vd, 2), round(vd / voltage * 100, 2)
    return None, None, None


def calculate(form):
    warnings = []

    phases = form.get("phases", "3")
    try:
        voltage = float(form.get("voltage") or 0)
        rating_value = float(form.get("rating_value") or 0)
        length_m = float(form.get("length_m") or 0)
        max_vd_pct = float(form.get("max_vd_pct") or 2.5)
        power_factor = float(form.get("power_factor") or 0.8)
        circuits = int(float(form.get("circuits") or 1))
        ambient = float(form.get("ambient") or 40)
    except ValueError:
        return {"error": "Please enter valid numbers in all fields."}

    rating_unit = form.get("rating_unit", "A")
    conductor = form.get("conductor", "cu")
    insulation = form.get("insulation", "V-90")
    method = form.get("method", "conduit")

    i_b = design_current(phases, voltage, rating_value, rating_unit, power_factor)
    if i_b is None:
        return {"error": "Enter a voltage and a load rating greater than zero."}
    i_b = round(i_b, 1)

    temp_factor, temp_row = cd.nearest_temp_factor(insulation, ambient)
    grp_factor = cd.group_factor(circuits)

    cc_size, cc_base, cc_derated = size_by_current(
        conductor, insulation, method, i_b, temp_factor, grp_factor
    )
    if cc_size is None:
        warnings.append(
            "Current capacity exceeds the largest cable in this DRAFT table (300mm²) "
            "for the chosen method — consider parallel cables, a different install "
            "method, or verify/extend the table."
        )

    vd_size, vd_volts, vd_pct = size_by_voltage_drop(
        conductor, phases, voltage, i_b, length_m, max_vd_pct
    )
    if vd_size is None:
        warnings.append(
            "Voltage drop can't be met within 300mm² for this run length — consider "
            "parallel cables or a shorter run."
        )

    # Governing size = larger of the two requirements.
    final_size = None
    governed_by = None
    if cc_size and vd_size:
        if cc_size >= vd_size:
            final_size, governed_by = cc_size, "current capacity"
        else:
            final_size, governed_by = vd_size, "voltage drop"
    elif cc_size:
        final_size, governed_by = cc_size, "current capacity"
    elif vd_size:
        final_size, governed_by = vd_size, "voltage drop"

    # Recompute the actual voltage drop AT the final chosen size for the report.
    final_vd_pct = None
    if final_size:
        vtable = cd.VOLTAGE_DROP_MVAM.get(conductor, {})
        row = vtable.get(final_size)
        if row:
            key = "three" if phases == "3" else "single"
            mvam = row.get(key)
            if mvam:
                final_vd = mvam * i_b * length_m / 1000.0
                final_vd_pct = round(final_vd / voltage * 100, 2)

    return {
        "i_b": i_b,
        "temp_factor": temp_factor,
        "temp_row": temp_row,
        "grp_factor": grp_factor,
        "circuits": circuits,
        "cc_size": cc_size,
        "cc_base": cc_base,
        "cc_derated": cc_derated,
        "vd_size": vd_size,
        "vd_volts": vd_volts,
        "vd_pct": vd_pct,
        "max_vd_pct": max_vd_pct,
        "final_size": final_size,
        "governed_by": governed_by,
        "final_vd_pct": final_vd_pct,
        "warnings": warnings,
        "inputs": {
            "phases": phases,
            "voltage": voltage,
            "rating_value": rating_value,
            "rating_unit": rating_unit,
            "length_m": length_m,
            "conductor": conductor,
            "insulation": insulation,
            "method": method,
            "power_factor": power_factor,
            "ambient": ambient,
        },
    }


@bp.route("/calculator", methods=["GET", "POST"])
@login_required
def calculator():
    result = calculate(request.form) if request.method == "POST" else None
    return render_template(
        "calculator.html",
        result=result,
        form=request.form,
        install_methods=cd.INSTALL_METHODS,
        insulations=cd.INSULATIONS,
        conductors=cd.CONDUCTORS,
    )
