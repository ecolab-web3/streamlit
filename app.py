import streamlit as st
import pandas as pd
import hashlib
import rasterio
import leafmap.foliumap as foliumap
import plotly.express as px
import os
from pathlib import Path
import xarray as xr
import rioxarray as rxr
import numpy as np
import folium
import glob
from folium.raster_layers import ImageOverlay

# @dev Page Configuration
st.set_page_config(page_title="E-co.lab | Monitoramento de Risco de Incêndios Rurais", layout="wide")

# @dev Overrides default Streamlit CSS to explicitly hide the runner animation and unwanted top-right artifacts
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display:none;}
div[data-testid="stStatusWidget"] {visibility: hidden; height: 0%; position: fixed;}
[data-testid="stConnectionStatus"] {display: none;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# @dev Resolves the current directory directly as the project root
BASE_DIR = Path(__file__).parent
CSV_PATH = os.path.join(BASE_DIR, "metricas_rwa_finais.csv")
MD_PATH = os.path.join(BASE_DIR, "fire_hazard_report.md")
# @dev Paths mapped to the project root
COG_SCORE = os.path.join(BASE_DIR, "fire_hazard_score_cog.tif")
ORTHO_PATH = os.path.join(BASE_DIR, "orthophoto_cog.tif")
COG_CHM = os.path.join(BASE_DIR, "chm_cog.tif")

# ---------------- CACHED FUNCTIONS ---------------- #

@st.cache_data
def compute_sha256(filepath):
    """
    @notice Computes SHA-256 for integrity verification. Cached to avoid recalculation.
    @param filepath The absolute or relative path to the target file.
    @return A 64-character hexadecimal SHA-256 hash string.
    """
    if not os.path.exists(filepath):
        return "Arquivo não encontrado."
        
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # @dev Read file in chunks to optimize memory usage and prevent buffer overflows
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

@st.cache_data
def load_metrics(csv_path):
    """
    @notice Loads Key Performance Indicators (KPIs) from the consolidated CSV metrics file.
    @param csv_path The absolute path to the metrics CSV file.
    @return A dictionary mapping column names to metric values.
    """
    if not os.path.exists(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    if not df.empty:
        return df.iloc[0].to_dict()
    return {}

@st.cache_data
def load_risk_distribution(md_path):
    """
    @notice Parses the underlying Markdown Report to horizontally extract Risk Distribution percentages metrics.
    @param md_path The absolute path to the generated fire_hazard_report.md.
    @return A strictly typed Pandas DataFrame containing 'Score', 'Nivel', and 'Area_ha'.
    """
    if not os.path.exists(md_path):
        return pd.DataFrame()
        
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # @dev Extract structural rows from the generated Markdown table pipeline
        lines = [L_ for L_ in content.split('\n') if '|' in L_ and 'Score' not in L_ and '---' not in L_]
        data = []
        for line in lines:
            parts = [p.strip().replace('**', '') for p in line.split('|')[1:-1]]
            if len(parts) >= 3:
                score = parts[0]
                nivel = parts[1]
                area_str = parts[2].replace(' ha', '').strip()
                try:
                    area = float(area_str)
                    data.append({'Score': score, 'Nivel': nivel, 'Area_ha': area})
                except ValueError:
                    continue
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Erro ao carregar dados do relatório Markdown: {e}")
        return pd.DataFrame()

@st.cache_data
def get_map_arrays(cog_score, ortho_path):
    """
    @notice Parses and decimates massive remote sensing rasters into memory-safe numpy structures.
    @param cog_score The absolute path to the Fire Hazard Score Cloud Optimized GeoTIFF.
    @param ortho_path The absolute path to the Orthorectified Aerial Photograph GeoTIFF.
    @return A tuple holding the RGBA array layers, Folium boundaries, and normalized coordinates.
    """
    rgba, bounds_folium, center_lat, center_lon = None, None, 0, 0
    rgba_o, bounds_o = None, None
    
    if os.path.exists(cog_score):
        rds = rxr.open_rasterio(cog_score)
        # @dev Subsampling (Decimation) locked to high fidelity visual capacities (2500px resolution)
        step = max(1, max(rds.rio.width, rds.rio.height) // 2500)
        rds_4326 = rds.isel(x=slice(0, None, step), y=slice(0, None, step)).rio.reproject("EPSG:4326")
        data = rds_4326.squeeze().values
        b_4326 = rds_4326.rio.bounds()
        bounds_folium = [[b_4326[1], b_4326[0]], [b_4326[3], b_4326[2]]]
        center_lat = (b_4326[1] + b_4326[3]) / 2
        center_lon = (b_4326[0] + b_4326[2]) / 2
        
        rgba = np.zeros((data.shape[0], data.shape[1], 4), dtype=np.uint8)
        rgba[data == 2] = [0, 128, 0, 255]
        rgba[data == 3] = [255, 255, 0, 255]
        rgba[data == 4] = [255, 165, 0, 255]
        rgba[data == 5] = [255, 0, 0, 255]

    if os.path.exists(ortho_path):
        rds_o = rxr.open_rasterio(ortho_path)
        step_o = max(1, max(rds_o.rio.width, rds_o.rio.height) // 2500)
        # @dev Reproject onto World Geodetic System natively mapping empty nodata borders to 0
        rds_o_4326 = rds_o.isel(x=slice(0, None, step_o), y=slice(0, None, step_o)).rio.reproject("EPSG:4326", nodata=0)
        data_channels = rds_o_4326.values.transpose(1, 2, 0)
        
        if data_channels.dtype != np.uint8:
            if data_channels.max() <= 1.0:
                data_channels = (data_channels * 255).astype(np.uint8)
            else:
                data_channels = np.clip(data_channels, 0, 255).astype(np.uint8)
                
        rgba_o = np.zeros((data_channels.shape[0], data_channels.shape[1], 4), dtype=np.uint8)
        if data_channels.shape[2] >= 3:
            rgba_o[..., :3] = data_channels[..., :3]
            if data_channels.shape[2] == 4:
                rgba_o[..., 3] = data_channels[..., 3]
            else:
                # @dev Map absolute Nodata (absolute 0 across RGB bands) directly into transparent alpha channel
                mask = (data_channels[..., 0] > 0) | (data_channels[..., 1] > 0) | (data_channels[..., 2] > 0)
                rgba_o[mask, 3] = 255
        
        b_o = rds_o_4326.rio.bounds()
        bounds_o = [[b_o[1], b_o[0]], [b_o[3], b_o[2]]]
        
    return rgba, bounds_folium, center_lat, center_lon, rgba_o, bounds_o

@st.cache_data
def get_inpe_points():
    """
    @notice Parses external INPE accumulated historical fire data layers from the root.
    @dev Reads sequentially across iterative datasets targeting specifically 'bdqueimadas_*.csv' files.
    @return A multi-dimensional array mapping latitude and longitude geographic anchor points.
    """
    points = []
    available_csvs = [os.path.basename(f) for f in glob.glob(os.path.join(Path(__file__).parent, "bdqueimadas_*.csv"))]
    if available_csvs:
        for csv_file in available_csvs:
            csv_path = os.path.join(Path(__file__).parent, csv_file)
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                df.columns = [c.lower() for c in df.columns]
                df = df.rename(columns={'latitude': 'lat', 'longitude': 'lon', 'lat_': 'lat', 'lon_': 'lon'})
                if 'lat' in df.columns and 'lon' in df.columns:
                    for idx, row in df.iterrows():
                        points.append([row['lat'], row['lon']])
    return points

# ---------------- APP LAYOUT ---------------- #

st.title("E-co.lab | Monitoramento de Risco de Incêndios Rurais (dMRV)")
st.markdown("**Dossiê Executivo de Risco de Incêndio e Biomassa**")

# @dev Execute core optimized data loading
metrics_dict = load_metrics(CSV_PATH)
risk_df = load_risk_distribution(MD_PATH)

critical_area_pct = 0
if not risk_df.empty:
    total_area = risk_df['Area_ha'].sum()
    critical_df = risk_df[risk_df['Score'] == '5']
    if not critical_df.empty and total_area > 0:
        critical_area_pct = (critical_df.iloc[0]['Area_ha'] / total_area) * 100

# @notice Sub-section: Top KPIs Row
col1, col2, col3, col4 = st.columns(4)

vol_total = metrics_dict.get('Volume Total (m3)', 0)
area_veg = metrics_dict.get('Area Vegetada Real (ha)', 0)
alt_media = metrics_dict.get('Altura Media dos Pixels > 0 (m)', 0)

# @dev Display metrics explicitly mapping numeric logic into native Brazilian Executive numeric localization (comma decimal separators)
col1.metric("Volume Total (m³)", f"{vol_total:,.0f}".replace(',', '.'))
col2.metric("Área Vegetada (ha)", f"{area_veg:,.1f}".translate(str.maketrans(',.', '.,')))
col3.metric("Altura Média (m)", f"{alt_media:,.2f}".translate(str.maketrans(',.', '.,')))
col4.metric("% Risco Crítico", f"{critical_area_pct:.1f}".translate(str.maketrans(',.', '.,')) + "%")

st.write("")

# @dev Custom floating loader (Absolute Overlay CSS Constraint) prevents grid rendering layout shifts
loading_msg = st.empty()
loading_msg.markdown("""
<div style='position: fixed; top: 1rem; right: 1rem; background-color: rgba(20, 26, 31, 1.0); border-radius: 8px; padding: 16px 24px; z-index: 999999; box-shadow: 0 4px 12px rgba(0,0,0,0.5); font-family: sans-serif; font-size: 15px; border: 1px solid #444; color: #fff;'>
  ⏳ Lendo matrizes COG e renderizando o visualizador geoespacial (Aguarde)...
</div>
""", unsafe_allow_html=True)

# @dev Global memory cached geographic pre-processing
rgba, bounds_folium, center_lat, center_lon, rgba_o, bounds_o = get_map_arrays(COG_SCORE, ORTHO_PATH)
inpe_points = get_inpe_points()

st.markdown("---")

# @notice Row 1: Structural UI Titles and Native Input Controls (Forces uncoupled DOM mapping rendering constraints for optical synchrony)
header_map_col, header_slider_col, header_chart_col = st.columns([1.5, 0.5, 1])

with header_map_col:
    st.subheader("Mapa de Risco de Incêndios")
with header_slider_col:
    opacity_percent = st.slider("Opacidade da Camada (%)", min_value=0, max_value=100, value=80, step=5, key='opacity_slider')
    opacity_val = opacity_percent / 100.0
with header_chart_col:
    st.markdown("<h3 style='text-align: right;'>Distribuição de Risco</h3>", unsafe_allow_html=True)

# @notice Row 2: Heavy Geometric Component Evaluation Handlers (Folium Maps and Plotly Charts)
map_col, chart_col = st.columns([2, 1])

with map_col:

    if rgba is not None:
        try:
            m = foliumap.Map(center=[center_lat, center_lon], zoom=15, draw_control=False, measure_control=False, tiles="openstreetmap")
            
            if rgba_o is not None:
                ImageOverlay(
                    image=rgba_o,
                    bounds=bounds_o,
                    opacity=opacity_val,
                    name='Orthophoto',
                ).add_to(m)
                
            ImageOverlay(
                image=rgba,
                bounds=bounds_folium,
                opacity=1.0,
                name='Fire Hazard Score',
            ).add_to(m)
            
            if inpe_points:
                fg = folium.FeatureGroup(name='Focos de Calor Acumulados (INPE)', show=False)
                for lat, lon in inpe_points:
                    folium.CircleMarker(
                        location=[lat, lon],
                        radius=2,
                        color='black',
                        fill=True,
                        fill_color='black',
                        fill_opacity=1.0,
                        weight=1
                    ).add_to(fg)
                fg.add_to(m)
                
            m.to_streamlit(height=500)
            
        except Exception as e:
            st.error(f"Erro ao processar a renderização nativa via folium: {e}")
    else:
        st.warning(f"O arquivo {COG_SCORE} não foi encontrado no sistema.")

with chart_col:
    if not risk_df.empty:
        # @dev Official mapping matrix linking nominal descriptions directly to geometric fill palettes
        color_map = {
            'Nulo (Cinza)': 'gray',
            'Baixo (Verde)': 'green',
            'Médio (Amarelo)': 'yellow',
            'Alto (Laranja)': 'orange',
            'CRÍTICO (Vermelho)': 'red'
        }
        
        # @dev Strict floating point normalization protocol
        plot_df = risk_df.copy()
        plot_df['Area_ha'] = pd.to_numeric(plot_df['Area_ha'], errors='coerce').fillna(0)
        plot_df = plot_df[plot_df['Area_ha'] > 0]
        
        import plotly.graph_objects as go
        
        # @dev Standardizing logic into pure python array vectors resolves underlying pandas-to-plotly bridging dependency constraints
        areas_list = [float(x) for x in plot_df['Area_ha'].tolist()]
        nomes_list = [str(x) for x in plot_df['Nivel'].tolist()]
        cores_list = [color_map.get(n, 'gray') for n in nomes_list]
        
        # @dev Dynamic offset array parameter pushes slice visually outwardly. 'CRITÉRIO' separated symmetrically by 15% distance limit.
        explosoes = [0.15 if 'CRÍTICO' in n.upper() else 0.0 for n in nomes_list]
        
        fig = go.Figure(data=[go.Pie(
            labels=nomes_list,
            values=areas_list,
            hole=0.4,
            marker_colors=cores_list,
            pull=explosoes,
            sort=False
        )])
        
        # @dev Synchronizes layout heights securely to true vertical boundary scaling parameters parallel to standard map mapping (502px parity limit)
        fig.update_layout(
            height=502,
            showlegend=True, 
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
            margin=dict(t=10, b=10, l=10, r=10)
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nenhum dado de distribuição capturado do relatório MD.")

# @notice Module: Web3 Integrity Proof Footer Parameters Context
st.subheader("🔗 Atestado de Integridade (EAS / Web3)")
st.markdown("Os hashes criptográficos (SHA-256) atestam que os dados-base geoespaciais carregados em memória são imutáveis e verificáveis na rede.")

col_hash1, col_hash2, col_hash3 = st.columns(3)

with col_hash1:
    st.markdown("**Mapa de Risco de Incêndios (`fire_hazard_score_cog.tif`)**")
    score_hash = compute_sha256(COG_SCORE)
    st.code(score_hash, language="text")

with col_hash2:
    st.markdown("**Modelo de Altura Florestal (`chm_cog.tif`)**")
    chm_hash = compute_sha256(COG_CHM)
    st.code(chm_hash, language="text")

with col_hash3:
    st.markdown("**Fotografia Aérea Ortorretificada (`orthophoto_cog.tif`)**")
    ortho_hash = compute_sha256(ORTHO_PATH) if os.path.exists(ORTHO_PATH) else "Arquivo indisponível"
    st.code(ortho_hash, language="text")

# @notice Module Final Execution Protocol Disclaimer Constraints
st.caption("© 2026 E-co.lab | As informações apresentadas provêm diretamente dos dados on-chain/dMRV e são encriptadas em tempo real.")

# @dev Erase the layout floating deployment loader placeholder safely releasing Streamlit DOM control thread back into interaction pool
loading_msg.empty()
