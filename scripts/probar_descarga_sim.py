"""Prueba independiente: descarga CSV de la primera fila del reporte SIM.
No modifica los datos del dashboard. Requiere: pip install requests beautifulsoup4
"""
from pathlib import Path
import re
import requests
from bs4 import BeautifulSoup

URL = 'https://www.cenace.gob.mx/Paginas/SIM/Reportes/EnergiaGeneradaTipoTec.aspx'
OUT = Path('prueba_sim')
OUT.mkdir(exist_ok=True)

with requests.Session() as s:
    s.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; SIM-CSV-Test/1.0)'})
    page = s.get(URL, timeout=40)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, 'html.parser')
    form = soup.find('form')
    if form is None:
        raise RuntimeError('No se encontró formulario ASP.NET. Revisar respuesta de la página.')

    fields = {}
    for inp in form.find_all('input'):
        name = inp.get('name')
        if name and inp.get('type', '').lower() not in ('submit', 'button', 'image', 'file'):
            fields[name] = inp.get('value', '')
    for sel in form.find_all('select'):
        name = sel.get('name')
        if name:
            chosen = sel.find('option', selected=True) or sel.find('option')
            fields[name] = chosen.get('value', '') if chosen else ''

    # Detecta el control de CSV por el nombre observado en DevTools.
    candidates = form.find_all('input', attrs={'name': re.compile(r'GridRadResultado.*gbccolumn', re.I)})
    if not candidates:
        print('No se encontró el botón CSV en la página inicial.')
        print('Puede ser necesario seleccionar el mes o generar la tabla antes de descargar.')
        (OUT / 'pagina_inicial.html').write_text(page.text, encoding='utf-8')
        raise SystemExit(2)
    btn = candidates[0]
    print('Control de descarga:', btn['name'])
    print('ATENCIÓN: prueba con la primera fila visible; no garantiza agosto 2026 ni L0.')
    fields[btn['name'] + '.x'] = '12'
    fields[btn['name'] + '.y'] = '15'
    fields.setdefault('__EVENTTARGET', '')
    fields.setdefault('__EVENTARGUMENT', '')

    response = s.post(URL, data=fields, headers={'Referer': URL}, timeout=90)
    response.raise_for_status()
    disposition = response.headers.get('Content-Disposition', '')
    print('HTTP:', response.status_code)
    print('Content-Type:', response.headers.get('Content-Type'))
    print('Content-Disposition:', disposition)
    if 'attachment' not in disposition.lower():
        (OUT / 'respuesta.html').write_bytes(response.content)
        raise RuntimeError('No se recibió descarga. Respuesta guardada en prueba_sim/respuesta.html para diagnóstico.')
    filename = 'generacion_sim_prueba.csv'
    target = OUT / filename
    target.write_bytes(response.content)
    print('Descarga recibida:', target, 'bytes:', len(response.content))
    print('Verificar periodo, sistema y liquidación dentro del archivo antes de procesarlo.')
