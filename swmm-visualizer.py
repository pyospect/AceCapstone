import pandas as pd
import geopandas as gpd
import re
import folium
import math

def read_section(inp_contents, section_name):
    pattern = rf'\[{section_name}\]\n(.*?)(?:\n\n|\Z)'
    section = re.search(pattern, inp_contents, re.DOTALL).group(1).strip()
    return section.split('\n')[2:]

def create_dataframe(lines, columns):
    return pd.DataFrame([line.split() for line in lines], columns = columns)

def extract_coords_and_create_gdf(df):
    df[['X-Coord', 'Y-Coord']] = df[['X-Coord', 'Y-Coord']].apply(pd.to_numeric)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['X-Coord'], df['Y-Coord']), crs='epsg:5174')
    return gdf.to_crs(epsg=4326)

def extract_node_surcharge_summary(contents):
    pattern = r'Node Surcharge Summary.*?-----\n(.*?)\n\n'
    match = re.search(pattern, contents, re.DOTALL)
    if match:
        data = match.group(1).strip().split('\n')[4:]
        processed_data = []
        for line in data:
            if not line.strip():
                break
            parts = re.split(r'\s{2,}', line.strip())
            if len(parts) >= 5:
                node = parts[0]
                max_height = parts[-2]
                min_depth = parts[-1]
                processed_data.append([node, max_height, min_depth])
        return pd.DataFrame(processed_data, columns = ['Node', 'Max Height (Meters)', 'Min Depth (Meters)'])
    else:
        return None

def extract_node_flooding_summary(contents):
    pattern = r'Node Flooding Summary.*?-----\n(.*?)\n\n'
    match = re.search(pattern, contents, re.DOTALL)
    if match:
        data = match.group(1).strip().split('\n')[5:]
        processed_data = []
        for line in data:
            if not line.strip():
                break
            parts = re.split(r'\s{2,}', line.strip())
            if len(parts) >= 7:
                node = parts[0]
                total_flood_volume = parts[-2]
                processed_data.append([node, total_flood_volume])
        return pd.DataFrame(processed_data, columns = ['Node', 'Total Flood Volume (10^6 ltr)'])
    else:
        return None

def calculate_color(overload_rate):
    if overload_rate >= 0.5:
        # Transition from Yellow to Red
        green = 255 * (1 - 2 * (overload_rate - 0.5))
        return f'#{int(255):02x}{int(green):02x}00'
    else:
        # Transition from Green to Yellow
        red = 255 * (2 * overload_rate)
        return f'#{int(red):02x}{int(255):02x}00'

# 파일 읽기
print('\n\nSWMM VISUALIZER\n\n------------------------------\n')
event_name = input('Enter your file name : ')
inp_path = f'{event_name}.inp'
with open(inp_path, 'r', encoding = 'ISO-8859-1') as inp_file:
    inp_contents = inp_file.read()
rpt_path = f'{event_name}.rpt'
with open(rpt_path, 'r', encoding = 'ISO-8859-1') as rpt_file:
    rpt_contents = rpt_file.read()
print('\n------------------------------\n')

# 데이터 추출 및 DataFrame 생성
coordinates_lines = read_section(inp_contents, 'COORDINATES')
conduits_lines = read_section(inp_contents, 'CONDUITS')
coordinates_df = create_dataframe(coordinates_lines, ['Node', 'X-Coord', 'Y-Coord'])
conduits_df = create_dataframe(conduits_lines, ['Name', 'From Node', 'To Node', 'Length', 'Roughness', 'InOffset', 'OutOffset', 'InitFlow', 'MaxFlow'])
node_surcharge_df = extract_node_surcharge_summary(rpt_contents)
node_flooding_df = extract_node_flooding_summary(rpt_contents)

# 열의 수치가 아닌 값을 NaN으로 변환
node_surcharge_df['Max Height (Meters)'] = pd.to_numeric(node_surcharge_df['Max Height (Meters)'])
node_surcharge_df['Min Depth (Meters)'] = pd.to_numeric(node_surcharge_df['Min Depth (Meters)'])
node_flooding_df['Total Flood Volume (10^6 ltr)'] = pd.to_numeric(node_flooding_df['Total Flood Volume (10^6 ltr)'])

# Overload Rate 계산
node_surcharge_df['Overload Rate'] = node_surcharge_df['Max Height (Meters)'] / (node_surcharge_df['Max Height (Meters)'] + node_surcharge_df['Min Depth (Meters)'])

# GeoDataFrame 생성 및 좌표 변환
gdf = extract_coords_and_create_gdf(coordinates_df)
node_coords = gdf.set_index('Node')['geometry'].to_dict()

# Folium 지도 생성 및 노드, 라인 표시
map_center = [gdf.geometry.y.mean()-0.005, gdf.geometry.x.mean()-0.005]
map = folium.Map(
    location = map_center,
    zoom_start = 14,
    tiles = 'cartodb positron',
    attr = 'Map data © OpenStreetMap contributors'
    )

# CONDUITS 시각화
for index, row in conduits_df.iterrows():
    if row['From Node'] in node_coords and row['To Node'] in node_coords:
        from_coord, to_coord = node_coords[row['From Node']], node_coords[row['To Node']]
        folium.PolyLine(
            [(from_coord.y, from_coord.x), (to_coord.y, to_coord.x)],
            weight = 2,
            color = 'gray'
            ).add_to(map)
print('CONDUITS are visualized.')

# COORDINATES 시각화
for _, row in gdf.iterrows():
    folium.CircleMarker(
        [row.geometry.y, row.geometry.x],
        radius = 2,
        weight = 2,
        color = 'gray',
        fill = True,
        fill_color = 'gray',
        fill_opacity = 1,
        popup = folium.Popup(f'Node: {row["Node"]}', max_width = 300)
        ).add_to(map)
print('NODE COORDINATES are visualized.')

# 각 노드에 마커 추가하기 전에 DataFrame 정렬
node_surcharge_df = node_surcharge_df.sort_values(by = 'Overload Rate')
node_flooding_df = node_flooding_df.sort_values(by = 'Total Flood Volume (10^6 ltr)')

# Overload Rate를 기준으로 각 노드에 마커 추가
for _, row in node_surcharge_df.iterrows():
    node = row['Node']
    overload_rate = row['Overload Rate']
    if node in node_coords:
        node_coord = node_coords[node]
        color = calculate_color(overload_rate)
        folium.CircleMarker(
            [node_coord.y, node_coord.x],
            radius = 6,
            weight = 2,
            color = 'black',
            fill = True,
            fill_color = color,
            fill_opacity = 1,
            popup = folium.Popup(f'Node: {node}<br>Overload Rate: {overload_rate:.2%}', max_width = 300)
        ).add_to(map)
print('OVERLOAD RATE MARKERS are visualized.')

# Flooding 기준으로 각 노드에 마커 추가
for _, row in node_flooding_df.iterrows():
    node = row['Node']
    flood_volume = row['Total Flood Volume (10^6 ltr)']
    if node in node_coords:
        node_coord = node_coords[node]
        folium.CircleMarker(
            [node_coord.y, node_coord.x],
            radius = math.sqrt(flood_volume) * 4,
            weight = 2,
            color = 'blue',
            fill = True,
            fill_opacity = 0.2,
            popup = folium.Popup(f'Node: {node}<br>Flooding: {flood_volume} * 10^6 ltr', max_width = 300)
        ).add_to(map)
print('FLOODING POINT MARKERS are visualized.')

# HTML 파일로 저장
map.save(f'{event_name}.html')
print(f'\n------------------------------\n\n{event_name}.html is generated. Check it out!\n')