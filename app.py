
import streamlit as st
import pandas as pd
import simplekml
from pyproj import Transformer
import zipfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import io

st.title("🔥 Generador KMZ Quemas Biobío")

# =====================================================
# 1. FECHA Y HORA OFICIAL DE CHILE
# =====================================================

zona_chile = ZoneInfo("America/Santiago")

ahora_chile = datetime.now(zona_chile)
hoy_chile = ahora_chile.date()
mañana = hoy_chile + timedelta(days=1)

fecha_servidor = datetime.now().date()
fecha_utc = datetime.now(timezone.utc).date()

st.info(
    f"📅 Fecha actual en Chile: {hoy_chile.strftime('%d-%m-%Y')}\n\n"
    f"🕒 Hora en Chile: {ahora_chile.strftime('%H:%M:%S')}\n\n"
    f"📅 Fecha del servidor: {fecha_servidor.strftime('%d-%m-%Y')}\n\n"
    f"📅 Fecha UTC: {fecha_utc.strftime('%d-%m-%Y')}\n\n"
    f"🎯 Fecha que se procesará: {mañana.strftime('%d-%m-%Y')}"
)

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

        df = df[
            df[col_provincia]
            .astype(str)
            .str.upper()
            .str.strip()
            .isin(provincias_validas)
        ].copy()

        # =====================================================
        # 2. CONVERSIÓN DE FECHAS
        # =====================================================

        df["INICIO"] = pd.to_datetime(
            df["INICIO"], errors="coerce", dayfirst=True
        )

        df["TERMINO"] = pd.to_datetime(
            df["TERMINO"], errors="coerce", dayfirst=True
        )

        df["FECHA_INICIO"] = df["INICIO"].dt.date
        df["FECHA_TERMINO"] = df["TERMINO"].dt.date

        # =====================================================
        # 3. FILTRO EXCLUSIVO PARA EL DÍA SIGUIENTE EN CHILE
        # =====================================================

        fecha_objetivo = mañana

        nombre_archivo = (
            f"Quemas vigentes al {fecha_objetivo.strftime('%d-%m-%Y')}"
        )

        df = df[
            (df["FECHA_INICIO"] <= fecha_objetivo) &
            (df["FECHA_TERMINO"] >= fecha_objetivo)
        ].copy()

        if df.empty:
            st.warning(
                f"No existen quemas vigentes para el día "
                f"{fecha_objetivo.strftime('%d-%m-%Y')}."
            )
            st.stop()

        # --- Control de fechas seleccionadas ---

        st.success(
            f"Se encontraron {len(df)} quemas vigentes para "
            f"el {fecha_objetivo.strftime('%d-%m-%Y')}."
        )

        st.write("### 🔎 Verificación de fechas seleccionadas")

        st.write(
            "Fecha más antigua de inicio:",
            df["FECHA_INICIO"].min().strftime("%d-%m-%Y")
        )

        st.write(
            "Fecha más reciente de inicio:",
            df["FECHA_INICIO"].max().strftime("%d-%m-%Y")
        )

        st.write(
            "Fecha más antigua de término:",
            df["FECHA_TERMINO"].min().strftime("%d-%m-%Y")
        )

        st.write(
            "Fecha más reciente de término:",
            df["FECHA_TERMINO"].max().strftime("%d-%m-%Y")
        )

        # =====================================================
        # 4. CONVERSIÓN DE COORDENADAS
        # =====================================================

        transformer_18 = Transformer.from_crs(
            "EPSG:32718", "EPSG:4326", always_xy=True
        )

        transformer_19 = Transformer.from_crs(
            "EPSG:32719", "EPSG:4326", always_xy=True
        )

        def convertir(x, y):

            lon18, lat18 = transformer_18.transform(x, y)

            if -38.5 <= lat18 <= -36 and -74 <= lon18 <= -71:
                return lat18, lon18

            lon19, lat19 = transformer_19.transform(x, y)

            return lat19, lon19

        df["LATITUD"], df["LONGITUD"] = zip(
            *df.apply(
                lambda r: convertir(r["X"], r["Y"]),
                axis=1
            )
        )

        # =====================================================
        # 5. GENERACIÓN KMZ
        # =====================================================

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

            p = kml.newpoint(
                coords=[(row["LONGITUD"], row["LATITUD"])]
            )

            p.name = str(row[col_rol])
            p.style.labelstyle.scale = 0

            p.style.iconstyle.icon.href = icono
            p.style.iconstyle.scale = 0.8

            p.description = html

        # =====================================================
        # 6. GUARDAR KMZ
        # =====================================================

        kml.save("temp.kml")

        with zipfile.ZipFile("temp.kmz", "w") as kmz:
            kmz.write("temp.kml")

        with open("temp.kmz", "rb") as f:
            kmz_bytes = f.read()

        # =====================================================
        # 7. GENERACIÓN EXCEL
        # =====================================================

        df_export = df.copy()

        columnas_eliminar_aux = [
            "FECHA_INICIO",
            "FECHA_TERMINO"
        ]

        df_export = df_export.drop(
            columns=[
                c for c in columnas_eliminar_aux
                if c in df_export.columns
            ]
        )

        columnas_a_eliminar = df_export.columns[18:21]

        df_export = df_export.drop(
            columns=columnas_a_eliminar,
            errors="ignore"
        )

        columnas = list(df_export.columns)

        if len(columnas) > 14:
            columnas[14] = "FECHA INICIO"

        if len(columnas) > 15:
            columnas[15] = "FECHA TÉRMINO"

        if len(columnas) > 16:
            columnas[16] = "HORA INICIO"

        if len(columnas) > 17:
            columnas[17] = "HORA FIN"

        df_export.columns = columnas

        for col in ["FECHA INICIO", "FECHA TÉRMINO"]:

            if col in df_export.columns:

                df_export[col] = pd.to_datetime(
                    df_export[col],
                    errors="coerce"
                ).dt.strftime("%d-%m-%Y")

        for col in ["HORA INICIO", "HORA FIN"]:

            if col in df_export.columns:

                df_export[col] = pd.to_datetime(
                    df_export[col],
                    errors="coerce"
                ).dt.strftime("%H:%M")

        excel_bytes = io.BytesIO()

        df_export.to_excel(
            excel_bytes,
            index=False
        )

        # =====================================================
        # 8. DESCARGAS
        # =====================================================

        st.success(
            f"✅ Proceso completado. "
            f"Quemas correspondientes al {fecha_objetivo.strftime('%d-%m-%Y')}."
        )

        st.download_button(
            "Descargar KMZ",
            kmz_bytes,
            file_name=f"{nombre_archivo}.kmz"
        )

        st.download_button(
            "Descargar Excel",
            excel_bytes.getvalue(),
            file_name=f"{nombre_archivo}.xlsx"
        )
