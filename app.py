import os

import html

import time

import math

import urllib.parse

from datetime import datetime


 

import pandas as pd

import requests

import streamlit as st

import folium


 

from branca.element import MacroElement

from jinja2 import Template

from folium.plugins import MeasureControl, LocateControl, MarkerCluster

from streamlit_folium import st_folium


 

# ============================================================

# Solar Mkt Map - Final Production Build (v5-final)

# 공지사항 10개 원칙 100% 준수:

# 1. CSV fallback: Sheets 미설정 시에만, 실패 시 명확한 실패 표시

# 2. 기존 UI/지도 기능 100% 보존

# 3. 마커 선택: coord_key (소수점 6자리) 기반, fuzzy 금지

# 4. 신규 핀: 20m 이내 → 기존 선택, 20m 밖 → 신규

# 5. 주소 중복: normalize_address 정규화

# 6. 5,000㎡ 기준: 지번별 합산, 사용자 수정 면적 덮어쓰기 금지

# 7. Google Sheets: 행 단위 수정 (ws.clear() 금지)

# 8. API 안정성: Kakao 0.05초 delay + 429 retry, 공공데이터 500페이지/5만건

# 9. 모바일 UX: selectbox 키보드 방지

# 10. 기능 보존 우선

# ============================================================


 

st.set_page_config(page_title="Solar Mkt Map", layout="centered")


 


 

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

    https://port-0-solarmap-mtatayuj7b3bb02b.sel3.cloudtype.app,

)

GOOGLE_SHEET_ID = secret("spreadsheet_id")


 

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

    "site_id", "상호명", "지번주소", "상태", "컨택방식",

    "등록일시", "수정일시", "메모", "최근수정내역",

]

NUM_COLS = ["면적", "lat", "lng"]

BOOL_COLS = ["수동등록"]

TARGET_COLS = TEXT_COLS + NUM_COLS + BOOL_COLS


 

STATUS_OPTIONS = ["미컨택", "거절/보류", "협의중", "승낙서수령", "계약완료", "기설치"]

METHOD_OPTIONS = ["미진행", "전화", "이메일", "방문", "기타"]


 

STATUS_COLORS = {

    "미컨택": "red", "거절/보류": "orange", "협의중": "blue",

    "승낙서수령": "lightgreen", "계약완료": "green", "기설치": "gray",

}


 

ACTIVITY_HEADERS = [

    "기록일시", "site_id", "지역탭", "상호명", "지번주소",

    "접촉방식", "상태", "면적", "메모", "변경내역", "행동",

]


 


 

# ============================================================

# Region Data (원본 유지)

# ============================================================

REGION_DATA = {

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

        "해운대구": ["우동", "중동", "좌동", "송정동", "반여동", "반송동", "재송동"],

    },

    "울산광역시": {

        "남구": ["신정동", "달동", "삼산동", "무거동", "옥동", "야음동", "장생포동", "선암동", "매암동", "여천동", "용잠동", "용연동", "황성동", "고사동", "성암동"],

        "동구": ["방어동", "일산동", "전하동", "남목동", "화정동", "미포동"],

        "북구": ["농소동", "강동동", "효문동", "송정동", "양정동", "염포동", "명촌동", "연암동", "매곡동", "중산동"],

        "울주군": ["온산읍", "언양읍", "온양읍", "범서읍", "서생면", "청량읍", "웅촌면", "두동면", "두서면", "상북면", "삼남읍", "삼동면"],

        "중구": ["학성동", "반구동", "복산동", "성안동", "중앙동", "우정동", "태화동", "다운동", "병영동", "약사동"],

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

        "합천군": ["합천읍", "봉산면", "묘산면", "가야면", "야로면", "율곡면", "초계면", "쌍책면", "덕곡면", "청덕면", "적중면", "대양면", "쌍백면", "삼가면", "가회면", "대병면", "용주면"],

        "의령군": ["의령읍", "가례면", "칠곡면", "대의면", "화정면", "용덕면", "정곡면", "지정면", "낙서면", "부림면", "봉수면", "궁류면", "유곡면"],

        "남해군": ["남해읍", "이동면", "상주면", "삼동면", "미조면", "남면", "서면", "고현면", "설천면", "창선면"],

        "산청군": ["산청읍", "차황면", "오부면", "생초면", "금서면", "삼장면", "시천면", "단성면", "신안면", "생비량면", "신등면"],

        "함양군": ["함양읍", "마천면", "휴천면", "유림면", "수동면", "지곡면", "안의면", "서하면", "서상면", "백전면", "병곡면"],

        "거창군": ["거창읍", "주상면", "웅양면", "고제면", "북상면", "위천면", "마리면", "남상면", "남하면", "신원면", "가조면", "가북면"],

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

        "영주시": ["풍기읍", "이산면", "평은면", "문수면", "장수면", "안정면", "봉현면", "순흥면", "단산면", "부석면", "상망동", "하망동", "영주1동", "영주2동", "휴천동", "가흥1동", "가흥2동"],

        "상주시": ["함창읍", "중동면", "사벌국면", "낙동면", "청리면", "공성면", "외남면", "내서면", "모동면", "모서면", "화동면", "화서면", "화북면", "외서면", "은척면", "공검면", "이안면", "화남면", "남원동", "북문동", "계림동", "동문동", "동성동", "신흥동"],

        "문경시": ["문경읍", "가은읍", "영순면", "산양면", "호계면", "산북면", "동로면", "마성면", "농암면", "점촌1동", "점촌2동", "점촌3동", "점촌4동", "점촌5동"],

        "의성군": ["의성읍", "단촌면", "점곡면", "옥산면", "사곡면", "춘산면", "가음면", "금성면", "봉양면", "비안면", "구천면", "단밀면", "단북면", "안계면", "다인면", "신평면", "안평면", "안사면"],

        "청송군": ["청송읍", "주왕산면", "부남면", "현동면", "현서면", "안덕면", "파천면", "진보면"],

        "영양군": ["영양읍", "입암면", "청기면", "일월면", "수비면", "석보면"],

        "영덕군": ["영덕읍", "강구면", "남정면", "달산면", "지품면", "축산면", "영해면", "병곡면", "창수면"],

        "청도군": ["청도읍", "화양읍", "각남면", "풍각면", "각북면", "이서면", "운문면", "금천면", "매전면"],

        "예천군": ["예천읍", "용문면", "감천면", "보문면", "호명면", "유천면", "용궁면", "개포면", "지보면", "풍양면", "효자면", "은풍면"],

        "봉화군": ["봉화읍", "물야면", "봉성면", "법전면", "춘양면", "소천면", "재산면", "명호면", "상운면", "석포면"],

        "울진군": ["울진읍", "평해읍", "북면", "금강송면", "근남면", "매화면", "기성면", "온정면", "죽변면", "후포면"],

        "울릉군": ["울릉읍", "서면", "북면"],

        "칠곡군": ["왜관읍", "북삼읍", "석적읍", "지천면", "동명면", "가산면", "약목면", "기산면"],

        "성주군": ["성주읍", "선남면", "용암면", "수륜면", "가천면", "금수면", "대가면", "벽진면", "초전면", "월항면"],

        "고령군": ["대가야읍", "덕곡면", "운수면", "성산면", "다산면", "개진면", "우곡면", "쌍림면"],

    },

}


 


 

# ============================================================

# Session State

# ============================================================

def init_state():

    defaults = {

        "target_data": pd.DataFrame(columns=TARGET_COLS),

        "search_center": [35.1695, 129.1760],  # 해운대구 좌동

        "map_zoom": 15,

        "current_tab": "",

        "selected_site_id": None,

        "selected_addr": None,

        "new_pin_coord": None,

        "save_success": False,

        "last_loaded_tab": "",

        "activity_status": "",

        "activity_rows_session": [],

        "last_click_hash": "",  # 클릭 이벤트 debounce

    }

    for key, value in defaults.items():

        if key not in st.session_state:

            st.session_state[key] = value


 


 

init_state()


 


 

# ============================================================

# HTTP Session

# ============================================================

if "http_session" not in st.session_state:

    _session = requests.Session()

    _adapter = requests.adapters.HTTPAdapter(

        pool_connections=20, pool_maxsize=20, max_retries=0,

    )

    _session.mount(http://, _adapter)

    _session.mount(https://, _adapter)

    st.session_state.http_session = _session


 

HTTP_SESSION = st.session_state.http_session


 


 

# ============================================================

# Styling

# ============================================================

st.markdown("""

<style>

.stApp { background-color: #f9fafb; }

div[data-testid="stForm"] {

    border:1px solid #e5e7eb; border-radius:12px;

    padding:24px; background:#fff;

    box-shadow:0 1px 2px rgba(0,0,0,.05);

}

.main-header {

    padding:1.5rem 0 1rem;

    border-bottom:1px solid #e5e7eb;

    margin-bottom:2rem;

}

.main-header h2 {

    margin:0; color:#111827;

    font-size:1.6rem; font-weight:800;

    letter-spacing:-.5px;

}

.section-title {

    font-size:1.05rem; font-weight:600;

    color:#374151; margin-bottom:1rem;

    padding-bottom:.5rem;

    border-bottom:1px solid #e5e7eb;

}

.helper-text {

    font-size:13px; color:#6b7280;

    margin-bottom:8px;

}

</style>

""", unsafe_allow_html=True)


 

if st.session_state.save_success:

    st.toast("✅ 저장되었습니다.")

    st.session_state.save_success = False


 

st.markdown(

    '<div class="main-header"><h2>Solar Mkt Map ☀️</h2></div>',

    unsafe_allow_html=True,

)


 


 

# ============================================================

# Helpers

# ============================================================

def now_str() -> str:

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


 


 

def normalize_address(value) -> str:

    """공지 5: 주소 정규화 (123-1, 123-1번지, 123 - 1 등을 동일 취급)"""

    text = "" if value is None else str(value)

    text = text.strip().lower()

    text = text.replace("번지", "")

    text = text.replace("\u00a0", "")  # non-breaking space

    text = "".join(text.split())

    return text


 


 

def coord_key(lat, lng) -> str:

    """공지 3: 소수점 6자리 정밀 매칭용"""

    try:

        return f"{float(lat):.6f}|{float(lng):.6f}"

    except Exception:

        return ""


 


 

def haversine_m(lat1, lon1, lat2, lon2) -> float:

    try:

        lat1, lon1 = float(lat1), float(lon1)

        lat2, lon2 = float(lat2), float(lon2)

    except Exception:

        return float("inf")

    r = 6371000.0

    p1, p2 = math.radians(lat1), math.radians(lat2)

    dp = math.radians(lat2 - lat1)

    dl = math.radians(lon2 - lon1)

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2

    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


 


 

def new_site_id(df: pd.DataFrame) -> str:

    if df is None or df.empty or "site_id" not in df.columns:

        return "SITE-000001"

    ids = df["site_id"].astype(str)

    nums = pd.to_numeric(

        ids.str.extract(r"SITE-(\d+)")[0], errors="coerce",

    ).dropna()

    n = int(nums.max()) + 1 if not nums.empty else len(df) + 1

    used = set(ids)

    while f"SITE-{n:06d}" in used:

        n += 1

    return f"SITE-{n:06d}"


 


 

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


 

    legacy_status = {"미개척": "미컨택", "거절": "거절/보류", "진행중": "협의중"}

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

        df[col] = (

            df[col].astype(str)

            .str.replace(",", "", regex=False)

        )

        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)


 

    if "수동등록" not in df.columns:

        df["수동등록"] = False

    df["수동등록"] = (

        df["수동등록"].astype(str).str.lower()

        .isin(["true", "1", "yes", "y", "t"])

    )


 

    # site_id 보정

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


 


 

def require_api_keys() -> bool:

    missing = []

    if not KAKAO_REST_KEY:

        missing.append("KAKAO_REST_KEY")

    if not DATA_GO_KR_KEY:

        missing.append("DATA_GO_KR_KEY")

    if not VWORLD_KEY:

        missing.append("VWORLD_KEY")

    if missing:

        st.error("API 키가 설정되지 않았습니다: " + ", ".join(missing))

        return False

    return True


 


 

# ============================================================

# Google Sheets

# ============================================================

@st.cache_resource(ttl=3600, show_spinner=False)

def get_gspread_client():

    if not GS_AVAILABLE or not GOOGLE_SHEET_ID:

        return None

    try:

        service_info = st.secrets.get("gcp_service_account")

        if not service_info:

            return None

        credentials = Credentials.from_service_account_info(

            dict(service_info),

            scopes=[

                https://www.googleapis.com/auth/spreadsheets,

                https://www.googleapis.com/auth/drive,

            ],

        )

        return gspread.authorize(credentials)

    except Exception:

        return None


 


 

def sheets_enabled() -> bool:

    return get_gspread_client() is not None


 


 

def get_or_create_ws(sh, title, rows=100, cols=30):

    try:

        return sh.worksheet(title)

    except Exception:

        return sh.add_worksheet(

            title=title,

            rows=str(max(rows, 100)),

            cols=str(max(cols, 20)),

        )


 


 

def col_letter(n: int) -> str:

    if n < 1:

        return "A"

    result = ""

    while n > 0:

        n, rem = divmod(n - 1, 26)

        result = chr(65 + rem) + result

    return result


 


 

def _sheet_headers(ws):

    """헤더가 없으면 TARGET_COLS로 초기화, 있으면 부족한 컬럼만 추가"""

    headers = ws.row_values(1)

    if not headers or all(not h for h in headers):

        headers = list(TARGET_COLS)

        ws.update(

            values=[headers],

            range_name=f"A1:{col_letter(len(headers))}1",

            value_input_option="USER_ENTERED",

        )

        return headers


 

    missing = [c for c in TARGET_COLS if c not in headers]

    if missing:

        headers = list(headers) + missing

        ws.update(

            values=[headers],

            range_name=f"A1:{col_letter(len(headers))}1",

            value_input_option="USER_ENTERED",

        )

    return headers


 


 

def _row_values(record, headers):

    """dict → sheet row 변환 (NaN/None 안전 처리)"""

    result = []

    for h in headers:

        val = record.get(h, "")

        try:

            if pd.isna(val):

                val = ""

        except Exception:

            pass

        if isinstance(val, bool):

            val = "TRUE" if val else "FALSE"

        elif isinstance(val, float) and math.isnan(val):

            val = ""

        elif val is None:

            val = ""

        result.append(str(val))

    return result


 


 

@st.cache_data(ttl=30, show_spinner=False)

def load_target_data(tab_name: str) -> pd.DataFrame:

    gc = get_gspread_client()

    if gc:

        try:

            sh = gc.open_by_key(GOOGLE_SHEET_ID)

            ws = get_or_create_ws(sh, tab_name)

            records = ws.get_all_records()

            return (

                normalize_df(pd.DataFrame(records))

                if records

                else pd.DataFrame(columns=TARGET_COLS)

            )

        except Exception as e:

            st.warning(f"Google Sheets 불러오기 실패: {e}")

            return pd.DataFrame(columns=TARGET_COLS)


 

    # CSV fallback (Sheets 미설정 시에만)

    filename = f"{tab_name}.csv"

    if os.path.exists(filename):

        try:

            return normalize_df(pd.read_csv(filename))

        except Exception as e:

            st.error(f"CSV 불러오기 실패: {e}")

    return pd.DataFrame(columns=TARGET_COLS)


 


 

def save_target_data_initial(tab_name: str, df: pd.DataFrame) -> bool:

    """최초 지역 구축 시에만 사용 (신규 워크시트에 데이터 쓰기)"""

    df_save = normalize_df(df)

    gc = get_gspread_client()


 

    if gc:

        try:

            sh = gc.open_by_key(GOOGLE_SHEET_ID)

            ws = get_or_create_ws(

                sh, tab_name,

                rows=max(len(df_save) + 50, 100),

                cols=max(len(TARGET_COLS), 20),

            )

            # 헤더 먼저 확인

            headers = _sheet_headers(ws)


 

            # 데이터 영역만 확인 (헤더 제외)

            all_values = ws.get_all_values()

            data_rows = all_values[1:] if len(all_values) > 1 else []

            has_real_data = any(

                any(cell.strip() for cell in row)

                for row in data_rows

            )


 

            if has_real_data:

                st.error(

                    "기존 Google Sheets 데이터가 있어 전체 덮어쓰기를 차단했습니다. "

                    "행 단위 저장을 사용하세요."

                )

                return False


 

            if not df_save.empty:

                values = [

                    _row_values(r.to_dict(), headers)

                    for _, r in df_save.iterrows()

                ]

                ws.update(

                    values=values,

                    range_name=f"A2:{col_letter(len(headers))}{len(values)+1}",

                    value_input_option="USER_ENTERED",

                )

            load_target_data.clear()

            return True

        except Exception as e:

            st.error(f"Google Sheets 저장 실패: {e}")

            return False


 

    # CSV fallback

    try:

        df_save.to_csv(f"{tab_name}.csv", index=False, encoding="utf-8-sig")

        load_target_data.clear()

        return True

    except Exception as e:

        st.error(f"CSV 저장 실패: {e}")

        return False


 


 

def save_target_row(

    tab_name: str,

    row_dict: dict,

    append_if_missing: bool = False,

) -> bool:

    """공지 7: site_id 기반 단일 행 update/append"""

    row = normalize_df(pd.DataFrame([row_dict])).iloc[0].to_dict()

    gc = get_gspread_client()


 

    if gc:

        try:

            sh = gc.open_by_key(GOOGLE_SHEET_ID)

            ws = get_or_create_ws(

                sh, tab_name,

                rows=100, cols=max(len(TARGET_COLS), 20),

            )

            headers = _sheet_headers(ws)


 

            site_id = str(row.get("site_id", "")).strip()

            if not site_id:

                st.error("저장할 site_id가 없습니다.")

                return False


 

            site_col_idx = headers.index("site_id") + 1  # 1-based


 

            # 직접 순회로 정확 매칭 (버그 #3 수정)

            all_values = ws.get_all_values()

            target_row_num = None

            for row_idx, r in enumerate(all_values[1:], start=2):

                if (

                    site_col_idx - 1 < len(r)

                    and str(r[site_col_idx - 1]).strip() == site_id

                ):

                    target_row_num = row_idx

                    break


 

            values = _row_values(row, headers)


 

            if target_row_num is not None:

                end_letter = col_letter(len(headers))

                ws.update(

                    values=[values],

                    range_name=f"A{target_row_num}:{end_letter}{target_row_num}",

                    value_input_option="USER_ENTERED",

                )

            else:

                if not append_if_missing:

                    st.error(

                        f"Google Sheets에서 {site_id} 행을 찾지 못해 "

                        "저장을 중단했습니다."

                    )

                    return False

                ws.append_row(values, value_input_option="USER_ENTERED")


 

            load_target_data.clear()

            return True

        except Exception as e:

            st.error(f"Google Sheets 행 저장 실패: {e}")

            return False


 

    # CSV fallback (Sheets 미설정 시에만)

    filename = f"{tab_name}.csv"

    try:

        existing = load_target_data(tab_name)

        site_id = str(row.get("site_id", ""))

        if (

            not existing.empty

            and site_id in existing["site_id"].astype(str).values

        ):

            mask = existing["site_id"].astype(str) == site_id

            for key, value in row.items():

                if key in existing.columns:

                    existing.loc[mask, key] = value

        else:

            existing = pd.concat(

                [existing, pd.DataFrame([row])],

                ignore_index=True,

            )

        normalize_df(existing).to_csv(

            filename, index=False, encoding="utf-8-sig",

        )

        load_target_data.clear()

        return True

    except Exception as e:

        st.error(f"CSV 저장 실패: {e}")

        return False


 


 

# ============================================================

# Activity Log

# ============================================================

def activity_row(site_id, tab_name, before, after, action):

    changes = []

    for label, key in [

        ("상태", "상태"), ("방식", "컨택방식"),

        ("면적", "면적"), ("상호명", "상호명"), ("메모", "메모"),

    ]:

        b, a = str(before.get(key, "")), str(after.get(key, ""))

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

        "변경내역": (

            " | ".join(changes) if changes else "단순열람(수정없음)"

        ),

        "행동": action,

    }


 


 

def append_activity(site_id, tab_name, before, after, action) -> bool:

    """공지 1: Sheets 설정된 경우 저장 실패는 명확히 실패로 처리"""

    row = activity_row(site_id, tab_name, before, after, action)


 

    # 세션에 즉시 반영 (Sheets 지연 대응)

    st.session_state.activity_rows_session = (

        [row] + list(st.session_state.get("activity_rows_session", []))

    )


 

    gc = get_gspread_client()

    if gc:

        try:

            sh = gc.open_by_key(GOOGLE_SHEET_ID)

            ws = get_or_create_ws(

                sh, "activity_log",

                rows=1000, cols=len(ACTIVITY_HEADERS),

            )

            existing = ws.get_all_values()

            if not existing:

                ws.update(

                    values=[ACTIVITY_HEADERS],

                    range_name="A1",

                    value_input_option="USER_ENTERED",

                )

                headers = ACTIVITY_HEADERS

            else:

                headers = list(existing[0])

                missing = [c for c in ACTIVITY_HEADERS if c not in headers]

                if missing:

                    headers = headers + missing

                    ws.update(

                        values=[headers],

                        range_name=f"A1:{col_letter(len(headers))}1",

                        value_input_option="USER_ENTERED",

                    )


 

            ws.append_row(

                _row_values(row, headers),

                value_input_option="USER_ENTERED",

            )

            load_activity_log.clear()

            st.session_state.activity_status = "Google Sheets 활동 이력 저장 완료"

            return True

        except Exception as e:

            st.session_state.activity_status = (

                f"Google Sheets 활동 이력 저장 실패: {e}"

            )

            st.warning(

                "활동 이력은 저장되지 않았습니다. "

                "Google Sheets 연결 상태를 확인하세요."

            )

            return False


 

    # CSV fallback (Sheets 미설정 시에만)

    path = "activity_log.csv"

    try:

        old = (

            pd.read_csv(path)

            if os.path.exists(path)

            else pd.DataFrame(columns=ACTIVITY_HEADERS)

        )

        pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(

            path, index=False, encoding="utf-8-sig",

        )

        load_activity_log.clear()

        st.session_state.activity_status = "CSV 활동 이력 저장 완료"

        return True

    except Exception as e:

        st.session_state.activity_status = f"CSV 활동 이력 저장 실패: {e}"

        st.error("활동 이력 저장에 실패했습니다.")

        return False


 


 

@st.cache_data(ttl=10, show_spinner=False)

def load_activity_log() -> pd.DataFrame:

    gc = get_gspread_client()

    if gc:

        try:

            sh = gc.open_by_key(GOOGLE_SHEET_ID)

            ws = get_or_create_ws(

                sh, "activity_log",

                rows=1000, cols=len(ACTIVITY_HEADERS),

            )

            values = ws.get_all_values()

            if values and len(values) > 1:

                headers = values[0]

                rows = values[1:]

                width = len(headers)

                normalized_rows = [

                    (r + [""] * width)[:width] for r in rows

                ]

                return pd.DataFrame(normalized_rows, columns=headers)

        except Exception as e:

            st.session_state.activity_status = (

                f"활동 이력 조회 실패: {e}"

            )


 

    if os.path.exists("activity_log.csv"):

        try:

            return pd.read_csv("activity_log.csv")

        except Exception:

            pass

    return pd.DataFrame()


 


 

# ============================================================

# Kakao API (공지 8: 0.05s delay + 429 retry)

# ============================================================

def kakao_get(path: str, params: dict, timeout: int = 10):

    url = f"https://dapi.kakao.com{path}"

    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}


 

    last_error = None

    for attempt in range(4):

        if attempt > 0:

            time.sleep(min(2 ** attempt, 8))

        try:

            response = HTTP_SESSION.get(

                url, headers=headers, params=params, timeout=timeout,

            )

            if response.status_code == 429:

                last_error = RuntimeError("Kakao API 429 Rate Limit")

                continue

            response.raise_for_status()

            time.sleep(0.05)  # 공지 8

            return response.json()

        except requests.exceptions.RequestException as exc:

            last_error = exc

            if attempt == 3:

                break


 

    raise RuntimeError(f"Kakao API 요청 실패: {last_error}")


 


 

@st.cache_data(ttl=86400, show_spinner=False)

def geocode_address(address: str):

    if not address:

        return None

    try:

        data = kakao_get(

            "/v2/local/search/address.json",

            {"query": address},

        )

        docs = data.get("documents", [])

        if not docs:

            return None

        d = docs[0]

        return {

            "lat": float(d["y"]),

            "lng": float(d["x"]),

            "b_code": d.get("address", {}).get("b_code", ""),

        }

    except Exception:

        return None


 


 

@st.cache_data(ttl=86400, show_spinner=False)

def reverse_geocode(lat: float, lng: float):

    try:

        data = kakao_get(

            "/v2/local/geo/coord2address.json",

            {"x": lng, "y": lat},

        )

        docs = data.get("documents", [])

        if not docs:

            return "직접 입력 필요", ""

        d = docs[0]

        addr = d.get("address") or {}

        road = d.get("road_address") or {}

        name = (

            addr.get("address_name")

            or road.get("address_name")

            or "직접 입력 필요"

        )

        return name, ""

    except Exception:

        return "직접 입력 필요", ""


 


 

@st.cache_data(ttl=86400, show_spinner=False)

def place_name_for_address(address: str):

    if not address:

        return ""

    try:

        data = kakao_get(

            "/v2/local/search/keyword.json",

            {"query": address},

        )

        docs = data.get("documents", [])

        if docs:

            return docs[0].get("place_name", "")

    except Exception:

        pass

    return ""


 


 

def get_place_info_from_coords(lat, lng):

    address_name, _ = reverse_geocode(lat, lng)

    building_name = (

        place_name_for_address(address_name)

        if address_name != "직접 입력 필요"

        else ""

    )

    return address_name, building_name


 


 

# ============================================================

# Public Data (공지 8: 500페이지/5만건 안전장치)

# ============================================================

def fetch_building_targets(sigungu_cd: str, bjdong_cd: str):

    raw = []

    page_no = 1

    total_count = 0

    MAX_PAGES = 500

    MAX_ITEMS = 50000


 

    progress = st.progress(0)

    status_box = st.empty()


 

    service_key = DATA_GO_KR_KEY.strip()

    key_is_encoded = "%" in service_key


 

    urls_to_try = [

        https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo,

        https://apis.data.go.kr/1613000/BldRgstService_2.0/getBrTitleInfo,

    ]


 

    successful_url = None


 

    while page_no <= MAX_PAGES and len(raw) < MAX_ITEMS:


 

        candidate_urls = (

            [successful_url] if successful_url else urls_to_try

        )

        page_success = False

        items = []

        last_error_msg = ""


 

        for url in candidate_urls:

            try:

                if key_is_encoded:

                    request_url = f"{url}?serviceKey={service_key}"

                    params = {

                        "sigunguCd": sigungu_cd,

                        "bjdongCd": bjdong_cd,

                        "numOfRows": 100,

                        "pageNo": page_no,

                        "_type": "json",

                    }

                    r = HTTP_SESSION.get(

                        request_url, params=params, timeout=20,

                    )

                else:

                    params = {

                        "serviceKey": service_key,

                        "sigunguCd": sigungu_cd,

                        "bjdongCd": bjdong_cd,

                        "numOfRows": 100,

                        "pageNo": page_no,

                        "_type": "json",

                    }

                    r = HTTP_SESSION.get(url, params=params, timeout=20)


 

                if r.status_code == 429:

                    time.sleep(1.0)

                    continue


 

                response_text = r.text.strip()


 

                if r.status_code >= 400:

                    last_error_msg = (

                        f"HTTP {r.status_code} @ "

                        f"{url.split('/')[-1]}"

                    )

                    continue


 

                if response_text.startswith("<"):

                    if "SERVICE_KEY_IS_NOT_REGISTERED" in response_text:

                        raise RuntimeError(

                            "❌ 인증키가 등록되지 않았습니다.\n"

                            "공공데이터포털에서 '건축HUB 건축물대장정보 서비스' "

                            "활용 신청 및 승인 여부, 그리고 "

                            "'일반 인증키 (Encoding)' 값을 확인하세요."

                        )

                    if "LIMITED_NUMBER" in response_text:

                        raise RuntimeError("❌ 일일 트래픽 한도 초과")

                    if "NO_OPENAPI_SERVICE" in response_text:

                        last_error_msg = "API 서비스 없음"

                        continue


 

                    last_error_msg = (

                        f"XML 오류: {response_text[:200]}"

                    )

                    continue


 

                try:

                    data = r.json()

                except Exception:

                    last_error_msg = (

                        f"JSON 파싱 실패: {response_text[:200]}"

                    )

                    continue


 

                header = data.get("response", {}).get("header", {})

                result_code = str(header.get("resultCode", "")).strip()

                if result_code and result_code != "00":

                    last_error_msg = (

                        header.get("resultMsg", f"resultCode={result_code}")

                    )

                    continue


 

                body = data.get("response", {}).get("body", {})

                total_count = int(body.get("totalCount", 0) or 0)

                items = body.get("items", {}).get("item", [])

                if isinstance(items, dict):

                    items = [items]


 

                successful_url = url

                page_success = True


 

                if not items:

                    break


 

                for item in items:

                    try:

                        area = float(item.get("archArea", 0) or 0)

                    except Exception:

                        area = 0.0

                    raw.append({

                        "지번주소": item.get("platPlc", "주소없음"),

                        "건물명": item.get("bldNm", ""),

                        "건축면적(㎡)": area,

                    })

                    if len(raw) >= MAX_ITEMS:

                        break


 

                processed = min(len(raw), total_count) if total_count else len(raw)

                progress.progress(

                    min(processed / max(total_count, 1), 1.0)

                )

                status_box.info(

                    f"건축물대장 수집 중: {processed:,}/{total_count:,}건"

                )

                break


 

            except requests.exceptions.RequestException as exc:

                last_error_msg = f"통신 오류: {exc}"

                continue

            except RuntimeError:

                progress.empty()

                status_box.empty()

                raise

            except Exception as exc:

                last_error_msg = f"예외: {exc}"

                continue


 

        if not page_success:

            progress.empty()

            status_box.empty()

            key_preview = (

                f"{service_key[:6]}...{service_key[-6:]}"

                if len(service_key) > 12 else "너무 짧음"

            )

            raise RuntimeError(

                f"공공데이터포털 통신 실패\n"

                f"인증키(일부): {key_preview}\n"

                f"인증키 길이: {len(service_key)}자\n"

                f"URL 인코딩됨: {'예' if key_is_encoded else '아니오'}\n"

                f"sigunguCd: {sigungu_cd}, bjdongCd: {bjdong_cd}\n"

                f"세부: {last_error_msg}"

            )


 

        if not items:

            break


 

        if len(raw) >= MAX_ITEMS or page_no * 100 >= total_count:

            break


 

        page_no += 1

        time.sleep(0.02)


 

    progress.empty()

    status_box.empty()


 

    if page_no > MAX_PAGES and total_count > MAX_ITEMS:

        st.warning(

            f"공공데이터가 {MAX_ITEMS:,}건을 초과하여 "

            f"안전상 {MAX_ITEMS:,}건까지만 처리했습니다."

        )

    return raw


 


 

def build_target_df(sido, sigungu, dong, min_area):

    center = geocode_address(f"{sido} {sigungu} {dong}")

    if not center or not center.get("b_code"):

        raise RuntimeError(

            "선택한 읍/면/동의 좌표 또는 법정동코드를 찾지 못했습니다."

        )


 

    b_code = center["b_code"]

    if len(b_code) < 10:

        raise RuntimeError("법정동코드가 유효하지 않습니다.")


 

    sigungu_cd = b_code[:5]

    bjdong_cd = b_code[5:10]


 

    raw = fetch_building_targets(sigungu_cd, bjdong_cd)

    if not raw:

        return pd.DataFrame(columns=TARGET_COLS), center


 

    raw_df = pd.DataFrame(raw)

    raw_df["주소키"] = raw_df["지번주소"].map(normalize_address)


 

    grouped = raw_df.groupby("주소키", as_index=False).agg({

        "지번주소": "first",

        "건축면적(㎡)": "sum",

        "건물명": lambda x: ", ".join(sorted(set(filter(None, x)))),

    })


 

    filtered = grouped[grouped["건축면적(㎡)"] >= float(min_area)].copy()

    if filtered.empty:

        return pd.DataFrame(columns=TARGET_COLS), center


 

    rows = []

    bar = st.progress(0)

    box = st.empty()


 

    for i, (_, row) in enumerate(filtered.iterrows(), start=1):

        addr = row["지번주소"]

        geo = geocode_address(addr)

        lat = geo["lat"] if geo else 0.0

        lng = geo["lng"] if geo else 0.0

        name = place_name_for_address(addr) if geo else ""

        if not name:

            name = row["건물명"] or ""

        rows.append({

            "site_id": "",

            "상호명": name,

            "지번주소": addr,

            "면적": round(float(row["건축면적(㎡)"]), 1),

            "lat": lat, "lng": lng,

            "상태": "미컨택",

            "컨택방식": "미진행",

            "등록일시": now_str(),

            "수정일시": now_str(),

            "메모": "",

            "최근수정내역": "",

            "수동등록": False,

        })

        bar.progress(i / len(filtered))

        box.info(f"주소 좌표/상호명 변환 중: {i}/{len(filtered)}")


 

    bar.empty()

    box.empty()


 

    result = normalize_df(pd.DataFrame(rows))

    return (

        result[

            result["lat"].ne(0) & result["lng"].ne(0)

        ].reset_index(drop=True),

        center,

    )


 


 

def merge_discovered_with_existing(

    existing: pd.DataFrame,

    discovered: pd.DataFrame,

) -> pd.DataFrame:

    """공지 6: 사용자 수정 데이터 절대 덮어쓰지 않음. 신규 주소만 추가."""

    existing = normalize_df(existing)

    discovered = normalize_df(discovered)


 

    if existing.empty:

        result = discovered.copy()

        seen = set()

        n = 1

        for i in result.index:

            sid = str(result.at[i, "site_id"])

            if not sid or sid == "nan":

                while f"SITE-{n:06d}" in seen:

                    n += 1

                result.at[i, "site_id"] = f"SITE-{n:06d}"

                seen.add(result.at[i, "site_id"])

                n += 1

            else:

                seen.add(sid)

        return normalize_df(result)


 

    if discovered.empty:

        return existing


 

    known = {normalize_address(v) for v in existing["지번주소"].astype(str)}


 

    # 성능 최적화: concat 반복 없이 리스트로 수집

    new_rows = []

    used_ids = set(existing["site_id"].astype(str))

    ids_num = pd.to_numeric(

        existing["site_id"].astype(str).str.extract(r"SITE-(\d+)")[0],

        errors="coerce",

    ).dropna()

    next_num = int(ids_num.max()) + 1 if not ids_num.empty else 1


 

    for _, row in discovered.iterrows():

        key = normalize_address(row.get("지번주소", ""))

        if not key or key in known:

            continue

        row_dict = row.to_dict()

        while f"SITE-{next_num:06d}" in used_ids:

            next_num += 1

        row_dict["site_id"] = f"SITE-{next_num:06d}"

        used_ids.add(row_dict["site_id"])

        next_num += 1

        new_rows.append(row_dict)

        known.add(key)


 

    if new_rows:

        return normalize_df(

            pd.concat(

                [existing, pd.DataFrame(new_rows)],

                ignore_index=True,

            )

        )

    return existing


 


 

# ============================================================

# Region UI

# ============================================================

st.markdown(

    '<div class="section-title">타겟 지역 및 조건 설정</div>',

    unsafe_allow_html=True,

)


 

# 공지 9: 모바일 selectbox 키보드 방지

st.markdown("""

<script>

(function(){

  function disableSelectKeyboard(){

    try {

      var selects = document.querySelectorAll(

        'div[data-baseweb="select"] input[role="combobox"]'

      );

      selects.forEach(function(el){

        el.setAttribute('readonly','readonly');

        el.setAttribute('inputmode','none');

        el.setAttribute('autocomplete','off');

        el.style.caretColor='transparent';

      });

    } catch(e) {}

  }

  disableSelectKeyboard();

  setTimeout(disableSelectKeyboard, 100);

  setTimeout(disableSelectKeyboard, 500);

  setTimeout(disableSelectKeyboard, 1500);

  try {

    var observer = new MutationObserver(disableSelectKeyboard);

    observer.observe(document.body, {childList:true, subtree:true});

  } catch(e) {}

})();

</script>

""", unsafe_allow_html=True)


 

col1, col2, col3 = st.columns(3)


 

sido_options = list(REGION_DATA.keys())

sido_default = (

    sido_options.index("부산광역시")

    if "부산광역시" in sido_options else 0

)

with col1:

    sido = st.selectbox(

        "시/도", sido_options,

        index=sido_default, key="region_sido",

    )


 

sigungu_options = list(REGION_DATA[sido].keys())

sigungu_default = (

    sigungu_options.index("해운대구")

    if sido == "부산광역시" and "해운대구" in sigungu_options else 0

)

with col2:

    sigungu = st.selectbox(

        "시/군/구", sigungu_options,

        index=sigungu_default, key="region_sigungu",

    )


 

dong_options = REGION_DATA[sido][sigungu]

dong_default = (

    dong_options.index("좌동")

    if sido == "부산광역시" and sigungu == "해운대구" and "좌동" in dong_options

    else 0

)

with col3:

    dong = st.selectbox(

        "읍/면/동", dong_options,

        index=dong_default, key="region_dong",

    )


 

min_area = st.number_input(

    "최소 건축면적 (㎡)",

    min_value=100, value=5000, step=500,

    key="min_area",

)


 

target_tab_name = f"target_{sido}_{sigungu}_{dong}"


 

q1, q2 = st.columns(2)

with q1:

    query_clicked = st.button(

        "데이터 조회 및 지도 적용",

        use_container_width=True, type="primary",

    )

with q2:

    refresh_clicked = st.button(

        "공공데이터 재조회 · 신규 타겟 반영",

        use_container_width=True,

    )


 

if query_clicked or refresh_clicked:

    if not require_api_keys():

        st.stop()

    try:

        with st.spinner("기존 DB 확인 중..."):

            existing = load_target_data(target_tab_name)


 

        st.session_state.current_tab = target_tab_name


 

        center = geocode_address(f"{sido} {sigungu} {dong}")

        if not center:

            st.error("선택한 지역의 지도 좌표를 찾지 못했습니다.")

            st.stop()


 

        # 지역 검색 시에만 지도를 해당 위치로 이동

        st.session_state.search_center = [center["lat"], center["lng"]]

        st.session_state.map_zoom = 15

        st.session_state.selected_site_id = None

        st.session_state.selected_addr = None

        st.session_state.new_pin_coord = None

        st.session_state.last_click_hash = ""


 

        if refresh_clicked:

            with st.spinner("공공데이터를 재조회하여 신규 타겟만 추가합니다..."):

                discovered, _ = build_target_df(

                    sido, sigungu, dong, min_area,

                )


 

            merged = merge_discovered_with_existing(existing, discovered)


 

            existing_keys = (

                {

                    normalize_address(v)

                    for v in existing["지번주소"].astype(str)

                }

                if not existing.empty else set()

            )

            added = merged[

                ~merged["지번주소"].astype(str).map(normalize_address)

                .isin(existing_keys)

            ].copy()


 

            save_ok = True

            if existing.empty:

                if not merged.empty:

                    save_ok = save_target_data_initial(

                        target_tab_name, merged,

                    )

            else:

                for _, new_row in added.iterrows():

                    if not save_target_row(

                        target_tab_name,

                        new_row.to_dict(),

                        append_if_missing=True,

                    ):

                        save_ok = False

                        break


 

            if save_ok:

                st.session_state.target_data = merged

                st.session_state.last_loaded_tab = target_tab_name

                st.success(

                    f"재조회 완료: 기존 {len(existing):,}건 유지 · "

                    f"신규 {len(added):,}건 반영"

                )


 

        elif not existing.empty:

            st.session_state.target_data = existing

            st.session_state.last_loaded_tab = target_tab_name

            st.success(f"기존 데이터 {len(existing):,}건을 불러왔습니다.")


 

        else:

            with st.spinner(

                "최초 1회 타겟 DB를 구축합니다. "

                "대상이 많으면 시간이 걸릴 수 있습니다."

            ):

                built, _ = build_target_df(

                    sido, sigungu, dong, min_area,

                )

            if built.empty:

                st.info("조건에 일치하는 데이터가 없습니다.")

            else:

                if save_target_data_initial(target_tab_name, built):

                    st.session_state.target_data = built

                    st.session_state.last_loaded_tab = target_tab_name

                    st.success(

                        f"신규 타겟 DB 구축 완료: {len(built):,}건"

                    )

    except Exception as e:

        st.error(f"조회/구축 중 오류: {e}")


 


 

# ============================================================

# Map Macros

# ============================================================

class CadastralToggle(MacroElement):

    """공지 2: 지적도 ON/OFF 버튼"""

    _template = Template(r"""

    {% macro script(this, kwargs) %}

    (function() {

        var map = {{ this._parent.get_name() }};

        var layer = {{ this.layer_name }};

        var storageKey = {{ this.storage_key | tojson }};

        if (!map || !layer) return;


 

        function getSaved() {

            try { return window.localStorage.getItem(storageKey) === "1"; }

            catch(e) { return false; }

        }

        function setSaved(on) {

            try { window.localStorage.setItem(storageKey, on ? "1" : "0"); }

            catch(e) {}

        }

        function refresh(button) {

            var on = map.hasLayer(layer);

            button.innerHTML = on ? "지적도 ON" : "지적도 OFF";

            button.style.background = on ? "#eef2ff" : "#ffffff";

            button.style.color = on ? "#4338ca" : "#374151";

        }


 

        try {

            if (getSaved() && !map.hasLayer(layer)) map.addLayer(layer);

            else if (!getSaved() && map.hasLayer(layer)) map.removeLayer(layer);

        } catch(e) {}


 

        var Toggle = L.Control.extend({

            options: { position: "topright" },

            onAdd: function(map) {

                var container = L.DomUtil.create(

                    "div", "leaflet-control leaflet-bar"

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

                    if (map.hasLayer(layer)) {

                        map.removeLayer(layer); setSaved(false);

                    } else {

                        map.addLayer(layer); setSaved(true);

                    }

                    refresh(button);

                });

                refresh(button);

                return container;

            }

        });


 

        if (!map.__cadastralToggleAdded) {

            map.__cadastralToggleAdded = true;

            map.addControl(new Toggle());

        }

    })();

    {% endmacro %}

    """)


 

    def __init__(self, layer_name, storage_key):

        super().__init__()

        self._name = "CadastralToggle"

        self.layer_name = layer_name

        self.storage_key = storage_key


 


 

class MapViewPersistence(MacroElement):

    """지도 위치/줌을 브라우저 localStorage로 유지"""

    _template = Template(r"""

    {% macro script(this, kwargs) %}

    (function() {

        var map = {{ this._parent.get_name() }};

        var storageKey = {{ this.storage_key | tojson }};

        if (!map || !storageKey) return;


 

        function restore() {

            try {

                var raw = window.localStorage.getItem(storageKey);

                if (!raw) return;

                var s = JSON.parse(raw);

                if (

                    s && Array.isArray(s.center)

                    && s.center.length === 2

                    && typeof s.zoom === "number"

                ) {

                    map.setView(

                        [parseFloat(s.center[0]), parseFloat(s.center[1])],

                        s.zoom,

                        { animate: false }

                    );

                }

            } catch(e) {}

        }

        function save() {

            try {

                var c = map.getCenter();

                window.localStorage.setItem(storageKey, JSON.stringify({

                    center: [c.lat, c.lng], zoom: map.getZoom()

                }));

            } catch(e) {}

        }

        try {

            map.off("moveend.__persist");

            map.off("zoomend.__persist");

        } catch(e) {}

        map.on("moveend.__persist", save);

        map.on("zoomend.__persist", save);

        setTimeout(restore, 50);

        setTimeout(restore, 250);

    })();

    {% endmacro %}

    """)


 

    def __init__(self, storage_key):

        super().__init__()

        self._name = "MapViewPersistence"

        self.storage_key = storage_key


 


 

# ============================================================

# Map

# ============================================================

st.divider()

st.markdown(

    '<div class="helper-text">'

    '안내: 지도 빈 공간을 터치하면 신규 현장을 등록할 수 있습니다.'

    '</div>',

    unsafe_allow_html=True,

)


 

with st.expander("지도안내"):

    st.markdown("""

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

    """, unsafe_allow_html=True)


 

current_tab_for_map = st.session_state.current_tab or target_tab_name


 

m = folium.Map(

    location=st.session_state.search_center,

    zoom_start=st.session_state.map_zoom,

    max_zoom=19, min_zoom=1,

    tiles=None,

    control_scale=True,

)


 

# VWorld 위성지도 (인증 불필요)

folium.TileLayer(

    tiles=(

        https://xdworld.vworld.kr/

        "2d/Satellite/service/{z}/{x}/{y}.jpeg"

    ),

    attr="VWorld",

    name="위성지도",

    max_zoom=19,

    max_native_zoom=18,

    overlay=False,

    control=False,

    show=True,

).add_to(m)


 

# VWorld 지적도 (key/domain 필요 → URL에 직접 embed)

wms_query = urllib.parse.urlencode({

    "key": VWORLD_KEY,

    "domain": VWORLD_DOMAIN,

})

wms_url = fhttps://api.vworld.kr/req/wms?{wms_query}


 

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


 

# 버그 #1 수정: cadastral_layer.get_name() 사용

CadastralToggle(

    cadastral_layer.get_name(),

    f"solar_mkt_cadastral::{current_tab_for_map}",

).add_to(m)


 

MapViewPersistence(

    f"solar_mkt_view::{current_tab_for_map}",

).add_to(m)


 

LocateControl(

    position="topleft",

    strings={"title": "내 위치 확인", "popup": "현재 위치"},

    drawCircle=True,

    showPopup=False,

    keepCurrentZoomLevel=True,

    setView=False,

).add_to(m)


 

m.add_child(MeasureControl(

    position="topright",

    primary_length_unit="meters",

    primary_area_unit="sqmeters",

))


 

# 나침반

m.get_root().html.add_child(folium.Element("""

<div style="position:absolute;top:120px;left:11px;z-index:1000;

     background:rgba(255,255,255,.9);padding:4px;border-radius:6px;

     border:2px solid rgba(0,0,0,.2);

     box-shadow:0 1px 4px rgba(0,0,0,.3);

     width:32px;height:32px;

     display:flex;flex-direction:column;

     align-items:center;justify-content:center;

     pointer-events:none;">

    <div style="font-size:10px;font-weight:900;color:#ef4444;

         line-height:1;">N</div>

    <div style="font-size:13px;font-weight:900;line-height:1;">▲</div>

</div>

"""))


 

m.get_root().header.add_child(folium.Element("""

<style>

.leaflet-control-measure .coordinatetracker { display:none!important; }

.leaflet-control-measure h3,

.leaflet-control-measure .prompt { font-size:0!important; }

.leaflet-control-measure h3::after {

    content:'지붕 면적 실측';

    font-size:13px!important;font-weight:600;

    display:block;margin-bottom:5px;color:#374151;

}

.leaflet-control-measure .prompt::after {

    content:'지붕 모서리를 따라 점을 지정하세요 (완료: 더블클릭)';

    font-size:11px!important;display:block;color:#6b7280;

}

</style>

"""))


 


 

# ============================================================

# Markers

# ============================================================

df_all = normalize_df(st.session_state.target_data)

st.session_state.target_data = df_all


 

if not df_all.empty:

    df_filtered = df_all[df_all["면적"] >= float(min_area)].copy()

else:

    df_filtered = df_all.copy()


 

marker_count = 0

coord_missing_count = 0


 

# 100건 이상이면 MarkerCluster 사용

if len(df_filtered) >= 100:

    marker_parent = MarkerCluster(

        name="현장 핀",

        options={

            "disableClusteringAtZoom": 17,

            "spiderfyOnMaxZoom": True,

            "showCoverageOnHover": False,

            "removeOutsideVisibleBounds": True,

            "animate": False,

        },

    ).add_to(m)

else:

    marker_parent = m


 

# 마커 해시맵 (공지 3: 좌표 6자리 정밀 매칭)

marker_coord_map = {}


 

for _, row in df_filtered.iterrows():

    lat = pd.to_numeric(row.get("lat"), errors="coerce")

    lng = pd.to_numeric(row.get("lng"), errors="coerce")

    if pd.isna(lat) or pd.isna(lng) or float(lat) == 0 or float(lng) == 0:

        coord_missing_count += 1

        continue


 

    sid = str(row["site_id"])

    selected = st.session_state.selected_site_id == sid

    color = (

        "purple" if selected

        else STATUS_COLORS.get(row.get("상태", "미컨택"), "red")

    )

    icon = (

        "star"

        if selected or bool(row.get("수동등록", False))

        else "info-sign"

    )

    name = html.escape(str(row.get("상호명", "")) or "상호명 미상")

    addr = html.escape(str(row.get("지번주소", "")))


 

    popup = (

        f"<b>{name}</b><br>"

        f"현장ID: {html.escape(sid)}<br>"

        f"{addr}<br>"

        f"면적: {float(row['면적']):,.1f}㎡<br>"

        f"상태: {html.escape(str(row.get('상태','')))}"

    )


 

    key = coord_key(lat, lng)

    if key:

        marker_coord_map[key] = sid


 

    folium.Marker(

        [float(lat), float(lng)],

        tooltip=name,

        popup=folium.Popup(popup, max_width=280),

        icon=folium.Icon(color=color, icon=icon),

    ).add_to(marker_parent)

    marker_count += 1


 

# 신규 핀 임시 표시

if st.session_state.new_pin_coord:

    folium.Marker(

        [

            float(st.session_state.new_pin_coord["lat"]),

            float(st.session_state.new_pin_coord["lng"]),

        ],

        tooltip="신규 등록 예정 위치",

        icon=folium.Icon(color="purple", icon="star"),

    ).add_to(m)


 

st.caption(

    f"지도 표시 대상 {len(df_filtered):,}건 · "

    f"실제 핀 {marker_count:,}개 · "

    f"좌표 없음 {coord_missing_count:,}개"

)


 


 

# ============================================================

# Render Map

# 이슈 #4 수정: center 파라미터 제거 (매 rerun마다 지도 튐 방지)

# ============================================================

map_data = st_folium(

    m,

    width="100%",

    height=450,

    returned_objects=["last_object_clicked", "last_clicked"],

    key=f"solar_mkt_map__{current_tab_for_map}",

)


 


 

# ============================================================

# Click Handling (Debounce)

# ============================================================

def _click_hash(event_type: str, event_data) -> str:

    if not event_data or not isinstance(event_data, dict):

        return ""

    return (

        f"{event_type}:"

        f"{event_data.get('lat', '')}:"

        f"{event_data.get('lng', '')}"

    )


 


 

clicked_marker = (

    map_data.get("last_object_clicked") if map_data else None

)

clicked_map = map_data.get("last_clicked") if map_data else None


 

# 마커 클릭 (공지 3: coord_key 정밀 매칭)

if clicked_marker:

    curr_hash = _click_hash("marker", clicked_marker)

    if curr_hash and curr_hash != st.session_state.last_click_hash:

        st.session_state.last_click_hash = curr_hash

        clicked_key = coord_key(

            clicked_marker.get("lat"),

            clicked_marker.get("lng"),

        )

        sid = marker_coord_map.get(clicked_key, "")


 

        if sid and st.session_state.selected_site_id != sid:

            matched = df_all[df_all["site_id"].astype(str) == sid]

            if not matched.empty:

                row = matched.iloc[0]

                st.session_state.selected_site_id = sid

                st.session_state.selected_addr = row["지번주소"]

                st.session_state.new_pin_coord = None

                # 이슈 #5 수정: search_center 덮어쓰지 않음 (지도 위치 유지)

                st.rerun()


 

# 빈 공간 클릭 (공지 4: 20m 이내 → 기존, 20m 밖 → 신규)

elif clicked_map:

    curr_hash = _click_hash("empty", clicked_map)

    if curr_hash and curr_hash != st.session_state.last_click_hash:

        st.session_state.last_click_hash = curr_hash

        try:

            lat = float(clicked_map["lat"])

            lng = float(clicked_map["lng"])


 

            nearest = None

            nearest_dist = float("inf")

            if not df_all.empty:

                valid = df_all[

                    (df_all["lat"] != 0) & (df_all["lng"] != 0)

                ].copy()

                for _, r in valid.iterrows():

                    d = haversine_m(

                        lat, lng,

                        float(r["lat"]), float(r["lng"]),

                    )

                    if d < nearest_dist:

                        nearest_dist = d

                        nearest = r


 

            if nearest is not None and nearest_dist <= 20.0:

                st.session_state.selected_site_id = str(nearest["site_id"])

                st.session_state.selected_addr = nearest["지번주소"]

                st.session_state.new_pin_coord = None

                st.toast("기존 등록 현장을 불러왔습니다. (20m 이내)")

                st.rerun()

            else:

                st.session_state.new_pin_coord = {"lat": lat, "lng": lng}

                st.session_state.selected_site_id = None

                st.session_state.selected_addr = None

                st.rerun()

        except Exception:

            pass


 


 

# ============================================================

# Existing Target Edit

# ============================================================

selected_comp = None

if st.session_state.selected_site_id:

    matched = df_all[

        df_all["site_id"].astype(str)

        == str(st.session_state.selected_site_id)

    ]

    if not matched.empty:

        selected_comp = matched.iloc[0]

    else:

        st.session_state.selected_site_id = None

        st.session_state.selected_addr = None


 

if selected_comp is not None:

    comp = selected_comp

    st.markdown("<br>", unsafe_allow_html=True)

    display_name = str(comp.get("상호명", "")) or "상호명 미상"

    st.markdown(

        f"**{html.escape(display_name)}**  ·  "

        f"{float(comp['면적']):,.1f}㎡"

    )

    st.caption(

        f"현장ID: {comp['site_id']}  |  "

        f"최초 등록: {comp.get('등록일시','-')}  |  "

        f"최근 수정: {comp.get('수정일시','-')}"

    )

    st.code(str(comp.get("지번주소", "")), language="text")


 

    encoded_addr = urllib.parse.quote(str(comp.get("지번주소", "")))

    c1, c2, c3 = st.columns(3)

    with c1:

        st.link_button(

            "네이버지도",

            fhttps://map.naver.com/p/search/{encoded_addr},

            use_container_width=True,

        )

    with c2:

        st.link_button(

            "카카오맵",

            fhttps://map.kakao.com/link/search/{encoded_addr},

            use_container_width=True,

        )

    with c3:

        st.link_button(

            "티맵(App)",

            f"tmap://search?name={encoded_addr}",

            use_container_width=True,

        )


 

    st.divider()


 

    sid_key = comp['site_id']

    edited_name = st.text_input(

        "상호명 (간판 기준)",

        value=str(comp.get("상호명", "")),

        key=f"edit_name_{sid_key}",

    )

    edited_area = st.number_input(

        "지붕 실측 면적(㎡)",

        min_value=0.0,

        value=float(comp.get("면적", 0.0)),

        step=50.0,

        key=f"edit_area_{sid_key}",

    )


 

    is_installed = st.checkbox(

        "태양광 기설치 완료 (또는 불가 현장)",

        value=str(comp.get("상태", "")) == "기설치",

        key=f"installed_{sid_key}",

    )


 

    current_method = str(comp.get("컨택방식", "미진행"))

    if current_method in METHOD_OPTIONS:

        method_idx = METHOD_OPTIONS.index(current_method)

        custom_val = ""

    else:

        method_idx = METHOD_OPTIONS.index("기타")

        custom_val = current_method


 

    selected_contact = st.radio(

        "컨택방식", METHOD_OPTIONS,

        index=method_idx, horizontal=True,

        key=f"method_{sid_key}",

    )

    final_method = selected_contact

    if selected_contact == "기타":

        typed = st.text_input(

            "기타 방식 입력",

            value=custom_val,

            placeholder="예: 우편, 지인 소개 등",

            key=f"custom_{sid_key}",

        ).strip()

        final_method = typed or "기타"


 

    if selected_contact == "미진행":

        final_status = "기설치" if is_installed else "미컨택"

    else:

        contact_status_options = [

            x for x in STATUS_OPTIONS

            if x not in ("미컨택", "기설치")

        ]

        current_status = str(comp.get("상태", "협의중"))

        status_idx = (

            contact_status_options.index(current_status)

            if current_status in contact_status_options else 0

        )

        chosen_status = st.radio(

            "상세 단계",

            contact_status_options,

            index=status_idx,

            horizontal=True,

            key=f"status_{sid_key}",

        )

        final_status = "기설치" if is_installed else chosen_status


 

    memo = st.text_area(

        "현장 특이사항 및 미팅 노트",

        value=str(comp.get("메모", "")),

        key=f"memo_{sid_key}",

    )


 

    if st.button(

        "변경사항 저장",

        use_container_width=True,

        type="primary",

        key=f"save_{sid_key}",

    ):

        before = comp.to_dict()

        after = before.copy()

        after.update({

            "상호명": edited_name.strip(),

            "면적": float(edited_area),

            "컨택방식": final_method,

            "상태": final_status,

            "수정일시": now_str(),

            "메모": memo,

        })


 

        changes = []

        for label, key in [

            ("상태", "상태"), ("방식", "컨택방식"),

            ("면적", "면적"), ("상호명", "상호명"),

        ]:

            if str(before.get(key, "")) != str(after.get(key, "")):

                changes.append(

                    f"{label}("

                    f"{before.get(key,'')}→{after.get(key,'')})"

                )

        if (

            str(before.get("메모", "")).strip()

            != str(after.get("메모", "")).strip()

        ):

            changes.append("메모수정")

        after["최근수정내역"] = (

            " | ".join(changes) if changes else "단순열람(수정없음)"

        )


 

        if save_target_row(

            st.session_state.current_tab, after,

            append_if_missing=False,

        ):

            activity_ok = append_activity(

                comp["site_id"],

                st.session_state.current_tab,

                before, after, "수정",

            )

            if not activity_ok:

                st.warning(

                    "현장 데이터는 저장되었지만 "

                    "영업일지 이력은 저장되지 않았습니다."

                )

            updated = df_all.copy()

            mask = updated["site_id"].astype(str) == str(comp["site_id"])

            for key, value in after.items():

                if key in updated.columns:

                    updated.loc[mask, key] = value

            st.session_state.target_data = normalize_df(updated)

            st.session_state.save_success = True

            st.rerun()


 

# ============================================================

# New Target

# ============================================================

elif st.session_state.new_pin_coord:

    new_lat = float(st.session_state.new_pin_coord["lat"])

    new_lng = float(st.session_state.new_pin_coord["lng"])

    st.info("선택하신 위치에 신규 타겟을 등록합니다.")


 

    auto_address, auto_name = get_place_info_from_coords(new_lat, new_lng)


 

    with st.form("new_pin_form", clear_on_submit=True):

        new_addr = st.text_input("지번 주소", value=auto_address)

        new_name = st.text_input("상호명", value=auto_name)

        new_area = st.number_input(

            "예상 지붕 면적(㎡)",

            min_value=0.0,

            value=float(min_area),

            step=100.0,

        )


 

        if st.form_submit_button(

            "신규 현장 등록",

            use_container_width=True,

        ):

            # 공지 5: 주소 정규화 중복 검사

            duplicate = df_all[

                df_all["지번주소"].astype(str)

                .map(normalize_address)

                == normalize_address(new_addr)

            ]

            if not duplicate.empty:

                st.warning(

                    "이미 등록된 주소입니다. "

                    f"현장ID: {duplicate.iloc[0]['site_id']}"

                )

                st.session_state.selected_site_id = (

                    str(duplicate.iloc[0]["site_id"])

                )

                st.session_state.selected_addr = duplicate.iloc[0]["지번주소"]

                st.session_state.new_pin_coord = None

                st.rerun()

            else:

                sid = new_site_id(df_all)

                stamp = now_str()

                new_row = {

                    "site_id": sid,

                    "상호명": new_name.strip(),

                    "지번주소": new_addr.strip(),

                    "면적": float(new_area),

                    "lat": new_lat, "lng": new_lng,

                    "상태": "미컨택",

                    "컨택방식": "미진행",

                    "등록일시": stamp,

                    "수정일시": stamp,

                    "수동등록": True,

                    "메모": "",

                    "최근수정내역": "신규 현장 발굴 및 등록",

                }

                if save_target_row(

                    st.session_state.current_tab, new_row,

                    append_if_missing=True,

                ):

                    activity_ok = append_activity(

                        sid,

                        st.session_state.current_tab,

                        {}, new_row, "신규등록",

                    )

                    if not activity_ok:

                        st.warning(

                            "현장 데이터는 저장되었지만 "

                            "영업일지 이력은 저장되지 않았습니다."

                        )

                    updated = normalize_df(

                        pd.concat(

                            [df_all, pd.DataFrame([new_row])],

                            ignore_index=True,

                        )

                    )

                    st.session_state.target_data = updated

                    st.session_state.selected_site_id = sid

                    st.session_state.selected_addr = new_addr.strip()

                    st.session_state.new_pin_coord = None

                    st.session_state.save_success = True

                    if new_area < min_area:

                        st.warning(

                            "데이터는 저장되었지만 최소 면적 미달이라 "

                            "현재 지도 필터에서는 표시되지 않습니다."

                        )

                    st.rerun()


 


 

# ============================================================

# Daily Activity Log

# ============================================================

st.divider()


 

if st.session_state.get("activity_status"):

    status_text = html.escape(str(st.session_state.activity_status))

    if "실패" in status_text:

        st.warning(status_text)

    else:

        st.caption("📝 " + status_text)


 

st.markdown(

    '<div class="section-title">일자별 영업일지</div>',

    unsafe_allow_html=True,

)

selected_date = st.date_input("조회 일자 선택", value=datetime.today())

date_str = selected_date.strftime("%Y-%m-%d")


 

activity = load_activity_log()


 

# 세션 즉시 반영분

session_rows = st.session_state.get("activity_rows_session", [])

if session_rows:

    session_df = pd.DataFrame(session_rows)

    activity = (

        pd.concat([activity, session_df], ignore_index=True)

        if not activity.empty else session_df

    )

    if "기록일시" in activity.columns:

        activity = activity.drop_duplicates(

            subset=[

                c for c in ["기록일시", "site_id", "행동"]

                if c in activity.columns

            ],

            keep="first",

        )


 

if not activity.empty and "기록일시" in activity.columns:

    activity["기록일시"] = activity["기록일시"].fillna("").astype(str)

    daily = activity[

        activity["기록일시"].str.startswith(date_str)

    ].copy().sort_values("기록일시")


 

    if daily.empty:

        st.info(f"{date_str} 기준 영업 이력이 없습니다.")

    else:

        st.success(f"조회 결과: 총 {len(daily):,}건의 활동이 있습니다.")

        for _, row in daily.iloc[::-1].iterrows():

            title = html.escape(str(row.get("상호명", "")) or "상호명 미상")

            addr = html.escape(str(row.get("지번주소", "")))

            changes = html.escape(str(row.get("변경내역", "")))

            memo = html.escape(str(row.get("메모", "")))

            st.markdown(

                f"**{title}** "

                f"({html.escape(str(row.get('상태','')))})"

            )

            st.caption(

                f"{addr} | "

                f"접촉: {row.get('접촉방식','')} | "

                f"시간: {row.get('기록일시','')} | "

                f"{row.get('site_id','')}"

            )

            if changes:

                st.markdown(

                    f"<div style='font-size:13px;color:#ea580c;"

                    f"font-weight:600;'>🔄 {changes}</div>",

                    unsafe_allow_html=True,

                )

            if memo:

                st.markdown(

                    f"<div style='background:#f3f4f6;padding:10px;"

                    f"border-radius:6px;font-size:13px;color:#4b5563;"

                    f"margin-top:5px;'>{memo}</div>",

                    unsafe_allow_html=True,

                )

            st.markdown(

                "<hr style='margin:15px 0;"

                "border-top:1px solid #e5e7eb;'>",

                unsafe_allow_html=True,

            )

else:

    st.info(

        "아직 누적 영업활동 이력이 없습니다. "

        "현장을 수정/등록하면 이력에 쌓입니다."

    )


 

mode = "Google Sheets" if sheets_enabled() else "CSV(개발/임시)"

st.caption(

    f"저장 모드: {mode}  |  "

    f"현재 지역: {sido} {sigungu} {dong}"

)
