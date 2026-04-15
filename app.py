import streamlit as st
import pandas as pd
import simplekml
from pyproj import Transformer
import zipfile
from datetime import datetime, timedelta, date
import io

# 🔥 NUEVO
import geopandas as gpd
from shapely.geometry import Point

st.title("🔥 Generador KMZ Quemas")

archivo = st.file_uploader("Sube Excel", type=["xls", "xlsx"])

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
        # 🌍 API COMUNAS (GeoJSON)
        # =========================

        # 🔥 Fuente GeoJSON comunas Chile
        url_geojson = "https://raw.githubusercontent.com/caracena/chile-geojson/master/8.geojson"

        gdf = gpd.read_file(url_geojson)

        # ⚠️ Nombre de columna puede variar
        # revisamos nombres disponibles
        nombre_col = "NOM_COMUNA" if "NOM_COMUNA" in gdf.columns else gdf.columns[0]

        gdf["NOMBRE"] = gdf[nombre_col].str.upper()

        # --- Comunas restringidas ---
        comunas_restringidas = [
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
        ]

        gdf_restringidas = gdf[gdf["NOMBRE"].isin(comunas_restringidas)]

        # --- Fecha límite ---
        fecha_limite = date(2026, 9, 30)

        # =========================
        # 🔥 FUNCIÓN GEOGRÁFICA
        # =========================
        def es_erroneo(row):
            if pd.isnull(row["FECHA_INICIO"]):
                return False

            if row["FECHA_INICIO"] > fecha_limite:
                return False

            punto = Point(row["LONGITUD"], row["LATITUD"])

            return gdf_restringidas.contains(punto).any()

        df["ERRONEO"] = df.apply(es_erroneo, axis=1)

        # =========================
        # 🗺️ KML
        # =========================
        kml = simplekml.Kml()
        icono = "http://maps.google.com/mapfiles/kml/shapes/firedept.png"

        for _, row in df.iterrows():

            p = kml.newpoint(coords=[(row["LONGITUD"], row["LATITUD"])])

            if row["ERRONEO"]:
                p.style.iconstyle.color = "ff000000"  # ⚫ negro
            else:
                p.style.iconstyle.color = "ff0000ff"  # 🔴 rojo

            p.name = str(row[col_rol])
            p.style.labelstyle.scale = 0
            p.style.iconstyle.icon.href = icono
            p.style.iconstyle.scale = 0.8

        # --- KMZ ---
        kml.save("temp.kml")

        with zipfile.ZipFile("temp.kmz", "w") as kmz:
            kmz.write("temp.kml")

        with open("temp.kmz", "rb") as f:
            kmz_bytes = f.read()

        # --- Excel ---
        excel_bytes = io.BytesIO()
        df.to_excel(excel_bytes, index=False)

        st.success("✅ KMZ generado con validación geográfica real")

        st.download_button("Descargar KMZ", kmz_bytes, file_name=f"{nombre_archivo}.kmz")
        st.download_button("Descargar Excel", excel_bytes.getvalue(), file_name=f"{nombre_archivo}.xlsx")
