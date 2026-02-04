import io
from dataclasses import dataclass
from typing import List

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Narcotics Diversion Calculator", layout="wide")

# Global default thresholds (can be adjusted in sidebar)
MG_THRESHOLD = 5.0
ML_THRESHOLD = 1.0


# ---------- Core model ----------
@dataclass
class ReconciliationInput:
    box_id: str
    drug_name: str
    vial_total_mg: float   # total mass in mg (internal standard)
    vial_total_ml: float   # total volume in mL
    delivered_mg_list: List[float]  # list of delivered values in mg (internal)
    priming_ml: float
    waste_ml: float
    remaining_ml: float  # measured remaining volume


def reconcile_one(inp: ReconciliationInput):
    if inp.vial_total_ml <= 0:
        raise ValueError("Total vial mL must be > 0")

    mg_per_ml = inp.vial_total_mg / inp.vial_total_ml
    delivered_total = sum(v for v in inp.delivered_mg_list if pd.notna(v))
    priming_mg = inp.priming_ml * mg_per_ml
    waste_mg = inp.waste_ml * mg_per_ml
    accounted_mg = delivered_total + priming_mg + waste_mg

    expected_remaining_mg = round(inp.vial_total_mg - accounted_mg, 4)
    expected_remaining_ml = round(expected_remaining_mg / mg_per_ml, 4)

    entered_remaining_ml = round(inp.remaining_ml, 4)
    entered_remaining_mg = round(inp.remaining_ml * mg_per_ml, 4)

    discrepancy_mg = round(entered_remaining_mg - expected_remaining_mg, 4)
    discrepancy_ml = round(entered_remaining_ml - expected_remaining_ml, 4)

    exceed = (abs(discrepancy_mg) > MG_THRESHOLD) or (abs(discrepancy_ml) > ML_THRESHOLD)
    recommendation = (
        "Recommend getting statement from RNs involved in medication administration"
        if exceed else "No action required"
    )

    return {
        "mg_per_mL": round(mg_per_ml, 6),  # show more precision for conversions
        "Delivered_total_mg": round(delivered_total, 4),
        "Priming_mL": round(inp.priming_ml, 4),
        "Priming_mg": round(priming_mg, 4),
        "Waste_mL": round(inp.waste_ml, 4),
        "Waste_mg": round(waste_mg, 4),
        "Accounted_total_mg": round(accounted_mg, 4),
        "Vial_total_mg": round(inp.vial_total_mg, 4),
        "Expected_remaining_mg": expected_remaining_mg,
        "Expected_remaining_ML": expected_remaining_ml,
        "Entered_remaining_mL": entered_remaining_ml,
        "Entered_remaining_mg": entered_remaining_mg,
        "Discrepancy_mg": discrepancy_mg,
        "Discrepancy_ML": discrepancy_ml,
        "Threshold_exceeded": exceed,
        "Recommendation": recommendation,
    }


# ---------- Helpers ----------
def parse_delivered_series_to_list(cell) -> List[float]:
    """
    Accepts a cell that might be numeric or a comma/semicolon-separated string.
    Returns a list of floats. Non-parsable tokens are ignored.
    """
    if pd.isna(cell):
        return []
    if isinstance(cell, (int, float)):
        return [float(cell)]
    vals = []
    for t in str(cell).replace(",", ";").split(";"):
        t = t.strip()
        if not t:
            continue
        try:
            vals.append(float(t))
        except ValueError:
            pass
    return vals


def to_display_mass(mg_value: float, unit_to_mg: float) -> float:
    """Convert an internal mg value to the display unit."""
    if unit_to_mg <= 0:
        return float("nan")
    return round(mg_value / unit_to_mg, 4)  # e.g., mg->mcg divide by 0.001 = *1000


def concentration_labels(total_mass_display: float, total_ml: float, unit: str, unit_to_mg: float) -> str:
    """Builds a friendly concentration label like '100 mg / 20 mL (5 mg/mL)' or '2500 mcg / 50 mL (50 mcg/mL, 0.05 mg/mL)'."""
    mg_per_ml = (total_mass_display * unit_to_mg) / total_ml
    main = f"{total_mass_display:g} {unit} / {total_ml:g} mL"
    if unit.lower() == "mg":
        return f"{main}  ({mg_per_ml:.6f} mg/mL)"
    else:
        # e.g., mcg tab: also show both mcg/mL and mg/mL for clarity
        mcg_per_ml = mg_per_ml / 0.001  # mg/mL -> mcg/mL
        return f"{main}  ({mcg_per_ml:.6f} {unit}/mL, {mg_per_ml:.6f} mg/mL)"


def render_drug_tab(
    drug_name: str,
    total_mass_display: float,  # mass in the displayed unit (e.g., 2500 for mcg fentanyl)
    total_ml: float,
    unit: str,                  # "mg" or "mcg" (display + input unit for delivered)
    unit_to_mg: float,          # 1 for mg, 0.001 for mcg
):
    st.subheader(drug_name)
    st.caption(concentration_labels(total_mass_display, total_ml, unit, unit_to_mg))

    col_left, col_right = st.columns(2)

    # ---- Left: Single-box interactive ----
    with col_left:
        st.markdown("**Single Box – Interactive**")

        box_id = st.text_input(f"{drug_name} • Box ID", value=f"{drug_name[:3].upper()}-001")
        st.markdown(f"**Delivered ({unit})** – add rows or edit values below")
        delivered_df = st.data_editor(
            pd.DataFrame({f"Delivered_{unit}": [5.0]}),  # minimal starter row
            num_rows="dynamic",
            use_container_width=True,
            key=f"delivered_{drug_name}",
        )
        delivered_list_display = delivered_df[f"Delivered_{unit}"].dropna().astype(float).tolist()
        # Convert display unit -> mg (internal)
        delivered_list_mg = [x * unit_to_mg for x in delivered_list_display]

        priming_ml = st.number_input(f"Priming (mL) – {drug_name}", min_value=0.0, value=0.0, step=0.1, key=f"prim_{drug_name}")
        waste_ml = st.number_input(f"Waste (mL) – {drug_name}", min_value=0.0, value=0.0, step=0.1, key=f"waste_{drug_name}")
        remaining_ml = st.number_input(f"Measured remaining (mL) – {drug_name}", min_value=0.0, value=0.0, step=0.1, key=f"rem_{drug_name}")

        if st.button(f"Calculate {drug_name}", type="primary", key=f"calc_{drug_name}"):
            inp = ReconciliationInput(
                box_id=box_id,
                drug_name=drug_name,
                vial_total_mg=total_mass_display * unit_to_mg,
                vial_total_ml=total_ml,
                delivered_mg_list=delivered_list_mg,
                priming_ml=priming_ml,
                waste_ml=waste_ml,
                remaining_ml=remaining_ml,
            )
            res = reconcile_one(inp)

            # Metrics
            met1, met2, met3 = st.columns(3)
            # Also show concentration in display unit per mL
            disp_per_ml = (total_mass_display) / total_ml
            met1.metric(f"{unit}/mL", f"{disp_per_ml:.6f}")
            met2.metric("Delivered total (mg)", res["Delivered_total_mg"])
            met3.metric("Accounted total (mg)", res["Accounted_total_mg"])

            # Remaining vs Expected (show in mL and in display unit)
            st.markdown("### Remaining vs Expected")
            table = pd.DataFrame([{
                "Expected remaining (mL)": res["Expected_remaining_ML"],
                f"Expected remaining ({unit})": to_display_mass(res["Expected_remaining_mg"], unit_to_mg),
                "Entered remaining (mL)": res["Entered_remaining_ML"],
                f"Entered remaining ({unit})": to_display_mass(res["Entered_remaining_mg"], unit_to_mg),
                f"Discrepancy ({unit})": to_display_mass(res["Discrepancy_mg"], unit_to_mg),
                "Discrepancy (mL)": res["Discrepancy_ML"],
                "Threshold exceeded (>|5 mg| or >1 mL)": res["Threshold_exceeded"],
                "Recommendation": res["Recommendation"],
            }])
            st.dataframe(table, use_container_width=True)

            # Show also the mg thresholds converted to display unit for transparency
            thr_col1, thr_col2 = st.columns(2)
            with thr_col1:
                st.info(f"**Thresholds:** 5 mg (={to_display_mass(5.0, unit_to_mg)} {unit}) OR 1 mL")

    # ---- Right: Batch CSV upload ----
    with col_right:
        st.markdown("**Batch – CSV Upload**")
        st.write(
            f"CSV header required: `BoxID,Delivered_{unit},Priming_mL,Waste_mL,Remaining_mL`  "
            f"(This tab uses **{drug_name}** defaults for concentration: {concentration_labels(total_mass_display, total_ml, unit, unit_to_mg)})"
        )
        uploaded = st.file_uploader(f"Upload CSV for {drug_name}", type=["csv"], key=f"uploader_{drug_name}")

        if uploaded is not None:
            df = pd.read_csv(uploaded)

            out_rows = []
            for i, row in df.iterrows():
                box_id = str(row.get("BoxID") or f"Row{i+1}")
                delivered_cell = row.get(f"Delivered_{unit}")
                delivered_list_disp = parse_delivered_series_to_list(delivered_cell)
                delivered_list_mg = [x * unit_to_mg for x in delivered_list_disp]

                prim_ml = float(row.get("Priming_mL") or 0.0)
                wst_ml = float(row.get("Waste_mL") or 0.0)
                rem_ml = float(row.get("Remaining_mL") or 0.0)

                inp = ReconciliationInput(
                    box_id=box_id,
                    drug_name=drug_name,
                    vial_total_mg=total_mass_display * unit_to_mg,
                    vial_total_ml=total_ml,
                    delivered_mg_list=delivered_list_mg,
                    priming_ml=prim_ml,
                    waste_ml=wst_ml,
                    remaining_ml=rem_ml,
                )
                try:
                    res = reconcile_one(inp)
                    out_rows.append({
                        "BoxID": box_id,
                        "DrugName": drug_name,
                        f"Delivered_total_{unit}": sum(delivered_list_disp),
                        "Priming_mL": res["Priming_mL"],
                        f"Priming_{unit}": to_display_mass(res["Priming_mg"], unit_to_mg),
                        "Waste_mL": res["Waste_mL"],
                        f"Waste_{unit}": to_display_mass(res["Waste_mg"], unit_to_mg),
                        "Accounted_total_mg": res["Accounted_total_mg"],
                        f"Accounted_total_{unit}": to_display_mass(res["Accounted_total_mg"], unit_to_mg),
                        "Vial_total_mg": res["Vial_total_mg"],
                        f"Vial_total_{unit}": to_display_mass(res["Vial_total_mg"], unit_to_mg),
                        "Expected_remaining_mL": res["Expected_remaining_ML"],
                        f"Expected_remaining_{unit}": to_display_mass(res["Expected_remaining_mg"], unit_to_mg),
                        "Entered_remaining_mL": res["Entered_remaining_ML"],
                        f"Entered_remaining_{unit}": to_display_mass(res["Entered_remaining_mg"], unit_to_mg),
                        f"Discrepancy_{unit}": to_display_mass(res["Discrepancy_mg"], unit_to_mg),
                        "Discrepancy_mL": res["Discrepancy_ML"],
                        "Threshold_exceeded": res["Threshold_exceeded"],
                        "Recommendation": res["Recommendation"],
                    })
                except Exception as e:
                    out_rows.append({
                        "BoxID": box_id,
                        "DrugName": drug_name,
                        "Error": str(e),
                        "Recommendation": "Check input row formatting/values"
                    })

            out_df = pd.DataFrame(out_rows)
            st.dataframe(out_df, use_container_width=True)

            # Download button
            csv_buf = io.StringIO()
            out_df.to_csv(csv_buf, index=False)
            st.download_button(
                label=f"Download {drug_name} results CSV",
                data=csv_buf.getvalue(),
                file_name=f"{drug_name.lower().replace(' ', '_')}_results.csv",
                mime="text/csv",
                key=f"dl_{drug_name}"
            )


# ---------- UI FRAME ----------
st.title("Narcotics Diversion Calculator – Remaining Volume")
st.caption("Enter Delivered doses, Priming/Waste, and Measured Remaining to compare against Expected Remaining.")

with st.sidebar:
    st.header("Settings")
    st.write("Thresholds apply across all tabs:")
    mg_thr = st.number_input("MG threshold (default 5 mg)", min_value=0.0, value=MG_THRESHOLD, step=0.5, help="Absolute discrepancy in mg")
    ml_thr = st.number_input("mL threshold (default 1 mL)", min_value=0.0, value=ML_THRESHOLD, step=0.1, help="Absolute discrepancy in mL")

# Update globals from sidebar
MG_THRESHOLD = float(mg_thr)
ML_THRESHOLD = float(ml_thr)

st.markdown("---")

# Create tabs for the four meds with their standard concentrations
tabs = st.tabs(["Ketamine", "Morphine", "Fentanyl", "Dilaudid"])

with tabs[0]:
    # Ketamine 100 mg / 20 mL
    render_drug_tab(
        drug_name="Ketamine",
        total_mass_display=100.0,
        total_ml=20.0,
        unit="mg",
        unit_to_mg=1.0
    )

with tabs[1]:
    # Morphine 30 mg / 30 mL
    render_drug_tab(
        drug_name="Morphine",
        total_mass_display=30.0,
        total_ml=30.0,
        unit="mg",
        unit_to_mg=1.0
    )

with tabs[2]:
    # Fentanyl 2500 mcg / 50 mL
    # Internally we use mg, so 2500 mcg = 2.5 mg; unit_to_mg = 0.001
    render_drug_tab(
        drug_name="Fentanyl",
        total_mass_display=2500.0,
        total_ml=50.0,
        unit="mcg",
        unit_to_mg=0.001
    )

with tabs[3]:
    # Dilaudid (hydromorphone) 25 mg / 50 mL
    render_drug_tab(
        drug_name="Dilaudid (hydromorphone)",
        total_mass_display=25.0,
        total_ml=50.0,
        unit="mg",
        unit_to_mg=1.0
    )

st.markdown("---")
st.caption(
    "This tool supports reconciliation and policy workflows and does not replace clinical judgment or hospital policy. "
    "Thresholds are evaluated in mg and mL; the Fentanyl tab displays equivalent mcg values for clarity."
)
