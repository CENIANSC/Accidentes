from pathlib import Path
import unicodedata
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from folium.plugins import HeatMap, MarkerCluster
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, Point
from shapely.prepared import prep
import requests
import json
import re
import datetime
from shapely.geometry import mapping

MUNICIPIOS = [
'Abasolo','Acámbaro','San Miguel de Allende','Apaseo el Alto','Apaseo el Grande','Atarjea','Celaya','Manuel Doblado','Comonfort','Coroneo','Cortazar','Cuerámaro','Doctor Mora','Dolores Hidalgo Cuna de la Independencia Nacional','Guanajuato','Huanímaro','Irapuato','Jaral del Progreso','Jerécuaro','León','Moroleón','Ocampo','Pénjamo','Pueblo Nuevo','Purísima del Rincón','Romita','Salamanca','Salvatierra','San Diego de la Unión','San Felipe','San Francisco del Rincón','San José Iturbide','San Luis de la Paz','Santa Catarina','Santa Cruz de Juventino Rosas','Santiago Maravatío','Silao de la Victoria','Tarandacuao','Tarimoro','Tierra Blanca','Uriangato','Valle de Santiago','Victoria','Villagrán','Xichú','Yuriria']
MUNICIPIOS_POR_CLAVE = {f'11{i:03d}': nombre for i,nombre in enumerate(MUNICIPIOS,1)}
BASE_DIR = Path(__file__).parent
DATA = BASE_DIR / 'data' / 'accidentes.xlsx'
INEGI_BASE = 'https://gaia.inegi.org.mx/wscatgeo/v2/geo/mgem/'

st.set_page_config(page_title='Observatorio Guanajuato | Laboratorio geoespacial',page_icon='🗺️',layout='wide')
st.markdown("""<style>.block-container{padding-top:1.1rem;max-width:1550px}h1,h2,h3{letter-spacing:-.025em}div[data-testid="stMetric"]{background:#f3f6f9;border:1px solid #dce4ec;border-radius:10px;padding:14px}</style>""",unsafe_allow_html=True)
st.title('Observatorio de accidentes | Laboratorio geoespacial')
st.markdown('**Plataforma de exploración geográfica y estadística de accidentes de tránsito para los 46 municipios del estado de Guanajuato.**')
st.caption('Desarrollada por Daniel A. Aguirre Ibarra (Doctorado en Logística y Dirección de la Cadena de Suministro | UPAEP), con el apoyo del Observatorio Ciudadano de Irapuato.')

@st.cache_data(ttl=86400,show_spinner='Consultando polígono oficial INEGI…')
def get_municipal_boundary(cvegeo):
    response=requests.get(INEGI_BASE+cvegeo,timeout=35,headers={'Accept':'application/json','User-Agent':'ObservatorioGuanajuato/7.0'})
    response.raise_for_status()
    obj=response.json()
    if isinstance(obj,str):
        obj=json.loads(obj)
    if isinstance(obj,list): candidates=obj
    elif isinstance(obj,dict) and obj.get('type')=='FeatureCollection': candidates=obj.get('features',[])
    elif isinstance(obj,dict) and obj.get('type')=='Feature': candidates=[obj]
    elif isinstance(obj,dict) and obj.get('type') in ('Polygon','MultiPolygon'): candidates=[obj]
    elif isinstance(obj,dict) and 'features' in obj: candidates=obj['features']
    elif isinstance(obj,dict): candidates=[obj]
    else:raise ValueError('Respuesta INEGI no reconocible')
    geometries=[]
    for item in candidates:
        if not isinstance(item,dict):continue
        props=item.get('properties') or item
        code=str(props.get('cvegeo') or props.get('CVEGEO') or '').strip()
        if code and code!=cvegeo:continue
        g=item.get('geometry') or item.get('geojson') or item.get('geometria')
        if g is None and item.get('type') in ('Polygon','MultiPolygon'):g=item
        if isinstance(g,str):g=json.loads(g)
        if isinstance(g,dict) and g.get('type')=='Feature':g=g.get('geometry')
        if isinstance(g,dict) and g.get('type') in ('Polygon','MultiPolygon'):
            geom=shape(g)
            if geom.is_valid and not geom.is_empty:geometries.append(geom)
    if len(geometries)!=1:raise ValueError(f'INEGI no devolvió un polígono municipal único y válido para {cvegeo}; encontrados: {len(geometries)}')
    poly=geometries[0]
    minx,miny,maxx,maxy=poly.bounds
    if not (-104<minx<maxx<-99 and 18<miny<maxy<23):raise ValueError('Geometría fuera de Guanajuato')
    return mapping(poly)

@st.cache_data(show_spinner='Clasificando coordenadas…')
def classify_coordinates(data,geometry):
    polygon=prep(shape(geometry))
    d=data.copy()
    missing=d['lat'].isna() | d['lon'].isna()
    world=d['lat'].between(-90,90)&d['lon'].between(-180,180)
    zero=(d['lat']==0)&(d['lon']==0)
    valid=~missing & world & ~zero
    inside=np.array([bool(polygon.covers(Point(float(lon),float(lat)))) if ok else False for lat,lon,ok in zip(d['lat'],d['lon'],valid)])
    d['geo_ok']=inside
    d['coord_estado']=np.select([missing,~world|zero,~d['geo_ok']],['Sin coordenadas / no numéricas','Coordenadas inválidas','Fuera del municipio (revisar)'],default='Dentro del municipio')
    return d

st.markdown('### 00 / Territorio y fuente de datos')
with st.expander('📘 Instrucciones para preparar y cargar una base municipal',expanded=False):
    st.markdown("""**¿Qué archivo debo cargar?** Un Excel `.xlsx` con una hoja de datos, una fila por accidente y los encabezados en la primera fila. Descarga la plantilla para conservar los nombres exactos de las columnas.

**Columnas obligatorias:** `FECHA`, `HORA`, `COLONIA`, `CALLE1`, `CALLE2`, `LATITUD`, `LONGITUD`, `VEHÍCULOS PARTICIPANTES`, `TIPO DE ACCIDENTE`, `CAUSA`.

**Columnas recomendadas de la plantilla:** `DIA`, `MES`, `AÑO`. Se calculan a partir de `FECHA`, por lo que no es necesario llenarlas para que funcione el análisis.

**Formatos:** fecha como fecha de Excel o `AAAA-MM-DD`; hora como hora de Excel (`HH:MM`, formato de 24 horas); latitud y longitud en grados decimales (ejemplo: `20.6767`, `-101.3563`). No intercambies latitud y longitud.

**Datos no disponibles:** usa `N/E` o deja la celda vacía. No inventes valores ni uses coordenadas `0,0`. Las categorías no especificadas se conservan como *Sin dato*.

**Procedimiento:** selecciona el municipio, carga su propio Excel y revisa la auditoría. Los registros con coordenadas fuera del límite municipal o sin ubicación verificable no entran en las estadísticas. El archivo original no se modifica.

**Privacidad:** no incluyas nombres de personas, teléfonos, domicilios particulares ni datos clínicos. Si cargas un archivo desde el navegador, se utiliza para la sesión y no se incorpora automáticamente al repositorio.

**Periodos:** Madrugada 00:00–05:59 · Mañana 06:00–11:59 · Tarde 12:00–17:59 · Noche 18:00–23:59. Los registros sin hora se pueden incluir mediante una opción específica.""")
    template_path=BASE_DIR/'data'/'plantilla_municipal.xlsx'
    if template_path.exists():
        st.download_button('⬇ Descargar plantilla Excel municipal',template_path.read_bytes(),file_name='Plantilla_Accidentes_Municipal.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

mun_col,source_col=st.columns([1,2])
with mun_col:
    municipio=st.selectbox('Municipio de Guanajuato',list(MUNICIPIOS_POR_CLAVE),index=16,format_func=lambda k:f'{MUNICIPIOS_POR_CLAVE[k]} · {k}')
with source_col:
    local_path=BASE_DIR/'data'/'municipios'/f'{municipio}.xlsx'
    if municipio=='11017':
        st.caption('Fuente predeterminada: base histórica de Irapuato 2019–2025. Puedes sustituirla temporalmente.')
    elif local_path.exists():
        st.caption(f'Fuente municipal encontrada: data/municipios/{municipio}.xlsx')
    else:
        st.info('Para este municipio necesitas cargar su propia base. No se reutilizan los accidentes de Irapuato.')
    uploaded=st.file_uploader('Base de accidentes del municipio (.xlsx)',type=['xlsx'],key=f'upload_{municipio}')

if uploaded is None and municipio!='11017' and not local_path.exists():
    st.warning('Carga un archivo Excel del municipio seleccionado para habilitar mapas, estadísticas y auditoría.')
    st.stop()
source=uploaded if uploaded is not None else (DATA if municipio=='11017' else local_path)
try:
    municipal_geometry=get_municipal_boundary(municipio)
except (requests.RequestException,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
    st.error('No se pudo validar el límite oficial del municipio con INEGI. Los análisis se detienen para evitar resultados incorrectos.')
    st.caption(f'Detalle técnico: {exc}')
    st.stop()

DAYS = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
MONTHS = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']

def clean_text(x):
    if pd.isna(x): return 'Sin dato'
    s = str(x).strip().upper()
    if not s or s in ('N/E','N. E.','N.E.','N/D','N/A','NAN','NONE','-','S/D','SIN DATO'): return 'Sin dato'
    s = ' '.join(s.split())
    return unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode('ascii')

@st.cache_data(show_spinner='Leyendo base de accidentes…')
def load_data(source):
    excel = pd.ExcelFile(source, engine='openpyxl')
    sheet = '2019-2025' if '2019-2025' in excel.sheet_names else excel.sheet_names[0]
    d = pd.read_excel(excel, sheet_name=sheet)
    d.columns = d.columns.str.strip()
    required=['FECHA','HORA','COLONIA','CALLE1','CALLE2','TIPO DE ACCIDENTE','CAUSA','VEHÍCULOS PARTICIPANTES','LATITUD','LONGITUD']
    missing_cols=[c for c in required if c not in d.columns]
    if missing_cols:raise ValueError('Columnas faltantes: '+', '.join(missing_cols)+'. Descarga la plantilla municipal.')
    d['fila_excel'] = d.index + 2
    d['FECHA'] = pd.to_datetime(d['FECHA'], errors='coerce')
    d = d[d['FECHA'].notna()].copy()
    d['Año'] = d['FECHA'].dt.year.astype(int)
    d['Mes'] = d['FECHA'].dt.month.astype(int)
    d['Día'] = d['FECHA'].dt.dayofweek.astype(int)
    def parse_hour(v):
        if pd.isna(v):return np.nan
        if isinstance(v,(pd.Timestamp,datetime.datetime,datetime.time)):return v.hour
        if isinstance(v,datetime.timedelta):return int(v.total_seconds()//3600)%24
        if isinstance(v,(int,float,np.integer,np.floating)):
            f=float(v)
            if 0<=f<1:return int(f*24+1e-8)
            if 0<=f<=23 and f.is_integer():return int(f)
            return np.nan
        txt=str(v).strip()
        if txt.upper() in ('N/E','N/D','S/D','SIN DATO',''):return np.nan
        if re.fullmatch(r'\d{1,2}',txt):
            h=int(txt);return h if h<=23 else np.nan
        try:
            parsed=pd.to_datetime(txt,format='%H:%M:%S',errors='coerce')
            if pd.isna(parsed):parsed=pd.to_datetime(txt,format='%H:%M',errors='coerce')
            return parsed.hour if pd.notna(parsed) else np.nan
        except (ValueError,TypeError):return np.nan
    d['Hora'] = d['HORA'].map(parse_hour)
    d['Franja horaria']=pd.Series(np.select([d['Hora'].between(0,5),d['Hora'].between(6,11),d['Hora'].between(12,17),d['Hora'].between(18,23)],['Madrugada','Mañana','Tarde','Noche'],default='Sin hora'),index=d.index)
    for c in ['COLONIA','CALLE1','CALLE2','TIPO DE ACCIDENTE','CAUSA','VEHÍCULOS PARTICIPANTES']:
        d[c+' limpio'] = d[c].map(clean_text)
    d['lat'] = pd.to_numeric(d['LATITUD'],errors='coerce')
    d['lon'] = pd.to_numeric(d['LONGITUD'],errors='coerce')
    d['Día semana'] = d['Día'].map(dict(enumerate(DAYS)))
    d['Mes nombre'] = d['Mes'].map(dict(enumerate(MONTHS,1)))
    return d

try:
    df=load_data(source)
except (ValueError,KeyError,FileNotFoundError) as exc:
    st.error(f'No se pudo leer la base municipal: {exc}');st.stop()
if df.empty:st.warning('No hay registros con fecha válida.');st.stop()
classified=classify_coordinates(df,municipal_geometry)
excluded=classified[~classified['geo_ok']].copy()
df=classified[classified['geo_ok']].copy()

st.markdown('### Auditoría de georreferenciación')
counts=classified['coord_estado'].value_counts()
missing_n=int(counts.get('Sin coordenadas / no numéricas',0))
invalid_n=int(counts.get('Coordenadas inválidas',0))
outside_n=int(counts.get('Fuera del municipio (revisar)',0))
k1,k2,k3,k4,k5=st.columns(5)
k1.metric('Registros con fecha',f'{len(classified):,}')
k2.metric('Dentro del municipio',f'{len(df):,}')
k3.metric('Fuera (posible error)',f'{outside_n:,}')
k4.metric('Sin coordenadas',f'{missing_n:,}')
k5.metric('Coordenadas inválidas',f'{invalid_n:,}')
st.caption('Los puntos fuera del polígono son posibles errores de georreferenciación. Los registros sin coordenadas o con coordenadas inválidas se contabilizan por separado. Solo los puntos dentro del municipio se incluyen en los análisis.')
with st.expander('Ver auditoría y descargar registros excluidos',expanded=False):
    st.dataframe(classified['coord_estado'].value_counts().rename_axis('Clasificación').reset_index(name='Registros'),hide_index=True,use_container_width=True)
    audit_cols=['fila_excel','FECHA','COLONIA','CALLE1','CALLE2','LATITUD','LONGITUD','coord_estado']
    st.dataframe(excluded[audit_cols],hide_index=True,use_container_width=True)
    st.download_button('Descargar auditoría CSV',excluded[audit_cols].to_csv(index=False).encode('utf-8-sig'),file_name=f'auditoria_{municipio}.csv',mime='text/csv')
if df.empty:st.warning('No hay registros verificables dentro del municipio.');st.stop()

st.markdown('### 01 / Explorador espacial')
st.caption('Los filtros están junto al mapa. Abre el panel para seleccionar variables; las capas se activan dentro del propio mapa mediante el control de la esquina superior derecha.')
with st.expander('⚙ Filtros de investigación · abrir / cerrar',expanded=True):
    min_date,max_date=df['FECHA'].min().date(),df['FECHA'].max().date()
    r1,r2,r3=st.columns([1.4,1,1])
    with r1:period=st.date_input('Intervalo de fechas',(min_date,max_date),min_value=min_date,max_value=max_date)
    with r2:years=st.multiselect('Años',sorted(df['Año'].unique()))
    with r3:months=st.multiselect('Meses',list(range(1,13)),format_func=lambda x:MONTHS[x-1])
    r4,r5,r6=st.columns(3)
    with r4:days=st.multiselect('Días de la semana',list(range(7)),format_func=lambda x:DAYS[x])
    with r5:franjas=st.multiselect('Periodo del día',['Madrugada','Mañana','Tarde','Noche'],help='Madrugada 00:00–05:59; Mañana 06:00–11:59; Tarde 12:00–17:59; Noche 18:00–23:59. Sin selección: todos.')
    with r6:include_unknown_hours=st.checkbox('Incluir accidentes sin hora',value=True)
    r7,r8,r9=st.columns(3)
    with r7:colonies=st.multiselect('Colonias',sorted(df['COLONIA limpio'].unique()))
    with r8:types=st.multiselect('Tipo de accidente',sorted(df['TIPO DE ACCIDENTE limpio'].unique()))
    with r9:causes=st.multiselect('Causas',sorted(df['CAUSA limpio'].unique()))
    vehicles=st.multiselect('Vehículos participantes',sorted(df['VEHÍCULOS PARTICIPANTES limpio'].unique()))
if not isinstance(period,(tuple,list)) or len(period)!=2:
    st.info('Selecciona las dos fechas del intervalo.');st.stop()
start,end=period
sub=df.copy()
for col,selection in [('Año',years),('Mes',months),('Día',days),('COLONIA limpio',colonies),('TIPO DE ACCIDENTE limpio',types),('CAUSA limpio',causes),('VEHÍCULOS PARTICIPANTES limpio',vehicles)]:
    if selection:sub=sub[sub[col].isin(selection)]
sub=sub[(sub['Franja horaria'].isin(franjas) if franjas else sub['Hora'].notna()) | (sub['Hora'].isna() if include_unknown_hours else False)]
if sub.empty:st.warning('Sin resultados para estos filtros.');st.stop()
# Conservar la población filtrada SIN recorte temporal para comparaciones coherentes.
filtered_all_dates = sub.copy()
sub=sub[sub['FECHA'].dt.date.between(start,end)].copy()

st.markdown('#### Cartografía · capas y selección espacial')
st.caption('Activa/desactiva capas con el icono de capas del mapa (arriba a la derecha). Dibuja un polígono o rectángulo y pulsa Aplicar zona.')
base_geo=sub[sub['geo_ok']].copy()
if st.session_state.get('municipio_activo') != municipio:
    st.session_state.municipio_activo=municipio
    st.session_state.active_geometry=None
    st.session_state.spatial_drawing=None
if 'active_geometry' not in st.session_state:st.session_state.active_geometry=None
if 'spatial_drawing' not in st.session_state:st.session_state.spatial_drawing=None
if not base_geo.empty:
    center=[float(base_geo['lat'].median()),float(base_geo['lon'].median())]
    m=folium.Map(location=center,zoom_start=11,tiles='OpenStreetMap',control_scale=True,prefer_canvas=True)
    boundary_layer=folium.FeatureGroup(name='INEGI · Límite municipal',show=True)
    folium.GeoJson(municipal_geometry,style_function=lambda _: {'color':'#164e63','weight':3,'fillColor':'#38bdf8','fillOpacity':0.035},tooltip=f'Límite municipal INEGI · {MUNICIPIOS_POR_CLAVE[municipio]}').add_to(boundary_layer)
    boundary_layer.add_to(m)
    # Capas con control Leaflet; limitamos puntos para proteger la interfaz en Cloud.
    heat=folium.FeatureGroup(name='Densidad · mapa de calor',show=True)
    HeatMap(base_geo[['lat','lon']].dropna().values.tolist(),radius=17,blur=14,min_opacity=.25).add_to(heat)
    heat.add_to(m)
    pts=folium.FeatureGroup(name='Eventos · puntos individuales',show=False)
    max_points=3000
    shown=base_geo if len(base_geo)<=max_points else base_geo.sample(max_points,random_state=42)
    for row in shown.itertuples(index=False):
        # Popups deliberadamente simples, sin información personal.
        folium.CircleMarker(location=[row.lat,row.lon],radius=3,color='#be3344',fill=True,fill_opacity=.6,weight=1).add_to(pts)
    pts.add_to(m)
    clusters=folium.FeatureGroup(name='Agrupaciones · marcadores',show=False)
    cluster=MarkerCluster(disableClusteringAtZoom=16).add_to(clusters)
    for row in shown.itertuples(index=False):
        folium.CircleMarker([row.lat,row.lon],radius=3,color='#286fa8',fill=True).add_to(cluster)
    clusters.add_to(m)
    Draw(export=False,draw_options={'polyline':False,'circle':False,'circlemarker':False,'marker':False},edit_options={'edit':True}).add_to(m)
    folium.LayerControl(collapsed=False,position='topright').add_to(m)
    result=st_folium(m,height=590,key=f'mapa_laboratorio_{municipio}',returned_objects=['all_drawings','last_active_drawing'],use_container_width=True)
    drawings=result.get('all_drawings') or []
    if drawings:st.session_state.spatial_drawing=drawings[-1].get('geometry')
    ca,cb=st.columns(2)
    if ca.button('Aplicar zona dibujada',type='primary',use_container_width=True):
        geom=st.session_state.spatial_drawing
        if geom and geom.get('type') in ('Polygon','MultiPolygon'):
            try:
                polygon=shape(geom)
                if polygon.is_valid and not polygon.is_empty:
                    st.session_state.active_geometry=geom;st.rerun()
                else:st.error('La geometría no es válida.')
            except (ValueError,TypeError) as e:st.error(f'Geometría no válida: {e}')
        else:st.warning('Primero dibuja un rectángulo o polígono.')
    if cb.button('Quitar selección geográfica',use_container_width=True):
        st.session_state.active_geometry=None;st.session_state.spatial_drawing=None;st.rerun()
    if len(base_geo)>max_points:st.caption(f'Por rendimiento, las capas de puntos y agrupaciones muestran una muestra reproducible de {max_points:,} eventos; el mapa de calor y los indicadores usan todos los registros georreferenciados del filtro.')
else:st.warning('No hay accidentes georreferenciados dentro del municipio seleccionado para los filtros actuales.')
if st.session_state.active_geometry:
    try:
        polygon=prep(shape(st.session_state.active_geometry))
        mask=sub['geo_ok'] & pd.Series([polygon.covers(Point(lon,lat)) if ok else False for lat,lon,ok in zip(sub['lat'],sub['lon'],sub['geo_ok'])],index=sub.index)
        sub=sub[mask].copy()
        mask_all=filtered_all_dates['geo_ok'] & pd.Series([polygon.covers(Point(lon,lat)) if ok else False for lat,lon,ok in zip(filtered_all_dates['lat'],filtered_all_dates['lon'],filtered_all_dates['geo_ok'])],index=filtered_all_dates.index)
        filtered_all_dates=filtered_all_dates[mask_all].copy()
        st.info(f'Zona activa: {len(sub):,} accidentes con coordenadas dentro del polígono. Los registros sin coordenadas quedan excluidos de esta selección.')
    except (ValueError,TypeError) as e:
        st.error(f'Error en selección espacial: {e}')
if sub.empty:
    st.warning('No hay accidentes para esta selección. Cambia los filtros o elimina la zona dibujada.')
    st.stop()
geo=sub[sub['geo_ok']].copy()
st.subheader(f'Indicadores · {MUNICIPIOS_POR_CLAVE[municipio]}')
a,b,c,d=st.columns(4)
a.metric('Accidentes',f'{len(sub):,}')
b.metric('Georreferenciados',f'{len(geo):,}')
c.metric('Municipio seleccionado',MUNICIPIOS_POR_CLAVE[municipio])
d.metric('Sin tipo especificado',f'{sub["TIPO DE ACCIDENTE limpio"].eq("Sin dato").sum():,}')
st.caption(f'Cartografía: OpenStreetMap · Límite geoestadístico INEGI {municipio}. Todos los análisis usan exclusivamente eventos con coordenadas dentro del municipio.')
st.subheader('Análisis estadístico')
left,right=st.columns(2)
with left:
    byyear=sub.groupby('Año').size().reset_index(name='Accidentes')
    st.plotly_chart(px.bar(byyear,x='Año',y='Accidentes',text_auto=True,title='Accidentes por año'),use_container_width=True)
    month=sub.groupby('Mes').size().reindex(range(1,13),fill_value=0).reset_index(name='Accidentes')
    month['Mes']=month['Mes'].map(dict(enumerate(MONTHS,1)))
    st.plotly_chart(px.bar(month,x='Mes',y='Accidentes',category_orders={'Mes':MONTHS},title='Por mes'),use_container_width=True)
    franjas_df=sub['Franja horaria'].value_counts().reindex(['Madrugada','Mañana','Tarde','Noche','Sin hora'],fill_value=0).rename_axis('Periodo').reset_index(name='Accidentes')
    st.plotly_chart(px.bar(franjas_df,x='Periodo',y='Accidentes',title='Por periodo del día'),use_container_width=True)
with right:
    trend=sub.groupby(sub.FECHA.dt.to_period('M')).size().reset_index(name='Accidentes');trend['FECHA']=trend['FECHA'].dt.to_timestamp()
    st.plotly_chart(px.line(trend,x='FECHA',y='Accidentes',markers=True,title='Evolución mensual'),use_container_width=True)
    dow=sub.groupby('Día').size().reindex(range(7),fill_value=0).reset_index(name='Accidentes');dow['Día']=dow['Día'].map(dict(enumerate(DAYS)))
    st.plotly_chart(px.bar(dow,x='Día',y='Accidentes',category_orders={'Día':DAYS},title='Por día de semana'),use_container_width=True)
    typ=sub['TIPO DE ACCIDENTE limpio'].value_counts().head(12).sort_values().reset_index();typ.columns=['Tipo','Accidentes']
    st.plotly_chart(px.bar(typ,x='Accidentes',y='Tipo',orientation='h',title='Tipos (incluye Sin dato)'),use_container_width=True)
for col,title in [('COLONIA limpio','Colonias'),('CAUSA limpio','Causas'),('VEHÍCULOS PARTICIPANTES limpio','Participantes'),('CALLE1 limpio','Calles principales')]:
    values=sub.loc[sub[col]!='Sin dato',col].value_counts().head(15).sort_values().reset_index();values.columns=['Categoría','Accidentes']
    st.plotly_chart(px.bar(values,x='Accidentes',y='Categoría',orientation='h',title=title+' (con información)'),use_container_width=True)
st.subheader('Intersecciones con más accidentes registrados')
st.caption('Ranking basado en los nombres de CALLE1 y CALLE2, sin importar el orden. Una intersección se cuenta por registro, no por vehículos. Los nombres de calles pueden tener variantes ortográficas; el ranking es exploratorio y no sustituye una geocodificación de cruces.')
inter=sub[(sub['CALLE1 limpio']!='Sin dato') & (sub['CALLE2 limpio']!='Sin dato')].copy()
inter=inter[inter['CALLE1 limpio']!=inter['CALLE2 limpio']].copy()
if not inter.empty:
    inter['Cruce']=inter.apply(lambda r:' / '.join(sorted([r['CALLE1 limpio'],r['CALLE2 limpio']])),axis=1)
    ranking=inter.groupby('Cruce',as_index=False).size().rename(columns={'size':'Accidentes'}).sort_values(['Accidentes','Cruce'],ascending=[False,True])
    top_n=st.slider('Número de intersecciones a mostrar',5,30,15,5)
    top=ranking.head(top_n)
    st.plotly_chart(px.bar(top.sort_values('Accidentes'),x='Accidentes',y='Cruce',orientation='h',title='Intersecciones con más registros'),use_container_width=True)
    st.dataframe(ranking,hide_index=True,use_container_width=True)
    st.download_button('Descargar ranking de intersecciones',ranking.to_csv(index=False).encode('utf-8-sig'),file_name='intersecciones_v3.csv',mime='text/csv')
    st.caption(f'Cruces analizables: {len(inter):,} de {len(sub):,} registros filtrados. El resto tiene calles no especificadas o iguales.')
else:st.info('No hay intersecciones con ambas calles identificadas en esta selección.')

st.subheader('Puntos críticos · evolución anual de intersecciones')
st.caption('Las intersecciones se agrupan por pares de nombres de calles normalizados. No se infiere una localización exacta del cruce ni una tasa de riesgo. El análisis respeta los filtros de investigación y la zona geográfica activa, pero no el rango principal de fechas.')

def build_intersections(data):
    valid=data[(data['CALLE1 limpio']!='Sin dato') & (data['CALLE2 limpio']!='Sin dato') & (data['CALLE1 limpio']!=data['CALLE2 limpio'])].copy()
    if not valid.empty:
        valid['Cruce']=[' / '.join(sorted((a,b))) for a,b in zip(valid['CALLE1 limpio'],valid['CALLE2 limpio'])]
    return valid

all_inter=build_intersections(filtered_all_dates)
year_list=sorted(filtered_all_dates['Año'].unique().tolist())
if len(year_list)>=2 and not all_inter.empty:
    y1,y2=st.columns(2)
    base_year=y1.selectbox('Año base',year_list,index=max(0,len(year_list)-2),key='v4_base')
    target_year=y2.selectbox('Año de comparación',year_list,index=len(year_list)-1,key='v4_target')
    min_events=st.slider('Mínimo de accidentes en alguno de los dos años',1,20,3,key='v4_min_events')
    if base_year==target_year:
        st.info('Selecciona dos años diferentes para calcular variaciones.')
    else:
        year_counts=all_inter[all_inter['Año'].isin([base_year,target_year])].groupby(['Cruce','Año']).size().unstack(fill_value=0)
        for yr in (base_year,target_year):
            if yr not in year_counts:year_counts[yr]=0
        summary=year_counts[[base_year,target_year]].rename(columns={base_year:'Base',target_year:'Comparado'}).reset_index()
        summary=summary[summary[['Base','Comparado']].max(axis=1)>=min_events].copy()
        summary['Cambio absoluto']=summary['Comparado']-summary['Base']
        summary['Cambio %']=np.where(summary['Base']>0,100*summary['Cambio absoluto']/summary['Base'],np.nan)
        summary['Tendencia']=np.select([summary['Cambio absoluto']>0,summary['Cambio absoluto']<0],['Aumentó','Disminuyó'],default='Sin cambio')
        summary['Cambio %']=summary['Cambio %'].round(1)
        st.caption('Un cambio de 0 a un valor positivo se muestra como porcentaje no calculable, no como crecimiento infinito. El umbral se aplica al mayor conteo entre los dos años.')
        k1,k2,k3=st.columns(3)
        k1.metric('Cruces analizados',f'{len(summary):,}')
        k2.metric('Con aumento',f'{(summary["Tendencia"]=="Aumentó").sum():,}')
        k3.metric('Con disminución',f'{(summary["Tendencia"]=="Disminuyó").sum():,}')
        if not summary.empty:
            sort_mode=st.selectbox('Ordenar ranking',['Mayor aumento','Mayor disminución','Mayor número en año comparado'],key='v4_sort')
            if sort_mode=='Mayor aumento':ordered=summary.sort_values(['Cambio absoluto','Comparado'],ascending=[False,False])
            elif sort_mode=='Mayor disminución':ordered=summary.sort_values(['Cambio absoluto','Base'],ascending=[True,False])
            else:ordered=summary.sort_values(['Comparado','Cambio absoluto'],ascending=[False,False])
            top=ordered.head(15).copy()
            fig=px.bar(top.sort_values('Cambio absoluto'),x='Cambio absoluto',y='Cruce',orientation='h',color='Tendencia',color_discrete_map={'Aumentó':'#c0392b','Disminuyó':'#16806b','Sin cambio':'#7f8c8d'},title=f'Cambio de accidentes: {base_year} → {target_year}')
            st.plotly_chart(fig,use_container_width=True)
            st.dataframe(ordered.rename(columns={'Base':str(base_year),'Comparado':str(target_year)}),hide_index=True,use_container_width=True)
            st.download_button('Descargar comparativo de intersecciones',ordered.to_csv(index=False).encode('utf-8-sig'),file_name=f'cruces_{base_year}_{target_year}.csv',mime='text/csv')
            selected=st.selectbox('Explorar evolución de una intersección',ordered['Cruce'].tolist(),key='v4_cross')
            evolution=all_inter[all_inter['Cruce']==selected].groupby('Año').size().reindex(year_list,fill_value=0).rename_axis('Año').reset_index(name='Accidentes')
            st.plotly_chart(px.line(evolution,x='Año',y='Accidentes',markers=True,title=f'Evolución anual · {selected}'),use_container_width=True)
            # Sostenida = al menos 3 años consecutivos con incrementos estrictos; solo describe conteos.
            if len(evolution)>=3:
                vals=evolution['Accidentes'].tolist()
                rising=any(vals[i]<vals[i+1]<vals[i+2] for i in range(len(vals)-2))
                falling=any(vals[i]>vals[i+1]>vals[i+2] for i in range(len(vals)-2))
                st.caption(('Hay al menos tres años consecutivos con aumentos de registros. ' if rising else '')+('Hay al menos tres años consecutivos con disminuciones de registros. ' if falling else '')+('Estas tendencias descriptivas no implican causalidad ni riesgo ajustado por tránsito.'))
        else:st.info('No hay intersecciones que alcancen el umbral seleccionado.')
else:st.info('Se requieren al menos dos años y cruces con ambas calles identificadas para el análisis.')

