import streamlit as st
import pandas as pd
import simplekml
from pyproj import Transformer
import zipfile
from datetime import datetime, timedelta, date
import io
import unicodedata

st.title("🔥 Generador KMZ Quemas")

archivo = st.file_uploader("Sube Excel", type=["xls", "xlsx"])

# =========================
# 🧼 NORMALIZADOR DE TEXTO
# =========================
def normalizar(texto):
    if pd.isnull(texto):
        return ""
    texto = str(texto).strip().upper()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


if archivo:

    # --- Leer Excel ---
    if archivo.name.endswith(".xls"):
        df = pd.read_excel(archivo, header=8, engine="xlrd")
    else:
        df = pd.read_excel(archivo, header=8)

    df.columns = df.columns.str.strip().str.upper()

    st.dataframe(df.head())

    if st.button("Procesar"):

        # --- Columnas base ---
        col_provincia = "PROVINCIA"
        col_rol = "ROL"
        col_hora_inicio = "INICIO.1"
        col_hora_termino = "FIN"
        col_clas_riesgo = df.columns[13]

        # --- Filtrar provincias ---
        provincias_validas = ["CONCEPCION", "BIO-BIO", "ARAUCO"]
        df = df[df[col_provincia].astype(str).str.upper().str.strip().isin(provincias_validas)]

        # --- Fechas ---
        df["INICIO"] = pd.to_datetime(df["INICIO"], errors='coerce', dayfirst=True)
        df["TERMINO"] = pd.to_datetime(df["TERMINO"], errors='coerce', dayfirst=True)

        df["FECHA_INICIO"] = df["INICIO"].dt.date
        df["FECHA_TERMINO"] = df["TERMINO"].dt.date

        mañana = datetime.today().date() + timedelta(days=1)
        nombre_archivo = f"Quemas vigentes al {mañana.strftime('%d-%m-%Y')}"

        # --- filtro operativo (se mantiene como tu lógica original) ---
        df = df[(df["FECHA_INICIO"] <= mañana) & (df["FECHA_TERMINO"] >= mañana)]

        if df.empty:
            st.warning("Sin datos")
            st.stop()

        # =========================
        # 📍 COORDENADAS
        # =========================
        transformer_18 = Transformer.from_crs("EPSG:32718", "EPSG:4326", always_xy=True)
        transformer_19 = Transformer.from_crs("EPSG:32719", "EPSG:4326", always_xy=True)

        def convertir(x, y):
            lon18, lat18 = transformer_18.transform(x, y)
            if -38.5 <= lat18 <= -36 and -74 <= lon18 <= -71:
                return lat18, lon18
            lon19, lat19 = transformer_19.transform(x, y)
            return lat19, lon19

        df["LATITUD"], df["LONGITUD"] = zip(*df.apply(lambda r: convertir(r["X"], r["Y"]), axis=1))

        # =========================
        # 🧠 REGLA DE COMUNAS
        # =========================
        comunas_restringidas = {
            "LOS ANGELES",
            "TOME",
            "PENCO",
            "CONCEPCION",
            "HUALPEN",
            "TALCAHUANO",
            "CHIGUAYANTE",
            "HUALQUI",
            "SAN PEDRO DE LA PAZ",
            "CORONEL",
            "LOTA"
        }

        fecha_limite = date(2026, 9, 30)

        # --- normalizar comunas ---
        df["COMUNA_NORM"] = df["COMUNA"].apply(normalizar)

        # --- regla final ---
        def es_erroneo(row):
            comuna = row["COMUNA_NORM"]
            fecha = row["FECHA_INICIO"]

            if pd.isnull(fecha):
                return False

            return (comuna in comunas_restringidas and fecha <= fecha_limite)

        df["ERRONEO"] = df.apply(es_erroneo, axis=1)

        # =========================
        # 🗺️ KML
        # =========================
        kml = simplekml.Kml()
        icono = "http://maps.google.com/mapfiles/kml/shapes/firedept.png"

        campos_popup = {
            "ROL": col_rol,
            "Nº AVISO": "NÚMERO AVISO",
            "TIPO DE AVISO": "TIPO DE AVISO",
            "FECHA INGRESO": "FECHA INGRESO",
            "COMUNA": "COMUNA",
            "PREDIO": "PREDIO",
            "UBICACIÓN": "UBICACIÓN",
            "SUPERFICIE (ha)": "SUPERFICIE (HA)",
            "TIPO QUEMA": "TIPO QUEMA",
            "CLASIFICACIÓN DE RIESGO": col_clas_riesgo,
            "FECHA INICIO": "INICIO",
            "FECHA TÉRMINO": "TERMINO",
            "HORA INICIO": col_hora_inicio,
            "HORA TÉRMINO": col_hora_termino
        }

        for _, row in df.iterrows():

            html = "<table border='1' style='border-collapse:collapse;'>"

            for nombre, col in campos_popup.items():
                valor = row.get(col, "")

                if "HORA" in nombre and pd.notnull(valor):
                    valor = pd.to_datetime(valor).strftime("%H:%M")
                elif "FECHA" in nombre and pd.notnull(valor):
                    valor = pd.to_datetime(valor).strftime("%d-%m-%Y")
                else:
                    valor = "" if pd.isnull(valor) else str(valor)

                html += f"<tr><th>{nombre}</th><td>{valor}</td></tr>"

            html += "</table>"

            p = kml.newpoint(coords=[(row["LONGITUD"], row["LATITUD"])])

            # =========================
            # 🎯 SOLO 2 COLORES
            # =========================
            if row["ERRONEO"]:
                p.style.iconstyle.color = "ff000000"  # ⚫ negro
            else:
                p.style.iconstyle.color = "ff0000ff"  # 🔴 rojo

            p.name = str(row[col_rol])
            p.style.labelstyle.scale = 0
            p.style.iconstyle.icon.href = icono
            p.style.iconstyle.scale = 0.8
            p.description = html

        # =========================
        # 📦 KMZ
        # =========================
        kml.save("temp.kml")

        with zipfile.ZipFile("temp.kmz", "w") as kmz:
            kmz.write("temp.kml")

        with open("temp.kmz", "rb") as f:
            kmz_bytes = f.read()

        # =========================
        # 📊 EXCEL
        # =========================
        excel_bytes = io.BytesIO()
        df.to_excel(excel_bytes, index=False)

        st.success("✅ KMZ generado correctamente")

        st.download_button("Descargar KMZ", kmz_bytes, file_name=f"{nombre_archivo}.kmz")
        st.download_button("Descargar Excel", excel_bytes.getvalue(), file_name=f"{nombre_archivo}.xlsx")
