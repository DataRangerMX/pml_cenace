from pathlib import Path
import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

SISTEMA_OBJETIVO = "BCS"


# ============================================================
# LOCALIZAR CATÁLOGO AUTOMÁTICAMENTE
# ============================================================

archivos = list(
    Path(".").glob("Catálogo NodosP Sistema Eléctrico Nacional*.xlsx")
)

if not archivos:
    raise FileNotFoundError(
        "No se encontró el catálogo de NodoP en la raíz del repositorio."
    )

# Si hubiera varias versiones, usamos la de nombre mayor.
archivo_catalogo = sorted(archivos)[-1]

print("=" * 70)
print("DIAGNÓSTICO CATÁLOGO NODOSP")
print("=" * 70)
print(f"Archivo: {archivo_catalogo}")
print()


# ============================================================
# LEER EXCEL
# ============================================================

# El catálogo de CENACE tiene encabezados informativos antes
# de la tabla. Probamos distintas filas hasta encontrar CLAVE
# y SISTEMA.

df = None
fila_encabezado = None

for fila in range(0, 10):

    prueba = pd.read_excel(
        archivo_catalogo,
        header=fila
    )

    columnas = [
        str(col).strip().upper()
        for col in prueba.columns
    ]

    if "CLAVE" in columnas and "SISTEMA" in columnas:
        df = prueba
        fila_encabezado = fila
        break


if df is None:
    raise ValueError(
        "No se pudo localizar automáticamente "
        "el encabezado del catálogo."
    )


# ============================================================
# LIMPIAR NOMBRES DE COLUMNAS
# ============================================================

df.columns = [
    str(col).strip()
    for col in df.columns
]


print(f"Encabezado detectado en fila Excel: {fila_encabezado + 1}")
print(f"Registros totales del catálogo: {len(df):,}")
print(f"Columnas detectadas: {len(df.columns)}")
print()


# ============================================================
# MOSTRAR COLUMNAS
# ============================================================

print("=" * 70)
print("COLUMNAS DEL CATÁLOGO")
print("=" * 70)

for numero, columna in enumerate(df.columns, start=1):
    print(f"{numero:02d}. {columna}")

print()


# ============================================================
# LIMPIAR SISTEMA Y CLAVE
# ============================================================

df["SISTEMA"] = (
    df["SISTEMA"]
    .astype(str)
    .str.strip()
    .str.upper()
)

df["CLAVE"] = (
    df["CLAVE"]
    .astype(str)
    .str.strip()
)


# Eliminar filas sin una clave real
df = df[
    df["CLAVE"].notna()
    & (df["CLAVE"] != "")
    & (df["CLAVE"].str.lower() != "nan")
].copy()


# ============================================================
# RESUMEN POR SISTEMA
# ============================================================

print("=" * 70)
print("NODOSP POR SISTEMA")
print("=" * 70)

resumen_sistemas = (
    df.groupby("SISTEMA")["CLAVE"]
    .nunique()
    .sort_values(ascending=False)
)

print(resumen_sistemas.to_string())
print()


# ============================================================
# FILTRAR BCS
# ============================================================

bcs = df[
    df["SISTEMA"] == SISTEMA_OBJETIVO
].copy()


total_registros_bcs = len(bcs)

nodos_unicos_bcs = (
    bcs["CLAVE"].nunique()
)


print("=" * 70)
print(f"DIAGNÓSTICO {SISTEMA_OBJETIVO}")
print("=" * 70)

print(
    f"Registros: {total_registros_bcs:,}"
)

print(
    f"NodoP únicos: {nodos_unicos_bcs:,}"
)

print()


# ============================================================
# DUPLICADOS
# ============================================================

duplicados = (
    bcs[
        bcs.duplicated(
            subset=["CLAVE"],
            keep=False
        )
    ]
    .sort_values("CLAVE")
)


print(
    f"Registros correspondientes a claves duplicadas: "
    f"{len(duplicados):,}"
)

print()


if not duplicados.empty:

    print("CLAVES DUPLICADAS:")

    print(
        duplicados[
            ["CLAVE"]
        ]
        .drop_duplicates()
        .to_string(index=False)
    )

    print()


# ============================================================
# PRIMEROS NODOS
# ============================================================

columnas_muestra = [
    columna
    for columna in [
        "SISTEMA",
        "CLAVE",
        "NOMBRE",
        "CENTRO DE CONTROL REGIONAL",
        "ZONA DE CARGA",
        "ENTIDAD FEDERATIVA",
        "MUNICIPIO"
    ]
    if columna in bcs.columns
]


print("=" * 70)
print("PRIMEROS 10 NODOSP BCS")
print("=" * 70)

print(
    bcs[
        columnas_muestra
    ]
    .head(10)
    .to_string(index=False)
)

print()


# ============================================================
# ESTIMACIÓN DE LA CONSULTA SW-PML
# ============================================================

TAMANO_LOTE = 20

numero_lotes = (
    nodos_unicos_bcs
    + TAMANO_LOTE
    - 1
) // TAMANO_LOTE


registros_teoricos = (
    nodos_unicos_bcs
    * 24
)


print("=" * 70)
print("ESTIMACIÓN PARA CONSULTAR SW-PML")
print("=" * 70)

print(
    f"NodoP BCS: {nodos_unicos_bcs:,}"
)

print(
    f"Tamaño máximo por lote: {TAMANO_LOTE}"
)

print(
    f"Consultas necesarias aproximadamente: {numero_lotes:,}"
)

print(
    f"Registros teóricos para 1 día: "
    f"{registros_teoricos:,}"
)

print()


print("=" * 70)
print("DIAGNÓSTICO TERMINADO CORRECTAMENTE")
print("=" * 70)
