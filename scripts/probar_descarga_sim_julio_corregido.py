"""Prueba controlada de descarga del SIM para JULIO 2026.
No altera el dashboard ni requiere cookies del navegador.
Dependencias: requests, beautifulsoup4.
"""
import json
import re
from pathlib import Path
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

URL = 'https://www.cenace.gob.mx/Paginas/SIM/Reportes/EnergiaGeneradaTipoTec.aspx'
OUT = Path('prueba_sim')
OUT.mkdir(parents=True, exist_ok=True)
ANIO, MES, DIA = 2026, 7, 17
MES_NOMBRE = 'julio'
FECHA = f'{ANIO:04d}-{MES:02d}-{DIA:02d}'


def campos_formulario(html):
    soup = BeautifulSoup(html, 'html.parser')
    form = soup.find('form')
    if form is None:
        raise RuntimeError('No se encontró el formulario ASP.NET.')
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
    return soup, form, fields


def cambiar_fecha(fields, control):
    base = f'ctl00$ContentPlaceHolder1${control}'
    prefix = f'ctl00_ContentPlaceHolder1_{control}'
    fields[base] = FECHA
    fields[base + '$dateInput'] = f'{MES_NOMBRE} de {ANIO}'
    state_key = prefix + '_dateInput_ClientState'
    state = json.loads(fields.get(state_key, '{}') or '{}')
    value = f'{FECHA}-00-00-00'
    state.update(validationText=value, valueAsString=value,
                 lastSetTextBoxValue=f'{MES_NOMBRE} de {ANIO}')
    fields[state_key] = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
    ad_key = prefix + '_AD'
    if ad_key in fields:
        ad = json.loads(fields[ad_key])
        if isinstance(ad, list) and len(ad) >= 3:
            ad[1] = [ANIO, MES, DIA]
            ad[2] = [ANIO, MES, DIA]
            fields[ad_key] = json.dumps(ad, separators=(',', ':'))


def localizar_boton_julio(form):
    for row in form.find_all('tr'):
        texto = row.get_text(' ', strip=True).lower()
        if not re.search(r'\bjulio\s+2026\b', texto):
            continue
        if not re.search(r'(?<![a-z0-9])(?:0|l0)(?![a-z0-9])', texto):
            continue
        inp = row.find('input', attrs={'name': re.compile(r'GridRadResultado.*gbccolumn', re.I)})
        if inp:
            return inp['name'], texto[:240]
    return None, None


def guardar_html(nombre, response):
    (OUT / nombre).write_bytes(response.content)
    print('Diagnóstico guardado:', OUT / nombre)


with requests.Session() as session:
    session.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; SIM-CSV-Test/1.1)'})
    response = session.get(URL, timeout=45)
    response.raise_for_status()
    soup, form, fields = campos_formulario(response.text)
    boton, fila = localizar_boton_julio(form)

    if not boton:
        print('Julio L0 no está visible inicialmente. Intentando seleccionar julio 2026...')
        for control in ('FechaConsulta', 'FechaInicial', 'FechaFinal'):
            cambiar_fecha(fields, control)
        fields['__EVENTTARGET'] = 'ctl00$ContentPlaceHolder1$FechaConsulta'
        fields['__EVENTARGUMENT'] = ''
        response = session.post(URL, data=fields, headers={'Referer': URL}, timeout=90)
        response.raise_for_status()
        if 'attachment' in response.headers.get('Content-Disposition', '').lower():
            raise RuntimeError('El cambio de mes devolvió inesperadamente una descarga; se detiene por seguridad.')
        soup, form, fields = campos_formulario(response.text)
        boton, fila = localizar_boton_julio(form)
        if not boton:
            guardar_html('respuesta_seleccion_julio.html', response)
            print('No se encontró una fila identificada como Julio 2026 / L0.')
            print('No se descargó otro mes por error. Comparte el artifact para revisar la selección de mes.')
            raise SystemExit(2)

    print('Fila objetivo:', fila)
    print('Botón CSV:', boton)
    fields[boton + '.x'] = '12'
    fields[boton + '.y'] = '15'
    fields['__EVENTTARGET'] = ''
    fields['__EVENTARGUMENT'] = ''
    response = session.post(URL, data=fields, headers={'Referer': URL}, timeout=90)
    response.raise_for_status()
    disposition = response.headers.get('Content-Disposition', '')
    print('HTTP:', response.status_code)
    print('Content-Disposition:', disposition)
    if 'attachment' not in disposition.lower():
        guardar_html('respuesta_descarga_julio.html', response)
        raise RuntimeError('El servidor no devolvió un archivo adjunto.')
    filename = unquote(disposition).lower()
    if not re.search(r'julio[ _-]+2026', filename, re.I) or not re.search(r'(?<![a-z0-9])l0(?![a-z0-9])', filename, re.I):
        raise RuntimeError('Archivo rechazado: el nombre no confirma JULIO 2026 y L0.')
    if not response.content or response.content.lstrip().lower().startswith(b'<!doctype html'):
        raise RuntimeError('Contenido vacío o HTML en lugar de CSV.')
    target = OUT / 'generacion_L0_SEN_julio_2026.csv'
    target.write_bytes(response.content)
    print('VALIDACIÓN DEL NOMBRE: JULIO 2026 / L0')
    print('Archivo guardado:', target, '| bytes:', len(response.content))
    print('Pendiente: validar estructura y valores internos del CSV.')
