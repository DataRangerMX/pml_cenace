from pathlib import Path
from datetime import datetime, timedelta
import json
import urllib.request
import urllib.error
import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

SISTEMA = "BCS"
PROCESO = "MDA"

MAX_NODOS_POR_CONSULTA = 20
MAX_DIAS_BUSQUEDA = 10


# ============================================================
# BUSCAR CATÁLOGO
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

archivo_catalogo = sorted(
    archivos_catalogo
)[-1]


print("=" * 75)
print("PRUEBA PML COMPLETO BCS")
print("=" * 75)

print(f"Catálogo : {archivo_catalogo}")
print(f"Sistema  : {SISTEMA}")
print(f"Proceso  : {PROCESO}")

print("=" * 75)


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


# ============================================================
# FILTRAR BCS
# ============================================================

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


df_bcs = (
    df_catalogo[
        df_catalogo["SISTEMA"]
        == SISTEMA
    ]
    .copy()
)


df_bcs = (
    df_bcs
    .drop_duplicates(
        subset=["CLAVE"]
    )
)


nodos = sorted(
    df_bcs["CLAVE"]
    .dropna()
    .tolist()
)


print()
print(f"NodoP encontrados: {len(nodos)}")


# ============================================================
# DIVIDIR EN LOTES
# ============================================================

lotes = [

    nodos[i:i + MAX_NODOS_POR_CONSULTA]

    for i in range(
        0,
        len(nodos),
        MAX_NODOS_POR_CONSULTA
    )

]


print(
    f"Lotes necesarios: {len(lotes)}"
)

for numero, lote in enumerate(
    lotes,
    start=1
):

    print(
        f"Lote {numero}: "
        f"{len(lote)} NodoP"
    )


# ============================================================
# FUNCIÓN CONSULTA
# ============================================================

def consultar_lote(
    fecha,
    lote,
    numero_lote
):

    fecha_url = fecha.strftime(
        "%Y/%m/%d"
    )

    # SW-PML recibe las claves separadas por coma
    lista_nodos = ",".join(lote)

    url = (
        "https://ws01.cenace.gob.mx:8082/"
        "SWPML/SIM/"
        f"{SISTEMA}/"
        f"{PROCESO}/"
        f"{lista_nodos}/"
        f"{fecha_url}/"
        f"{fecha_url}/"
        "JSON"
    )


    print()
    print(
        f"  Consultando lote "
        f"{numero_lote}/{len(lotes)} "
        f"({len(lote)} NodoP)"
    )


    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0"
        }
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=90
        ) as response:

            contenido = (
                response
                .read()
                .decode("utf-8")
            )


        datos = json.loads(
            contenido
        )


        if datos.get("status") != "OK":

            print(
                "  Sin status OK."
            )

            return None


        resultados = datos.get(
            "Resultados",
            []
        )


        if not resultados:

            print(
                "  Sin resultados."
            )

            return None


        print(
            f"  Respuesta: "
            f"{len(resultados)} NodoP"
        )


        return datos


    except urllib.error.HTTPError as error:

        print(
            f"  HTTP {error.code}: "
            f"{error.reason}"
        )

        return None


    except Exception as error:

        print(
            "  ERROR:",
            type(error).__name__,
            error
        )

        return None


# ============================================================
# BUSCAR ÚLTIMA FECHA COMPLETA
# ============================================================

hoy = datetime.now().date()

datos_fecha = None
fecha_encontrada = None


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
    print("=" * 75)
    print(
        f"PROBANDO FECHA: "
        f"{fecha_prueba}"
    )
    print("=" * 75)


    respuestas = []

    fecha_valida = True


    for numero_lote, lote in enumerate(
        lotes,
        start=1
    ):

        respuesta = consultar_lote(
            fecha_prueba,
            lote,
            numero_lote
        )


        if respuesta is None:

            fecha_valida = False
            break


        respuestas.append(
            respuesta
        )


    if fecha_valida:

        datos_fecha = respuestas
        fecha_encontrada = fecha_prueba

        print()
        print(
            "FECHA DISPONIBLE EN TODOS "
            "LOS LOTES"
        )

        break


if datos_fecha is None:

    raise RuntimeError(
        "No se encontró una fecha "
        "completa en los últimos "
        f"{MAX_DIAS_BUSQUEDA} días."
    )


# ============================================================
# CONVERTIR RESPUESTAS A TABLA
# ============================================================

registros = []


for respuesta in datos_fecha:

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
                    SISTEMA,

                "NodoP":
                    nodo,

                "Hora":
                    int(valor.get("hora")),

                "PML":
                    float(valor.get("pml")),

                "Energia":
                    float(valor.get("pml_ene")),

                "Perdidas":
                    float(valor.get("pml_per")),

                "Congestion":
                    float(valor.get("pml_cng"))

            })


df_pml = pd.DataFrame(
    registros
)


# ============================================================
# VALIDACIÓN
# ============================================================

nodos_recibidos = (
    df_pml["NodoP"]
    .nunique()
)


registros_obtenidos = len(
    df_pml
)


registros_teoricos = (
    len(nodos)
    * 24
)


nodos_sin_datos = sorted(
    set(nodos)
    -
    set(
        df_pml["NodoP"]
        .unique()
    )
)


print()
print("=" * 75)
print("VALIDACIÓN DE LA DESCARGA")
print("=" * 75)

print(
    f"Fecha: {fecha_encontrada}"
)

print(
    f"NodoP catálogo: "
    f"{len(nodos)}"
)

print(
    f"NodoP recibidos: "
    f"{nodos_recibidos}"
)

print(
    f"Registros teóricos: "
    f"{registros_teoricos:,}"
)

print(
    f"Registros obtenidos: "
    f"{registros_obtenidos:,}"
)

print(
    f"NodoP sin datos: "
    f"{len(nodos_sin_datos)}"
)


if nodos_sin_datos:

    print(
        "Claves sin datos:"
    )

    for nodo in nodos_sin_datos:
        print(
            f" - {nodo}"
        )


# ============================================================
# CRUZAR CON CATÁLOGO
# ============================================================

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

    c for c in columnas_catalogo

    if c in df_bcs.columns

]


df_catalogo_cruce = (
    df_bcs[
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


# ============================================================
# ESTADÍSTICAS
# ============================================================

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


print()
print("=" * 75)
print("RESULTADOS GENERALES BCS")
print("=" * 75)

print(
    f"PML promedio: "
    f"${pml_promedio:,.2f}/MWh"
)

print()

print("PML MÁXIMO")

print(
    f"  PML: "
    f"${fila_max['PML']:,.2f}/MWh"
)

print(
    f"  NodoP: "
    f"{fila_max['NodoP']}"
)

print(
    f"  Hora: "
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
    f"  PML: "
    f"${fila_min['PML']:,.2f}/MWh"
)

print(
    f"  NodoP: "
    f"{fila_min['NodoP']}"
)

print(
    f"  Hora: "
    f"H{fila_min['Hora']}"
)

if "NOMBRE" in df_final.columns:

    print(
        f"  Nombre: "
        f"{fila_min['NOMBRE']}"
    )


# ============================================================
# PROMEDIO HORARIO
# ============================================================

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


print()
print("=" * 75)
print("PML PROMEDIO HORARIO BCS")
print("=" * 75)

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


# ============================================================
# DISTRIBUCIÓN
# ============================================================

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


print()
print("=" * 75)
print("DISTRIBUCIÓN DEL PML")
print("=" * 75)

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


# ============================================================
# GUARDAR RESULTADO DE PRUEBA
# ============================================================

carpeta_salida = Path(
    "resultados_prueba"
)

carpeta_salida.mkdir(
    exist_ok=True
)


archivo_csv = (
    carpeta_salida
    /
    "pml_bcs_prueba.csv"
)


df_final.to_csv(
    archivo_csv,
    index=False,
    encoding="utf-8-sig"
)


tamano_bytes = (
    archivo_csv.stat().st_size
)


tamano_kb = (
    tamano_bytes
    / 1024
)


print()
print("=" * 75)
print("TAMAÑO REAL")
print("=" * 75)

print(
    f"Archivo: {archivo_csv}"
)

print(
    f"Registros: "
    f"{len(df_final):,}"
)

print(
    f"Tamaño: "
    f"{tamano_kb:,.2f} KB"
)


print()
print("=" * 75)
print("PRUEBA BCS TERMINADA CORRECTAMENTE")
print("=" * 75)
