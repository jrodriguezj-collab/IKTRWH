# @title
import pandas as pd
import requests
import io
import datetime
import concurrent.futures
from google.colab import files, output
from IPython.display import display, HTML, clear_output
import ipywidgets as widgets

SIMPLIROUTE_TOKEN = "b388c699ed3bc4ecd2f748383e40b94ff650a8f6"
# ==========================================
# --- Variables Globales ---
df_final = pd.DataFrame()
BASE_URL = "https://api.simpliroute.com"
# --- Estilos CSS ---
estilo_limpio = """
<style>
   .tabla-reporte {
       border-collapse: collapse;
       font-family: 'Segoe UI', Arial, sans-serif;
       font-size: 13px;
       width: 100%;
       border: 1px solid #ddd;
       box-shadow: 0 2px 4px rgba(0,0,0,0.1);
   }
   .tabla-reporte th {
       background-color: #2c3e50;
       color: white;
       padding: 12px;
       text-transform: uppercase;
       font-size: 12px;
       letter-spacing: 0.5px;
   }
   .tabla-reporte td {
       border-bottom: 1px solid #eee;
       padding: 10px;
       text-align: center;
       color: #333;
   }
   .tabla-reporte tr:hover { background-color: #f8f9fa; }
   .alerta-roja { background-color: #ffebee !important; color: #c0392b !important; font-weight: bold; }
   .alerta-naranja { background-color: #fff8e1 !important; color: #e67e22 !important; }
   .btn-copiar {
       background: #27ae60;
       color: white;
       border: none;
       padding: 8px 15px;
       border-radius: 4px;
       cursor: pointer;
       font-weight: bold;
   }
</style>
"""
# --- 1. Conexión API (Paralela) ---
def api_get(endpoint, params=None):
   headers = {"Authorization": f"Token {SIMPLIROUTE_TOKEN}", "Content-Type": "application/json"}
   try:
       r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params)
       return r.json() if r.status_code == 200 else None
   except: return None
def worker_detalle(v):
   d = api_get(f"/v1/plans/visits/{v.get('id')}/detail/") or {}
   return {
       'ISO': str(v.get('title') or "S/N").strip(),
       'VEHICULO_SIMPLI': str(d.get("vehicle_name") or v.get("vehicle_name") or "").strip(),
       'CONDUCTOR_SIMPLI': str(d.get("driver_name") or "").strip(),
       'ESTADO_VISITA': str(v.get("status") or "").strip()
   }
def obtener_data_simpli():
   if not SIMPLIROUTE_TOKEN or "PEGA_AQUI" in SIMPLIROUTE_TOKEN:
       return None, "❌ Falta el Token."
   hoy = datetime.date.today().strftime("%Y-%m-%d")
   print(f"⏳ Consultando SimpliRoute ({hoy})...")
   visits = api_get("/v1/routes/visits/", {"planned_date": hoy})
   if not visits: return pd.DataFrame(), "No hay visitas hoy."
   print(f"🚀 Analizando {len(visits)} visitas...")
   with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
       resultados = list(executor.map(worker_detalle, visits))
   return pd.DataFrame(resultados), "OK"
# --- 2. Motor de Análisis ---
def motor_analisis(df_base_raw):
   global df_final
   # A. Simpli
   df_simpli, msg = obtener_data_simpli()
   if df_simpli.empty:
       print(msg)
       return
   # B. Base
   print("⚙️ Cruzando datos...")
   try:
       df_base_raw.columns = df_base_raw.columns.str.strip()
       col_com = next((c for c in df_base_raw.columns if c.lower() == 'commerce'), None)
       col_pat = next((c for c in df_base_raw.columns if c.lower() == 'patente'), None)
       col_iso = next((c for c in df_base_raw.columns if c.lower() == 'parentorder'), None)
       col_est = next((c for c in df_base_raw.columns if c.lower() == 'estado'), None)
       base_ref = df_base_raw[df_base_raw[col_com].astype(str).str.lower() == 'ikea'].copy()
       # NOTA: Ya no eliminamos los que no tienen patente para poder ver vacíos si se desea,
       # o puedes descomentar la linea de abajo si prefieres eliminar filas enteras sin patente.
       # base_ref = base_ref.dropna(subset=[col_pat])
       base_ref = base_ref[[col_iso, col_pat, col_est]]
       base_ref.columns = ['ISO', 'PATENTE_BASE', 'ESTADO_BASE']
       base_ref['ISO'] = base_ref['ISO'].astype(str).str.strip()
   except Exception as e:
       print(f"❌ Error Base: {e}")
       return
   # C. Cruce
   df_merge = pd.merge(df_simpli, base_ref, on='ISO', how='left')
   duplicados = df_simpli[df_simpli.duplicated(subset=['ISO'], keep=False)]
   # D. Lógica
   def procesar_fila(row):
       mostrar = False
       alerta = ""
       clase = ""
       # Lógica original
       if row['CONDUCTOR_SIMPLI'] == "":
           mostrar = True
           if pd.isna(row['PATENTE_BASE']) or str(row['PATENTE_BASE']).strip() == "":
               alerta = "NO EN BASE / SIN PATENTE"
               clase = "alerta-naranja"
           if row['ISO'] in duplicados['ISO'].values:
               otras = duplicados[duplicados['ISO'] == row['ISO']]
               asignadas = otras[otras['CONDUCTOR_SIMPLI'] != ""]
               if not asignadas.empty:
                   veh = asignadas.iloc[0]['VEHICULO_SIMPLI']
                   alerta = f"DUPLICADA (En {veh})"
                   clase = "alerta-roja"
       return pd.Series([alerta, clase, mostrar])
   df_merge[['ANÁLISIS', 'CLASE_CSS', 'MOSTRAR']] = df_merge.apply(procesar_fila, axis=1)
   df_final = df_merge[df_merge['MOSTRAR'] == True].copy()
   # Rellenar vacíos
   cols = ['ISO', 'PATENTE_BASE', 'ESTADO_BASE', 'VEHICULO_SIMPLI', 'ANÁLISIS', 'CLASE_CSS']
   for c in cols:
       if c not in df_final.columns: df_final[c] = ""
   df_final = df_final[cols].fillna("")
   # --- CAMBIO CLAVE PARA FILTROS ---
   # Reemplazamos strings vacíos por "(VACÍO)" para que sean clicables en el filtro
   df_final['PATENTE_BASE'] = df_final['PATENTE_BASE'].replace("", "(VACÍO)")
   df_final['ESTADO_BASE'] = df_final['ESTADO_BASE'].replace("", "(VACÍO)")
   # --- POBLAR FILTROS DESPLEGABLES ---
   # Ya no filtramos "if x != ''" porque ahora son "(VACÍO)"
   patentes = sorted([str(x) for x in df_final['PATENTE_BASE'].unique()])
   estados = sorted([str(x) for x in df_final['ESTADO_BASE'].unique()])
   filtro_patente.options = patentes
   filtro_estado.options = estados
   render_panel()
# --- 3. Panel Visual ---
out_tabla = widgets.Output()
# Widgets de Selección Múltiple
filtro_patente = widgets.SelectMultiple(
   options=[],
   description='Patentes:',
   disabled=False,
   layout=widgets.Layout(width='48%', height='120px')
)
filtro_estado = widgets.SelectMultiple(
   options=[],
   description='Estados:',
   disabled=False,
   layout=widgets.Layout(width='48%', height='120px')
)
def generar_html(df):
   if df.empty: return "<p style='padding:15px; color:green;'>✅ No hay registros pendientes con ese filtro.</p>"
   rows = ""
   for _, r in df.iterrows():
       rows += f"<tr class='{r['CLASE_CSS']}'>"
       rows += f"<td>{r['ISO']}</td>"
       rows += f"<td>{r['PATENTE_BASE']}</td>"
       rows += f"<td>{r['ESTADO_BASE']}</td>"
       rows += f"<td>{r['VEHICULO_SIMPLI']}</td>"
       rows += f"<td>{r['ANÁLISIS']}</td>"
       rows += "</tr>"
   return f"""
<table class="tabla-reporte" id="tFinal">
<thead>
<tr><th>ISO</th><th>PATENTE</th><th>ESTADO</th><th>VEHÍCULO</th><th>ANÁLISIS</th></tr>
</thead>
<tbody>{rows}</tbody>
</table>"""
def actualizar_tabla(change=None):
   with out_tabla:
       clear_output()
       if df_final.empty:
           display(HTML("<p>Sin datos.</p>"))
           return
       df_view = df_final.copy()
       # Filtro Lógico:
       vals_patente = filtro_patente.value
       vals_estado = filtro_estado.value
       if vals_patente:
           df_view = df_view[df_view['PATENTE_BASE'].astype(str).isin(vals_patente)]
       if vals_estado:
           df_view = df_view[df_view['ESTADO_BASE'].astype(str).isin(vals_estado)]
       display(HTML(f"""
       {estilo_limpio}
<div style="margin-bottom:10px; display:flex; justify-content:space-between;">
<strong>Mostrando: {len(df_view)} registros</strong>
<button class="btn-copiar" onclick="copiar()">📋 Copiar Tabla</button>
</div>
<div style="max-height:500px; overflow-y:auto;">
           {generar_html(df_view)}
</div>
<script>
       function copiar() {{
           const r = document.createRange(); r.selectNodeContents(document.getElementById('tFinal'));
           const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
           document.execCommand('copy');
           alert('¡Tabla copiada!');
       }}
</script>
       """))
filtro_patente.observe(actualizar_tabla, names='value')
filtro_estado.observe(actualizar_tabla, names='value')
def render_panel():
   clear_output()
   display(HTML("<h3>🚛 Panel de Revisión</h3><p style='font-size:12px; color:#666;'>💡 Tip: Usa <b>Ctrl + Click</b> (o Cmd + Click en Mac) para seleccionar varias opciones. Busca <b>'(VACÍO)'</b> para ver celdas en blanco.</p>"))
   display(widgets.HBox([filtro_patente, filtro_estado]))
   display(out_tabla)
   actualizar_tabla()
# --- 4. Inicio ---
def inicio():
   print("📂 Sube tu archivo Base:")
   upl = files.upload()
   if upl:
       fn = list(upl.keys())[0]
       try:
           if fn.endswith('.xlsx'): df = pd.read_excel(io.BytesIO(upl[fn]))
           else: df = pd.read_csv(io.BytesIO(upl[fn]), sep=None, engine='python')
           motor_analisis(df)
       except Exception as e: print(f"❌ Error: {e}")
if __name__ == "__main__":
   inicio()
