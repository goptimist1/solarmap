import os
import re
import html
import time
import math
import urllib.parse
import unicodedata
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import folium

from branca.element import MacroElement
from jinja2 import Template
from folium.plugins import MeasureControl, LocateControl
from streamlit_folium import st_folium

# ============================================================
# Solar Mkt Map 3세대 - Final Production Build
#
# [공지사항 12개 원칙 100% 준수]
# - Google Sheets ONLY (CSV fallback 금지)
# - 기존 CRM 데이터 자동 덮어쓰기 금지
# - 사용자 수동 면적 수정값 보존
# - Kakao API 0.05초 delay + 429 retry
# - 주소 정규화 (정규화된 지번주소 + 좌표 20m 이중 중복검사)
# - site_id 기반 마커 선택 (popup에서 추출)
# - 지도 위치/줌 유지
# - ws.clear() 전체 재작성 금지
# ============================================================

# ============================================================
# Page
# ============================================================

st.set_page_config(
    page_title="Solar Mkt Map",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ============================================================
# HTTP Session (Session State에 보관하여 재사용)
# ============================================================

if "http_session" not in st.session_state:
    _session = requests.Session()
    _adapter = requests.adapters.HTTPAdapter(
        pool_connections=20,
        pool_maxsize=20,
        max_retries=0,
    )
    _session.mount("http://", _adapter)
    _session.mount("https://", _adapter)
    st.session_state.http_session = _session

HTTP_SESSION = st.session_state.http_session
KAKAO_REQUEST_DELAY = 0.05
KAKAO_MAX_RETRIES = 4
PUBLIC_DATA_MAX_PAGES = 500

# ============================================================
# Secrets
# ============================================================

def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)

KAKAO_REST_KEY = secret("KAKAO_REST_KEY")
DATA_GO_KR_KEY = secret("DATA_GO_KR_KEY")
VWORLD_KEY = secret("VWORLD_KEY")

VWORLD_DOMAIN = secret(
    "VWORLD_DOMAIN",
    "https://port-0-solarmap-mtatayuj7b3bb02b.sel3.cloudtype.app",
)

GOOGLE_SHEET_ID = secret("spreadsheet_id")

# ============================================================
# Google Library
# ============================================================

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GS_AVAILABLE = True
except ImportError:
    GS_AVAILABLE = False

# ============================================================
# Constants
# ============================================================

TEXT_COLS = [
    "site_id",
    "상호명",
    "지번주소",
    "상태",
    "컨택방식",
    "등록일시",
    "수정일시",
    "메모",
    "최근수정내역",
]

NUM_COLS = [
    "면적",
    "lat",
    "lng",
]

BOOL_COLS = [
    "수동등록",
]

TARGET_COLS = TEXT_COLS + NUM_COLS + BOOL_COLS

STATUS_OPTIONS = [
    "미컨택",
    "거절/보류",
    "협의중",
    "승낙서수령",
    "계약완료",
    "기설치",
]

METHOD_OPTIONS = [
    "미진행",
    "전화",
    "이메일",
    "방문",
    "기타",
]

STATUS_COLORS = {
    "미컨택": "red",
    "거절/보류": "orange",
    "협의중": "blue",
    "승낙서수령": "lightgreen",
    "계약완료": "green",
    "기설치": "gray",
}

ACTIVITY_HEADERS = [
    "기록일시",
    "site_id",
    "지역탭",
    "상호명",
    "지번주소",
    "접촉방식",
    "상태",
    "면적",
    "메모",
    "변경내역",
    "행동",
]

# ============================================================
# Region
# ============================================================

REGION_DATA = {
    "부산광역시": {
        "강서구": [
            "녹산동", "송정동", "명지동", "명지1동", "명지2동",
            "대저1동", "대저2동", "강동동", "가락동", "가달동",
            "구랑동", "미음동", "범방동", "봉림동", "생곡동",
            "성북동", "식만동", "신호동", "죽동동", "죽림동",
            "지사동", "천성동", "화전동"
        ],
        "기장군": ["기장읍", "장안읍", "정관읍", "일광읍", "철마면"],
        "남구": ["대연동", "용호동", "용당동", "문현동", "우암동", "감만동"],
        "동구": ["초량동", "수정동", "좌천동", "범일동"],
        "동래구": [
            "수민동", "복산동", "명륜동", "온천동",
            "사직동", "안락동", "명장동"
        ],
        "부산진구": [
            "부전동", "연지동", "초읍동", "양정동",
            "전포동", "부암동", "당감동", "가야동",
            "개금동", "범천동"
        ],
        "북구": ["구포동", "금곡동", "화명동", "덕천동", "만덕동"],
        "사상구": [
            "삼락동", "모라동", "덕포동", "괘법동",
            "감전동", "주례동", "학장동", "엄궁동"
        ],
        "사하구": [
            "괴정동", "당리동", "하단동", "신평동",
            "장림동", "다대동", "구평동", "감천동"
        ],
        "서구": [
            "동대신동", "서대신동", "부민동", "아미동",
            "초장동", "충무동", "남부민동", "암남동"
        ],
        "수영구": ["남천동", "수영동", "망미동", "광안동", "민락동"],
        "연제구": ["거제동", "연산동"],
        "영도구": [
            "남항동", "영선동", "신선동",
            "봉래동", "청학동", "동삼동"
        ],
        "중구": [
            "중앙동", "동광동", "대청동", "보수동",
            "부평동", "광복동", "남포동", "영주동"
        ],
        "해운대구": [
            "우동", "중동", "좌동", "송정동",
            "반여동", "반송동", "재송동"
        ],
    },
    "울산광역시": {
        "남구": [
            "신정동", "달동", "삼산동", "무거동",
            "옥동", "야음동", "장생포동", "선암동",
            "매암동", "여천동", "용잠동", "용연동",
            "황성동", "고사동", "성암동"
        ],
        "동구": [
            "방어동", "일산동", "전하동",
            "남목동", "화정동", "미포동"
        ],
        "북구": [
            "농소동", "강동동", "효문동", "송정동",
            "양정동", "염포동", "명촌동", "연암동",
            "매곡동", "중산동"
        ],
        "울주군": [
            "온산읍", "언양읍", "온양읍", "범서읍",
            "서생면", "청량읍", "웅촌면", "두동면",
            "두서면", "상북면", "삼남읍", "삼동면"
        ],
        "중구": [
            "학성동", "반구동", "복산동", "성안동",
            "중앙동", "우정동", "태화동", "다운동",
            "병영동", "약사동"
        ],
    },
    "경상남도": {
        "김해시": [
            "진영읍", "주촌면", "진례면", "한림면",
            "생림면", "상동면", "대동면", "동상동",
            "회현동", "부원동", "내외동", "북부동",
            "칠산서부동", "활천동", "삼안동", "불암동",
            "장유1동", "장유2동", "장유3동"
        ],
        "양산시": [
            "물금읍", "동면", "원동면", "상북면",
            "하북면", "중앙동", "양주동", "삼성동",
            "강서동", "소주동", "평산동", "덕계동",
            "서창동", "어곡동", "산막동", "유산동",
            "북정동"
        ],
        "창원시 의창구": [
            "동읍", "북면", "대산면", "의창동",
            "팔룡동", "명곡동", "봉림동"
        ],
        "창원시 성산구": [
            "반송동", "용지동", "중앙동", "상남동",
            "사파동", "가음정동", "성주동", "웅남동",
            "신촌동"
        ],
        "진주시": [
            "문산읍", "내동면", "정촌면", "금곡면",
            "진성면", "일반성면", "이반성면", "사봉면",
            "지수면", "대곡면", "금산면", "집현면",
            "미천면", "명석면", "대평면", "수곡면",
            "천전동", "성북동", "중앙동", "상봉동",
            "상대동", "하대동", "상평동", "초장동",
            "평거동", "신안동", "이현동", "판문동",
            "가호동", "충무공동"
        ],
    },
}

# ============================================================
# Session State
# ============================================================

def init_state():
    defaults = {
        "target_data": pd.DataFrame(columns=TARGET_COLS),
        "search_center": [35.1695, 129.1760],
        "map_zoom": 15,
        "current_tab": "",
        "last_loaded_tab": "",
        "selected_site_id": None,
        "selected_addr": None,
        "new_pin_coord": None,
        "save_success": False,
        "activity_status": "",
        "cadastral_on": False,
        "last_map_center": None,
        "last_map_zoom": None,
        "last_handled_map_click": None,
        "last_marker_click_count": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #f9fafb;
    }
    div[data-testid="stForm"] {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 24px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,.05);
    }
    .main-header {
        padding: 1.5rem 0 1rem;
        border-bottom: 1px solid #e5e7eb;
        margin-bottom: 2rem;
    }
    .main-header h2 {
        margin: 0;
        color: #111827;
        font-size: 1.6rem;
        font-weight: 800;
        letter-spacing: -.5px;
    }
    .section-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #374151;
        margin-bottom: 1rem;
        padding-bottom: .5rem;
        border-bottom: 1px solid #e5e7eb;
    }
    .helper-text {
        font-size: 13px;
        color: #6b7280;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Header
# ============================================================

st.markdown(
    '<div class="main-header"><h2>Solar Mkt Map ☀️</h2></div>',
    unsafe_allow_html=True,
)

# ============================================================
# Save Toast (rerun 직후 화면 상단에 표시)
# ============================================================

if st.session_state.save_success:
    st.toast("✅ Google Sheets 저장 완료")
    st.session_state.save_success = False

# ============================================================
# Basic Helpers
# ============================================================

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        value = str(value).replace(",", "").strip()
        if value == "":
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default

def normalize_address(address: str) -> str:
    if address is None:
        return ""
    value = str(address)
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*번지\s*$", "", value)
    return value.strip()

def address_key(address: str) -> str:
    return normalize_address(address).replace(" ", "")

def coordinate_distance_meters(lat1, lng1, lat2, lng2):
    try:
        lat1 = float(lat1)
        lng1 = float(lng1)
        lat2 = float(lat2)
        lng2 = float(lng2)
    except Exception:
        return float("inf")

    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def new_site_id(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "SITE-000001"
    if "site_id" not in df.columns:
        return "SITE-000001"

    ids = df["site_id"].astype(str)
    nums = pd.to_numeric(
        ids.str.extract(r"SITE-(\d+)")[0],
        errors="coerce",
    ).dropna()

    n = int(nums.max()) + 1 if not nums.empty else len(df) + 1
    used_ids = set(ids)

    while f"SITE-{n:06d}" in used_ids:
        n += 1

    return f"SITE-{n:06d}"

# ============================================================
# Normalize DataFrame
# ============================================================

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=TARGET_COLS)

    df = df.copy()
    rename_map = {}

    if "건물명" in df.columns and "상호명" not in df.columns:
        rename_map["건물명"] = "상호명"
    if "건축면적(㎡)" in df.columns and "면적" not in df.columns:
        rename_map["건축면적(㎡)"] = "면적"

    df = df.rename(columns=rename_map)

    legacy_status = {
        "미개척": "미컨택",
        "거절": "거절/보류",
        "진행중": "협의중",
    }
    if "상태" in df.columns:
        df["상태"] = df["상태"].replace(legacy_status)
    if "컨택방식" in df.columns:
        df["컨택방식"] = df["컨택방식"].replace({"메일": "이메일"})

    for col in TEXT_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).replace("nan", "")

    for col in NUM_COLS:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].astype(str).str.replace(",", "", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "수동등록" not in df.columns:
        df["수동등록"] = False
    df["수동등록"] = (
        df["수동등록"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes", "y", "t"])
    )

    # site_id 생성
    seen = set()
    generated = []

    for sid in df["site_id"].astype(str):
        sid = sid.strip()
        if sid and sid != "nan" and sid not in seen:
            generated.append(sid)
            seen.add(sid)
        else:
            generated.append("")

    next_num = 1
    for i, sid in enumerate(generated):
        if sid:
            continue
        while f"SITE-{next_num:06d}" in seen:
            next_num += 1
        generated[i] = f"SITE-{next_num:06d}"
        seen.add(generated[i])
        next_num += 1

    df["site_id"] = generated

    extras = [c for c in df.columns if c not in TARGET_COLS]
    return df[TARGET_COLS + extras]

# ============================================================
# API Key Check
# ============================================================

def require_api_keys() -> bool:
    missing = []
    if not KAKAO_REST_KEY:
        missing.append("KAKAO_REST_KEY")
    if not DATA_GO_KR_KEY:
        missing.append("DATA_GO_KR_KEY")
    if not VWORLD_KEY:
        missing.append("VWORLD_KEY")
    if not GOOGLE_SHEET_ID:
        missing.append("spreadsheet_id")

    if missing:
        st.error("필수 설정값이 없습니다: " + ", ".join(missing))
        return False
    if not GS_AVAILABLE:
        st.error("gspread 또는 google-auth가 설치되어 있지 않습니다.")
        return False
    return True

# ============================================================
# Google Sheets
# ============================================================

@st.cache_resource(ttl=3600, show_spinner=False)
def get_gspread_client():
    if not GS_AVAILABLE:
        return None
    if not GOOGLE_SHEET_ID:
        return None
    try:
        service_info = st.secrets.get("gcp_service_account")
        if not service_info:
            return None
        credentials = Credentials.from_service_account_info(
            dict(service_info),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        return gspread.authorize(credentials)
    except Exception:
        return None

def sheets_enabled() -> bool:
    return get_gspread_client() is not None

def get_or_create_ws(spreadsheet, title, rows=100, cols=30):
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        return spreadsheet.add_worksheet(
            title=title,
            rows=str(max(rows, 100)),
            cols=str(max(cols, 30)),
        )

def col_letter(number: int) -> str:
    if number < 1:
        return "A"
    result = ""
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result

def ensure_target_schema(ws):
    values = ws.get_all_values()
    if not values:
        headers = TARGET_COLS.copy()
        ws.update(
            range_name=f"A1:{col_letter(len(headers))}1",
            values=[headers],
        )
        return headers

    headers = list(values[0])
    if not headers or all(not h for h in headers):
        headers = TARGET_COLS.copy()
        ws.update(
            range_name=f"A1:{col_letter(len(headers))}1",
            values=[headers],
        )
        return headers

    missing = [c for c in TARGET_COLS if c not in headers]
    if missing:
        required_end = len(headers) + len(missing)
        if required_end > ws.col_count:
            ws.add_cols(required_end - ws.col_count)
        headers.extend(missing)
        ws.update(
            range_name=f"A1:{col_letter(len(headers))}1",
            values=[headers],
        )

    if "site_id" not in headers:
        raise RuntimeError("Google Sheets에 site_id 열이 없습니다.")
    return headers

@st.cache_data(ttl=15, show_spinner=False)
def load_target_data(tab_name: str):
    gc = get_gspread_client()
    if gc is None:
        raise RuntimeError("Google Sheets 연결이 준비되지 않았습니다.")
    
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    ws = get_or_create_ws(
        sh,
        tab_name,
        rows=100,
        cols=max(len(TARGET_COLS), 30),
    )
    
    values = ws.get_all_values()
    if not values:
        ensure_target_schema(ws)
        return pd.DataFrame(columns=TARGET_COLS)
        
    headers = values[0]
    if not headers or all(not h for h in headers):
        ensure_target_schema(ws)
        return pd.DataFrame(columns=TARGET_COLS)
        
    rows = values[1:]
    if not rows:
        return pd.DataFrame(columns=headers)
        
    width = len(headers)
    normalized_rows = [(row + [""] * width)[:width] for row in rows]
    df = pd.DataFrame(normalized_rows, columns=headers)
    
    return normalize_df(df)

def sheet_row_values(row_dict, headers):
    result = []
    for col in headers:
        value = row_dict.get(col, "")
        try:
            if pd.isna(value):
                value = ""
        except Exception:
            pass
            
        if isinstance(value, bool):
            value = "TRUE" if value else "FALSE"
        elif isinstance(value, float) and math.isnan(value):
            value = ""
        elif value is None:
            value = ""
            
        result.append(str(value))
    return result

def append_target_rows(tab_name: str, rows_df: pd.DataFrame) -> bool:
    if rows_df is None or rows_df.empty:
        return True
        
    gc = get_gspread_client()
    if gc is None:
        raise RuntimeError("Google Sheets 연결이 없습니다.")
        
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    ws = get_or_create_ws(
        sh,
        tab_name,
        rows=len(rows_df) + 100,
        cols=max(len(TARGET_COLS), 30),
    )
    
    headers = ensure_target_schema(ws)
    rows_to_append = []
    
    for _, row in rows_df.iterrows():
        rows_to_append.append(sheet_row_values(row.to_dict(), headers))
        
    if rows_to_append:
        ws.append_rows(rows_to_append, value_input_option="RAW")
        
    load_target_data.clear()
    return True

def update_target_row(tab_name: str, site_id: str, row_dict: dict) -> bool:
    gc = get_gspread_client()
    if gc is None:
        raise RuntimeError("Google Sheets 연결이 없습니다.")
        
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    ws = get_or_create_ws(
        sh,
        tab_name,
        rows=100,
        cols=max(len(TARGET_COLS), 30),
    )
    
    headers = ensure_target_schema(ws)
    site_col_idx_zero = headers.index("site_id")
    site_col = site_col_idx_zero + 1  # 1-based
    
    all_values = ws.get_all_values()
    target_row = None
    match_count = 0
    
    for row_idx, row in enumerate(all_values[1:], start=2):
        if site_col_idx_zero < len(row):
            cell_value = str(row[site_col_idx_zero]).strip()
            if cell_value == str(site_id).strip():
                target_row = row_idx
                match_count += 1
                
    if target_row is None:
        raise RuntimeError(f"Google Sheets에서 {site_id} 행을 찾지 못했습니다.")
    if match_count > 1:
        raise RuntimeError(f"{site_id}가 Google Sheets에 중복되어 있습니다. 자동 수정하지 않았습니다.")
        
    values = [sheet_row_values(row_dict, headers)]
    start = f"A{target_row}"
    end = f"{col_letter(len(headers))}{target_row}"
    
    ws.update(range_name=f"{start}:{end}", values=values)
    load_target_data.clear()
    return True

# ============================================================
# Activity Log
# ============================================================

def activity_row(site_id, tab_name, before, after, action):
    changes = []
    compare_items = [
        ("상태", "상태"),
        ("방식", "컨택방식"),
        ("면적", "면적"),
        ("상호명", "상호명"),
        ("메모", "메모"),
    ]
    
    for label, key in compare_items:
        b = str(before.get(key, ""))
        a = str(after.get(key, ""))
        if b != a:
            changes.append(f"{label}({b}→{a})")
            
    if action == "신규등록":
        changes = ["신규 현장 발굴 및 등록"]
        
    return {
        "기록일시": now_str(),
        "site_id": site_id,
        "지역탭": tab_name,
        "상호명": after.get("상호명", ""),
        "지번주소": after.get("지번주소", ""),
        "접촉방식": after.get("컨택방식", ""),
        "상태": after.get("상태", ""),
        "면적": after.get("면적", ""),
        "메모": after.get("메모", ""),
        "변경내역": " | ".join(changes) if changes else "단순열람(수정없음)",
        "행동": action,
    }

def append_activity(site_id, tab_name, before, after, action):
    row = activity_row(site_id, tab_name, before, after, action)
    gc = get_gspread_client()
    if gc is None:
        raise RuntimeError("Google Sheets 연결이 없습니다.")
        
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    ws = get_or_create_ws(
        sh,
        "activity_log",
        rows=1000,
        cols=len(ACTIVITY_HEADERS),
    )
    
    values = ws.get_all_values()
    
    if not values:
        headers = ACTIVITY_HEADERS.copy()
        ws.update(range_name=f"A1:{col_letter(len(headers))}1", values=[headers])
    else:
        current_headers = list(values[0])
        if not current_headers or all(not h for h in current_headers):
            headers = ACTIVITY_HEADERS.copy()
            ws.update(range_name=f"A1:{col_letter(len(headers))}1", values=[headers])
        else:
            headers = current_headers
            missing = [c for c in ACTIVITY_HEADERS if c not in headers]
            if missing:
                headers = headers + missing
                required_end = len(headers)
                if required_end > ws.col_count:
                    ws.add_cols(required_end - ws.col_count)
                ws.update(range_name=f"A1:{col_letter(len(headers))}1", values=[headers])
                
    ws.append_row(sheet_row_values(row, headers), value_input_option="RAW")
    load_activity_log.clear()
    return True

@st.cache_data(ttl=5, show_spinner=False)
def load_activity_log():
    gc = get_gspread_client()
    if gc is None:
        raise RuntimeError("Google Sheets 연결이 없습니다.")
        
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    ws = get_or_create_ws(
        sh,
        "activity_log",
        rows=1000,
        cols=len(ACTIVITY_HEADERS),
    )
    
    values = ws.get_all_values()
    if not values or len(values) <= 1:
        return pd.DataFrame(columns=ACTIVITY_HEADERS)
        
    headers = values[0]
    rows = values[1:]
    width = len(headers)
    rows = [(r + [""] * width)[:width] for r in rows]
    
    return pd.DataFrame(rows, columns=headers)

# ============================================================
# Kakao API
# ============================================================

def kakao_get(path: str, params: dict, timeout: int = 10):
    if not KAKAO_REST_KEY:
        raise RuntimeError("KAKAO_REST_KEY가 없습니다.")
        
    url = "https://dapi.kakao.com" + path
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    last_error = None
    
    for attempt in range(KAKAO_MAX_RETRIES):
        if attempt > 0:
            wait_seconds = min(2 ** attempt, 8)
            time.sleep(wait_seconds)
            
        try:
            response = HTTP_SESSION.get(
                url, headers=headers, params=params, timeout=timeout
            )
            if response.status_code == 429:
                last_error = RuntimeError("Kakao API Rate Limit(429)")
                continue
                
            response.raise_for_status()
            time.sleep(KAKAO_REQUEST_DELAY)
            return response.json()
            
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt == KAKAO_MAX_RETRIES - 1:
                break
                
    raise RuntimeError(f"Kakao API 요청 실패: {last_error}")

@st.cache_data(ttl=86400, show_spinner=False)
def geocode_address(address: str):
    if not address:
        return None
    try:
        data = kakao_get("/v2/local/search/address.json", {"query": address})
        documents = data.get("documents", [])
        if not documents:
            return None
            
        doc = documents[0]
        address_obj = doc.get("address") or doc.get("road_address") or {}
        return {
            "lat": float(doc["y"]),
            "lng": float(doc["x"]),
            "b_code": address_obj.get("b_code", ""),
        }
    except Exception:
        return None

@st.cache_data(ttl=86400, show_spinner=False)
def reverse_geocode(lat: float, lng: float):
    try:
        data = kakao_get("/v2/local/geo/coord2address.json", {"x": lng, "y": lat})
        documents = data.get("documents", [])
        if not documents:
            return ("직접 입력 필요", "")
            
        doc = documents[0]
        addr = doc.get("address") or {}
        road = doc.get("road_address") or {}
        address_name = addr.get("address_name") or road.get("address_name") or "직접 입력 필요"
        
        return (address_name, "")
    except Exception:
        return ("직접 입력 필요", "")

@st.cache_data(ttl=86400, show_spinner=False)
def place_name_for_address(address: str):
    if not address:
        return ""
    try:
        data = kakao_get("/v2/local/search/keyword.json", {"query": address})
        documents = data.get("documents", [])
        if documents:
            return documents[0].get("place_name", "")
    except Exception:
        pass
    return ""

def get_place_info_from_coords(lat, lng):
    address_name, _ = reverse_geocode(lat, lng)
    building_name = ""
    if address_name != "직접 입력 필요":
        building_name = place_name_for_address(address_name)
    return (address_name, building_name)

# ============================================================
# Public Data
# ============================================================

def fetch_building_targets(sigungu_cd: str, bjdong_cd: str):
    raw = []
    page_no = 1
    total_count = 0
    progress = st.progress(0)
    status_box = st.empty()
    
    url = "https://apis.data.go.kr/1613000/BldRgstService_2.0/getBrTitleInfo"
    
    while page_no <= PUBLIC_DATA_MAX_PAGES:
        params = {
            "serviceKey": DATA_GO_KR_KEY,
            "sigunguCd": sigungu_cd,
            "bjdongCd": bjdong_cd,
            "numOfRows": 100,
            "pageNo": page_no,
            "_type": "json",
        }
        
        try:
            response = HTTP_SESSION.get(url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            response_obj = data.get("response", {})
            header = response_obj.get("header", {})
            
            if header.get("resultCode") != "00":
                raise RuntimeError(header.get("resultMsg", "건축물대장 API 오류"))
                
            body = response_obj.get("body", {})
            total_count = int(body.get("totalCount", 0) or 0)
            items = body.get("items", {}).get("item", [])
            
            if isinstance(items, dict):
                items = [items]
            if not items:
                break
                
            for item in items:
                area = safe_float(item.get("archArea", 0))
                raw.append({
                    "지번주소": item.get("platPlc", "주소없음"),
                    "건물명": item.get("bldNm", ""),
                    "건축면적(㎡)": area,
                })
                
            processed = min(page_no * 100, total_count)
            progress_value = processed / max(total_count, 1)
            progress.progress(min(progress_value, 1.0))
            status_box.info(f"건축물대장 수집 중: {processed:,}/{total_count:,}")
            
            if page_no * 100 >= total_count:
                break
            page_no += 1
            
        except requests.exceptions.RequestException as exc:
            progress.empty()
            status_box.empty()
            raise RuntimeError(f"공공데이터포털 통신 실패: {exc}")
        except Exception as exc:
            progress.empty()
            status_box.empty()
            raise RuntimeError(f"건축물대장 조회 실패: {exc}")
            
    progress.empty()
    status_box.empty()
    return raw

# ============================================================
# Build Target DB
# ============================================================

def build_target_df(sido, sigungu, dong, min_area, existing_df=None):
    center = geocode_address(f"{sido} {sigungu} {dong}")
    if not center:
        raise RuntimeError("선택한 지역의 좌표를 찾지 못했습니다.")
        
    b_code = center.get("b_code", "")
    if len(b_code) < 10:
        raise RuntimeError("선택한 지역의 법정동코드를 찾지 못했습니다.")
        
    sigungu_cd = b_code[:5]
    bjdong_cd = b_code[5:10]
    
    raw = fetch_building_targets(sigungu_cd, bjdong_cd)
    
    if existing_df is None:
        base_df = pd.DataFrame(columns=TARGET_COLS)
    else:
        base_df = normalize_df(existing_df)
        
    existing_address_keys = set()
    if not base_df.empty:
        existing_address_keys = set(base_df["지번주소"].astype(str).map(address_key))
        
    if not raw:
        return (base_df, center, 0)
        
    raw_df = pd.DataFrame(raw)
    raw_df["주소KEY"] = raw_df["지번주소"].astype(str).map(address_key)
    
    grouped = (
        raw_df
        .groupby("주소KEY", as_index=False)
        .agg({
            "지번주소": "first",
            "건축면적(㎡)": "sum",
            "건물명": lambda x: ", ".join(sorted(set(filter(None, x)))),
        })
    )
    
    filtered = grouped[grouped["건축면적(㎡)"] >= float(min_area)].copy()
    new_targets = filtered[~filtered["주소KEY"].isin(existing_address_keys)].copy()
    
    if new_targets.empty:
        return (base_df, center, 0)
        
    rows = []
    progress = st.progress(0)
    status_box = st.empty()
    total_new = len(new_targets)
    
    for i, (_, row) in enumerate(new_targets.iterrows(), start=1):
        addr = str(row["지번주소"]).strip()
        geo = geocode_address(addr)
        
        lat = geo["lat"] if geo else 0.0
        lng = geo["lng"] if geo else 0.0
        
        name = ""
        if geo:
            name = place_name_for_address(addr)
        if not name:
            name = str(row["건물명"] or "")
            
        stamp = now_str()
        rows.append({
            "site_id": "",
            "상호명": name,
            "지번주소": addr,
            "면적": round(safe_float(row["건축면적(㎡)"]), 1),
            "lat": lat,
            "lng": lng,
            "상태": "미컨택",
            "컨택방식": "미진행",
            "등록일시": stamp,
            "수정일시": stamp,
            "메모": "",
            "최근수정내역": "",
            "수동등록": False,
        })
        
        progress.progress(i / total_new)
        status_box.info(f"신규 현장 좌표 변환 중: {i:,}/{total_new:,}")
        
    progress.empty()
    status_box.empty()
    
    new_df = normalize_df(pd.DataFrame(rows))
    combined = pd.concat([base_df, new_df], ignore_index=True)
    
    return (normalize_df(combined), center, len(new_df))

# ============================================================
# Map Macros
# ============================================================

class CadastralToggle(MacroElement):
    _template = Template(
        r"""
        {% macro script(this, kwargs) %}
        (function() {
            var map = {{ this._parent.get_name() }};
            var layer = {{ this.layer_name }};
            var storageKey = {{ this.storage_key | tojson }};

            if (!map || !layer) return;

            function getSavedState() {
                try {
                    return window.localStorage.getItem(storageKey) === "1";
                } catch(e) {
                    return false;
                }
            }

            function saveState(on) {
                try {
                    window.localStorage.setItem(storageKey, on ? "1" : "0");
                } catch(e) {}
            }

            function refresh(button) {
                var on = map.hasLayer(layer);
                button.innerHTML = on ? "지적도 ON" : "지적도 OFF";
                button.style.background = on ? "#eef2ff" : "#ffffff";
                button.style.color = on ? "#4338ca" : "#374151";
            }

            try {
                if (getSavedState() && !map.hasLayer(layer)) {
                    map.addLayer(layer);
                }
                if (!getSavedState() && map.hasLayer(layer)) {
                    map.removeLayer(layer);
                }
            } catch(e) {}

            var Toggle = L.Control.extend({
                options: { position: "topright" },
                onAdd: function(map) {
                    var container = L.DomUtil.create(
                        "div",
                        "leaflet-control leaflet-bar solar-cadastral-toggle"
                    );
                    var button = L.DomUtil.create("button", "", container);
                    button.type = "button";
                    button.title = "지적도 켜기 / 끄기";
                    button.style.cssText =
                        "border:0;padding:6px 8px;" +
                        "font-size:12px;font-weight:700;" +
                        "cursor:pointer;white-space:nowrap;" +
                        "height:32px;min-width:76px;";

                    L.DomEvent.disableClickPropagation(container);
                    L.DomEvent.disableScrollPropagation(container);

                    L.DomEvent.on(button, "click", function(e) {
                        L.DomEvent.stop(e);
                        try {
                            if (map.hasLayer(layer)) {
                                map.removeLayer(layer);
                                saveState(false);
                            } else {
                                map.addLayer(layer);
                                saveState(true);
                            }
                            refresh(button);
                        } catch(err) {}
                    });

                    refresh(button);
                    return container;
                }
            });

            if (!map.__solarCadastralControlAdded) {
                map.__solarCadastralControlAdded = true;
                map.addControl(new Toggle());
            }
        })();
        {% endmacro %}
        """
    )
    def __init__(self, layer_name, storage_key):
        super().__init__()
        self._name = "CadastralToggle"
        self.layer_name = layer_name
        self.storage_key = storage_key


class MapViewPersistence(MacroElement):
    _template = Template(
        r"""
        {% macro script(this, kwargs) %}
        (function() {
            var map = {{ this._parent.get_name() }};
            var storageKey = {{ this.storage_key | tojson }};

            if (!map || !storageKey) return;

            function restore() {
                try {
                    var raw = window.localStorage.getItem(storageKey);
                    if (!raw) return;
                    var saved = JSON.parse(raw);
                    if (
                        saved &&
                        Array.isArray(saved.center) &&
                        saved.center.length === 2 &&
                        typeof saved.zoom === "number"
                    ) {
                        map.setView(
                            [parseFloat(saved.center[0]), parseFloat(saved.center[1])],
                            saved.zoom,
                            { animate: false }
                        );
                    }
                } catch(e) {}
            }

            function save() {
                try {
                    var center = map.getCenter();
                    window.localStorage.setItem(
                        storageKey,
                        JSON.stringify({
                            center: [center.lat, center.lng],
                            zoom: map.getZoom()
                        })
                    );
                } catch(e) {}
            }

            if (map.__solarPersistHandler) {
                try {
                    map.off("moveend", map.__solarPersistHandler);
                    map.off("zoomend", map.__solarPersistHandler);
                } catch(e) {}
            }

            map.__solarPersistHandler = save;
            map.on("moveend", save);
            map.on("zoomend", save);

            setTimeout(restore, 50);
            setTimeout(restore, 250);
        })();
        {% endmacro %}
        """
    )
    def __init__(self, storage_key):
        super().__init__()
        self._name = "MapViewPersistence"
        self.storage_key = storage_key

# ============================================================
# Region UI
# ============================================================

st.markdown('<div class="section-title">타겟 지역 및 조건 설정</div>', unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)

sido_options = list(REGION_DATA.keys())
sido_default = sido_options.index("부산광역시") if "부산광역시" in sido_options else 0

with col1:
    sido = st.selectbox("시/도", sido_options, index=sido_default)

sigungu_options = list(REGION_DATA[sido].keys())
sigungu_default = sigungu_options.index("해운대구") if (sido == "부산광역시" and "해운대구" in sigungu_options) else 0

with col2:
    sigungu = st.selectbox("시/군/구", sigungu_options, index=sigungu_default)

dong_options = REGION_DATA[sido][sigungu]
dong_default = dong_options.index("좌동") if (sido == "부산광역시" and sigungu == "해운대구" and "좌동" in dong_options) else 0

with col3:
    dong = st.selectbox("읍/면/동", dong_options, index=dong_default)

min_area = st.number_input("최소 건축면적 (㎡)", min_value=100, value=5000, step=500)
update_db = st.checkbox("🔄 공공데이터 재조회 및 신규 타겟 추가", value=False, help="기존 영업이력은 유지하고 새롭게 발견된 타겟만 추가합니다.")
target_tab_name = f"target_{sido}_{sigungu}_{dong}"

if st.button("데이터 조회 및 지도 적용", use_container_width=True, type="primary"):
    if not require_api_keys():
        st.stop()
    try:
        with st.spinner("Google Sheets 기존 DB 확인 중..."):
            existing = load_target_data(target_tab_name)
            
        st.session_state.current_tab = target_tab_name
        center = geocode_address(f"{sido} {sigungu} {dong}")
        if not center:
            st.error("선택한 지역의 지도 좌표를 찾지 못했습니다.")
            st.stop()
            
        st.session_state.search_center = [center["lat"], center["lng"]]
        st.session_state.last_map_center = [center["lat"], center["lng"]]
        st.session_state.map_zoom = 15
        st.session_state.last_map_zoom = 15
        st.session_state.selected_site_id = None
        st.session_state.selected_addr = None
        st.session_state.new_pin_coord = None
        st.session_state.last_handled_map_click = None
        st.session_state.last_marker_click_count = None
        
        if not existing.empty and not update_db:
            st.session_state.target_data = existing
            st.session_state.last_loaded_tab = target_tab_name
            st.success(f"기존 DB {len(existing):,}건을 불러왔습니다.")
        else:
            message = "최초 타겟 DB를 구축합니다." if existing.empty else "공공데이터를 재조회하여 신규 타겟만 추가합니다."
            with st.spinner(message):
                built, center, added_count = build_target_df(sido, sigungu, dong, min_area, existing)
                
            if added_count > 0:
                new_rows = built.tail(added_count).copy()
                append_target_rows(target_tab_name, new_rows)
                st.session_state.target_data = built
                st.session_state.last_loaded_tab = target_tab_name
                st.success(f"신규 타겟 {added_count:,}건 추가 완료. 총 {len(built):,}건.")
            else:
                st.session_state.target_data = existing
                st.session_state.last_loaded_tab = target_tab_name
                st.info("새롭게 추가되는 타겟이 없습니다. 기존 영업 데이터는 그대로 유지됩니다.")
                
    except Exception as exc:
        st.error("조회 또는 저장 과정에서 오류가 발생했습니다.")
        st.exception(exc)

# ============================================================
# Map
# ============================================================

current_tab_for_map = st.session_state.current_tab or target_tab_name
zoom_storage_key = f"solar_mkt_view::{current_tab_for_map}"
cadastral_storage_key = f"solar_mkt_cadastral::{current_tab_for_map}"

st.divider()
st.markdown('<div class="helper-text">안내: 지도 빈 공간을 클릭하면 신규 현장을 등록할 수 있습니다.</div>', unsafe_allow_html=True)

with st.expander("지도안내"):
    st.markdown(
        """
        <div style="font-size:13px;color:#374151;">
        <b>📌 핀 색상</b><br>
        <span style="color:red;">●</span> 미컨택 &nbsp;
        <span style="color:orange;">●</span> 거절/보류 &nbsp;
        <span style="color:blue;">●</span> 협의중 &nbsp;
        <span style="color:lightgreen;">●</span> 승낙서수령 &nbsp;
        <span style="color:green;">●</span> 계약완료 &nbsp;
        <span style="color:gray;">●</span> 기설치<br>
        <span style="color:purple;font-size:16px;">★</span> 현재 선택된 타겟
        </div>
        """,
        unsafe_allow_html=True,
    )

map_center = st.session_state.last_map_center or st.session_state.search_center or [35.1695, 129.1760]
map_zoom = st.session_state.last_map_zoom or st.session_state.map_zoom or 15

m = folium.Map(
    location=map_center,
    zoom_start=int(map_zoom),
    max_zoom=19,
    min_zoom=1,
    tiles=None,
    control_scale=True,
)

folium.TileLayer(
    tiles="https://xdworld.vworld.kr/2d/Satellite/service/{z}/{x}/{y}.jpeg",
    attr="VWorld",
    name="위성지도",
    max_zoom=19,
    max_native_zoom=18,
    overlay=False,
    control=False,
    show=True,
).add_to(m)

wms_query = urllib.parse.urlencode({
    "key": VWORLD_KEY,
    "domain": VWORLD_DOMAIN,
})

wms_url = f"https://api.vworld.kr/req/wms?{wms_query}"

cadastral_layer = folium.WmsTileLayer(
    url=wms_url,
    layers="lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun",
    styles="lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun",
    fmt="image/png",
    transparent=True,
    version="1.3.0",
    attr="VWorld Cadastral",
    name="지적도(지번경계)",
    overlay=True,
    control=False,
    opacity=0.6,
    show=False,
)

cadastral_layer.add_to(m)
CadastralToggle(cadastral_layer.get_name(), cadastral_storage_key).add_to(m)
MapViewPersistence(zoom_storage_key).add_to(m)

LocateControl(
    position="topleft",
    strings={"title": "내 위치 확인", "popup": "현재 위치"},
    drawCircle=True,
    showPopup=False,
    keepCurrentZoomLevel=True,
    setView=False,
).add_to(m)

m.add_child(MeasureControl(position="topright", primary_length_unit="meters", primary_area_unit="sqmeters"))

m.get_root().html.add_child(folium.Element("""
<div style="position:absolute;top:120px;left:11px;z-index:1000;
     background:rgba(255,255,255,.92);padding:4px;border-radius:6px;
     border:2px solid rgba(0,0,0,.2);box-shadow:0 1px 4px rgba(0,0,0,.3);
     width:32px;height:32px;display:flex;flex-direction:column;
     align-items:center;justify-content:center;pointer-events:none;">
    <div style="font-size:10px;font-weight:900;color:#ef4444;line-height:1;">N</div>
    <div style="font-size:13px;font-weight:900;line-height:1;">▲</div>
</div>
"""))

m.get_root().header.add_child(folium.Element("""
<style>
.leaflet-control-measure .coordinatetracker { display:none!important; }
.leaflet-control-measure h3, .leaflet-control-measure .prompt { font-size:0!important; }
.leaflet-control-measure h3::after {
    content:'지붕 면적 실측'; font-size:13px!important; font-weight:600;
    display:block; margin-bottom:5px; color:#374151;
}
.leaflet-control-measure .prompt::after {
    content:'지붕 모서리를 따라 점을 지정하세요 (완료: 더블클릭)';
    font-size:11px!important; display:block; color:#6b7280;
}
</style>
"""))

# ============================================================
# Data
# ============================================================

df_all = normalize_df(st.session_state.target_data)
st.session_state.target_data = df_all

if not df_all.empty:
    df_filtered = df_all[df_all["면적"] >= float(min_area)].copy()
else:
    df_filtered = df_all.copy()

marker_count = 0
coord_missing_count = 0

for _, row in df_filtered.iterrows():
    lat = safe_float(row.get("lat"), 0)
    lng = safe_float(row.get("lng"), 0)
    if lat == 0 or lng == 0:
        coord_missing_count += 1
        continue
        
    site_id = str(row.get("site_id", ""))
    selected = (st.session_state.selected_site_id == site_id)
    status = str(row.get("상태", "미컨택"))
    color = "purple" if selected else STATUS_COLORS.get(status, "red")
    icon = "star" if (selected or bool(row.get("수동등록", False))) else "info-sign"
    
    name = html.escape(str(row.get("상호명", "")) or "상호명 미상")
    addr = html.escape(str(row.get("지번주소", "")))
    safe_site_id = html.escape(site_id)
    
    popup_html = f"""
    <div style="font-size:13px;line-height:1.6;">
        <b>{name}</b><br>
        현장ID: {safe_site_id}<br>
        {addr}<br>
        면적: {safe_float(row.get("면적")):,.1f}㎡<br>
        상태: {html.escape(status)}
    </div>
    """
    
    folium.Marker(
        [lat, lng],
        tooltip=html.unescape(name),
        popup=folium.Popup(popup_html, max_width=320),
        icon=folium.Icon(color=color, icon=icon),
    ).add_to(m)
    marker_count += 1

if st.session_state.new_pin_coord:
    new_coord = st.session_state.new_pin_coord
    folium.Marker(
        [float(new_coord["lat"]), float(new_coord["lng"])],
        tooltip="신규 등록 예정 위치",
        icon=folium.Icon(color="purple", icon="star"),
    ).add_to(m)

st.caption(f"지도 표시 대상 {len(df_filtered):,}건 · 실제 핀 {marker_count:,}개 · 좌표 없음 {coord_missing_count:,}개")

# ============================================================
# Render Map
# ============================================================

map_data = st_folium(
    m,
    width="100%",
    height=450,
    returned_objects=["last_object_clicked", "last_object_clicked_popup", "last_object_clicked_tooltip", "last_clicked"],
    key=f"solar_mkt_map__{current_tab_for_map}",
)

# ============================================================
# Marker Click
# ============================================================

clicked_marker = map_data.get("last_object_clicked") if map_data else None
clicked_popup = map_data.get("last_object_clicked_popup") if map_data else None
marker_site_id = None

if clicked_popup:
    match = re.search(r"SITE-\d+", str(clicked_popup))
    if match:
        marker_site_id = match.group(0)

marker_click_signature = None
if clicked_marker and marker_site_id:
    marker_click_signature = f"{marker_site_id}::{clicked_marker.get('lat', '')}::{clicked_marker.get('lng', '')}"

if marker_site_id and marker_click_signature and marker_click_signature != st.session_state.last_marker_click_count:
    st.session_state.last_marker_click_count = marker_click_signature
    matched = df_all[df_all["site_id"].astype(str) == marker_site_id]
    
    if not matched.empty:
        row = matched.iloc[0]
        current_zoom = st.session_state.last_map_zoom or map_zoom or 15
        st.session_state.last_map_center = [safe_float(row["lat"]), safe_float(row["lng"])]
        st.session_state.last_map_zoom = int(current_zoom)
        st.session_state.selected_site_id = marker_site_id
        st.session_state.selected_addr = row["지번주소"]
        st.session_state.new_pin_coord = None
        st.rerun()

# ============================================================
# Empty Map Click
# ============================================================

clicked_map = map_data.get("last_clicked") if map_data else None

if clicked_map and not marker_site_id:
    try:
        lat = float(clicked_map["lat"])
        lng = float(clicked_map["lng"])
        click_key = (round(lat, 7), round(lng, 7))
        
        if st.session_state.last_handled_map_click != click_key:
            st.session_state.last_handled_map_click = click_key
            st.session_state.new_pin_coord = {"lat": lat, "lng": lng}
            st.session_state.selected_site_id = None
            st.session_state.selected_addr = None
            current_zoom = st.session_state.last_map_zoom or map_zoom or 15
            st.session_state.last_map_center = [lat, lng]
            st.session_state.last_map_zoom = int(current_zoom)
            st.rerun()
    except Exception:
        pass

# ============================================================
# Selected CRM
# ============================================================

selected_comp = None
if st.session_state.selected_site_id:
    matched = df_all[df_all["site_id"].astype(str) == str(st.session_state.selected_site_id)]
    if not matched.empty:
        selected_comp = matched.iloc[0]
    else:
        st.session_state.selected_site_id = None
        st.session_state.selected_addr = None

# ============================================================
# Edit Existing Target
# ============================================================

if selected_comp is not None:
    comp = selected_comp
    st.markdown("<br>", unsafe_allow_html=True)
    display_name = str(comp.get("상호명", "")) or "상호명 미상"
    st.markdown(f"**{html.escape(display_name)}** · {safe_float(comp.get('면적')):,.1f}㎡")
    st.caption(f"현장ID: {comp['site_id']} | 최초 등록: {comp.get('등록일시', '-')} | 최근 수정: {comp.get('수정일시', '-')}")
    st.code(str(comp.get("지번주소", "")), language="text")
    
    encoded_addr = urllib.parse.quote(str(comp.get("지번주소", "")))
    c1, c2, c3 = st.columns(3)
    c1.link_button("네이버지도", f"https://map.naver.com/p/search/{encoded_addr}", use_container_width=True)
    c2.link_button("카카오맵", f"https://map.kakao.com/link/search/{encoded_addr}", use_container_width=True)
    c3.link_button("티맵(App)", f"tmap://search?name={encoded_addr}", use_container_width=True)
    st.divider()
    
    with st.form(key=f"edit_form_{comp['site_id']}"):
        edited_name = st.text_input("상호명 (간판 기준)", value=str(comp.get("상호명", "")))
        edited_area = st.number_input("지붕 실측 면적(㎡)", min_value=0.0, value=safe_float(comp.get("면적", 0)), step=50.0)
        is_installed = st.checkbox("태양광 기설치 완료 (또는 불가 현장)", value=(str(comp.get("상태", "")) == "기설치"))
        
        current_method = str(comp.get("컨택방식", "미진행"))
        method_idx = METHOD_OPTIONS.index(current_method) if current_method in METHOD_OPTIONS else METHOD_OPTIONS.index("기타")
        selected_contact = st.radio("컨택방식", METHOD_OPTIONS, index=method_idx, horizontal=True)
        custom_method = st.text_input("기타 컨택방식", value=(current_method if current_method not in METHOD_OPTIONS else ""), placeholder="예: 우편, 지인 소개 등")
        
        current_status = str(comp.get("상태", "미컨택"))
        status_idx = STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0
        chosen_status = st.radio("영업 상세 단계", STATUS_OPTIONS, index=status_idx, horizontal=True)
        memo = st.text_area("현장 특이사항 및 미팅 노트", value=str(comp.get("메모", "")))
        
        submitted = st.form_submit_button("변경사항 저장", use_container_width=True, type="primary")
        
        if submitted:
            final_method = custom_method.strip() if (selected_contact == "기타" and custom_method.strip()) else selected_contact
            final_status = "기설치" if is_installed else chosen_status
            
            before = comp.to_dict()
            after = comp.to_dict()
            after.update({
                "상호명": edited_name.strip(),
                "면적": float(edited_area),
                "컨택방식": final_method,
                "상태": final_status,
                "수정일시": now_str(),
                "메모": memo,
            })
            
            changes = []
            for label, key in [("상태", "상태"), ("방식", "컨택방식"), ("면적", "면적"), ("상호명", "상호명")]:
                if str(before.get(key, "")) != str(after.get(key, "")):
                    changes.append(f"{label}({before.get(key, '')}→{after.get(key, '')})")
                    
            if str(before.get("메모", "")).strip() != str(after.get("메모", "")).strip():
                changes.append("메모수정")
                
            after["최근수정내역"] = " | ".join(changes) if changes else "단순열람(수정없음)"
            
            try:
                update_target_row(st.session_state.current_tab, str(comp["site_id"]), after)
                try:
                    append_activity(comp["site_id"], st.session_state.current_tab, before, after, "수정")
                except Exception as activity_exc:
                    st.warning("현장 데이터는 Google Sheets에 저장되었지만 영업일지 저장에는 실패했습니다.")
                    st.caption(str(activity_exc))
                    
                updated = df_all.copy()
                mask = (updated["site_id"].astype(str) == str(comp["site_id"]))
                for key, value in after.items():
                    if key in updated.columns:
                        updated.loc[mask, key] = value
                        
                updated = normalize_df(updated)
                st.session_state.target_data = updated
                st.session_state.save_success = True
                st.rerun()
                
            except Exception as exc:
                st.error("❌ 저장되지 않았습니다. Google Sheets에 변경사항을 반영하지 못했습니다.")
                st.exception(exc)

# ============================================================
# New Pin Registration
# ============================================================

elif st.session_state.new_pin_coord:
    new_lat = float(st.session_state.new_pin_coord["lat"])
    new_lng = float(st.session_state.new_pin_coord["lng"])
    st.info("선택하신 위치에 신규 타겟을 등록합니다.")
    auto_address, auto_name = get_place_info_from_coords(new_lat, new_lng)
    
    with st.form("new_pin_form", clear_on_submit=False):
        new_addr = st.text_input("지번 주소", value=auto_address)
        new_name = st.text_input("상호명", value=auto_name)
        new_area = st.number_input("예상 지붕 면적(㎡)", min_value=0.0, value=float(min_area), step=100.0)
        new_pin_submit = st.form_submit_button("신규 현장 등록", use_container_width=True, type="primary")
        
        if new_pin_submit:
            normalized_new_address = address_key(new_addr)
            duplicate = pd.DataFrame()
            
            if normalized_new_address and not df_all.empty:
                duplicate = df_all[df_all["지번주소"].astype(str).map(address_key) == normalized_new_address]
                
            if not duplicate.empty:
                existing_site_id = str(duplicate.iloc[0]["site_id"])
                st.warning(f"이미 등록된 주소입니다. 현장ID: {existing_site_id}")
                st.session_state.selected_site_id = existing_site_id
                st.session_state.selected_addr = duplicate.iloc[0]["지번주소"]
                st.session_state.new_pin_coord = None
                st.rerun()
                
            coordinate_duplicate = None
            if not df_all.empty:
                for _, existing_row in df_all.iterrows():
                    existing_lat = safe_float(existing_row.get("lat", 0))
                    existing_lng = safe_float(existing_row.get("lng", 0))
                    if existing_lat == 0 or existing_lng == 0:
                        continue
                    distance = coordinate_distance_meters(new_lat, new_lng, existing_lat, existing_lng)
                    if distance <= 20:
                        coordinate_duplicate = existing_row
                        break
                        
            if coordinate_duplicate is not None:
                existing_site_id = str(coordinate_duplicate["site_id"])
                st.warning(f"약 20m 이내에 기존 현장이 존재합니다. 현장ID: {existing_site_id}")
                st.session_state.selected_site_id = existing_site_id
                st.session_state.selected_addr = coordinate_duplicate["지번주소"]
                st.session_state.new_pin_coord = None
                st.rerun()
                
            sid = new_site_id(df_all)
            stamp = now_str()
            new_row = {
                "site_id": sid,
                "상호명": new_name.strip(),
                "지번주소": new_addr.strip(),
                "면적": float(new_area),
                "lat": new_lat,
                "lng": new_lng,
                "상태": "미컨택",
                "컨택방식": "미진행",
                "등록일시": stamp,
                "수정일시": stamp,
                "수동등록": True,
                "메모": "",
                "최근수정내역": "신규 현장 발굴 및 등록",
            }
            
            new_row_df = normalize_df(pd.DataFrame([new_row]))
            
            try:
                append_target_rows(st.session_state.current_tab, new_row_df)
                try:
                    append_activity(sid, st.session_state.current_tab, {}, new_row, "신규등록")
                except Exception as activity_exc:
                    st.warning("신규 현장은 저장되었지만 영업일지 저장에 실패했습니다.")
                    st.caption(str(activity_exc))
                    
                updated = pd.concat([df_all, new_row_df], ignore_index=True)
                st.session_state.target_data = normalize_df(updated)
                st.session_state.selected_site_id = sid
                st.session_state.selected_addr = new_addr.strip()
                st.session_state.new_pin_coord = None
                st.session_state.save_success = True
                st.rerun()
                
            except Exception as exc:
                st.error("❌ 신규 현장이 저장되지 않았습니다. Google Sheets 저장에 실패했습니다.")
                st.exception(exc)

# ============================================================
# Activity Log
# ============================================================

st.divider()
st.markdown('<div class="section-title">일자별 영업일지</div>', unsafe_allow_html=True)

selected_date = st.date_input("조회 일자 선택", value=datetime.today())
date_str = selected_date.strftime("%Y-%m-%d")

try:
    activity = load_activity_log()
except Exception as exc:
    activity = pd.DataFrame(columns=ACTIVITY_HEADERS)
    st.warning("Google Sheets 영업일지를 불러오지 못했습니다.")
    st.caption(str(exc))
    
if not activity.empty:
    activity = activity.loc[:, ~activity.columns.duplicated()].copy()
    
if not activity.empty and "기록일시" in activity.columns:
    activity["기록일시"] = activity["기록일시"].fillna("").astype(str)
    daily = activity[activity["기록일시"].str.startswith(date_str)].copy()
    daily = daily.sort_values("기록일시")
    
    if daily.empty:
        st.info(f"{date_str} 기준 영업 이력이 없습니다.")
    else:
        st.success(f"조회 결과: 총 {len(daily):,}건의 활동이 있습니다.")
        for _, row in daily.iloc[::-1].iterrows():
            title = html.escape(str(row.get("상호명", "")) or "상호명 미상")
            addr = html.escape(str(row.get("지번주소", "")))
            changes = html.escape(str(row.get("변경내역", "")))
            memo = html.escape(str(row.get("메모", "")))
            
            st.markdown(f"**{title}** ({html.escape(str(row.get('상태', '')))})")
            st.caption(f"{addr} | 접촉: {row.get('접촉방식', '')} | 시간: {row.get('기록일시', '')} | {row.get('site_id', '')}")
            
            if changes:
                st.markdown(f"<div style='font-size:13px;color:#ea580c;font-weight:600;'>🔄 {changes}</div>", unsafe_allow_html=True)
            if memo:
                st.markdown(f"<div style='background:#f3f4f6;padding:10px;border-radius:6px;font-size:13px;color:#4b5563;margin-top:5px;'>{memo}</div>", unsafe_allow_html=True)
            st.markdown("<hr style='margin:15px 0;border-top:1px solid #e5e7eb;'>", unsafe_allow_html=True)
else:
    st.info("아직 누적 영업활동 이력이 없습니다. 현장을 수정/등록하면 Google Sheets에 쌓입니다.")

# ============================================================
# Status
# ============================================================

if sheets_enabled():
    st.caption(f"저장 모드: Google Sheets ONLY | 현재 지역: {sido} {sigungu} {dong}")
else:
    st.error("⚠️ Google Sheets 연결이 없습니다. 데이터는 저장되지 않습니다.")
