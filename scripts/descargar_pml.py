import json
import urllib.request
import urllib.error

from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# CONFIGURACIÓN
# ============================================================

SISTEMA = "SIN"
PROCESO = "MDA"
NODO = "01PLO-115"

# Cantidad aproximada de días históricos que queremos conservar
DIAS_HISTORICOS = 30

# El SW-PML permite consultar periodos de hasta 7 días
DIAS_POR_BLOQUE = 7


# ============================================================
# CONSTRUIR URL
# ============================================================

def construir_url(fecha_inicio, fecha_fin):

    inicio = fecha_inicio.strftime("%Y/%m/%d")
    fin = fecha_fin.strftime("%Y/%m/%d")

    return (
        "https://ws01.cenace.gob.mx:8082/"
        "SWPML/SIM/"
        f"{SISTEMA}/"
        f"{PROCESO}/"
        f"{NODO}/"
        f"{inicio}/"
        f"{fin}/"
        "JSON"
    )


# ============================================================
# CONSULTAR CENACE
# ============================================================

def consultar_cenace(fecha_inicio, fecha_fin):

    url = construir_url(
        fecha_inicio,
        fecha_fin
    )

    print()
    print("=" * 75)

    print(
        "Consultando:",
        fecha_inicio.strftime("%Y-%m-%d"),
        "a",
        fecha_fin.strftime("%Y-%m-%d")
    )

    print(url)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=60
        ) as response:

            contenido = (
                response
                .read()
                .decode("utf-8")
            )

        datos = json.loads(contenido)

        if datos.get("status") != "OK":

            print(
                "Respuesta sin status OK."
            )

            return None

        if not datos.get("Resultados"):

            print(
                "Respuesta sin resultados."
            )

            return None

        return datos


    except urllib.error.HTTPError as error:

        print(
            f"HTTP {error.code}: "
            f"{error.reason}"
        )

        return None


    except Exception as error:

        print(
            "ERROR:",
            type(error).__name__,
            error
        )

        return None


# ============================================================
# CARPETAS
# ============================================================

carpeta_datos = Path("datos")

carpeta_datos.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# PERIODO A DESCARGAR
# ============================================================

hoy = datetime.now().date()

fecha_inicio_total = (
    hoy
    - timedelta(
        days=DIAS_HISTORICOS - 1
    )
)

fecha_fin_total = hoy


print("=" * 75)
print("DESCARGA HISTÓRICA SW-PML CENACE")
print("=" * 75)

print(f"Sistema : {SISTEMA}")
print(f"Proceso : {PROCESO}")
print(f"NodoP   : {NODO}")

print(
    "Periodo :",
    fecha_inicio_total,
    "a",
    fecha_fin_total
)


# ============================================================
# GENERAR BLOQUES DE HASTA 7 DÍAS
# ============================================================

fecha_bloque_inicio = fecha_inicio_total

total_archivos_guardados = 0


while fecha_bloque_inicio <= fecha_fin_total:

    fecha_bloque_fin = min(
        fecha_bloque_inicio
        + timedelta(
            days=DIAS_POR_BLOQUE - 1
        ),
        fecha_fin_total
    )


    datos = consultar_cenace(
        fecha_bloque_inicio,
        fecha_bloque_fin
    )


    if datos:

        resultados = datos.get(
            "Resultados",
            []
        )


        # ====================================================
        # PUEDE HABER UNO O MÁS NODOS
        # ====================================================

        for resultado in resultados:

            valores = resultado.get(
                "Valores",
                []
            )


            # ================================================
            # AGRUPAR REGISTROS POR FECHA
            # ================================================

            registros_por_fecha = {}


            for registro in valores:

                fecha = registro.get(
                    "fecha"
                )

                if not fecha:
                    continue


                if fecha not in registros_por_fecha:

                    registros_por_fecha[
                        fecha
                    ] = []


                registros_por_fecha[
                    fecha
                ].append(
                    registro
                )


            # ================================================
            # CREAR UN JSON POR DÍA
            # ================================================

            for fecha, registros in registros_por_fecha.items():

                anio = fecha[:4]


                carpeta_anio = (
                    carpeta_datos
                    /
                    anio
                )


                carpeta_anio.mkdir(
                    parents=True,
                    exist_ok=True
                )


                datos_dia = {

                    "nombre":
                        datos.get("nombre"),

                    "proceso":
                        datos.get("proceso"),

                    "sistema":
                        datos.get("sistema"),

                    "area":
                        datos.get("area"),

                    "Resultados": [

                        {

                            "clv_nodo":
                                resultado.get(
                                    "clv_nodo"
                                ),

                            "Valores":
                                registros

                        }

                    ],

                    "status":
                        datos.get("status")

                }


                archivo_dia = (
                    carpeta_anio
                    /
                    f"{fecha}.json"
                )


                with open(
                    archivo_dia,
                    "w",
                    encoding="utf-8"
                ) as archivo:

                    json.dump(
                        datos_dia,
                        archivo,
                        ensure_ascii=False,
                        indent=4
                    )


                total_archivos_guardados += 1


                print(
                    "Guardado:",
                    archivo_dia,
                    f"({len(registros)} registros)"
                )


    fecha_bloque_inicio = (
        fecha_bloque_fin
        + timedelta(days=1)
    )


# ============================================================
# BUSCAR TODOS LOS ARCHIVOS HISTÓRICOS
# ============================================================

archivos_historicos = sorted(
    carpeta_datos.glob("*/*.json")
)


if not archivos_historicos:

    raise RuntimeError(
        "No se pudo obtener ningún "
        "archivo histórico."
    )


# ============================================================
# CREAR LISTA DE FECHAS
# ============================================================

fechas_disponibles = sorted(
    [
        archivo.stem
        for archivo
        in archivos_historicos
    ],
    reverse=True
)


ultima_fecha = fechas_disponibles[0]


print()
print("=" * 75)
print("RESUMEN")
print("=" * 75)

print(
    "Archivos generados en esta ejecución:",
    total_archivos_guardados
)

print(
    "Fechas históricas disponibles:",
    len(fechas_disponibles)
)

print(
    "Última fecha disponible:",
    ultima_fecha
)


# ============================================================
# COPIAR ÚLTIMO DÍA A datos_pml.json
# ============================================================

archivo_ultimo = (
    carpeta_datos
    /
    ultima_fecha[:4]
    /
    f"{ultima_fecha}.json"
)


with open(
    archivo_ultimo,
    "r",
    encoding="utf-8"
) as archivo:

    datos_ultimo = json.load(
        archivo
    )


with open(
    "datos_pml.json",
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        datos_ultimo,
        archivo,
        ensure_ascii=False,
        indent=4
    )


print(
    "Actualizado: datos_pml.json"
)


# ============================================================
# CREAR ÍNDICE PARA EL DASHBOARD
# ============================================================

indice = {

    "ultima_actualizacion":
        datetime.now().isoformat(
            timespec="seconds"
        ),

    "sistema":
        SISTEMA,

    "proceso":
        PROCESO,

    "nodo":
        NODO,

    "ultima_fecha_disponible":
        ultima_fecha,

    "total_fechas":
        len(
            fechas_disponibles
        ),

    "fechas_disponibles":
        fechas_disponibles

}


with open(
    "indice_pml.json",
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        indice,
        archivo,
        ensure_ascii=False,
        indent=4
    )


print(
    "Actualizado: indice_pml.json"
)

print()
print("=" * 75)
print("PROCESO TERMINADO CORRECTAMENTE")
print("=" * 75)
