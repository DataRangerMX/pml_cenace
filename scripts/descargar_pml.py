import json
import urllib.request
import urllib.error
from pathlib import Path


# ============================================================
# CONFIGURACIÓN DE LA CONSULTA
# ============================================================

SISTEMA = "SIN"
PROCESO = "MDA"
NODO = "01PLO-115"

FECHA_INICIO = "2017/11/07"
FECHA_FIN = "2017/11/07"


# ============================================================
# CONSTRUIR URL DEL SW-PML
# ============================================================

url = (
    "https://ws01.cenace.gob.mx:8082/"
    "SWPML/SIM/"
    f"{SISTEMA}/"
    f"{PROCESO}/"
    f"{NODO}/"
    f"{FECHA_INICIO}/"
    f"{FECHA_FIN}/"
    "JSON"
)


print("=" * 60)
print("PRUEBA SW-PML CENACE")
print("=" * 60)

print(f"Sistema : {SISTEMA}")
print(f"Proceso : {PROCESO}")
print(f"NodoP   : {NODO}")
print(f"URL     : {url}")

print()
print("Intentando conectar con CENACE...")


# ============================================================
# REALIZAR CONSULTA
# ============================================================

try:

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        status = response.status

        contenido = response.read().decode("utf-8")


    print()
    print("CONEXIÓN EXITOSA")
    print(f"Código HTTP: {status}")

    print()
    print("Primeros 500 caracteres recibidos:")
    print("-" * 60)

    print(contenido[:500])


    # ========================================================
    # INTENTAR INTERPRETAR RESPUESTA COMO JSON
    # ========================================================

    datos = json.loads(contenido)


    # ========================================================
    # GUARDAR RESULTADO
    # ========================================================

    archivo_salida = Path("datos_pml.json")

    with open(
        archivo_salida,
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            datos,
            archivo,
            ensure_ascii=False,
            indent=4
        )


    print()
    print("=" * 60)
    print("ARCHIVO GENERADO CORRECTAMENTE")
    print("=" * 60)

    print(f"Archivo: {archivo_salida}")


# ============================================================
# ERRORES HTTP
# ============================================================

except urllib.error.HTTPError as error:

    print()
    print("ERROR HTTP")

    print(f"Código: {error.code}")
    print(f"Mensaje: {error.reason}")

    raise


# ============================================================
# OTROS ERRORES
# ============================================================

except Exception as error:

    print()
    print("ERROR AL CONSULTAR CENACE")

    print(type(error).__name__)
    print(error)

    raise
