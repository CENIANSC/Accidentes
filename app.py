from pathlib import Path
import unicodedata
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import pydeck as pdk
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, Point
from shapely.prepared import prep

st.set_page_config(page_title='Observatorio de Accidentes V4 | 2019–2025', page_icon='🚦', layout='wide')
st.title('🚦 Observatorio de Accidentes de Tránsito')
st.caption('Exploración geográfica y estadística de los registros 2019–2025 · Los puntos representan eventos reportados, no tasas de riesgo.')

DATA = Path(__file__).parent / 'data' / 'accidentes.xlsx'
DAYS = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
MONTHS = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']

def clean_text(x):
    if pd.isna(x): return 'Sin dato'
    s = str(x).strip().upper()
    if not s or s in ('N/E','N. E.','N.E.','N/D','N/A','NAN','NONE','-','S/D','SIN DATO'): return 'Sin dato'
    s = ' '.join(s.split())
    return unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode('ascii')

@st.cache_data(show_spinner='Leyendo base de accidentes…')
def load_data():
    d = pd.read_excel(DATA, sheet_name='2019-2025', engine='openpyxl')
    d.columns = d.columns.str.strip()
    d['FECHA'] = pd.to_datetime(d['FECHA'], errors='coerce')
    d = d[d['FECHA'].notna()].copy()
    d['Año'] = d['FECHA'].dt.year.astype(int)
    d['Mes'] = d['FECHA'].dt.month.astype(int)
    d['Día'] = d['FECHA'].dt.dayofweek.astype(int)
    d['Hora'] = pd.to_numeric(d['HORA 2'],errors='coerce')
    d.loc[~d['Hora'].between(0,23),'Hora']=np.nan
    for c in ['COLONIA','CALLE1','CALLE2','TIPO DE ACCIDENTE','CAUSA','VEHÍCULOS PARTICIPANTES','ESPECÍFICA']:
        d[c+' limpio'] = d[c].map(clean_text)
    d['lat'] = pd.to_numeric(d['LATITUD'],errors='coerce')
    d['lon'] = pd.to_numeric(d['LONGITUD'],errors='coerce')
    # Extensión amplia de Guanajuato; coordenadas fuera se señalan como no utilizables en el mapa.
    d['geo_ok'] = d['lat'].between(19.5,22.0) & d['lon'].between(-102.7,-99.5)
    d['Día semana'] = d['Día'].map(dict(enumerate(DAYS)))
    d['Mes nombre'] = d['Mes'].map(dict(enumerate(MONTHS,1)))
    return d

if not DATA.exists():
    st.error('No se encontró data/accidentes.xlsx. Añade el archivo a esa ruta en GitHub.'); st.stop()
df = load_data()
if df.empty:
    st.warning('No hay registros con fecha válida.'); st.stop()


st.sidebar.header('Filtros vinculados')
min_date,max_date=df['FECHA'].min().date(),df['FECHA'].max().date()
period=st.sidebar.date_input('Rango de fechas',(min_date,max_date),min_value=min_date,max_value=max_date)
if not isinstance(period,(tuple,list)) or len(period)!=2:
    st.info('Selecciona fecha inicial y final.');st.stop()
start,end=period
sub=df.copy()
years=st.sidebar.multiselect('Años',sorted(df['Año'].unique()),default=[])
if years:sub=sub[sub['Año'].isin(years)]
months=st.sidebar.multiselect('Meses',list(range(1,13)),format_func=lambda x:MONTHS[x-1])
if months:sub=sub[sub['Mes'].isin(months)]
days=st.sidebar.multiselect('Días',list(range(7)),format_func=lambda x:DAYS[x])
if days:sub=sub[sub['Día'].isin(days)]
hours=st.sidebar.slider('Rango horario',0,23,(0,23))
include_unknown_hours=st.sidebar.checkbox('Incluir registros sin hora',value=True)
sub=sub[sub['Hora'].between(*hours)|(sub['Hora'].isna() if include_unknown_hours else False)]
for col,label in [('COLONIA limpio','Colonias'),('CALLE1 limpio','Calle principal'),('CALLE2 limpio','Calle secundaria / cruce'),('TIPO DE ACCIDENTE limpio','Tipo de accidente'),('CAUSA limpio','Causa'),('ESPECÍFICA limpio','Horario específico'),('VEHÍCULOS PARTICIPANTES limpio','Vehículos participantes')]:
    options=sorted(sub[col].unique().tolist())
    selection=st.sidebar.multiselect(label,options,placeholder='Todas (incluye Sin dato)')
    if selection:sub=sub[sub[col].isin(selection)]
missing=st.sidebar.selectbox('Calidad de información',['Todos','Solo registros con N/E o sin dato','Solo registros completos en campos clave'])
keycols=['COLONIA limpio','TIPO DE ACCIDENTE limpio','CAUSA limpio','VEHÍCULOS PARTICIPANTES limpio']
unknown=sub[keycols].eq('Sin dato').any(axis=1)
if missing.startswith('Solo registros con'):sub=sub[unknown]
elif missing.startswith('Solo registros completos'):sub=sub[~unknown]
if sub.empty:st.warning('Sin resultados para estos filtros.');st.stop()
# Conservar la población filtrada SIN recorte temporal para comparaciones coherentes.
filtered_all_dates = sub.copy()
sub=sub[sub['FECHA'].dt.date.between(start,end)].copy()

st.subheader('Selección geográfica sobre el mapa')
st.caption('Dibuja un rectángulo o polígono y pulsa «Aplicar zona dibujada». El recorte afecta al mapa, las gráficas, los indicadores y la tabla. Los registros sin coordenadas no pueden pertenecer a una zona dibujada.')
base_geo = sub[sub['geo_ok']].copy()
if 'active_geometry' not in st.session_state:
    st.session_state.active_geometry = None
if 'spatial_drawing' not in st.session_state:
    st.session_state.spatial_drawing = None
if not base_geo.empty:
    center = [float(base_geo['lat'].median()),float(base_geo['lon'].median())]
    draw_map = folium.Map(location=center,zoom_start=12,tiles='CartoDB positron',control_scale=True)
    Draw(export=False,draw_options={'polyline':False,'circle':False,'circlemarker':False,'marker':False},edit_options={'edit':True}).add_to(draw_map)
    result = st_folium(draw_map,height=360,key='selector_espacial',returned_objects=['all_drawings','last_active_drawing'])
    drawings = result.get('all_drawings') or []
    if drawings:
        st.session_state.spatial_drawing = drawings[-1].get('geometry')
    ca,cb=st.columns(2)
    if ca.button('Aplicar zona dibujada',type='primary',use_container_width=True):
        geom=st.session_state.spatial_drawing
        if geom and geom.get('type') in ('Polygon','MultiPolygon'):
            try:
                polygon=shape(geom)
                if polygon.is_valid and not polygon.is_empty:
                    st.session_state.active_geometry=geom
                    st.rerun()
                else: st.error('La geometría dibujada no es válida.')
            except (ValueError,TypeError) as e: st.error(f'No se pudo interpretar la zona: {e}')
        else: st.warning('Dibuja primero un rectángulo o polígono.')
    if cb.button('Quitar selección geográfica',use_container_width=True):
        st.session_state.active_geometry=None
        st.session_state.spatial_drawing=None
        st.rerun()
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
st.subheader('Indicadores')
a,b,c,d=st.columns(4)
a.metric('Accidentes',f'{len(sub):,}')
b.metric('Georreferenciados',f'{len(geo):,}')
c.metric('Sin coordenadas válidas',f'{len(sub)-len(geo):,}')
d.metric('Sin tipo especificado',f'{sub["TIPO DE ACCIDENTE limpio"].eq("Sin dato").sum():,}')
with st.expander('Criterios y calidad de datos',expanded=False):
    st.write('N/E, N/D, N/A, guiones y celdas vacías se clasifican como **Sin dato** para el análisis, sin eliminar el accidente. El CSV conserva los valores originales.')
    summary=[]
    for col in ['HORA','HORA 2','COLONIA','CALLE1','CALLE2','VEHÍCULOS PARTICIPANTES','TIPO DE ACCIDENTE','CAUSA']:
        vals=sub[col].astype('string').str.strip().str.upper()
        n=vals.isin(['N/E','N/D','N/A','-','S/D','SIN DATO']).sum()
        blank=sub[col].isna().sum()+(vals=='').sum()
        summary.append({'Campo':col,'N/E u otro marcador':int(n),'Vacíos':int(blank),'% sin especificar':round(100*(n+blank)/len(sub),1)})
    st.dataframe(pd.DataFrame(summary),hide_index=True,use_container_width=True)
    st.caption('La validación geográfica usa un rectángulo amplio de Guanajuato, no límites municipales. No se infieren causas ni gravedad.')
st.subheader('Mapa interactivo · capas combinables')
opts=st.multiselect('Capas',['Puntos individuales','Mapa de calor','Cuadrícula 350 m'],default=['Mapa de calor'])
if geo.empty:st.warning('Los registros filtrados no tienen coordenadas utilizables.')
else:
    layers=[]
    if 'Mapa de calor' in opts:
        layers.append(pdk.Layer('HeatmapLayer',data=geo[['lat','lon']],get_position='[lon,lat]',get_weight=1,radius_pixels=48))
    if 'Cuadrícula 350 m' in opts:
        layers.append(pdk.Layer('GridLayer',data=geo[['lat','lon']],get_position='[lon,lat]',cell_size=350,extruded=False,pickable=True,opacity=0.25,color_range=[[255,245,235],[254,230,206],[253,174,107],[253,141,60],[230,85,13],[166,54,3]]))
    if 'Puntos individuales' in opts:
        pts=geo[['lat','lon','FECHA','COLONIA limpio','CALLE1 limpio','CALLE2 limpio','TIPO DE ACCIDENTE limpio']].copy()
        pts['FECHA']=pts['FECHA'].dt.strftime('%Y-%m-%d')
        layers.append(pdk.Layer('ScatterplotLayer',data=pts,get_position='[lon,lat]',get_radius=30,get_fill_color=[210,55,50,145],radius_min_pixels=2,pickable=True))
    if layers:
        tooltip={'html':'<b>{COLONIA limpio}</b><br/>{CALLE1 limpio} / {CALLE2 limpio}<br/>{FECHA}<br/>{TIPO DE ACCIDENTE limpio}<br/>Eventos en celda: {count}'}
        st.pydeck_chart(pdk.Deck(layers=layers,initial_view_state=pdk.ViewState(latitude=float(geo.lat.median()),longitude=float(geo.lon.median()),zoom=11),map_style='https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',tooltip=tooltip),use_container_width=True)
    else:st.info('Activa al menos una capa.')
st.caption('Los puntos y las celdas representan eventos registrados, no riesgo ajustado por volumen vehicular.')
st.subheader('Análisis estadístico')
left,right=st.columns(2)
with left:
    byyear=sub.groupby('Año').size().reset_index(name='Accidentes')
    st.plotly_chart(px.bar(byyear,x='Año',y='Accidentes',text_auto=True,title='Accidentes por año'),use_container_width=True)
    month=sub.groupby('Mes').size().reindex(range(1,13),fill_value=0).reset_index(name='Accidentes')
    month['Mes']=month['Mes'].map(dict(enumerate(MONTHS,1)))
    st.plotly_chart(px.bar(month,x='Mes',y='Accidentes',category_orders={'Mes':MONTHS},title='Por mes'),use_container_width=True)
    hours_df=sub.dropna(subset=['Hora']).groupby('Hora').size().reindex(range(24),fill_value=0).reset_index(name='Accidentes')
    st.plotly_chart(px.line(hours_df,x='Hora',y='Accidentes',markers=True,title='Por hora (solo hora conocida)'),use_container_width=True)
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
st.caption('Las intersecciones se agrupan por pares de nombres de calles normalizados. No se infiere una localización exacta del cruce ni una tasa de riesgo. El análisis respeta los filtros laterales y la zona geográfica activa, pero no el rango principal de fechas.')

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

st.subheader('Comparación de dos periodos con filtros vinculados')
ca,cb=st.columns(2)
with ca:period_a=st.date_input('Periodo A',(min_date,min(max_date,min_date+pd.Timedelta(days=364))),key='period_a',min_value=min_date,max_value=max_date)
with cb:period_b=st.date_input('Periodo B',(max(min_date,max_date-pd.Timedelta(days=364)),max_date),key='period_b',min_value=min_date,max_value=max_date)
if len(period_a)==2 and len(period_b)==2:
    def period_count(pair):
        return int(filtered_all_dates['FECHA'].dt.date.between(pair[0],pair[1]).sum())
    na,nb=period_count(period_a),period_count(period_b)
    st.metric('Cambio de eventos registrados (B vs A)',f'{nb-na:+,}',delta=f'{(nb-na)/na*100:+.1f}%' if na else None)
    st.caption(f'Periodo A: {na:,} eventos · Periodo B: {nb:,} eventos. Se aplican los filtros laterales y la selección geográfica, excepto el rango principal de fechas. Para comparar tendencias verifica cobertura y duración equivalentes.')
st.subheader('Registros filtrados y descarga')
cols=['FECHA','Año','Mes','Día semana','Hora','COLONIA','CALLE1','CALLE2','LATITUD','LONGITUD','VEHÍCULOS PARTICIPANTES','TIPO DE ACCIDENTE','CAUSA']
st.download_button('Descargar CSV (valores originales)',sub[cols].to_csv(index=False).encode('utf-8-sig'),file_name='accidentes_v4_filtrados.csv',mime='text/csv')
st.dataframe(sub[cols].sort_values('FECHA',ascending=False),hide_index=True,use_container_width=True)
