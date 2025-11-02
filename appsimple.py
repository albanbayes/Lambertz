import streamlit as st
import pandas as pd
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import streamlit.components.v1 as components
import io
import os
import math

# --------------------------------------------------------------------------------------
# Globala konstanter för säker procentintervall i beräkningar (undvik 0 % och 100 %)
# 0.000001 % = 1e-8 i decimaltal
EPS_PCT = 0.000001
EPS = EPS_PCT / 100.0            # 1e-8
ONE_MINUS_EPS = 1.0 - EPS        # 0.99999999

def clamp_prob(p: float) -> float:
    """Håll sannolikheter inom [1e-8, 0.99999999]."""
    return max(EPS, min(ONE_MINUS_EPS, float(p)))

def fmt_pct(p: float) -> str:
    """Formatera sannolikhet (0..1) som procent med gränser enligt kravet."""
    pct = p * 100.0
    if pct <= EPS_PCT:
        return f"≤{EPS_PCT:.6f}%"
    if pct >= 99.99999:
        return "≥99.99999%"
    s = f"{pct:.6f}".rstrip('0').rstrip('.')
    return f"{s}%"

def fmt_lr(lr: float) -> str:
    """Visa LR med mänsklig formatering."""
    if lr <= 1e-6:
        return "≤0.000001"
    if lr >= 1_000_000:
        return "≥1,000,000"
    if lr >= 1000 or lr <= 0.001:
        return f"{lr:.6g}"
    s = f"{lr:,.4f}"
    if "." in s:
        s = s.rstrip('0').rstrip('.')
    return s

def lr_category(lr: float) -> str:
    """Verbal kategori för valt LR (symmetriskt runt 1)."""
    if lr < 0.001:
        return "Extremely strong support for innocence"
    elif lr < 0.01:
        return "Very strong support for innocence"
    elif lr < 0.1:
        return "Strong support for innocence"
    elif lr < 0.33:
        return "Moderate support for innocence"
    elif lr < 1.0:
        return "Limited (weak) support for innocence"
    elif lr == 1.0:
        return "Neutral"
    elif lr <= 3:
        return "Limited (weak) support for guilt"
    elif lr <= 10:
        return "Moderate support for guilt"
    elif lr <= 30:
        return "Strong support for guilt"
    elif lr <= 100:
        return "Very strong support for guilt"
    else:
        return "Extremely strong support for guilt"

def lr_to_prob_pair(lr: float) -> tuple[float, float]:
    """
    Beräkna (P(B|Skuld), P(B|Oskuld)) från LR (= pba/pbna) så att båda hamnar inom
    [0.000001%, 99.99999%] ⇒ [1e-8, 1-1e-8] i decimaltal.
    """
    lr = max(1e-6, min(1_000_000.0, float(lr)))
    lower = max(EPS, EPS / lr)
    if lr >= 1.0:
        upper = min(ONE_MINUS_EPS, ONE_MINUS_EPS / lr)
    else:
        upper = ONE_MINUS_EPS
    if lower > upper:
        pbna = 0.5
    else:
        pbna = (lower + upper) / 2.0
    pba = lr * pbna
    return clamp_prob(pba), clamp_prob(pbna)

def render_lr_overlay_on_slider(unique_id: str) -> None:
    """
    Överlagring som lägger *streck* (verbal equivalents) och *egna min/max-etiketter*
    direkt ovanpå slider-ytan. Fångar inte klick (pointer-events: none).
    Samtidigt döljs Streamlits egna min/max-etiketter helt.
    """
    TICKS = [
        (-6.0, "1e-6", "Extremely (I)"),
        (-5.0, "1e-5", "Very strong (I)"),
        (-4.0, "1e-4", "Strong (I)"),
        (-3.0, "1e-3", "Mod. strong (I)"),
        (-2.0, "1e-2", "Moderate (I)"),
        (math.log10(1/3), "1/3", "Limited (I)"),
        (0.0, "1", "Neutral"),
        (math.log10(3), "3", "Limited (G)"),
        (1.0, "10", "Moderate (G)"),
        (math.log10(30), "30", "Strong (G)"),
        (2.0, "100", "Very strong (G)"),
        (6.0, "1e6", "Extremely (G)"),
    ]
    def pos_from_log10(x: float) -> float:
        return (x + 6.0) / 12.0 * 100.0

    ticks_html = ""
    for x, main, sub in TICKS:
        left = pos_from_log10(x)
        ticks_html += f"""
          <div class="lr-ov-tick-{unique_id}" style="left:{left:.4f}%"></div>
          <div class="lr-ov-label-{unique_id}" style="left:{left:.4f}%">{main}</div>
          <div class="lr-ov-sub-{unique_id}" style="left:{left:.4f}%">{sub}</div>
        """

    html = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        /* DÖLJ Streamlits egna min/max (t.ex. “-6.00”/“6.00”) */
        div[data-testid="stSlider"] [data-testid="stTickBarMin"],
        div[data-testid="stSlider"] [data-testid="stTickBarMax"] {{
          display: none !important;
          visibility: hidden !important;
        }}
        /* Överlagringen placeras ovanpå slider-ytan */
        .lr-ov-wrap-{unique_id} {{
          position: relative;
          width: 100%;
          height: 0px;
          margin-top: -28px;     /* dras upp över sliderbanan */
          pointer-events: none;  /* låt slider ta alla klick */
        }}
        .lr-ov-area-{unique_id} {{
          position: relative;
          height: 46px;          /* utrymme för streck + etiketter */
          width: 100%;
        }}
        .lr-ov-tick-{unique_id} {{
          position: absolute; top: 0px;
          width: 1px; height: 16px;
          background: rgba(0,0,0,0.45);
        }}
        .lr-ov-label-{unique_id} {{
          position: absolute; top: 16px; transform: translateX(-50%);
          font-size: 10px; color: #666; white-space: nowrap;
        }}
        .lr-ov-sub-{unique_id} {{
          position: absolute; top: 30px; transform: translateX(-50%);
          font-size: 10px; color: #888; white-space: nowrap;
        }}
        .lr-ov-ends-{unique_id} {{
          position: relative;
          display:flex; justify-content:space-between; align-items:center;
          font-size:11px; color:#666;
          margin-top: 6px;
          width:100%;
          pointer-events: none;
        }}
        /* Färgad rail (grön→röd) för alla sliders */
        div[data-baseweb="slider"] > div:first-child {{
          background: linear-gradient(90deg, #00c853 0%, #ffeb3b 50%, #ff3d00 100%) !important;
          height: 8px !important; border-radius: 4px !important;
        }}
      </style>
    </head>
    <body>
      <div class="lr-ov-wrap-{unique_id}">
        <div class="lr-ov-area-{unique_id}">
          {ticks_html}
        </div>
        <div class="lr-ov-ends-{unique_id}">
          <span>≤ 0.000001</span>
          <span>≥ 1,000,000</span>
        </div>
      </div>
    </body>
    </html>
    """
    components.html(html, height=0, scrolling=False)

# --------------------------------------------------------------------------------------

st.set_page_config(page_title="Bayes Kalkylator", layout="centered")
st.image("lambertz_logo.png", width=160)

st.title("Bayesianska Kalkylator")
st.caption("Juridisk bevisvärdering, enkelt och transparent – utvecklad för pågående artikel.")

with st.expander("💡 Vad är detta? (Klicka för info)"):
    st.write("""
    **Den här kalkylatorn hjälper dig att räkna på bevisvärde i brottmål eller andra mål enligt Bayesiansk metod.**
    - Ange först *prior* (din första gissning om skuld, som procentsats).
    - Mata sedan in bevis (t.ex. DNA, vittnesmål) och för varje: Sannolikhet om den misstänkte är skyldig och om hen är oskyldig.
    - Kalkylatorn räknar ut *slutlig sannolikhet* steg för steg, och du får tydliga tolkningar och snygga PDF-rapporter.
    - Du kan spara/ladda egna scenarier (CSV) eller använda färdiga mallar.
    """)

st.markdown("""
<br><br>
<span style='font-size:0.9em; color:#888;'>© 2025 Orimlig Hyra | Utvecklad av Alban Dautaj</span>
""", unsafe_allow_html=True)

st.markdown("---")

# ------------------ SCENARIO/MALLAR -------------------
MALLAR = {
    "Årsta torg": [
        {"desc": "Vittnesmål 1 (A. E)", "pba": 0.95, "pbna": 0.05},
        {"desc": "Vittnesmål 2 (M. L)", "pba": 0.95, "pbna": 0.05},
        {"desc": "Vittnesmål 3 (N. E)", "pba": 0.7,  "pbna": 0.5},
        {"desc": "DNA",               "pba": 0.95, "pbna": 0.01},
        {"desc": "Jacka (saknas)",    "pba": 0.25, "pbna": 0.5},
        {"desc": "Annat",             "pba": 0.25, "pbna": 0.6}
    ],
    "Busshållsplatsen": [
        {"desc": "Vittnesmål 1", "pba": 0.7,  "pbna": 0.2},
        {"desc": "Vittnesmål 2", "pba": 0.7,  "pbna": 0.1},
        {"desc": "Vittnesmål 3", "pba": 0.7,  "pbna": 0.15},
        {"desc": "DNA",          "pba": 0.6,  "pbna": 0.02},
        {"desc": "Kamera",       "pba": 0.95, "pbna": 0.3}
    ]
}
MOTBEVIS_MALLAR = {
    "Årsta torg": [
        {"desc": "Alibiuppgift", "pba": 0.3, "pbna": 0.6},
        {"desc": "Motvittne",    "pba": 0.5, "pbna": 0.9}
    ],
    "Busshållsplatsen": [
        {"desc": "Tidsuppgift avviker", "pba": 0.4, "pbna": 0.7}
    ]
}

st.header("1. Välj eller skapa scenario")

colm1, colm2 = st.columns([3,2])
with colm1:
    mallnamn = st.selectbox(
        "Välj mall/scenario:",
        ["Skapa eget scenario"] + list(MALLAR.keys())
    )

with colm2:
    uploaded_csv = st.file_uploader("Ladda upp scenario (CSV)", type=["csv"])
    scenario_loaded = False

if uploaded_csv:
    df = pd.read_csv(uploaded_csv)
    prior = float(df.iloc[0]['prior'])
    bevisdata = df[df['typ'] == 'bevis'][['desc', 'pba', 'pbna']].to_dict("records")
    motbevisdata = df[df['typ'] == 'motbevis'][['desc', 'pba', 'pbna']].to_dict("records")
    scenario_loaded = True
    st.success("Scenario laddat från CSV!")
elif mallnamn != "Skapa eget scenario":
    prior = 0.1
    bevisdata = MALLAR[mallnamn].copy()
    motbevisdata = MOTBEVIS_MALLAR.get(mallnamn, []).copy()
    st.success(f"Du har valt mallen: {mallnamn}")
else:
    bevisdata = []
    motbevisdata = []
    prior = 0.1

st.header("2. Ange ursprungssannolikhet")
if not scenario_loaded:
    prior = st.number_input(
        "Prior (ursprunglig sannolikhet för skuld) i %",
        min_value=0.0, max_value=100.0, value=float(prior)*100, step=0.1
    ) / 100.0

st.header("3. Lägg till bevis")
if (mallnamn == "Skapa eget scenario") and not scenario_loaded:
    antal_bevis = st.number_input("Antal bevis (talar FÖR skuld)", min_value=1, max_value=20, value=max(1, len(bevisdata)), step=1)
    antal_motbevis = st.number_input("Antal motbevis (talar EMOT skuld)", min_value=0, max_value=10, value=len(motbevisdata), step=1)
    if len(bevisdata) < antal_bevis:
        bevisdata.extend([{"desc": f"Bevis {i+1}", "pba": 0.7, "pbna": 0.2} for i in range(len(bevisdata), int(antal_bevis))])
    elif len(bevisdata) > antal_bevis:
        bevisdata = bevisdata[:int(antal_bevis)]
    if len(motbevisdata) < antal_motbevis:
        motbevisdata.extend([{"desc": f"Motbevis {i+1}", "pba": 0.4, "pbna": 0.7} for i in range(len(motbevisdata), int(antal_motbevis))])
    elif len(motbevisdata) > antal_motbevis:
        motbevisdata = motbevisdata[:int(antal_motbevis)]

# --------------------------------------------
# BEVIS (FÖR skuld) – valbar LR-skala eller procent
# --------------------------------------------
for i, row in enumerate(bevisdata):
    col1, col2, col3 = st.columns([3,2,2])
    row["desc"] = col1.text_input(f"Beskriv bevis {i+1}", value=row["desc"], key=f"bevisdesc_{i}")

    use_scale = col1.checkbox("Ange med styrkeskala istället för procent", key=f"use_scale_bevis_{i}", value=False)

    if use_scale:
        lr_log = col2.slider(
            label="Styrkeskala (LR)",
            min_value=-6.0, max_value=6.0, value=0.0, step=0.01,
            label_visibility="collapsed", key=f"lr_bevis_{i}",
            help="Drag reglaget. Skalan motsvarar LR mellan 0.000001 och 1,000,000."
        )
        lr_val = 10 ** lr_log

        # Överlagring: tickmarks + egna ändetiketter (≤0.000001 / ≥1,000,000) på samma bana
        with col2:
            render_lr_overlay_on_slider(unique_id=f"bevis_{i}")

        with col3:
            st.write(f"**Vald LR:** {fmt_lr(lr_val)}")
            st.caption(lr_category(lr_val))
            pba, pbna = lr_to_prob_pair(lr_val)
            row["pba"], row["pbna"] = pba, pbna
            st.markdown(f"**Används i beräkningen:** P(B\\|Skuld) = {fmt_pct(pba)} · P(B\\|Oskuld) = {fmt_pct(pbna)}")

    else:
        row["pba"] = col2.number_input(f"P(B|Skuld) %", min_value=0.0, max_value=100.0, value=float(row["pba"])*100, key=f"pba_{i}")/100.0
        row["pbna"] = col3.number_input(f"P(B|Oskuld) %", min_value=0.0, max_value=100.0, value=float(row["pbna"])*100, key=f"pbna_{i}")/100.0
        row["pba"] = clamp_prob(row["pba"])
        row["pbna"] = clamp_prob(row["pbna"])

# -------------------------------------------------
# MOTBEVIS (EMOT skuld) – valbar LR-skala eller procent
# -------------------------------------------------
for i, row in enumerate(motbevisdata):
    col1, col2, col3 = st.columns([3,2,2])
    row["desc"] = col1.text_input(f"Beskriv motbevis {i+1}", value=row["desc"], key=f"motdesc_{i}")

    use_scale_m = col1.checkbox("Ange med styrkeskala istället för procent", key=f"use_scale_mot_{i}", value=False)

    if use_scale_m:
        lr_log = col2.slider(
            label="Styrkeskala (LR)",
            min_value=-6.0, max_value=6.0, value=0.0, step=0.01,
            label_visibility="collapsed", key=f"lr_mot_{i}",
            help="Drag reglaget. Skalan motsvarar LR mellan 0.000001 och 1,000,000."
        )
        lr_val = 10 ** lr_log
        with col2:
            render_lr_overlay_on_slider(unique_id=f"mot_{i}")

        with col3:
            st.write(f"**Vald LR:** {fmt_lr(lr_val)}")
            st.caption(lr_category(lr_val))
            pba, pbna = lr_to_prob_pair(lr_val)  # pba= P(MB|Skuld), pbna= P(MB|Oskuld)
            row["pba"], row["pbna"] = pba, pbna
            st.markdown(f"**Används i beräkningen:** P(MB\\|Skuld) = {fmt_pct(pba)} · P(MB\\|Oskuld) = {fmt_pct(pbna)}")
    else:
        row["pba"] = col2.number_input(f"P(MB|Skuld) %", min_value=0.0, max_value=100.0, value=float(row["pba"])*100, key=f"mbpba_{i}")/100.0
        row["pbna"] = col3.number_input(f"P(MB|Oskuld) %", min_value=0.0, max_value=100.0, value=float(row["pbna"])*100, key=f"mbpbna_{i}")/100.0
        row["pba"] = clamp_prob(row["pba"])
        row["pbna"] = clamp_prob(row["pbna"])

st.header("4. Resultat och tolkning")

def bayes_step(prior, pba, pbna):
    numerator = pba * prior
    denominator = numerator + pbna * (1 - prior)
    return numerator / denominator if denominator != 0 else 0

posterior = prior
result_tab = []
for row in bevisdata:
    old_post = posterior
    posterior = bayes_step(old_post, row["pba"], row["pbna"])
    result_tab.append({
        "Bevis": row["desc"],
        "P(B|Skuld)": f"{row['pba']*100:.2f}%",
        "P(B|Oskuld)": f"{row['pbna']*100:.2f}%",
        "Föregående %": f"{old_post*100:.2f}%",
        "Ny %": f"{posterior*100:.2f}%"
    })
for row in motbevisdata:
    old_post = posterior
    posterior = bayes_step(old_post, row["pba"], row["pbna"])
    result_tab.append({
        "Bevis": f"Motbevis: {row['desc']}",
        "P(B|Skuld)": f"{row['pba']*100:.2f}%",
        "P(B|Oskuld)": f"{row['pbna']*100:.2f}%",
        "Föregående %": f"{old_post*100:.2f}%",
        "Ny %": f"{posterior*100:.2f}%"
    })
df = pd.DataFrame(result_tab)
st.dataframe(df)

def interpret(pct):
    if pct >= 95:
        return "Bortom rimligt tvivel"
    elif pct >= 80:
        return "Starkt stöd för skuld"
    elif pct >= 60:
        return "Huvudsakligen styrkt"
    elif pct >= 50:
        return "Bevisövervikt"
    elif pct >= 30:
        return "Tveksamt"
    else:
        return "Osannolikt eller stöd för oskuld"

st.markdown(f"## Slutlig sannolikhet: **{posterior*100:.2f} %**")
st.info(f"Tolkning: **{interpret(posterior*100)}**")

st.markdown("---")
st.subheader("Ladda ner rapport som PDF")

def generate_pdf_reportlab(df, posterior, interpret_text):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Lambertz Bayesianska Kalkylatorn – Rapport", styles['Title']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>Slutlig sannolikhet:</b> {posterior*100:.2f} %", styles['Normal']))
    elements.append(Paragraph(f"<b>Tolkning:</b> {interpret_text}", styles['Normal']))
    elements.append(Spacer(1, 12))

    data = [df.columns.tolist()] + df.values.tolist()
    table = Table(data, hAlign='LEFT')
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ]))
    elements.append(table)

    elements.append(Spacer(1, 24))
    elements.append(Paragraph("© 2025 Orimlig Hyra | Utvecklad av Alban Dautaj", styles['Normal']))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

if st.button("Skapa PDF-rapport"):
    pdf_bytes = generate_pdf_reportlab(df, posterior, interpret(posterior*100))
    st.download_button(
        label="Ladda ner PDF",
        data=pdf_bytes,
        file_name="rapport.pdf",
        mime="application/pdf"
    )

st.markdown("---")
st.subheader("Spara aktuellt scenario till CSV")

if st.button("Spara scenario till CSV"):
    bevis_rows = [
        {"typ": "bevis", "desc": r["desc"], "pba": r["pba"], "pbna": r["pbna"], "prior": prior}
        for r in bevisdata
    ]
    motbevis_rows = [
        {"typ": "motbevis", "desc": r["desc"], "pba": r["pba"], "pbna": r["pbna"], "prior": prior}
        for r in motbevisdata
    ]
    df_scenario = pd.DataFrame(bevis_rows + motbevis_rows)
    csv_bytes = df_scenario.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Ladda ner scenario som CSV",
        data=csv_bytes,
        file_name="scenario_bayes.csv",
        mime="text/csv"
    )
