import streamlit as st
import pandas as pd
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
import io
import os

st.set_page_config(page_title="Lambertz Bayes Kalkylator", layout="centered")
st.image("lambertz_logo.png", width=160)

st.title("Lambertz Bayesianska Kalkylator")
st.caption("Juridisk bevisvärdering, enkelt och transparent – utvecklad med inspiration av Lambertz och Dautaj.")

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
        {"desc": "Vittnesmål 3 (N. E)", "pba": 0.7, "pbna": 0.5},
        {"desc": "DNA", "pba": 0.95, "pbna": 0.01},
        {"desc": "Jacka (saknas)", "pba": 0.25, "pbna": 0.5},
        {"desc": "Annat", "pba": 0.25, "pbna": 0.6}
    ],
    "Busshållsplatsen": [
        {"desc": "Vittnesmål 1", "pba": 0.7, "pbna": 0.2},
        {"desc": "Vittnesmål 2", "pba": 0.7, "pbna": 0.1},
        {"desc": "Vittnesmål 3", "pba": 0.7, "pbna": 0.15},
        {"desc": "DNA", "pba": 0.6, "pbna": 0.02},
        {"desc": "Kamera", "pba": 0.95, "pbna": 0.3}
    ]
}
MOTBEVIS_MALLAR = {
    "Årsta torg": [
        {"desc": "Alibiuppgift", "pba": 0.3, "pbna": 0.6},
        {"desc": "Motvittne", "pba": 0.5, "pbna": 0.9}
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

for i, row in enumerate(bevisdata):
    col1, col2, col3 = st.columns([3,2,2])
    row["desc"] = col1.text_input(f"Beskriv bevis {i+1}", value=row["desc"], key=f"bevisdesc_{i}")
    row["pba"] = col2.number_input(f"P(B|Skuld) %", min_value=0.0, max_value=100.0, value=float(row["pba"])*100, key=f"pba_{i}")/100.0
    row["pbna"] = col3.number_input(f"P(B|Oskuld) %", min_value=0.0, max_value=100.0, value=float(row["pbna"])*100, key=f"pbna_{i}")/100.0

for i, row in enumerate(motbevisdata):
    col1, col2, col3 = st.columns([3,2,2])
    row["desc"] = col1.text_input(f"Beskriv motbevis {i+1}", value=row["desc"], key=f"motdesc_{i}")
    row["pba"] = col2.number_input(f"P(MB|Skuld) %", min_value=0.0, max_value=100.0, value=float(row["pba"])*100, key=f"mbpba_{i}")/100.0
    row["pbna"] = col3.number_input(f"P(MB|Oskuld) %", min_value=0.0, max_value=100.0, value=float(row["pbna"])*100, key=f"mbpbna_{i}")/100.0

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
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(30, height-40, "Lambertz Bayesianska Kalkylatorn – Rapport")

    c.setFont("Helvetica", 12)
    c.drawString(30, height-65, f"Slutlig sannolikhet: {posterior*100:.2f}%")
    c.drawString(30, height-85, f"Tolkning: {interpret_text}")

    # Tabellhuvud
    c.setFont("Helvetica-Bold", 10)
    x, y = 30, height-115
    columns = list(df.columns)
    col_widths = [120, 70, 70, 80, 80]
    for col, w in zip(columns, col_widths):
        c.drawString(x, y, str(col))
        x += w

    # Tabellinnehåll
    c.setFont("Helvetica", 10)
    y -= 18
    for idx, row in df.iterrows():
        x = 30
        for j, col in enumerate(columns):
            c.drawString(x, y, str(row[col]))
            x += col_widths[j]
        y -= 15
        if y < 60:  # Ny sida om det blir för lågt
            c.showPage()
            y = height-50

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(30, 30, "© 2025 Orimlig Hyra | Utvecklad av Alban Dautaj")

    c.save()
    buffer.seek(0)
    return buffer

if st.button("Skapa PDF-rapport"):
    pdf_buffer = generate_pdf_reportlab(df, posterior, interpret(posterior*100))
    st.download_button(
        label="Ladda ner PDF",
        data=pdf_buffer,
        file_name="rapport.pdf",
        mime="application/pdf"
    )

# ----------- SPARA SCENARIO SOM CSV ----------------------
st.markdown("---")
st.subheader("Spara aktuellt scenario till CSV")

if st.button("Spara scenario till CSV"):
    # Gör DataFrame
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
