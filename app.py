import streamlit as st
import requests
import pandas as pd
import folium
from folium.plugins import MeasureControl, LocateControl, MarkerCluster
from streamlit_folium import st_folium
import os
import urllib.parse
from datetime import datetime

# ----------------------------------------------------
# 🔑 1. API 키 및 구글 시트 연동 설정
# ----------------------------------------------------
KAKAO_REST_KEY = "f75505b4b7997750a587e104d87e89d3"
DATA_GO_KR_KEY = "ed720b69db88e9ae1a1b9779fadafa0ef967945a71407b7d3f1a22d56667461a"
VWORLD_KEY = "E15629E8-E82E-3C3C-BCA4-40C188FF3935"

# 상준님의 실제 클라우드타입 서비스 주소
VWORLD_DOMAIN = "https://port-0-solarmap-mtatayuj7b3bb02b.sel3.cloudtype.app" 

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GS_AVAILABLE = True
except ImportError:
    GS_AVAILABLE = False

def get_gspread_client():
    if GS_AVAILABLE and hasattr(st, "secrets") and "gcp_service_account" in st.secrets and "spreadsheet_id" in st.secrets:
        try:
            credentials = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            )
            return gspread.authorize(credentials)
        except Exception:
            return None
    return None

def load_target_data(tab_name):
    gc = get_gspread_client()
    df = pd.DataFrame()
    
    if gc:
        try:
            sh = gc.open_by_key(st.secrets["spreadsheet_id"])
            ws = sh.worksheet(tab_name)
            records = ws.get_all_records()
            if records:
                df = pd.DataFrame(records)
        except Exception:
            pass
    else:
        filename = f"{tab_name}.csv"
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            
    if not df.empty:
        df['상태'] = df['상태'].replace({
            '미개척': '미컨택',
            '거절': '거절/보류',
            '진행중': '협의중'
        })
        df['컨택방식'] = df['컨택방식'].replace({'메일': '이메일'})
        
        text_columns = ['상호명', '지번주소', '상태', '컨택방식', '등록일시', '수정일시', '메모', '최근수정내역']
        for col in text_columns:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].fillna("").astype(str).replace('nan', '')
            
        num_columns = ['면적', 'lat', 'lng']
        for col in num_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                
    return df

def save_target_data(tab_name, df):
    df_save = df.copy()
    
    text_columns = ['상호명', '지번주소', '상태', '컨택방식', '등록일시', '수정일시', '메모', '최근수정내역']
    for col in text_columns:
        if col in df_save.columns:
            df_save[col] = df_save[col].fillna("").astype(str).replace('nan', '')
            
    num_columns = ['면적', 'lat', 'lng']
    for col in num_columns:
        if col in df_save.columns:
            df_save[col] = pd.to_numeric(df_save[col], errors='coerce').fillna(0.0)
            
    gc = get_gspread_client()
    if gc:
        try:
            sh = gc.open_by_key(st.secrets["spreadsheet_id"])
            try:
                ws = sh.worksheet(tab_name)
            except:
                ws = sh.add_worksheet(title=tab_name, rows=str(max(100, len(df_save)+50)), cols="20")
            ws.clear()
            ws.update(values=[df_save.columns.values.tolist()] + df_save.values.tolist(), range_name='A1')
        except Exception as e:
            st.error(f"구글 시트 동기화 실패: {e}")
    else:
        filename = f"{tab_name}.csv"
        df_save.to_csv(filename, index=False)

# ----------------------------------------------------
# 📱 2. 모바일 최적화 화면 설정 및 커스텀 CSS
# ----------------------------------------------------
st.set_page_config(page_title="Solar Mkt Map", layout="centered")

custom_ui_css = """
<style>
    .stApp { background-color: #f9fafb; }
    div[data-testid="stForm"] {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 24px;
        background-color: #ffffff;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stTextArea>div>div>textarea {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }
    div[data-testid="stButton"] > button {
        border-radius: 8px;
        border: 1px solid #d1d5db;
        background-color: #ffffff;
        color: #374151;
        font-weight: 500;
        transition: all 0.2s;
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        background-color: #3b82f6;
        color: #ffffff;
        border: none;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background-color: #2563eb;
    }
    div[data-testid="stExpander"] {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        background-color: #ffffff;
    }
    .main-header {
        padding: 1.5rem 0 1rem 0;
        border-bottom: 1px solid #e5e7eb;
        margin-bottom: 2rem;
    }
    .main-header h2 {
        margin: 0;
        color: #111827;
        font-size: 1.6rem;
        font-weight: 800;
        letter-spacing: -0.5px;
    }
    .section-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #374151;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e5e7eb;
    }
    .helper-text {
        font-size: 13px;
        color: #6b7280;
        margin-bottom: 8px;
    }
</style>
"""
st.markdown(custom_ui_css, unsafe_allow_html=True)

if st.session_state.get('save_success', False):
    st.toast("✅ 변경사항이 성공적으로 저장되었습니다!")
    st.session_state.save_success = False

st.markdown("""
<div class="main-header">
    <h2>Solar Mkt Map ☀️</h2>
</div>
""", unsafe_allow_html=True)

if 'target_data' not in st.session_state:
    st.session_state.target_data = pd.DataFrame()
if 'search_center' not in st.session_state:
    st.session_state.search_center = [35.0910, 128.8475]
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 17
if 'current_tab' not in st.session_state:
    st.session_state.current_tab = ""
if 'selected_addr' not in st.session_state:
    st.session_state.selected_addr = None
if 'new_pin_coord' not in st.session_state:
    st.session_state.new_pin_coord = None

def get_place_info_from_coords(lat, lng):
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    address_name = "직접 입력 필요"
    building_name = ""
    
    addr_url = f"https://dapi.kakao.com/v2/local/geo/coord2address.json?x={lng}&y={lat}"
    try:
        res = requests.get(addr_url, headers=headers).json()
        if res.get("documents"):
            addr_info = res["documents"][0].get("address")
            if addr_info:
                address_name = addr_info.get("address_name", "")
            else:
                address_name = res["documents"][0].get("road_address", {}).get("address_name", "")
    except:
        pass

    if address_name and address_name != "직접 입력 필요":
        keyword_url = f"https://dapi.kakao.com/v2/local/search/keyword.json?query={address_name}"
        try:
            res_kw = requests.get(keyword_url, headers=headers).json()
            if res_kw.get("documents"):
                building_name = res_kw["documents"][0].get("place_name", "")
        except:
            pass
            
    return address_name, building_name

# ----------------------------------------------------
# 🔍 3. 검색 조건 설정 (영남권 풀 드롭다운 모드)
# ----------------------------------------------------
st.markdown('<div class="section-title">타겟 지역 및 조건 설정</div>', unsafe_allow_html=True)

region_data = {
    "부산광역시": {
        "강서구": ["녹산동", "송정동", "명지동", "명지1동", "명지2동", "대저1동", "대저2동", "강동동", "가락동", "가달동", "구랑동", "미음동", "범방동", "봉림동", "생곡동", "성북동", "식만동", "신호동", "죽동동", "죽림동", "지사동", "천성동", "화전동"],
        "기장군": ["기장읍", "장안읍", "정관읍", "일광읍", "철마면"],
        "남구": ["대연동", "용호동", "용당동", "문현동", "우암동", "감만동"],
        "동구": ["초량동", "수정동", "좌천동", "범일동"],
        "동래구": ["수민동", "복산동", "명륜동", "온천동", "사직동", "안락동", "명장동"],
        "부산진구": ["부전동", "연지동", "초읍동", "양정동", "전포동", "부암동", "당감동", "가야동", "개금동", "범천동"],
        "북구": ["구포동", "금곡동", "화명동", "덕천동", "만덕동"],
        "사상구": ["삼락동", "모라동", "덕포동", "괘법동", "감전동", "주례동", "학장동", "엄궁동"],
        "사하구": ["괴정동", "당리동", "하단동", "신평동", "장림동", "다대동", "구평동", "감천동"],
        "서구": ["동대신동", "서대신동", "부민동", "아미동", "초장동", "충무동", "남부민동", "암남동"],
        "수영구": ["남천동", "수영동", "망미동", "광안동", "민락동"],
        "연제구": ["거제동", "연산동"],
        "영도구": ["남항동", "영선동", "신선동", "봉래동", "청학동", "동삼동"],
        "중구": ["중앙동", "동광동", "대청동", "보수동", "부평동", "광복동", "남포동", "영주동"],
        "해운대구": ["우동", "중동", "좌동", "송정동", "반여동", "반송동", "재송동"]
    },
    "울산광역시": {
        "남구": ["신정동", "달동", "삼산동", "무거동", "옥동", "야음동", "장생포동", "선암동", "매암동", "여천동", "용잠동", "용연동", "황성동", "고사동", "성암동"],
        "동구": ["방어동", "일산동", "전하동", "남목동", "화정동", "미포동"],
        "북구": ["농소동", "강동동", "효문동", "송정동", "양정동", "염포동", "명촌동", "연암동", "매곡동", "중산동"],
        "울주군": ["온산읍", "언양읍", "온양읍", "범서읍", "서생면", "청량읍", "웅촌면", "두동면", "두서면", "상북면", "삼남읍", "삼동면"],
        "중구": ["학성동", "반구동", "복산동", "성안동", "중앙동", "우정동", "태화동", "다운동", "병영동", "약사동"]
    },
    "경상남도": {
        "김해시": ["진영읍", "주촌면", "진례면", "한림면", "생림면", "상동면", "대동면", "동상동", "회현동", "부원동", "내외동", "북부동", "칠산서부동", "활천동", "삼안동", "불암동", "장유1동", "장유2동", "장유3동"],
        "양산시": ["물금읍", "동면", "원동면", "상북면", "하북면", "중앙동", "양주동", "삼성동", "강서동", "소주동", "평산동", "덕계동", "서창동", "어곡동", "산막동", "유산동", "북정동"],
        "밀양시": ["삼랑진읍", "하남읍", "부북면", "상남면", "초동면", "무안면", "청도면", "단장면", "산외면", "산내면", "내일동", "내이동", "교동", "삼문동", "가곡동"],
        "창원시 의창구": ["동읍", "북면", "대산면", "의창동", "팔룡동", "명곡동", "봉림동"],
        "창원시 성산구": ["반송동", "용지동", "중앙동", "상남동", "사파동", "가음정동", "성주동", "웅남동", "신촌동"],
        "창원시 마산합포구": ["구산면", "진동면", "진북면", "진전면", "현동", "가포동", "월영동", "문화동", "반월중앙동", "완월동", "자산동", "교방동", "노산동", "오동동", "합포동", "산호동"],
        "창원시 마산회원구": ["내서읍", "회원동", "석전동", "회성동", "양덕동", "합성동", "구암동", "봉암동"],
        "창원시 진해구": ["충무동", "여좌동", "태백동", "경화동", "병암동", "석동", "이동", "자은동", "덕산동", "풍호동", "웅천동", "웅동1동", "웅동2동", "마천동", "남양동", "명동"],
        "진주시": ["문산읍", "내동면", "정촌면", "금곡면", "진성면", "일반성면", "이반성면", "사봉면", "지수면", "대곡면", "금산면", "집현면", "미천면", "명석면", "대평면", "수곡면", "천전동", "성북동", "중앙동", "상봉동", "상대동", "하대동", "상평동", "초장동", "평거동", "신안동", "이현동", "판문동", "가호동", "충무공동"],
        "사천시": ["사천읍", "정동면", "사남면", "용현면", "축동면", "곤양면", "곤명면", "서포면", "동서동", "선구동", "동서금동", "벌용동", "향촌동", "남양동"],
        "거제시": ["일운면", "동부면", "남부면", "거제면", "둔덕면", "사등면", "연초면", "하청면", "장목면", "장승포동", "능포동", "아주동", "옥포1동", "옥포2동", "장평동", "고현동", "상문동", "수양동"],
        "통영시": ["산양읍", "용남면", "도산면", "광도면", "욕지면", "한산면", "사량면", "도천동", "명정동", "중앙동", "정량동", "북신동", "무전동", "미수동", "봉평동"],
        "함안군": ["가야읍", "칠원읍", "함안면", "군북면", "법수면", "대산면", "칠서면", "칠북면", "산인면", "여항면"],
        "창녕군": ["창녕읍", "남지읍", "고암면", "성산면", "대합면", "이방면", "유어면", "대지면", "계성면", "영산면", "장마면", "도천면", "길곡면", "부곡면"],
        "고성군": ["고성읍", "삼산면", "하일면", "하이면", "상리면", "대가면", "영현면", "영오면", "개천면", "구만면", "회화면", "마암면", "동해면", "거류면"],
        "하동군": ["하동읍", "화개면", "악양면", "적량면", "횡천면", "고전면", "금남면", "금성면", "진교면", "양보면", "북천면", "청암면", "옥종면"],
        "합천군": ["합천읍", "봉산면", "묘산면", "가야면", "야로면", "율곡면", "초계면", "쌍책면", "덕곡면", "청덕면", "적중면", "대양면", "쌍백면", "삼가면", "가회면", "대병면", "용주면"]
    },
    "경상북도": {
        "포항시 남구": ["구룡포읍", "연일읍", "오천읍", "대송면", "동해면", "장기면", "호미곶면", "상대동", "해도동", "송도동", "청림동", "제철동", "효곡동", "대이동", "철강동", "장흥동"],
        "포항시 북구": ["흥해읍", "신광면", "청하면", "송라면", "기계면", "죽장면", "기북면", "중앙동", "양학동", "죽도동", "용흥동", "우창동", "두호동", "장량동", "환여동"],
        "경주시": ["건천읍", "외동읍", "안강읍", "감포읍", "양남면", "문무대왕면", "내남면", "산내면", "서면", "현곡면", "강동면", "천북면", "중부동", "황오동", "성건동", "황남동", "월성동", "선도동", "용강동", "황성동", "동천동", "불국동", "보덕동"],
        "구미시": ["선산읍", "고아읍", "산동읍", "무을면", "옥성면", "도개면", "해평면", "장천면", "송정동", "원평동", "지산동", "도량동", "선주원남동", "형곡1동", "형곡2동", "신평1동", "신평2동", "비산동", "공단동", "광평동", "상모사곡동", "임오동", "인동동", "진미동", "양포동", "임수동", "시미동"],
        "경산시": ["하양읍", "진량읍", "압량읍", "와촌면", "자인면", "용성면", "남산면", "남천면", "중방동", "중앙동", "남부동", "서부1동", "서부2동", "북부동", "동부동"],
        "영천시": ["금호읍", "청통면", "신녕면", "화산면", "화북면", "화남면", "자양면", "임고면", "고경면", "북안면", "대창면", "동부동", "중앙동", "명부동", "완산동", "남부동"],
        "김천시": ["아포읍", "농소면", "남면", "개령면", "감문면", "어모면", "봉산면", "대항면", "감천면", "조마면", "구성면", "지례면", "부항면", "대덕면", "증산면", "자산동", "평화남산동", "양금동", "대신동", "대곡동", "지좌동", "율곡동"],
        "안동시": ["풍산읍", "와룡면", "북후면", "서후면", "풍천면", "일직면", "남후면", "남선면", "임하면", "길안면", "임동면", "예안면", "도산면", "녹전면", "중구동", "명륜동", "옥동", "송하동", "안기동", "평화동", "안막동", "태화동", "강남동"],
        "칠곡군": ["왜관읍", "북삼읍", "석적읍", "지천면", "동명면", "가산면", "약목면", "기산면"],
        "성주군": ["성주읍", "선남면", "용암면", "수륜면", "가천면", "금수면", "대가면", "벽진면", "초전면", "월항면"],
        "고령군": ["대가야읍", "덕곡면", "운수면", "성산면", "다산면", "개진면", "우곡면", "쌍림면"]
    }
}

col1, col2, col3 = st.columns(3)
with col1: 
    sido = st.selectbox("시/도", list(region_data.keys()))
with col2: 
    sigungu = st.selectbox("시/군/구", list(region_data[sido].keys()))
with col3: 
    dong = st.selectbox("읍/면/동", region_data[sido][sigungu])

min_area = st.number_input("최소 건축면적 (㎡)", min_value=100, value=5000, step=500)
target_tab_name = f"target_{sido}_{sigungu}_{dong}"

# ----------------------------------------------------
# 🚀 4. 데이터 수집 및 캐시 로직
# ----------------------------------------------------
if st.button("데이터 조회 및 지도 적용", use_container_width=True):
    address_input = f"{sido} {sigungu} {dong}"
    st.session_state.current_tab = target_tab_name
    
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    res_center = requests.get(url, headers=headers, params={"query": address_input}).json()
    if res_center.get("documents"):
        doc = res_center["documents"][0]
        st.session_state.search_center = [float(doc["y"]), float(doc["x"])]
        st.session_state.map_zoom = 15 
        b_code = doc["address"]["b_code"]
        sigunguCd = b_code[:5]
        bjdongCd = b_code[5:]
    
    all_data = load_target_data(target_tab_name)
    
    if not all_data.empty:
        st.session_state.target_data = all_data
        st.success("데이터베이스에서 리스트를 성공적으로 불러왔습니다.")
    else:
        raw_data_list = []
        page_no = 1
        progress_text = st.empty()
        
        with st.spinner(f"최초 1회 데이터베이스 구축 중입니다..."):
            while True:
                bld_url = (
                    f"http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
                    f"?serviceKey={DATA_GO_KR_KEY}&sigunguCd={sigunguCd}&bjdongCd={bjdongCd}"
                    f"&numOfRows=100&pageNo={page_no}&_type=json"
                )
                try:
                    bld_res = requests.get(bld_url).json()
                    if "response" in bld_res and bld_res['response'].get('header', {}).get('resultCode') == '00':
                        items = bld_res['response'].get('body', {}).get('items', {}).get('item', [])
                        total_count = int(bld_res['response']['body'].get('totalCount', 0))
                        if isinstance(items, dict): items = [items]
                        if not items: break
                        progress_text.info(f"건축물대장 수집 중 ({min(page_no * 100, total_count)}/{total_count})")
                        for item in items:
                            raw_data_list.append({
                                "지번주소": item.get('platPlc', '주소없음'),
                                "건물명": item.get('bldNm', ''),
                                "건축면적(㎡)": float(item.get('archArea', 0) or 0)
                            })
                        if page_no * 100 >= total_count: break
                        page_no += 1
                    else: break
                except: break
        
        progress_text.empty()
        
        if raw_data_list:
            raw_df = pd.DataFrame(raw_data_list)
            grouped_df = raw_df.groupby('지번주소').agg({'건축면적(㎡)': 'sum', '건물명': lambda x: ', '.join(sorted(set(filter(None, x))))}).reset_index()
            filtered_df = grouped_df[grouped_df['건축면적(㎡)'] >= 100].copy()
            
            if not filtered_df.empty:
                final_data = []
                bar = st.progress(0)
                st.toast("위치 좌표 변환 및 매핑 작업 중...")
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                for i, (index, row) in enumerate(filtered_df.iterrows()):
                    plat_plc = row['지번주소']
                    coord_res = requests.get(url, headers=headers, params={"query": plat_plc}).json()
                    lng = float(coord_res["documents"][0]["x"]) if coord_res.get("documents") else None
                    lat = float(coord_res["documents"][0]["y"]) if coord_res.get("documents") else None
                    
                    kakao_place_name = ""
                    if lng and lat:
                        kw_url = f"https://dapi.kakao.com/v2/local/search/keyword.json?query={plat_plc}"
                        try:
                            kw_res = requests.get(kw_url, headers=headers).json()
                            if kw_res.get("documents"):
                                kakao_place_name = kw_res["documents"][0].get("place_name", "")
                        except:
                            pass
                    
                    final_building_name = kakao_place_name if kakao_place_name else (row['건물명'] if row['건물명'] else "")
                    
                    final_data.append({
                        "상호명": final_building_name,
                        "지번주소": plat_plc,
                        "면적": round(row['건축면적(㎡)'], 1),
                        "lat": lat, "lng": lng,
                        "상태": "미컨택",     
                        "컨택방식": "미진행",
                        "등록일시": now_str,
                        "수정일시": now_str,
                        "수동등록": False,
                        "메모": "",
                        "최근수정내역": ""
                    })
                    bar.progress((i + 1) / len(filtered_df))
                bar.empty()
                
                valid_df = pd.DataFrame([d for d in final_data if d['lat'] is not None])
                save_target_data(target_tab_name, valid_df)
                st.session_state.target_data = valid_df
                st.success("데이터베이스 구축 및 연동 저장 완료")
            else:
                st.info("조건에 일치하는 데이터가 없습니다.")

# ----------------------------------------------------
# 🗺️ 5. 지도 렌더링 
# ----------------------------------------------------
st.divider()

st.markdown('<div class="helper-text">안내: 지도의 빈 공간을 터치하여 새로운 현장 타겟을 추가할 수 있습니다.</div>', unsafe_allow_html=True)

with st.expander("지도안내"):
    st.markdown("""
    <div style="font-size: 13px; color: #374151;">
    <b>📌 핀 색상 안내</b><br>
    <span style="color: red;">●</span> 미컨택 &nbsp;&nbsp;
    <span style="color: orange;">●</span> 거절/보류 (노란색/주황색) &nbsp;&nbsp;
    <span style="color: blue;">●</span> 협의중 (파란색) <br>
    <span style="color: lightgreen;">●</span> 승낙서수령 (연두색) &nbsp;&nbsp;
    <span style="color: green;">●</span> 계약완료 (녹색) &nbsp;&nbsp;
    <span style="color: gray;">●</span> 기설치(불가) <br>
    <span style="color: purple; font-size: 16px;">★</span> <b>현재 선택된 타겟 (보라색 별표)</b>
    <hr style="margin: 10px 0; border-color: #e5e7eb;">
    <b>🗺️ 지적도 기호</b><br>
    <span style="color: #2563eb; font-weight: 600;">큰 숫자</span> : 본번 (메인 지번) &nbsp;|&nbsp; <span style="color: #4b5563; font-weight: 600;">작은 숫자</span> : 부번 (가지번호)<br>
    <span style="color: #9ca3af; font-size: 12px;">(예시: '1587' 구역 내 '2장' = 1587-2번지)</span><br>
    <b>장</b>: 공장용지 &nbsp;/&nbsp; <b>창</b>: 창고용지 &nbsp;/&nbsp; <b>대</b>: 대지 &nbsp;/&nbsp; <b>잡</b>: 잡종지 &nbsp;/&nbsp; <b>임</b>: 임야
    </div>
    """, unsafe_allow_html=True)

m = folium.Map(location=st.session_state.search_center, zoom_start=st.session_state.map_zoom, max_zoom=19, tiles=None)

folium.TileLayer(
    tiles='https://xdworld.vworld.kr/2d/Satellite/service/{z}/{x}/{y}.jpeg',
    attr='VWorld',
    name='위성지도',
    max_zoom=19,
    max_native_zoom=18, 
    control=False
).add_to(m)

folium.raster_layers.WmsTileLayer(
    url="https://api.vworld.kr/req/wms",
    layers="lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun",
    styles="lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun",
    format="image/png",
    transparent=True,
    version="1.3.0",
    key=VWORLD_KEY,
    domain=VWORLD_DOMAIN, 
    attr="VWorld Cadastral",
    name="지적도(지번경계)",
    overlay=True,
    control=True,
    opacity=0.6,
    show=False
).add_to(m)

folium.LayerControl().add_to(m)

LocateControl(
    position="topleft",
    strings={"title": "내 위치 확인", "popup": "현재 위치"},
    drawCircle=True,
    showPopup=False,
    keepCurrentZoomLevel=False
).add_to(m)

m.add_child(MeasureControl(
    position='topright',
    primary_length_unit='meters',
    secondary_length_unit=None, 
    primary_area_unit='sqmeters',
    secondary_area_unit=None
))

compass_html = """
<div style="position: absolute; top: 120px; left: 11px; z-index: 1000; background-color: rgba(255, 255, 255, 0.9); padding: 4px; border-radius: 6px; border: 2px solid rgba(0,0,0,0.2); box-shadow: 0 1px 4px rgba(0,0,0,0.3); width: 32px; height: 32px; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none;">
    <div style="font-size: 10px; font-weight: 900; color: #ef4444; line-height: 1;">N</div>
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#374151" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-top: 1px;">
        <polygon points="12 2 19 21 12 17 5 21 12 2"></polygon>
    </svg>
</div>
"""
m.get_root().html.add_child(folium.Element(compass_html))

custom_css = """
<style>
.leaflet-control-measure .coordinatetracker { display: none !important; }
.leaflet-control-measure h3, .leaflet-control-measure .prompt { font-size: 0 !important; }
.leaflet-control-measure h3::after { content: '지붕 면적 실측'; font-size: 13px !important; font-weight: 600; display: block; margin-bottom: 5px; color: #374151;}
.leaflet-control-measure .prompt::after { content: '지붕 모서를 따라 점을 지정하세요 (완료: 더블클릭)'; font-size: 11px !important; display: block; color: #6b7280; }
.js-cancel { font-size: 0 !important; }
.js-cancel::after { content: '취소'; font-size: 12px !important; color: #ef4444; margin-right: 15px; text-decoration: underline;}
.js-finish { font-size: 0 !important; }
.js-finish::after { content: '측정 완료'; font-size: 12px !important; color: #2563eb; text-decoration: underline;}
.leaflet-control-measure .results .group { font-size: 0 !important; }
.leaflet-control-measure .results .group span { font-size: 12px !important; font-weight: 600; color: #111827; }
.leaflet-control-measure .results .group:first-of-type::before { content: '둘레: '; font-size: 11px !important; color: #6b7280; }
.leaflet-control-measure .results .group:last-of-type::before { content: '면적: '; font-size: 12px !important; color: #2563eb; font-weight: 600;}
</style>
"""
m.get_root().header.add_child(folium.Element(custom_css))

color_map = {
    "미컨택": "red", 
    "거절/보류": "orange",
    "협의중": "blue", 
    "승낙서수령": "lightgreen",
    "계약완료": "green", 
    "기설치": "gray"
}

df_all = st.session_state.target_data

if not df_all.empty:
    df_all['면적'] = pd.to_numeric(df_all['면적'], errors='coerce').fillna(0.0)
    df_all['lat'] = pd.to_numeric(df_all['lat'], errors='coerce')
    df_all['lng'] = pd.to_numeric(df_all['lng'], errors='coerce')
    
    df_filtered = df_all[df_all['면적'] >= min_area]
    
    marker_cluster = MarkerCluster().add_to(m)
    
    for idx, row in df_filtered.iterrows():
        is_selected = (st.session_state.selected_addr is not None and row['지번주소'] == st.session_state.selected_addr)
        
        if is_selected:
            pin_color = 'purple'
            icon_shape = 'star'
        else:
            pin_color = color_map.get(row.get('상태', '미컨택'), "red")
            is_manual = row.get('수동등록', False)
            icon_shape = "star" if is_manual else "info-sign"
        
        if pd.notna(row['lat']) and pd.notna(row['lng']):
            folium.Marker(
                location=[row['lat'], row['lng']],
                tooltip=f"{row['상호명'] if pd.notna(row['상호명']) else '상호명 미상'}",
                icon=folium.Icon(color=pin_color, icon=icon_shape)
            ).add_to(marker_cluster) 

map_data = st_folium(m, width="100%", height=450, returned_objects=["last_object_clicked", "last_clicked"])

# ----------------------------------------------------
# 📝 6. 네비게이션 연동 및 편집/신규 폼 
# ----------------------------------------------------
clicked_marker = map_data.get("last_object_clicked")
clicked_map = map_data.get("last_clicked")

if clicked_marker:
    matched = df_all[(abs(df_all['lat'] - clicked_marker['lat']) < 0.0001) & (abs(df_all['lng'] - clicked_marker['lng']) < 0.0001)]
    if not matched.empty:
        clicked_addr = matched.iloc[0]['지번주소']
        if st.session_state.selected_addr != clicked_addr:
            st.session_state.selected_addr = clicked_addr
            st.session_state.new_pin_coord = None
            st.session_state.search_center = [clicked_marker['lat'], clicked_marker['lng']]
            st.rerun()

if clicked_map:
    is_far = not clicked_marker or (abs(clicked_marker['lat'] - clicked_map['lat']) > 0.001 or abs(clicked_marker['lng'] - clicked_map['lng']) > 0.001)
    if is_far:
        new_lat = clicked_map['lat']
        new_lng = clicked_map['lng']
        
        min_dist = 9999
        nearest_idx = -1
        if not df_all.empty:
            distances = ((df_all['lat'] - new_lat)**2 + (df_all['lng'] - new_lng)**2)**0.5
            nearest_idx = distances.idxmin()
            min_dist = distances.min()
        
        if min_dist < 0.0007:
            clicked_addr = df_all.loc[nearest_idx, '지번주소']
            if st.session_state.selected_addr != clicked_addr:
                st.session_state.selected_addr = clicked_addr
                st.session_state.new_pin_coord = None
                st.session_state.search_center = [df_all.loc[nearest_idx, 'lat'], df_all.loc[nearest_idx, 'lng']]
                st.toast("기존 등록된 타겟 데이터를 로드했습니다.")
                st.rerun()
        else:
            current_new_pin = st.session_state.new_pin_coord
            if not current_new_pin or abs(current_new_pin['lat'] - clicked_map['lat']) > 0.0001:
                st.session_state.new_pin_coord = clicked_map
                st.session_state.selected_addr = None
                st.session_state.search_center = [clicked_map['lat'], clicked_map['lng']]
                st.rerun()

show_marker_info = False
show_new_pin_form = False
selected_comp = None

if st.session_state.selected_addr:
    matched = df_all[df_all['지번주소'] == st.session_state.selected_addr]
    if not matched.empty:
        selected_comp = matched.iloc[0]
        show_marker_info = True
    else:
        st.session_state.selected_addr = None

elif st.session_state.new_pin_coord:
    show_new_pin_form = True

# ------------------------------------------------
# [A] 기존 핀 편집 모드 
# ------------------------------------------------
if show_marker_info and selected_comp is not None:
    comp = selected_comp
    display_name_form = str(comp['상호명']) if pd.notna(comp['상호명']) and comp['상호명'] != "" else "상호명 미상"
    
    st.markdown('<br>', unsafe_allow_html=True)
    st.markdown(f"**{display_name_form}** (면적: {comp['면적']}㎡)")

    reg_time = comp.get('등록일시', '-') if pd.notna(comp.get('등록일시')) else '-'
    mod_time = comp.get('수정일시', '-') if pd.notna(comp.get('수정일시')) else '-'
    st.markdown(f"<div class='helper-text'>최초 등록: {reg_time} &nbsp;|&nbsp; 최근 수정: {mod_time}</div>", unsafe_allow_html=True)

    st.code(comp['지번주소'], language="plaintext")
    
    encoded_addr = urllib.parse.quote(comp['지번주소'])
    
    st.markdown("<div style='font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 5px;'>현장 경로 탐색</div>", unsafe_allow_html=True)
    col_nav1, col_nav2, col_nav3 = st.columns(3)
    with col_nav1:
        st.link_button("네이버지도", f"https://map.naver.com/p/search/{encoded_addr}", use_container_width=True)
    with col_nav2:
        st.link_button("카카오맵", f"https://map.kakao.com/link/search/{encoded_addr}", use_container_width=True)
    with col_nav3:
        st.link_button("티맵(App)", f"tmap://search?name={encoded_addr}", use_container_width=True)
    
    st.divider()
    
    st.markdown('<div style="font-weight: 600; color: #111827; margin-bottom: 10px;">기본 정보 및 실측 데이터</div>', unsafe_allow_html=True)
    edited_name = st.text_input("상호명 (간판 기준)", value=str(comp['상호명']) if pd.notna(comp['상호명']) else "")
    edited_area = st.number_input("지붕 실측 면적(㎡)", value=float(comp['면적']), step=50.0)
    
    st.markdown('<div style="font-weight: 600; color: #111827; margin-top: 15px; margin-bottom: 10px;">상태 관리</div>', unsafe_allow_html=True)
    is_already_installed = True if comp.get('상태', '') == '기설치' else False
    is_installed = st.checkbox("태양광 기설치 완료 (또는 불가 현장)", value=is_already_installed)
    
    st.markdown('<div style="font-weight: 600; color: #111827; margin-top: 15px; margin-bottom: 10px;">영업 현황 기록</div>', unsafe_allow_html=True)
    
    method_options = ["미진행", "전화", "이메일", "방문", "기타"]
    current_method = comp.get('컨택방식', '미진행')
    
    if current_method in method_options:
        contact_idx = method_options.index(current_method)
        custom_val = ""
    else:
        contact_idx = method_options.index("기타")
        custom_val = current_method

    selected_contact = st.radio("Contact", method_options, index=contact_idx, horizontal=True)

    final_contact_method = selected_contact
    if selected_contact == "기타":
        final_contact_method = st.text_input("기타 방식 입력", value=custom_val, placeholder="예: 우편, 지인 소개 등")
        if not final_contact_method.strip():
            final_contact_method = "기타"

    contact_result = "미컨택"
    if selected_contact != "미진행":
        status_options = ["거절/보류", "협의중", "승낙서수령", "계약완료"]
        current_status = comp.get('상태', '미컨택')
        
        default_status_idx = status_options.index(current_status) if current_status in status_options else 0 
        contact_result = st.radio("상세 단계", status_options, index=default_status_idx, horizontal=True)

    current_memo = comp.get('메모', '')
    if pd.isna(current_memo): current_memo = ""
    memo = st.text_area("현장 특이사항 및 미팅 노트", value=str(current_memo))
    
    if st.button("변경사항 저장", use_container_width=True, type="primary"):
        if is_installed: final_status = "기설치"
        elif selected_contact == "미진행": final_status = "미컨택"
        else: final_status = contact_result
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        old_status = str(comp.get('상태', ''))
        old_method = str(comp.get('컨택방식', ''))
        old_memo = str(comp.get('메모', '')).strip()
        
        changes = []
        if old_status != final_status: 
            changes.append(f"상태({old_status}→{final_status})")
        if old_method != final_contact_method: 
            changes.append(f"방식({old_method}→{final_contact_method})")
        if old_memo != memo.strip(): 
            changes.append("메모수정")
        
        change_log = " | ".join(changes) if changes else "단순열람(수정없음)"
        
        all_df = st.session_state.target_data.copy()
        mask = (all_df['지번주소'] == comp['지번주소'])
        
        all_df.loc[mask, '상호명'] = edited_name
        all_df.loc[mask, '면적'] = float(edited_area)
        all_df.loc[mask, '컨택방식'] = final_contact_method
        all_df.loc[mask, '상태'] = final_status
        all_df.loc[mask, '수정일시'] = now_str
        all_df.loc[mask, '메모'] = memo 
        all_df.loc[mask, '최근수정내역'] = change_log 
        
        if st.session_state.current_tab:
            save_target_data(st.session_state.current_tab, all_df)
        
        st.session_state.target_data = all_df
        st.session_state.save_success = True
        st.rerun()

# ------------------------------------------------
# [B] 지도 빈 공간 클릭 시 (신규 핀 추가 모드)
# ------------------------------------------------
elif show_new_pin_form:
    new_lat = st.session_state.new_pin_coord['lat']
    new_lng = st.session_state.new_pin_coord['lng']
    
    st.info("선택하신 위치에 신규 타겟을 등록합니다.")
    
    with st.form("new_pin_form", clear_on_submit=True):
        st.markdown('<div style="font-weight: 600; color: #111827; margin-bottom: 10px;">신규 현장 정보 입력</div>', unsafe_allow_html=True)
        
        auto_address, auto_building_name = get_place_info_from_coords(new_lat, new_lng)
        
        new_addr = st.text_input("지번 주소", value=auto_address)
        new_name = st.text_input("상호명", value=auto_building_name)
        new_area = st.number_input("예상 지붕 면적(㎡)", min_value=0.0, value=float(min_area), step=100.0)
        
        if st.form_submit_button("신규 현장 등록", use_container_width=True):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_row = {
                "상호명": new_name,
                "지번주소": new_addr,
                "면적": new_area,
                "lat": new_lat,
                "lng": new_lng,
                "상태": "미컨택",
                "컨택방식": "미진행",
                "등록일시": now_str,
                "수정일시": now_str,
                "수동등록": True,
                "메모": "",
                "최근수정내역": "신규 현장 발굴 및 등록" 
            }
            
            new_df = pd.DataFrame([new_row])
            all_df = st.session_state.target_data.copy()
            all_df = pd.concat([all_df, new_df], ignore_index=True)
            
            if st.session_state.current_tab:
                save_target_data(st.session_state.current_tab, all_df)
                
            st.session_state.target_data = all_df
            st.session_state.save_success = True
            
            if new_area < min_area:
                st.warning("설정된 최소 면적 미달로 지도에는 표시되지 않지만, 데이터는 저장되었습니다.")
            
            st.session_state.selected_addr = new_addr
            st.session_state.new_pin_coord = None
            st.rerun()

# ----------------------------------------------------
# 📅 7. 일자별 영업일지
# ----------------------------------------------------
st.divider()
st.markdown('<div class="section-title">일자별 영업일지</div>', unsafe_allow_html=True)

selected_date = st.date_input("조회 일자 선택", value=datetime.today())
date_str = selected_date.strftime("%Y-%m-%d")

df_log = st.session_state.target_data
if not df_log.empty:
    df_log['수정일시'] = df_log['수정일시'].fillna("").astype(str)
    mask = df_log['수정일시'].str.startswith(date_str)
    daily_log = df_log[mask].copy()
    
    if daily_log.empty:
        st.info(f"{date_str} 기준 영업 이력이 존재하지 않습니다.")
    else:
        daily_log = daily_log.sort_values(by='수정일시').drop_duplicates(subset=['지번주소'], keep='last')
        
        st.success(f"조회 결과: 총 {len(daily_log)}건의 이력이 확인되었습니다.")
        for idx, row in daily_log.iterrows():
            with st.container():
                st.markdown(f"<div style='font-size: 14px; font-weight: 600; color: #1f2937;'>{row['상호명']} <span style='font-size:12px; font-weight:400; color:#6b7280;'>({row['상태']})</span></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='helper-text'>{row['지번주소']} &nbsp;|&nbsp; 접촉: {row['컨택방식']} &nbsp;|&nbsp; 시간: {row['수정일시']}</div>", unsafe_allow_html=True)
                
                change_hist = row.get('최근수정내역', '')
                if pd.notna(change_hist) and str(change_hist).strip() != "":
                    st.markdown(f"<div style='font-size: 13px; color: #ea580c; font-weight: 600; margin-top: 4px;'>🔄 변경점: {change_hist}</div>", unsafe_allow_html=True)
                
                if '메모' in row and pd.notna(row['메모']) and str(row['메모']).strip() != "":
                    st.markdown(f"<div style='background-color: #f3f4f6; padding: 10px; border-radius: 6px; font-size: 13px; color: #4b5563; margin-top: 5px;'>{row['메모']}</div>", unsafe_allow_html=True)
                
                st.markdown("<hr style='margin: 15px 0; border-top: 1px solid #e5e7eb;'>", unsafe_allow_html=True)
else:
    st.info("현재 로드된 데이터베이스가 없습니다.")
