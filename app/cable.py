"""Cable-sizing calculator engine + page, following the AS/NZS 3008.1.1 methodology.

Sizes a cable two ways and takes the larger required size:
  1. Current-carrying capacity — the derated table rating must carry the design current.
  2. Voltage drop — the volt-drop over the run must be within the allowable %.

Design current I_b:
  Amps: entered directly.
  kVA:  3-phase I = S / (√3 · V)   |   1-phase I = S / V.   (no power factor needed)
Voltage drop:
  1-phase: Vd = I · L · (mV/A/m)_1φ / 1000
  3-phase: Vd = I · L · (mV/A/m)_3φ / 1000
Current capacity: required base rating = I_b / grouping_factor  (base ambient 40 °C).

All numeric table values come from cable_data.py, which is DRAFT and must be verified
against AS/NZS 3008 — see the disclaimer on the page. This tool is a guide only. Where no
rating table is loaded for a chosen conductor/insulation/method, the current-capacity check
is reported as NOT DONE rather than guessed.
"""
import math

from flask import Blueprint, render_template, request
from flask_login import login_required

from . import cable_data as cd

bp = Blueprint("cable", __name__)


def design_current(phases, voltage, rating_value, rating_unit):
    """Return design current I_b in amps, or None if inputs are insufficient."""
    if voltage <= 0 or rating_value <= 0:
        return None
    unit = rating_unit.lower()
    if unit == "a":
        return rating_value
    if unit == "kva":
        va = rating_value * 1000.0
        if phases == "3":
            return va / (math.sqrt(3) * voltage)
        return va / voltage
    return None


def size_by_current(conductor, insulation, method, i_b, derate_factor):
    """Smallest size whose derated rating carries i_b.
    Returns (size, base_rating, derated, reason) where reason is
    'ok' | 'no_data' | 'exceeds'.
    """
    table = cd.CURRENT_RATINGS.get((conductor, insulation, method))
    if not table:
        return None, None, None, "no_data"
    for size in cd.SIZES:
        base = table.get(size)
        if base is None:
            continue
        if base * derate_factor >= i_b:
            return size, base, round(base * derate_factor, 1), "ok"
    return None, None, None, "exceeds"


def size_by_voltage_drop(conductor, phases, voltage, i_b, length_m, max_vd_pct):
    """Smallest size within the voltage-drop limit.
    Returns (size, vd_volts, vd_pct, reason) — reason 'ok' | 'no_data' | 'exceeds'.
    """
    table = cd.VOLTAGE_DROP_MVAM.get(conductor)
    if not table:
        return None, None, None, "no_data"
    key = "three" if phases == "3" else "single"
    limit_volts = voltage * max_vd_pct / 100.0
    for size in cd.SIZES:
        row = table.get(size)
        if not row or key not in row:
            continue
        vd = row[key] * i_b * length_m / 1000.0
        if vd <= limit_volts:
            return size, round(vd, 2), round(vd / voltage * 100, 2), "ok"
    return None, None, None, "exceeds"


def calculate(form):
    phases = form.get("phases", "3")
    try:
        voltage = float(form.get("voltage") or 0)
        rating_value = float(form.get("rating_value") or 0)
        length_m = float(form.get("length_m") or 0)
        max_vd_pct = float(form.get("max_vd_pct") or 2.5)
        circuits = int(float(form.get("circuits") or 1))
    except ValueError:
        return {"error": "Please enter valid numbers in all fields."}

    rating_unit = form.get("rating_unit", "A")
    conductor = form.get("conductor", "cu")
    insulation = form.get("insulation", "V-90")
    method = form.get("method", "conduit_wall")

    i_b = design_current(phases, voltage, rating_value, rating_unit)
    if i_b is None:
        return {"error": "Enter a voltage and a load (A or kVA) greater than zero."}
    i_b = round(i_b, 1)

    grp_factor = cd.group_factor(circuits)
    warnings = []

    cc_size, cc_base, cc_derated, cc_reason = size_by_current(
        conductor, insulation, method, i_b, grp_factor
    )
    if cc_reason == "no_data":
        warnings.append(
            "⚠ CURRENT CAPACITY NOT CHECKED — no AS/NZS 3008 rating table is loaded for this "
            "conductor / insulation / installation method ({ref}). The size below is the "
            "voltage-drop result ONLY and may be too small for the load current. Add/verify "
            "that table before relying on this.".format(ref=cd.METHOD_TABLE_REF.get(method, "the relevant table"))
        )
    elif cc_reason == "exceeds":
        warnings.append(
            "Current capacity exceeds the largest cable in this DRAFT table (300mm²) for the "
            "chosen method — consider parallel cables or verify/extend the table."
        )

    vd_size, vd_volts, vd_pct, vd_reason = size_by_voltage_drop(
        conductor, phases, voltage, i_b, length_m, max_vd_pct
    )
    if vd_reason == "no_data":
        warnings.append(
            "No voltage-drop (mV/A/m) data loaded for this conductor — verify/add it from "
            "AS/NZS 3008 Tables 40–42."
        )
    elif vd_reason == "exceeds":
        warnings.append(
            "Voltage drop can't be met within 300mm² for this run length — consider parallel "
            "cables or a shorter run."
        )

    # Governing size = larger of the two requirements (only combine when both are real).
    final_size = None
    governed_by = None
    incomplete = cc_reason != "ok"
    if cc_size and vd_size:
        if cc_size >= vd_size:
            final_size, governed_by = cc_size, "current capacity"
        else:
            final_size, governed_by = vd_size, "voltage drop"
    elif cc_size:
        final_size, governed_by = cc_size, "current capacity"
    elif vd_size:
        final_size = vd_size
        governed_by = "voltage drop only (current capacity NOT checked)" if incomplete else "voltage drop"

    final_vd_pct = None
    if final_size:
        row = cd.VOLTAGE_DROP_MVAM.get(conductor, {}).get(final_size)
        if row:
            key = "three" if phases == "3" else "single"
            mvam = row.get(key)
            if mvam:
                final_vd_pct = round(mvam * i_b * length_m / 1000.0 / voltage * 100, 2)

    return {
        "i_b": i_b,
        "grp_factor": grp_factor,
        "circuits": circuits,
        "cc_size": cc_size,
        "cc_base": cc_base,
        "cc_derated": cc_derated,
        "cc_reason": cc_reason,
        "vd_size": vd_size,
        "vd_volts": vd_volts,
        "vd_pct": vd_pct,
        "max_vd_pct": max_vd_pct,
        "final_size": final_size,
        "governed_by": governed_by,
        "final_vd_pct": final_vd_pct,
        "incomplete": incomplete,
        "warnings": warnings,
    }


@bp.route("/calculator", methods=["GET", "POST"])
@login_required
def calculator():
    result = calculate(request.form) if request.method == "POST" else None
    return render_template(
        "calculator.html",
        result=result,
        form=request.form,
        voltages=cd.VOLTAGES,
        install_methods=cd.INSTALL_METHODS,
        insulations=cd.INSULATIONS,
        conductors=cd.CONDUCTORS,
    )
