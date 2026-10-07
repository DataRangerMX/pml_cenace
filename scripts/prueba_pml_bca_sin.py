from pathlib import Path
from datetime import datetime, timedelta
import json
import urllib.request
import urllib.error
import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

SISTEMAS = ["BCA", "SIN"]
PROCESO = "MDA"

MAX_NODOS_POR_CONSULTA = 20
MAX_DIAS_BUSQUEDA = 10


# ============================================================
# LOCALIZAR CATÁLOGO
# ============================================================

archivos_catalogo = list(
    Path(".").glob(
        "Catálogo NodosP Sistema Eléctrico Nacional*.xlsx"
    )
)

if not archivos_catalogo:
    raise FileNotFoundError(
        "No se encontró el catálogo de NodoP."
    )

archivo_catalogo = sorted(archivos_catalogo)[-1]


print("=" * 80)
print("PRUEBA PML COMPLETA - BCA Y SIN")
print("=" * 80)

print(f"Catálogo: {archivo_catalogo}")
print(f"Proceso : {PROCESO}")

print("=" * 80)


# ============================================================
# LEER CATÁLOGO
# ============================================================

df_catalogo = None

for fila in range(10):

    prueba = pd.read_excel(
        archivo_catalogo,
        header=fila
    )

    columnas = [
        str(c).strip().upper()
        for c in prueba.columns
    ]

    if (
        "CLAVE" in columnas
        and
        "SISTEMA" in columnas
    ):
        df_catalogo = prueba
        break


if df_catalogo is None:
    raise ValueError(
        "No fue posible localizar "
        "los encabezados del catálogo."
    )


df_catalogo.columns = [
    str(c).strip()
    for c in df_catalogo.columns
]


df_catalogo["SISTEMA"] = (
    df_catalogo["SISTEMA"]
    .astype(str)
    .str.strip()
    .str.upper()
)


df_catalogo["CLAVE"] = (
    df_catalogo["CLAVE"]
    .astype(str)
    .str.strip()
)


# ============================================================
# FUNCIÓN PARA CONSULTAR UN LOTE
# ============================================================

def consultar_lote(
    sistema,
    fecha,
    lote,
    numero_lote,
    total_lotes
):

    fecha_url = fecha.strftime("%Y/%m/%d")

    lista_nodos = ",".join(lote)

    url = (
        "https://ws01.cenace.gob.mx:8082/"
        "SWPML/SIM/"
        f"{sistema}/"
        f"{PROCESO}/"
        f"{lista_nodos}/"
        f"{fecha_url}/"
        f"{fecha_url}/"
        "JSON"
    )

    print(
        f"  Lote {numero_lote:03d}/{total_lotes:03d} "
        f"- {len(lote):02d} NodoP",
        end=""
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=120
        ) as response:

            contenido = (
                response
                .read()
                .decode("utf-8")
            )

        datos = json.loads(contenido)

        if datos.get("status") != "OK":

            print(" -> SIN STATUS OK")
            return None

        resultados = datos.get(
            "Resultados",
            []
        )

        if not resultados:

            print(" -> SIN RESULTADOS")
            return None

        print(
            f" -> OK ({len(resultados)} NodoP)"
        )

        return datos

    except urllib.error.HTTPError as error:

        print(
            f" -> HTTP {error.code}"
        )

        return None

    except Exception as error:

        print(
            f" -> ERROR: "
            f"{type(error).__name__}: {error}"
        )

        return None


# ============================================================
# PROCESAR UN SISTEMA
# ============================================================

def procesar_sistema(sistema):

    print()
    print()
    print("#" * 80)
    print(f"SISTEMA: {sistema}")
    print("#" * 80)

    df_sistema = (
        df_catalogo[
            df_catalogo["SISTEMA"] == sistema
        ]
        .drop_duplicates(
            subset=["CLAVE"]
        )
        .copy()
    )

    nodos = sorted(
        df_sistema["CLAVE"]
        .dropna()
        .tolist()
    )

    if not nodos:
        raise RuntimeError(
            f"No se encontraron NodoP para {sistema}."
        )

    lotes = [
        nodos[
            i:i + MAX_NODOS_POR_CONSULTA
        ]
        for i in range(
            0,
            len(nodos),
            MAX_NODOS_POR_CONSULTA
        )
    ]

    print()
    print(f"NodoP catálogo     : {len(nodos):,}")
    print(f"Lotes necesarios   : {len(lotes):,}")
    print(
        f"Registros teóricos : "
        f"{len(nodos) * 24:,}"
    )

    # ========================================================
    # BUSCAR ÚLTIMA FECHA DISPONIBLE
    # ========================================================

    hoy = datetime.now().date()

    fecha_encontrada = None
    respuestas_finales = None

    for dias_atras in range(
        MAX_DIAS_BUSQUEDA
    ):

        fecha_prueba = (
            hoy
            - timedelta(
                days=dias_atras
            )
        )

        print()
        print("=" * 80)
        print(
            f"{sistema} - PROBANDO FECHA: "
            f"{fecha_prueba}"
        )
        print("=" * 80)

        respuestas = []
        fecha_valida = True

        for numero_lote, lote in enumerate(
            lotes,
            start=1
        ):

            respuesta = consultar_lote(
                sistema,
                fecha_prueba,
                lote,
                numero_lote,
                len(lotes)
            )

            if respuesta is None:

                fecha_valida = False
                break

            respuestas.append(
                respuesta
            )

        if fecha_valida:

            fecha_encontrada = fecha_prueba
            respuestas_finales = respuestas

            print()
            print(
                f"{sistema}: FECHA DISPONIBLE "
                f"EN TODOS LOS LOTES"
            )

            break

    if respuestas_finales is None:

        raise RuntimeError(
            f"No se encontró una fecha completa "
            f"para {sistema} en los últimos "
            f"{MAX_DIAS_BUSQUEDA} días."
        )

    # ========================================================
    # CONVERTIR A TABLA
    # ========================================================

    registros = []

    for respuesta in respuestas_finales:

        for resultado in respuesta.get(
            "Resultados",
            []
        ):

            nodo = resultado.get(
                "clv_nodo"
            )

            for valor in resultado.get(
                "Valores",
                []
            ):

                registros.append({

                    "Fecha":
                        valor.get("fecha"),

                    "Proceso":
                        PROCESO,

                    "Sistema":
                        sistema,

                    "NodoP":
                        nodo,

                    "Hora":
                        int(
                            valor.get("hora")
                        ),

                    "PML":
                        float(
                            valor.get("pml")
                        ),

                    "Energia":
                        float(
                            valor.get("pml_ene")
                        ),

                    "Perdidas":
                        float(
                            valor.get("pml_per")
                        ),

                    "Congestion":
                        float(
                            valor.get("pml_cng")
                        )

                })

    df_pml = pd.DataFrame(
        registros
    )

    if df_pml.empty:
        raise RuntimeError(
            f"No se generaron registros "
            f"para {sistema}."
        )

    # ========================================================
    # VALIDAR NODOSP
    # ========================================================

    nodos_recibidos = (
        df_pml["NodoP"]
        .nunique()
    )

    registros_obtenidos = len(
        df_pml
    )

    registros_teoricos = (
        len(nodos) * 24
    )

    nodos_sin_datos = sorted(
        set(nodos)
        -
        set(
            df_pml["NodoP"]
            .unique()
        )
    )

    # ========================================================
    # CRUZAR CATÁLOGO
    # ========================================================

    columnas_catalogo = [

        "CLAVE",
        "NOMBRE",
        "CENTRO DE CONTROL REGIONAL",
        "ZONA DE CARGA",
        "NIVEL DE TENSIÓN (kV)",
        "ZONA DE OPERACIÓN DE TRANSMISIÓN",
        "GERENCIA REGIONAL DE TRANSMISIÓN",
        "ZONA DE DISTRIBUCIÓN",
        "GERENCIA DIVISIONAL DE DISTRIBUCIÓN",
        "CLAVE DE ENTIDAD FEDERATIVA (INEGI)",
        "ENTIDAD FEDERATIVA (INEGI)",
        "CLAVE DE MUNICIPIO (INEGI)",
        "MUNICIPIO (INEGI)",
        "REGION DE TRANSMISION"

    ]

    columnas_catalogo = [
        c
        for c in columnas_catalogo
        if c in df_sistema.columns
    ]

    df_catalogo_cruce = (
        df_sistema[
            columnas_catalogo
        ]
        .copy()
    )

    df_final = df_pml.merge(
        df_catalogo_cruce,
        left_on="NodoP",
        right_on="CLAVE",
        how="left"
    )

    # ========================================================
    # VALIDAR CRUCE CON CATÁLOGO
    # ========================================================

    if "NOMBRE" in df_final.columns:

        sin_nombre = int(
            df_final["NOMBRE"]
            .isna()
            .sum()
        )

    else:
        sin_nombre = len(
            df_final
        )

    # ========================================================
    # ESTADÍSTICAS
    # ========================================================

    pml_promedio = (
        df_final["PML"]
        .mean()
    )

    fila_max = df_final.loc[
        df_final["PML"].idxmax()
    ]

    fila_min = df_final.loc[
        df_final["PML"].idxmin()
    ]

    promedio_horario = (
        df_final
        .groupby(
            "Hora",
            as_index=False
        )
        .agg(
            PML_Promedio=(
                "PML",
                "mean"
            )
        )
    )

    # ========================================================
    # DISTRIBUCIÓN
    # ========================================================

    def clasificar_pml(valor):

        if valor < 0:
            return "< 0"

        elif valor < 500:
            return "0 - 500"

        elif valor < 1000:
            return "500 - 1,000"

        elif valor < 2000:
            return "1,000 - 2,000"

        elif valor < 5000:
            return "2,000 - 5,000"

        elif valor < 10000:
            return "5,000 - 10,000"

        else:
            return "10,000 o más"

    df_final["RangoPML"] = (
        df_final["PML"]
        .apply(
            clasificar_pml
        )
    )

    orden_rangos = [
        "< 0",
        "0 - 500",
        "500 - 1,000",
        "1,000 - 2,000",
        "2,000 - 5,000",
        "5,000 - 10,000",
        "10,000 o más"
    ]

    distribucion = (
        df_final["RangoPML"]
        .value_counts()
        .reindex(
            orden_rangos,
            fill_value=0
        )
        .reset_index()
    )

    distribucion.columns = [
        "RangoPML",
        "Observaciones"
    ]

    distribucion[
        "Participacion"
    ] = (
        distribucion[
            "Observaciones"
        ]
        /
        len(df_final)
        *
        100
    )

    # ========================================================
    # GUARDAR CSV
    # ========================================================

    carpeta_salida = Path(
        "resultados_prueba"
    )

    carpeta_salida.mkdir(
        exist_ok=True
    )

    archivo_csv = (
        carpeta_salida
        /
        f"pml_{sistema.lower()}_prueba.csv"
    )

    df_final.to_csv(
        archivo_csv,
        index=False,
        encoding="utf-8-sig"
    )

    tamano_kb = (
        archivo_csv.stat().st_size
        / 1024
    )

    # ========================================================
    # MOSTRAR VALIDACIÓN
    # ========================================================

    print()
    print("=" * 80)
    print(
        f"VALIDACIÓN DE LA DESCARGA - {sistema}"
    )
    print("=" * 80)

    print(
        f"Fecha                 : "
        f"{fecha_encontrada}"
    )

    print(
        f"NodoP catálogo        : "
        f"{len(nodos):,}"
    )

    print(
        f"NodoP recibidos       : "
        f"{nodos_recibidos:,}"
    )

    print(
        f"NodoP sin datos       : "
        f"{len(nodos_sin_datos):,}"
    )

    print(
        f"Registros teóricos    : "
        f"{registros_teoricos:,}"
    )

    print(
        f"Registros obtenidos   : "
        f"{registros_obtenidos:,}"
    )

    print(
        f"Registros sin catálogo: "
        f"{sin_nombre:,}"
    )

    if nodos_sin_datos:

        print()
        print("NodoP sin información:")

        for nodo in nodos_sin_datos:
            print(
                f"  - {nodo}"
            )

    # ========================================================
    # RESULTADOS GENERALES
    # ========================================================

    print()
    print("=" * 80)
    print(
        f"RESULTADOS GENERALES - {sistema}"
    )
    print("=" * 80)

    print(
        f"PML promedio: "
        f"${pml_promedio:,.2f}/MWh"
    )

    print()
    print("PML MÁXIMO")

    print(
        f"  PML   : "
        f"${fila_max['PML']:,.2f}/MWh"
    )

    print(
        f"  NodoP : "
        f"{fila_max['NodoP']}"
    )

    print(
        f"  Hora  : "
        f"H{fila_max['Hora']}"
    )

    if "NOMBRE" in df_final.columns:
        print(
            f"  Nombre: "
            f"{fila_max['NOMBRE']}"
        )

    print()
    print("PML MÍNIMO")

    print(
        f"  PML   : "
        f"${fila_min['PML']:,.2f}/MWh"
    )

    print(
        f"  NodoP : "
        f"{fila_min['NodoP']}"
    )

    print(
        f"  Hora  : "
        f"H{fila_min['Hora']}"
    )

    if "NOMBRE" in df_final.columns:
        print(
            f"  Nombre: "
            f"{fila_min['NOMBRE']}"
        )

    # ========================================================
    # PROMEDIO HORARIO
    # ========================================================

    print()
    print("=" * 80)
    print(
        f"PML PROMEDIO HORARIO - {sistema}"
    )
    print("=" * 80)

    print(
        promedio_horario
        .to_string(
            index=False,
            formatters={
                "PML_Promedio":
                    lambda x:
                        f"${x:,.2f}"
            }
        )
    )

    # ========================================================
    # DISTRIBUCIÓN
    # ========================================================

    print()
    print("=" * 80)
    print(
        f"DISTRIBUCIÓN DEL PML - {sistema}"
    )
    print("=" * 80)

    print(
        distribucion
        .to_string(
            index=False,
            formatters={
                "Participacion":
                    lambda x:
                        f"{x:.2f}%"
            }
        )
    )

    # ========================================================
    # TAMAÑO
    # ========================================================

    print()
    print("=" * 80)
    print(
        f"TAMAÑO REAL - {sistema}"
    )
    print("=" * 80)

    print(
        f"Archivo   : {archivo_csv}"
    )

    print(
        f"Registros : {len(df_final):,}"
    )

    print(
        f"Tamaño    : {tamano_kb:,.2f} KB"
    )

    print()
    print(
        f"{sistema} TERMINADO CORRECTAMENTE"
    )

    return {
        "Sistema": sistema,
        "Fecha": str(
            fecha_encontrada
        ),
        "NodoP_Catalogo": len(
            nodos
        ),
        "NodoP_Recibidos": int(
            nodos_recibidos
        ),
        "Registros": int(
            registros_obtenidos
        ),
        "Tamano_KB": round(
            tamano_kb,
            2
        ),
        "PML_Promedio": round(
            pml_promedio,
            2
        )
    }


# ============================================================
# EJECUTAR BCA Y SIN
# ============================================================

resumen = []

for sistema in SISTEMAS:

    resultado = procesar_sistema(
        sistema
    )

    resumen.append(
        resultado
    )


# ============================================================
# RESUMEN FINAL
# ============================================================

df_resumen = pd.DataFrame(
    resumen
)


print()
print()
print("#" * 80)
print("RESUMEN FINAL - BCA Y SIN")
print("#" * 80)

print(
    df_resumen.to_string(
        index=False
    )
)


print()
print(
    "PRUEBA BCA + SIN "
    "TERMINADA CORRECTAMENTE"
)
