import pandas as pd
import streamlit as st
from dataclasses import dataclass
from typing import List

st.set_page_config(page_title="Narcotics Diversion Calculator", layout="wide")

# ---------- Defaults / thresholds ----------
MG_THRESHOLD = 5.0   # absolute discrepancy mg
ML_THRESHOLD = 1.0   # absolute discrepancy mL


# ---------- Data model ----------
@dataclass
class ReconciliationInput:
    drug_name: str
    vial_total_mg: float    # internal mass in mg
    vial_total_ml: float    # total volume in mL
    delivered_mg_list: List[float]  # "Total Drug" entries, internal mg
    priming_ml: float
    waste_ml: float
    remaining_ml: float     # measured remaining mL


def reconcile_one(inp: ReconciliationInput):
    if inp.vial_total_ml <= 0:
        raise ValueError("Total vial mL must be > 0")

    mg_per_mL = inp.vial_total_mg / inp.vial_total_ml
    delivered_total_mg = sum(v for v in inp.delivered_mg_list if pd.notna(v))
    priming_mg = inp.priming_ml * mg_per_mL
    waste_mg = inp.waste_ml * mg_per_mL
    accounted_total_mg = delivered_total_mg + priming_mg + waste_mg

    expected_remaining_mg = round(inp.vial_total_mg - accounted_total_mg, 4)
    expected_remaining_mL = round(expected_remaining_mg / mg_per_mL, 4)

    entered_remaining_mL = round(inp.remaining_ml, 4)
    entered_remaining_mg = round(inp.remaining_ml * mg_per_mL, 4)

    discrepancy_mg = round(entered_remaining_mg - expected_remaining_mg, 4)
    discrepancy_mL = round(entered_remaining_mL - expected_remaining_mL, 4)

    exceed = (abs(discrepancy_mg) > MG_THRESHOLD) or (abs(discrepancy_mL) > ML_THRESHOLD)
    recommendation = (
        "Recommend getting statement from RNs involved in medication administration"
        if exceed else "No action required"
    )

    return {
        "mg_per_mL": round(mg_per_mL, 6),
        "Delivered_total_mg": round(delivered_total_mg, 4),
        "Priming_mL": round(inp.priming_ml, 4),
        "Priming_mg": round(priming_mg, 4),
        "Waste_mL": round(inp.waste_ml, 4),
        "Waste_mg": round(waste_mg, 4),
        "Accounted_total_mg": round(accounted_total_mg, 4),
        "Vial_total_mg": round(inp.vial_total_mg, 4),
        "Expected_remaining_mg": expected_remaining_mg,
        "Expected_remaining_mL": expected_remaining_mL,
        "Entered_remaining_mL": entered_remaining_mL,
        "Entered_remaining_mg": entered_remaining_mg,
        "Discrepancy_mg": discrepancy_mg,
        "Discrepancy_mL": discrepancy_mL,
        "Threshold_exceeded": exceed,
        "Recommendation": recommendation,
    }


# ---------- Helpers ----------
def parse_editor_numbers(series: pd.Series) -> List[float]:
    """Extract floats from the data editor column (ignore blanks/NaN)."""
    if series is None:
        return []
    try:
        return [float(x) for x in series.dropna().tolist()]
    except Exception:
        out = []
        for x in series:
            try:
                out.append(float(x))
            except Exception:
                pass
        return out


def to_display_mass(mg_value: float, unit_to_mg: float) -> float:
    """Convert internal mg to display unit (mg or mcg)."""
    if unit_to_mg <= 0:
        return float("nan")
    return round(mg_value / unit_to_mg, 4)


def concentration_label(total_mass_display: float, total_ml: float, unit: str, unit_to_mg: float) -> str:
    """Friendly label like '100 mg / 20 mL (5 mg/mL)' or '2500 mcg / 50 mL (50 mcg/mL, 0.05 mg/mL)'."""
    mg_per_mL = (total_mass_display * unit_to_mg) / total_ml
    main = f"{total_mass_display:g} {unit} / {total_ml:g} mL"
    if unit.lower() == "mg":
        return f"{main}  ({mg_per_mL:.6f} mg/mL)"
    else:
        mcg_per_mL = mg_per_mL / 0.001  # mg/mL -> mcg/mL
        return f"{main}  ({mcg_per_mL:.6f} {unit}/mL, {mg_per_mL:.6f} mg/mL)"


def render_calculator(
    drug_name: str,
    total_mass_display: float,  # in display unit (e.g., 2500 for mcg fentanyl)
    total_ml: float,
    unit: str,                  # "mg" or "mcg" (for labels)
    unit_to_mg: float,          # 1 for mg; 0.001 for mcg
):
    st.subheader(drug_name)
    st.caption(concentration_label(total_mass_display, total_ml, unit, unit_to_mg))

    st.markdown(f"**Total Drug ({unit})** – add rows or edit values as needed")
    editor = st.data_editor(
        pd.DataFrame({f"TotalDrug_{unit}": [0.0]}),
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{drug_name}",
    )
    # Convert the display-unit entries to internal mg:
    delivered_display = parse_editor_numbers(editor.get(f"TotalDrug_{unit}"))
    delivered_mg_list = [x * unit_to_mg for x in delivered_display]

    priming_ml = st.number_input(f"Priming (mL) – {drug_name}", min_value=0.0, value=0.0, step=0.1, key=f"prim_{drug_name}")
    waste_ml = st.number_input(f"Waste (mL) – {drug_name}", min_value=0.0, value=0.0, step=0.1, key=f"waste_{drug_name}")
    remaining_ml = st.number_input(f"Measured remaining (mL) – {drug_name}", min_value=0.0, value=0.0, step=0.1, key=f"rem_{drug_name}")

    if st.button(f"Calculate {drug_name}", type="primary", key=f"calc_{drug_name}"):
        inp = ReconciliationInput(
            drug_name=drug_name,
            vial_total_mg=total_mass_display * unit_to_mg,
            vial_total_ml=total_ml,
            delivered_mg_list=delivered_mg_list,
            priming_ml=priming_ml,
            waste_ml=waste_ml,
            remaining_ml=remaining_ml,
        )
        res = reconcile_one(inp)

        # Metrics (top line)
        m1, m2, m3, m4 = st.columns(4)
        display_conc_per_mL = total_mass_display / total_ml
        m1.metric(f"{unit}/mL", f"{display_conc_per_mL:.6f}")
        m2.metric("Total Drug (mg)", res["Delivered_total_mg"])
        m3.metric("Priming (mg)", res["Priming_mg"])
        m4.metric("Waste (mg)", res["Waste_mg"])

        # -------- Vertical layout for Remaining vs Expected (mobile-friendly) --------
        st.markdown("### Remaining vs Expected")

        # A simple vertical, single-column “card” with bold labels and bullets
        st.markdown(
            f"""
**Expected Remaining**
• {res["Expected_remaining_mL"]} mL  
• {to_display_mass(res["Expected_remaining_mg"], unit_to_mg)} {unit}

**Entered Remaining**
• {res["Entered_remaining_mL"]} mL  
• {to_display_mass(res["Entered_remaining_mg"], unit_to_mg)} {unit}

**Discrepancy**
• {res["Discrepancy_mL"]} mL  
• {to_display_mass(res["Discrepancy_mg"], unit_to_mg)} {unit}

**Threshold exceeded (>|5 mg| or >1 mL):** {'Yes' if res["Threshold_exceeded"] else 'No'}

**Recommendation:** {res["Recommendation"]}
            """.strip()
        )

        # Threshold transparency
        st.info(
            f"**Thresholds:** 5 mg (={to_display_mass(5.0, unit_to_mg)} {unit}) OR 1 mL. "
            f"You can adjust thresholds in the left sidebar."
        )


# ---------- App layout ----------
st.title("Narcotics Diversion Calculator – Remaining Volume")
st.caption("Enter Total Drug entries (mg/mcg), Priming/Waste (mL), and Measured Remaining (mL) to compare against Expected Remaining.")

with st.sidebar:
    st.header("Settings (applies to all tabs)")
    mg_thr = st.number_input("MG threshold", min_value=0.0, value=MG_THRESHOLD, step=0.5, help="Absolute discrepancy in mg")
    ml_thr = st.number_input("mL threshold", min_value=0.0, value=ML_THRESHOLD, step=0.1, help="Absolute discrepancy in mL")
MG_THRESHOLD = float(mg_thr)
ML_THRESHOLD = float(ml_thr)

st.markdown("---")

tabs = st.tabs(["Ketamine", "Morphine", "Fentanyl", "Dilaudid"])

with tabs[0]:
    # Ketamine 100 mg / 20 mL
    render_calculator(
        drug_name="Ketamine",
        total_mass_display=100.0,
        total_ml=20.0,
        unit="mg",
        unit_to_mg=1.0,
    )

with tabs[1]:
    # Morphine 30 mg / 30 mL
    render_calculator(
        drug_name="Morphine",
        total_mass_display=30.0,
        total_ml=30.0,
        unit="mg",
        unit_to_mg=1.0,
    )

with tabs[2]:
    # Fentanyl 2500 mcg / 50 mL  (internal = 2.5 mg; unit_to_mg = 0.001)
    render_calculator(
        drug_name="Fentanyl",
        total_mass_display=2500.0,
        total_ml=50.0,
        unit="mcg",
        unit_to_mg=0.001,
    )

with tabs[3]:
    # Dilaudid (hydromorphone) 25 mg / 50 mL
    render_calculator(
        drug_name="Dilaudid (hydromorphone)",
        total_mass_display=25.0,
        total_ml=50.0,
        unit="mg",
        unit_to_mg=1.0,
    )

st.markdown("---")
st.caption(
    "This tool supports reconciliation and policy workflows and does not replace clinical judgment or hospital policy. "
    "Thresholds are evaluated in mg and mL; the Fentanyl tab displays equivalent mcg values for clarity."
)
