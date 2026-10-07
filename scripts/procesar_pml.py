from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import time
import urllib.request
import urllib.error

import pandas as pd


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

SISTEMAS = ["SIN", "BCA", "BCS"]
PROCESOS = ["MDA", "MTR"]

MAX_NODOS_POR_CONSULTA = 20

# MDA suele estar disponible mucho antes que MTR.
# Dejamos una ventana amplia para buscar cada proceso.
MAX_DIAS_BUSQUEDA = {
    "MDA": 10,
    "MTR": 20
}

INTENTOS_POR_LOTE = 3
PAUSA_REINTENTO = 3

CARPETA_SALIDA = Path("dashboard_data")


# ============================================================
# FUNCIONES GENERALES
# ============================================================

def limpiar_numero(valor, decimales=2):

    if pd.isna(valor):
        return None

    return round(
        float(valor),
        decimales
    )


def limpiar_texto(valor):

    if pd.isna(valor):
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    return texto


def guardar_json(nombre, datos):

    CARPETA_SALIDA.mkdir(
        parents=True,
        exist_ok=True
    )

    ruta = (
        CARPETA_SALIDA
        /
        nombre
    )

    with open(
        ruta,
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            datos,
            archivo,
            ensure_ascii=False,
            indent=2
        )

    kb = (
        ruta.stat().st_size
        / 1024
    )

    print(
        f"  Guardado: {nombre} "
        f"({kb:,.2f} KB)"
    )


def crear_lotes(lista, tamano):

    return [
        lista[i:i + tamano]
        for i in range(
            0,
            len(lista),
            tamano
        )
    ]


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
        "No se encontró el catálogo NodoP."
    )


archivo_catalogo = sorted(
    archivos_catalogo
)[-1]


print("=" * 80)
print("PROCESADOR DEFINITIVO PML")
print("MDA + MTR | SIN + BCA + BCS")
print("=" * 80)

print(
    f"Catálogo: {archivo_catalogo}"
)


# ============================================================
# LEER CATÁLOGO
# ============================================================

catalogo = None


for fila_encabezado in range(10):

    prueba = pd.read_excel(
        archivo_catalogo,
        header=fila_encabezado
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

        catalogo = prueba
        break


if catalogo is None:

    raise RuntimeError(
        "No fue posible identificar "
        "el encabezado del catálogo."
    )


catalogo.columns = [
    str(c).strip()
    for c in catalogo.columns
]


catalogo["SISTEMA"] = (
    catalogo["SISTEMA"]
    .astype(str)
    .str.strip()
    .str.upper()
)


catalogo["CLAVE"] = (
    catalogo["CLAVE"]
    .astype(str)
    .str.strip()
)


catalogo = (
    catalogo[
        catalogo["SISTEMA"]
        .isin(SISTEMAS)
    ]
    .drop_duplicates(
        subset=[
            "SISTEMA",
            "CLAVE"
        ]
    )
    .copy()
)


print(
    f"NodoP catálogo: "
    f"{len(catalogo):,}"
)


for sistema in SISTEMAS:

    cantidad = (
        catalogo.loc[
            catalogo["SISTEMA"]
            == sistema,
            "CLAVE"
        ]
        .nunique()
    )

    print(
        f"  {sistema}: "
        f"{cantidad:,}"
    )


# ============================================================
# CONSULTAR SW-PML
# ============================================================

def consultar_lote(
    sistema,
    proceso,
    fecha,
    nodos,
    silencioso=False
):

    fecha_url = (
        fecha.strftime(
            "%Y/%m/%d"
        )
    )

    nodos_url = ",".join(
        nodos
    )

    url = (
        "https://ws01.cenace.gob.mx:8082/"
        "SWPML/SIM/"
        f"{sistema}/"
        f"{proceso}/"
        f"{nodos_url}/"
        f"{fecha_url}/"
        f"{fecha_url}/"
        "JSON"
    )

    solicitud = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0"
        }
    )

    for intento in range(
        1,
        INTENTOS_POR_LOTE + 1
    ):

        try:

            with urllib.request.urlopen(
                solicitud,
                timeout=120
            ) as respuesta:

                contenido = (
                    respuesta
                    .read()
                    .decode("utf-8")
                )

            datos = json.loads(
                contenido
            )

            if (
                datos.get("status")
                != "OK"
            ):

                return None

            resultados = datos.get(
                "Resultados",
                []
            )

            if not resultados:

                return None

            return datos

        except Exception as error:

            if (
                intento
                == INTENTOS_POR_LOTE
            ):

                if not silencioso:

                    print()
                    print(
                        f"ERROR {sistema} "
                        f"{proceso}: {error}"
                    )

                return None

            time.sleep(
                PAUSA_REINTENTO
            )


# ============================================================
# BUSCAR ÚLTIMA FECHA DISPONIBLE
# ============================================================

def buscar_fecha_proceso(
    proceso
):

    print()
    print("=" * 80)
    print(
        f"BUSCANDO ÚLTIMA FECHA "
        f"DISPONIBLE - {proceso}"
    )
    print("=" * 80)

    hoy = datetime.now().date()

    for dias_atras in range(
        MAX_DIAS_BUSQUEDA[
            proceso
        ]
    ):

        fecha = (
            hoy
            - timedelta(
                days=dias_atras
            )
        )

        print(
            f"Probando {fecha}...",
            end=" "
        )

        disponible = True

        for sistema in SISTEMAS:

            nodos = (
                catalogo.loc[
                    catalogo[
                        "SISTEMA"
                    ]
                    == sistema,
                    "CLAVE"
                ]
                .dropna()
                .unique()
                .tolist()
            )

            lote_prueba = (
                nodos[
                    :MAX_NODOS_POR_CONSULTA
                ]
            )

            respuesta = consultar_lote(
                sistema,
                proceso,
                fecha,
                lote_prueba,
                silencioso=True
            )

            if respuesta is None:

                disponible = False
                break

        if disponible:

            print("OK")

            return fecha

        print("No disponible")

    raise RuntimeError(
        f"No se encontró fecha "
        f"disponible para {proceso}."
    )


# ============================================================
# DESCARGAR UN PROCESO COMPLETO
# ============================================================

def descargar_proceso(
    proceso,
    fecha
):

    registros = []

    print()
    print("#" * 80)
    print(
        f"DESCARGA COMPLETA {proceso}"
    )
    print(
        f"Fecha: {fecha}"
    )
    print("#" * 80)

    for sistema in SISTEMAS:

        nodos = sorted(
            catalogo.loc[
                catalogo["SISTEMA"]
                == sistema,
                "CLAVE"
            ]
            .dropna()
            .unique()
            .tolist()
        )

        lotes = crear_lotes(
            nodos,
            MAX_NODOS_POR_CONSULTA
        )

        print()
        print(
            f"{proceso} - {sistema}"
        )

        print(
            f"NodoP: {len(nodos):,}"
        )

        print(
            f"Lotes: {len(lotes):,}"
        )

        nodos_recibidos = set()

        for numero, lote in enumerate(
            lotes,
            start=1
        ):

            print(
                f"\r  Lote "
                f"{numero:,}/"
                f"{len(lotes):,}",
                end="",
                flush=True
            )

            respuesta = consultar_lote(
                sistema,
                proceso,
                fecha,
                lote
            )

            if respuesta is None:

                raise RuntimeError(
                    f"\nFalló "
                    f"{proceso} - "
                    f"{sistema} - "
                    f"lote {numero}."
                )

            for resultado in (
                respuesta.get(
                    "Resultados",
                    []
                )
            ):

                nodo = (
                    resultado.get(
                        "clv_nodo"
                    )
                )

                nodos_recibidos.add(
                    nodo
                )

                for valor in (
                    resultado.get(
                        "Valores",
                        []
                    )
                ):

                    registros.append({

                        "Fecha":
                            valor.get(
                                "fecha"
                            ),

                        "Proceso":
                            proceso,

                        "Sistema":
                            sistema,

                        "NodoP":
                            nodo,

                        "Hora":
                            int(
                                valor.get(
                                    "hora"
                                )
                            ),

                        "PML":
                            float(
                                valor.get(
                                    "pml"
                                )
                            ),

                        "Energia":
                            float(
                                valor.get(
                                    "pml_ene"
                                )
                            ),

                        "Perdidas":
                            float(
                                valor.get(
                                    "pml_per"
                                )
                            ),

                        "Congestion":
                            float(
                                valor.get(
                                    "pml_cng"
                                )
                            )

                    })

        print()

        faltantes = (
            set(nodos)
            -
            nodos_recibidos
        )

        print(
            f"Recibidos: "
            f"{len(nodos_recibidos):,}/"
            f"{len(nodos):,}"
        )

        if faltantes:

            print(
                f"ADVERTENCIA: "
                f"{len(faltantes):,} "
                f"NodoP sin respuesta."
            )

    return pd.DataFrame(
        registros
    )


# ============================================================
# ENCONTRAR FECHAS
# ============================================================

fechas = {}


for proceso in PROCESOS:

    fechas[proceso] = (
        buscar_fecha_proceso(
            proceso
        )
    )


print()
print("=" * 80)
print("FECHAS SELECCIONADAS")
print("=" * 80)


for proceso in PROCESOS:

    print(
        f"{proceso}: "
        f"{fechas[proceso]}"
    )


# ============================================================
# DESCARGAR MDA + MTR
# ============================================================

dataframes = []


for proceso in PROCESOS:

    datos = descargar_proceso(
        proceso,
        fechas[proceso]
    )

    if datos.empty:

        raise RuntimeError(
            f"{proceso} no generó datos."
        )

    dataframes.append(
        datos
    )


pml = pd.concat(
    dataframes,
    ignore_index=True
)


# ============================================================
# VALIDACIÓN
# ============================================================

print()
print("=" * 80)
print("VALIDACIÓN GENERAL")
print("=" * 80)


validacion = (
    pml
    .groupby(
        [
            "Proceso",
            "Sistema"
        ]
    )
    .agg(
        NodoP=(
            "NodoP",
            "nunique"
        ),
        Registros=(
            "NodoP",
            "size"
        )
    )
    .reset_index()
)


print(
    validacion.to_string(
        index=False
    )
)


# ============================================================
# CRUZAR CON CATÁLOGO
# ============================================================

columnas_catalogo = [

    "SISTEMA",
    "CLAVE",
    "NOMBRE",
    "CENTRO DE CONTROL REGIONAL",
    "ZONA DE CARGA",
    "NIVEL DE TENSIÓN (kV)",
    "ZONA DE OPERACIÓN DE TRANSMISIÓN",
    "GERENCIA REGIONAL DE TRANSMISIÓN",
    "ZONA DE DISTRIBUCIÓN",
    "GERENCIA DIVISIONAL DE DISTRIBUCIÓN",
    "ENTIDAD FEDERATIVA (INEGI)",
    "MUNICIPIO (INEGI)",
    "REGION DE TRANSMISION"

]


columnas_catalogo = [
    columna
    for columna in columnas_catalogo
    if columna in catalogo.columns
]


catalogo_cruce = (
    catalogo[
        columnas_catalogo
    ]
    .copy()
)


final = pml.merge(
    catalogo_cruce,
    left_on=[
        "Sistema",
        "NodoP"
    ],
    right_on=[
        "SISTEMA",
        "CLAVE"
    ],
    how="left"
)


# ============================================================
# DISTRIBUCIÓN PML
# ============================================================

def clasificar_pml(valor):

    if valor < 0:
        return "<0"

    elif valor < 500:
        return "0-500"

    elif valor < 1000:
        return "500-1,000"

    elif valor < 2000:
        return "1,000-2,000"

    elif valor < 5000:
        return "2,000-5,000"

    elif valor < 10000:
        return "5,000-10,000"

    else:
        return "10,000 o más"


ORDEN_RANGOS = [

    "<0",
    "0-500",
    "500-1,000",
    "1,000-2,000",
    "2,000-5,000",
    "5,000-10,000",
    "10,000 o más"

]


final["RangoPML"] = (
    final["PML"]
    .apply(
        clasificar_pml
    )
)


# ============================================================
# JSON 1 - METADATOS
# ============================================================

metadata = {

    "actualizado_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "procesos": {

        "MDA": {
            "fecha":
                str(
                    fechas["MDA"]
                )
        },

        "MTR": {
            "fecha":
                str(
                    fechas["MTR"]
                )
        }

    },

    "sistemas":
        SISTEMAS,

    "nodos_catalogo":
        int(
            catalogo["CLAVE"]
            .nunique()
        ),

    "observaciones":
        int(
            len(final)
        )

}


guardar_json(
    "metadata.json",
    metadata
)


# ============================================================
# JSON 2 - RESUMEN POR PROCESO Y SISTEMA
# ============================================================

resumen = []


for proceso in PROCESOS:

    for sistema in SISTEMAS:

        datos = final[
            (
                final["Proceso"]
                == proceso
            )
            &
            (
                final["Sistema"]
                == sistema
            )
        ]

        if datos.empty:
            continue

        maximo = datos.loc[
            datos["PML"]
            .idxmax()
        ]

        minimo = datos.loc[
            datos["PML"]
            .idxmin()
        ]

        resumen.append({

            "proceso":
                proceso,

            "fecha":
                str(
                    fechas[proceso]
                ),

            "sistema":
                sistema,

            "nodos":
                int(
                    datos["NodoP"]
                    .nunique()
                ),

            "observaciones":
                int(
                    len(datos)
                ),

            "pml_promedio":
                limpiar_numero(
                    datos["PML"]
                    .mean()
                ),

            "pml_max":
                limpiar_numero(
                    maximo["PML"]
                ),

            "pml_max_nodo":
                maximo["NodoP"],

            "pml_max_hora":
                int(
                    maximo["Hora"]
                ),

            "pml_max_nombre":
                limpiar_texto(
                    maximo.get(
                        "NOMBRE"
                    )
                ),

            "pml_min":
                limpiar_numero(
                    minimo["PML"]
                ),

            "pml_min_nodo":
                minimo["NodoP"],

            "pml_min_hora":
                int(
                    minimo["Hora"]
                ),

            "pml_min_nombre":
                limpiar_texto(
                    minimo.get(
                        "NOMBRE"
                    )
                )

        })


guardar_json(
    "resumen_sistemas.json",
    resumen
)


# ============================================================
# JSON 3 - PROMEDIO HORARIO
# ============================================================

horario = (
    final
    .groupby(
        [
            "Proceso",
            "Sistema",
            "Hora"
        ],
        as_index=False
    )
    .agg(
        PML=(
            "PML",
            "mean"
        ),
        Energia=(
            "Energia",
            "mean"
        ),
        Perdidas=(
            "Perdidas",
            "mean"
        ),
        Congestion=(
            "Congestion",
            "mean"
        )
    )
)


salida_horaria = []


for _, fila in horario.iterrows():

    salida_horaria.append({

        "proceso":
            fila["Proceso"],

        "sistema":
            fila["Sistema"],

        "hora":
            int(
                fila["Hora"]
            ),

        "pml":
            limpiar_numero(
                fila["PML"]
            ),

        "energia":
            limpiar_numero(
                fila["Energia"]
            ),

        "perdidas":
            limpiar_numero(
                fila["Perdidas"]
            ),

        "congestion":
            limpiar_numero(
                fila["Congestion"]
            )

    })


guardar_json(
    "promedio_horario.json",
    salida_horaria
)


# ============================================================
# JSON 4 - DISTRIBUCIÓN
# ============================================================

salida_distribucion = []


for proceso in PROCESOS:

    for sistema in SISTEMAS:

        datos = final[
            (
                final["Proceso"]
                == proceso
            )
            &
            (
                final["Sistema"]
                == sistema
            )
        ]

        if datos.empty:
            continue

        total = len(
            datos
        )

        conteo = (
            datos["RangoPML"]
            .value_counts()
        )

        for orden, rango in enumerate(
            ORDEN_RANGOS,
            start=1
        ):

            cantidad = int(
                conteo.get(
                    rango,
                    0
                )
            )

            salida_distribucion.append({

                "proceso":
                    proceso,

                "sistema":
                    sistema,

                "orden":
                    orden,

                "rango":
                    rango,

                "observaciones":
                    cantidad,

                "participacion":
                    round(
                        cantidad
                        /
                        total
                        *
                        100,
                        2
                    )

            })


guardar_json(
    "distribucion_pml.json",
    salida_distribucion
)


# ============================================================
# JSON 5 - EXTREMOS
# ============================================================

extremos = []


for proceso in PROCESOS:

    for sistema in SISTEMAS:

        datos = final[
            (
                final["Proceso"]
                == proceso
            )
            &
            (
                final["Sistema"]
                == sistema
            )
        ]

        if datos.empty:
            continue

        indices = {

            "MAX":
                datos["PML"]
                .idxmax(),

            "MIN":
                datos["PML"]
                .idxmin()

        }

        for tipo, indice in (
            indices.items()
        ):

            fila = final.loc[
                indice
            ]

            extremos.append({

                "proceso":
                    proceso,

                "sistema":
                    sistema,

                "tipo":
                    tipo,

                "fecha":
                    fila["Fecha"],

                "hora":
                    int(
                        fila["Hora"]
                    ),

                "nodo":
                    fila["NodoP"],

                "nombre":
                    limpiar_texto(
                        fila.get(
                            "NOMBRE"
                        )
                    ),

                "zona_carga":
                    limpiar_texto(
                        fila.get(
                            "ZONA DE CARGA"
                        )
                    ),

                "gerencia":
                    limpiar_texto(
                        fila.get(
                            "GERENCIA REGIONAL DE TRANSMISIÓN"
                        )
                    ),

                "entidad":
                    limpiar_texto(
                        fila.get(
                            "ENTIDAD FEDERATIVA (INEGI)"
                        )
                    ),

                "municipio":
                    limpiar_texto(
                        fila.get(
                            "MUNICIPIO (INEGI)"
                        )
                    ),

                "pml":
                    limpiar_numero(
                        fila["PML"]
                    ),

                "energia":
                    limpiar_numero(
                        fila["Energia"]
                    ),

                "perdidas":
                    limpiar_numero(
                        fila["Perdidas"]
                    ),

                "congestion":
                    limpiar_numero(
                        fila["Congestion"]
                    )

            })


guardar_json(
    "extremos_pml.json",
    extremos
)


# ============================================================
# JSON 6 - RESUMEN POR GERENCIA
# ============================================================

salida_gerencias = []

col_gerencia = (
    "GERENCIA REGIONAL DE TRANSMISIÓN"
)


if col_gerencia in final.columns:

    agrupado = (
        final
        .dropna(
            subset=[
                col_gerencia
            ]
        )
        .groupby(
            [
                "Proceso",
                "Sistema",
                col_gerencia
            ],
            as_index=False
        )
        .agg(
            NodoP=(
                "NodoP",
                "nunique"
            ),
            PML_Promedio=(
                "PML",
                "mean"
            ),
            PML_Max=(
                "PML",
                "max"
            ),
            PML_Min=(
                "PML",
                "min"
            )
        )
    )

    for _, fila in (
        agrupado.iterrows()
    ):

        salida_gerencias.append({

            "proceso":
                fila["Proceso"],

            "sistema":
                fila["Sistema"],

            "gerencia":
                limpiar_texto(
                    fila[
                        col_gerencia
                    ]
                ),

            "nodos":
                int(
                    fila["NodoP"]
                ),

            "pml_promedio":
                limpiar_numero(
                    fila[
                        "PML_Promedio"
                    ]
                ),

            "pml_max":
                limpiar_numero(
                    fila[
                        "PML_Max"
                    ]
                ),

            "pml_min":
                limpiar_numero(
                    fila[
                        "PML_Min"
                    ]
                )

        })


guardar_json(
    "resumen_gerencias.json",
    salida_gerencias
)


# ============================================================
# JSON 7 - RESUMEN POR ENTIDAD
# ============================================================

salida_entidades = []

col_entidad = (
    "ENTIDAD FEDERATIVA (INEGI)"
)


if col_entidad in final.columns:

    agrupado = (
        final
        .dropna(
            subset=[
                col_entidad
            ]
        )
        .groupby(
            [
                "Proceso",
                "Sistema",
                col_entidad
            ],
            as_index=False
        )
        .agg(
            NodoP=(
                "NodoP",
                "nunique"
            ),
            PML_Promedio=(
                "PML",
                "mean"
            ),
            PML_Max=(
                "PML",
                "max"
            ),
            PML_Min=(
                "PML",
                "min"
            )
        )
    )

    for _, fila in (
        agrupado.iterrows()
    ):

        salida_entidades.append({

            "proceso":
                fila["Proceso"],

            "sistema":
                fila["Sistema"],

            "entidad":
                limpiar_texto(
                    fila[
                        col_entidad
                    ]
                ),

            "nodos":
                int(
                    fila["NodoP"]
                ),

            "pml_promedio":
                limpiar_numero(
                    fila[
                        "PML_Promedio"
                    ]
                ),

            "pml_max":
                limpiar_numero(
                    fila[
                        "PML_Max"
                    ]
                ),

            "pml_min":
                limpiar_numero(
                    fila[
                        "PML_Min"
                    ]
                )

        })


guardar_json(
    "resumen_entidades.json",
    salida_entidades
)


# ============================================================
# JSON 8 - CATÁLOGO COMPACTO
# ============================================================

catalogo_salida = []


for _, fila in (
    catalogo.iterrows()
):

    catalogo_salida.append({

        "sistema":
            fila["SISTEMA"],

        "nodo":
            fila["CLAVE"],

        "nombre":
            limpiar_texto(
                fila.get(
                    "NOMBRE"
                )
            ),

        "centro_control":
            limpiar_texto(
                fila.get(
                    "CENTRO DE CONTROL REGIONAL"
                )
            ),

        "zona_carga":
            limpiar_texto(
                fila.get(
                    "ZONA DE CARGA"
                )
            ),

        "nivel_tension":
            limpiar_texto(
                fila.get(
                    "NIVEL DE TENSIÓN (kV)"
                )
            ),

        "zona_transmision":
            limpiar_texto(
                fila.get(
                    "ZONA DE OPERACIÓN DE TRANSMISIÓN"
                )
            ),

        "gerencia":
            limpiar_texto(
                fila.get(
                    "GERENCIA REGIONAL DE TRANSMISIÓN"
                )
            ),

        "zona_distribucion":
            limpiar_texto(
                fila.get(
                    "ZONA DE DISTRIBUCIÓN"
                )
            ),

        "gerencia_distribucion":
            limpiar_texto(
                fila.get(
                    "GERENCIA DIVISIONAL DE DISTRIBUCIÓN"
                )
            ),

        "entidad":
            limpiar_texto(
                fila.get(
                    "ENTIDAD FEDERATIVA (INEGI)"
                )
            ),

        "municipio":
            limpiar_texto(
                fila.get(
                    "MUNICIPIO (INEGI)"
                )
            ),

        "region_transmision":
            limpiar_texto(
                fila.get(
                    "REGION DE TRANSMISION"
                )
            )

    })


guardar_json(
    "catalogo_nodos.json",
    catalogo_salida
)


# ============================================================
# RESUMEN FINAL
# ============================================================

print()
print("=" * 80)
print("PROCESAMIENTO TERMINADO CORRECTAMENTE")
print("=" * 80)

print(
    f"MDA: {fechas['MDA']}"
)

print(
    f"MTR: {fechas['MTR']}"
)

print(
    f"Observaciones procesadas: "
    f"{len(final):,}"
)

print()
print("Archivos para el dashboard:")

for archivo in sorted(
    CARPETA_SALIDA.glob(
        "*.json"
    )
):

    print(
        f"  {archivo}"
    )
