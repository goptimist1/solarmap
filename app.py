import os
import html
import urllib.parse
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import folium
from folium.plugins import MeasureControl, LocateControl, MarkerCluster
from streamlit_folium import st_folium

# ============================================================
# Solar Mkt Map - improved production-oriented version
# Existing UX/features are intentionally preserved:
# - Yeongnam dropdowns
# - building-register target discovery
# - satellite + cadastral layer
# - current-location / measure / compass
# - marker clustering
# - existing target edit
# - manual target registration
# - navigation links
# - daily activity log
# - Google Sheets persistence with CSV fallback during setup
# - NEW: stable site_id, cumulative activity log, safer secrets,
#        duplicate detection, timeouts, clearer save errors
# ============================================================

st.set_page_config(page_title="Solar Mkt Map", layout="centered")

# ------------------------- Secrets ----------------------------
def secret(name: str, default: str = "") -> str:
    """Read Streamlit secret first, then environment variable."""
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

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GS_AVAILABLE = True
except ImportError:
    GS_AVAILABLE = False

# ------------------------- Constants --------------------------
TEXT_COLS = [
    "site_id", "상호명", "지번주소", "상태", "컨택방식",
    "등록일시", "수정일시", "메모", "최근수정내역"
]
NUM_COLS = ["면적", "lat", "lng"]
BOOL_COLS = ["수동등록"]
TARGET_COLS = TEXT_COLS + NUM_COLS + BOOL_COLS

STATUS_OPTIONS = ["미컨택", "거절/보류", "협의중", "승낙서수령", "계약완료", "기설치"]
METHOD_OPTIONS = ["미진행", "전화", "이메일", "방문", "기타"]
STATUS_COLORS = {
    "미컨택": "red",
    "거절/보류": "orange",
    "협의중": "blue",
    "승낙서수령": "lightgreen",
    "계약완료": "green",
    "기설치": "gray",
}

# Existing Yeongnam selection structure retained from the working version.
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
        "고령군": ["대가야읍", "덕곡면", "운수면", "성산면", "다산면", "개진면", "우곡면", "쌍림면"],
    },
}

# ------------------------- Session state ----------------------
def init_state():
    defaults = {
        "target_data": pd.DataFrame(columns=TARGET_COLS),
        "search_center": [35.0910, 128.8475],
        "map_zoom": 15,
        "current_tab": "",
        "selected_site_id": None,
        "selected_addr": None,  # legacy compatibility
        "new_pin_coord": None,
        "save_success": False,
        "last_loaded_tab": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

# ------------------------- Styling ----------------------------
st.markdown("""
<style>
.stApp { background-color: #f9fafb; }
div[data-testid="stForm"] { border:1px solid #e5e7eb; border-radius:12px; padding:24px; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.05); }
.main-header { padding:1.5rem 0 1rem; border-bottom:1px solid #e5e7eb; margin-bottom:2rem; }
.main-header h2 { margin:0; color:#111827; font-size:1.6rem; font-weight:800; letter-spacing:-.5px; }
.section-title { font-size:1.05rem; font-weight:600; color:#374151; margin-bottom:1rem; padding-bottom:.5rem; border-bottom:1px solid #e5e7eb; }
.helper-text { font-size:13px; color:#6b7280; margin-bottom:8px; }
</style>
""", unsafe_allow_html=True)

if st.session_state.save_success:
    st.toast("✅ 저장되었습니다.")
    st.session_state.save_success = False

st.markdown('<div class="main-header"><h2>Solar Mkt Map ☀️</h2></div>', unsafe_allow_html=True)

# ------------------------- Helpers ----------------------------
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_site_id(df: pd.DataFrame) -> str:
    if df.empty or "site_id" not in df.columns:
        return "SITE-000001"
    ids = df["site_id"].astype(str)
    nums = pd.to_numeric(ids.str.extract(r"SITE-(\d+)")[0], errors="coerce").dropna()
    n = int(nums.max()) + 1 if not nums.empty else len(df) + 1
    return f"SITE-{n:06d}"


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=TARGET_COLS)
    df = df.copy()

    # Backward compatibility with the old schema.
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
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "수동등록" not in df.columns:
        df["수동등록"] = False
    df["수동등록"] = df["수동등록"].astype(str).str.lower().isin(["true", "1", "yes", "y", "t"])

    # Stable ID migration for old data.
    seen = set()
    generated = []
    for sid in df["site_id"].astype(str):
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

    # Put known columns first, preserve unknown columns after them.
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
        st.info("Cloudtype 환경변수 또는 Streamlit Secrets에 API 키를 등록한 뒤 다시 실행하세요.")
        return False
    return True


# ------------------------- Google Sheets ----------------------
def get_gspread_client():
    if not GS_AVAILABLE or not GOOGLE_SHEET_ID:
        return None
    try:
        # Supports the nested Streamlit secrets format used by the previous version.
        service_info = None
        try:
            service_info = st.secrets.get("gcp_service_account")
        except Exception:
            service_info = None
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


def get_or_create_ws(sh, title, rows=100, cols=30):
    try:
        return sh.worksheet(title)
    except Exception:
        return sh.add_worksheet(title=title, rows=str(max(rows, 100)), cols=str(max(cols, 20)))


def load_target_data(tab_name: str) -> pd.DataFrame:
    gc = get_gspread_client()
    if gc:
        try:
            sh = gc.open_by_key(GOOGLE_SHEET_ID)
            ws = get_or_create_ws(sh, tab_name)
            records = ws.get_all_records()
            return normalize_df(pd.DataFrame(records)) if records else pd.DataFrame(columns=TARGET_COLS)
        except Exception as e:
            st.warning(f"Google Sheets 불러오기 실패: {e}")
            return pd.DataFrame(columns=TARGET_COLS)

    filename = f"{tab_name}.csv"
    if os.path.exists(filename):
        try:
            return normalize_df(pd.read_csv(filename))
        except Exception as e:
            st.error(f"CSV 불러오기 실패: {e}")
    return pd.DataFrame(columns=TARGET_COLS)


def save_target_data(tab_name: str, df: pd.DataFrame) -> bool:
    df_save = normalize_df(df)
    gc = get_gspread_client()

    if gc:
        try:
            sh = gc.open_by_key(GOOGLE_SHEET_ID)
            ws = get_or_create_ws(sh, tab_name, rows=len(df_save) + 50, cols=max(len(df_save.columns), 20))
            # Keep the existing working behavior for compatibility, but make it
            # explicit and normalized. Activity history is stored separately.
            ws.clear()
            values = [df_save.columns.tolist()] + df_save.fillna("").astype(object).values.tolist()
            ws.update(values=values, range_name="A1")
            return True
        except Exception as e:
            st.error(f"Google Sheets 저장 실패: {e}")
            return False

    try:
        df_save.to_csv(f"{tab_name}.csv", index=False, encoding="utf-8-sig")
        return True
    except Exception as e:
        st.error(f"CSV 저장 실패: {e}")
        return False


def append_activity(site_id: str, tab_name: str, before: dict, after: dict, action: str) -> bool:
    """Append one cumulative activity row to a separate Google worksheet."""
    gc = get_gspread_client()
    if not gc:
        # During CSV-only development, maintain a local activity file.
        path = "activity_log.csv"
        row = activity_row(site_id, tab_name, before, after, action)
        try:
            old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
            pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(path, index=False, encoding="utf-8-sig")
            return True
        except Exception as e:
            st.warning(f"활동 이력 저장 실패: {e}")
            return False

    try:
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        ws = get_or_create_ws(sh, "activity_log", rows=1000, cols=12)
        headers = [
            "기록일시", "site_id", "지역탭", "상호명", "지번주소",
            "접촉방식", "상태", "면적", "메모", "변경내역", "행동"
        ]
        if not ws.get_all_values():
            ws.update(values=[headers], range_name="A1")
        row = activity_row(site_id, tab_name, before, after, action)
        ws.append_row([row.get(h, "") for h in headers], value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.warning(f"활동 이력 저장 실패: {e}")
        return False


def activity_row(site_id, tab_name, before, after, action):
    changes = []
    for label, key in [("상태", "상태"), ("방식", "컨택방식"), ("면적", "면적"), ("상호명", "상호명"), ("메모", "메모")]:
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


def load_activity_log() -> pd.DataFrame:
    gc = get_gspread_client()
    if gc:
        try:
            sh = gc.open_by_key(GOOGLE_SHEET_ID)
            ws = get_or_create_ws(sh, "activity_log", rows=1000, cols=12)
            values = ws.get_all_records()
            return pd.DataFrame(values) if values else pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    if os.path.exists("activity_log.csv"):
        try:
            return pd.read_csv("activity_log.csv")
        except Exception:
            pass
    return pd.DataFrame()

# ------------------------- Kakao API --------------------------
def kakao_headers():
    return {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}


def kakao_get(path: str, params: dict, timeout: int = 10):
    url = f"https://dapi.kakao.com{path}"
    response = requests.get(url, headers=kakao_headers(), params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=86400, show_spinner=False)
def geocode_address(address: str):
    try:
        data = kakao_get("/v2/local/search/address.json", {"query": address})
        if not data.get("documents"):
            return None
        d = data["documents"][0]
        return {"lat": float(d["y"]), "lng": float(d["x"]), "b_code": d.get("address", {}).get("b_code", "")}
    except Exception:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def reverse_geocode(lat: float, lng: float):
    try:
        data = kakao_get("/v2/local/geo/coord2address.json", {"x": lng, "y": lat})
        if not data.get("documents"):
            return "직접 입력 필요", ""
        d = data["documents"][0]
        address = d.get("address") or {}
        road = d.get("road_address") or {}
        address_name = address.get("address_name") or road.get("address_name") or "직접 입력 필요"
        return address_name, ""
    except Exception:
        return "직접 입력 필요", ""


@st.cache_data(ttl=86400, show_spinner=False)
def place_name_for_address(address: str):
    try:
        data = kakao_get("/v2/local/search/keyword.json", {"query": address})
        if data.get("documents"):
            return data["documents"][0].get("place_name", "")
    except Exception:
        pass
    return ""


def get_place_info_from_coords(lat, lng):
    address_name, _ = reverse_geocode(lat, lng)
    building_name = place_name_for_address(address_name) if address_name != "직접 입력 필요" else ""
    return address_name, building_name

# ------------------------- Data discovery ----------------------
def fetch_building_targets(sigungu_cd: str, bjdong_cd: str):
    raw = []
    page_no = 1
    total_count = 0
    progress = st.progress(0)
    status_box = st.empty()

    while True:
        url = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
        params = {
            "serviceKey": DATA_GO_KR_KEY,
            "sigunguCd": sigungu_cd,
            "bjdongCd": bjdong_cd,
            "numOfRows": 100,
            "pageNo": page_no,
            "_type": "json",
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            header = data.get("response", {}).get("header", {})
            if header.get("resultCode") != "00":
                raise RuntimeError(header.get("resultMsg", "건축물대장 API 오류"))
            body = data["response"]["body"]
            total_count = int(body.get("totalCount", 0) or 0)
            items = body.get("items", {}).get("item", [])
            if isinstance(items, dict):
                items = [items]
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
            progress.progress(min(page_no * 100 / max(total_count, 1), 1.0))
            status_box.info(f"건축물대장 수집 중: {min(page_no * 100, total_count)}/{total_count}")
            if page_no * 100 >= total_count:
                break
            page_no += 1
        except Exception as e:
            progress.empty(); status_box.empty()
            raise RuntimeError(f"건축물대장 조회 실패: {e}")

    progress.empty(); status_box.empty()
    return raw


def build_target_df(sido, sigungu, dong, min_area):
    center = geocode_address(f"{sido} {sigungu} {dong}")
    if not center or not center.get("b_code"):
        raise RuntimeError("선택한 읍/면/동의 좌표 또는 법정동코드를 찾지 못했습니다.")

    sigungu_cd = center["b_code"][:5]
    bjdong_cd = center["b_code"][5:]
    raw = fetch_building_targets(sigungu_cd, bjdong_cd)
    if not raw:
        return pd.DataFrame(columns=TARGET_COLS), center

    raw_df = pd.DataFrame(raw)
    grouped = raw_df.groupby("지번주소", as_index=False).agg({
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
            "site_id": "", "상호명": name, "지번주소": addr,
            "면적": round(float(row["건축면적(㎡)"]), 1),
            "lat": lat, "lng": lng, "상태": "미컨택", "컨택방식": "미진행",
            "등록일시": now_str(), "수정일시": now_str(), "메모": "",
            "최근수정내역": "", "수동등록": False,
        })
        bar.progress(i / len(filtered))
        box.info(f"주소 좌표/상호명 변환 중: {i}/{len(filtered)}")
    bar.empty(); box.empty()
    result = normalize_df(pd.DataFrame(rows))
    return result[result["lat"].ne(0) & result["lng"].ne(0)].reset_index(drop=True), center

# ------------------------- Region/search UI ------------------
st.markdown('<div class="section-title">타겟 지역 및 조건 설정</div>', unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)
with col1:
    sido = st.selectbox("시/도", list(REGION_DATA.keys()))
with col2:
    sigungu = st.selectbox("시/군/구", list(REGION_DATA[sido].keys()))
with col3:
    dong = st.selectbox("읍/면/동", REGION_DATA[sido][sigungu])
min_area = st.number_input("최소 건축면적 (㎡)", min_value=100, value=5000, step=500)
target_tab_name = f"target_{sido}_{sigungu}_{dong}"

if st.button("데이터 조회 및 지도 적용", use_container_width=True, type="primary"):
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
        st.session_state.search_center = [center["lat"], center["lng"]]
        st.session_state.map_zoom = 15

        if not existing.empty:
            st.session_state.target_data = existing
            st.session_state.last_loaded_tab = target_tab_name
            st.success(f"기존 데이터 {len(existing):,}건을 불러왔습니다.")
        else:
            with st.spinner("최초 1회 타겟 DB를 구축합니다. 대상이 많으면 시간이 걸릴 수 있습니다."):
                built, center = build_target_df(sido, sigungu, dong, min_area)
            if built.empty:
                st.info("조건에 일치하는 데이터가 없습니다.")
            else:
                if save_target_data(target_tab_name, built):
                    st.session_state.target_data = built
                    st.session_state.last_loaded_tab = target_tab_name
                    st.success(f"신규 타겟 DB 구축 완료: {len(built):,}건")
    except Exception as e:
        st.error(f"조회/구축 중 오류: {e}")

# ------------------------- Map -------------------------------
st.divider()
st.markdown('<div class="helper-text">안내: 지도 빈 공간을 터치하면 신규 현장을 등록할 수 있습니다.</div>', unsafe_allow_html=True)

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

m = folium.Map(location=st.session_state.search_center, zoom_start=st.session_state.map_zoom, max_zoom=19, tiles=None)
folium.TileLayer(
    tiles="https://xdworld.vworld.kr/2d/Satellite/service/{z}/{x}/{y}.jpeg",
    attr="VWorld", name="위성지도", max_zoom=19, max_native_zoom=18, control=False
).add_to(m)
folium.raster_layers.WmsTileLayer(
    url="https://api.vworld.kr/req/wms",
    layers="lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun",
    styles="lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun",
    format="image/png", transparent=True, version="1.3.0",
    key=VWORLD_KEY, domain=VWORLD_DOMAIN,
    attr="VWorld Cadastral", name="지적도(지번경계)", overlay=True,
    control=True, opacity=0.6, show=False
).add_to(m)
folium.LayerControl().add_to(m)
LocateControl(position="topleft", strings={"title":"내 위치 확인", "popup":"현재 위치"}, drawCircle=True, showPopup=False, keepCurrentZoomLevel=False).add_to(m)
m.add_child(MeasureControl(position="topright", primary_length_unit="meters", secondary_length_unit=None, primary_area_unit="sqmeters", secondary_area_unit=None))

compass_html = """
<div style="position:absolute;top:120px;left:11px;z-index:1000;background:rgba(255,255,255,.9);padding:4px;border-radius:6px;border:2px solid rgba(0,0,0,.2);box-shadow:0 1px 4px rgba(0,0,0,.3);width:32px;height:32px;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none;">
<div style="font-size:10px;font-weight:900;color:#ef4444;line-height:1;">N</div>
<div style="font-size:13px;font-weight:900;line-height:1;">▲</div>
</div>
"""
m.get_root().html.add_child(folium.Element(compass_html))

m.get_root().header.add_child(folium.Element("""
<style>
.leaflet-control-measure .coordinatetracker{display:none!important;}
.leaflet-control-measure h3,.leaflet-control-measure .prompt{font-size:0!important;}
.leaflet-control-measure h3::after{content:'지붕 면적 실측';font-size:13px!important;font-weight:600;display:block;margin-bottom:5px;color:#374151;}
.leaflet-control-measure .prompt::after{content:'지붕 모서리를 따라 점을 지정하세요 (완료: 더블클릭)';font-size:11px!important;display:block;color:#6b7280;}
</style>
"""))

df_all = normalize_df(st.session_state.target_data)
st.session_state.target_data = df_all

df_filtered = df_all[df_all["면적"] >= float(min_area)].copy() if not df_all.empty else df_all
marker_cluster = MarkerCluster().add_to(m)

for _, row in df_filtered.iterrows():
    if not row["lat"] or not row["lng"]:
        continue
    selected = st.session_state.selected_site_id == row["site_id"]
    color = "purple" if selected else STATUS_COLORS.get(row.get("상태", "미컨택"), "red")
    icon = "star" if selected or bool(row.get("수동등록", False)) else "info-sign"
    name = html.escape(str(row.get("상호명", "")) or "상호명 미상")
    addr = html.escape(str(row.get("지번주소", "")))
    popup = f"<b>{name}</b><br>{addr}<br>면적: {float(row['면적']):,.1f}㎡<br>상태: {html.escape(str(row.get('상태','')))}"
    folium.Marker(
        [row["lat"], row["lng"]],
        tooltip=name,
        popup=folium.Popup(popup, max_width=280),
        icon=folium.Icon(color=color, icon=icon),
    ).add_to(marker_cluster)

map_data = st_folium(m, width="100%", height=450, returned_objects=["last_object_clicked", "last_clicked"])
clicked_marker = map_data.get("last_object_clicked")
clicked_map = map_data.get("last_clicked")

# Marker click: match by coordinates but select by stable site_id.
if clicked_marker:
    matched = df_all[(abs(df_all["lat"] - clicked_marker["lat"]) < 0.0001) & (abs(df_all["lng"] - clicked_marker["lng"]) < 0.0001)]
    if not matched.empty:
        row = matched.iloc[0]
        if st.session_state.selected_site_id != row["site_id"]:
            st.session_state.selected_site_id = row["site_id"]
            st.session_state.selected_addr = row["지번주소"]
            st.session_state.new_pin_coord = None
            st.session_state.search_center = [float(row["lat"]), float(row["lng"])]
            st.rerun()

# Blank map click: avoid accidental registration close to an existing target.
if clicked_map:
    lat, lng = float(clicked_map["lat"]), float(clicked_map["lng"])
    is_marker_click = bool(clicked_marker) and abs(clicked_marker["lat"] - lat) <= 0.001 and abs(clicked_marker["lng"] - lng) <= 0.001
    if not is_marker_click:
        if not df_all.empty:
            valid = df_all[(df_all["lat"] != 0) & (df_all["lng"] != 0)].copy()
            if not valid.empty:
                # Simple degree distance is sufficient at this small map scale.
                distances = ((valid["lat"] - lat) ** 2 + (valid["lng"] - lng) ** 2) ** 0.5
                nearest_idx = distances.idxmin()
                nearest_dist = float(distances.loc[nearest_idx])
                if nearest_dist < 0.0007:
                    nearest = valid.loc[nearest_idx]
                    st.session_state.selected_site_id = nearest["site_id"]
                    st.session_state.selected_addr = nearest["지번주소"]
                    st.session_state.new_pin_coord = None
                    st.session_state.search_center = [float(nearest["lat"]), float(nearest["lng"])]
                    st.toast("기존 등록 현장을 불러왔습니다.")
                    st.rerun()
        current = st.session_state.new_pin_coord
        if not current or abs(current["lat"] - lat) > 0.0001 or abs(current["lng"] - lng) > 0.0001:
            st.session_state.new_pin_coord = {"lat": lat, "lng": lng}
            st.session_state.selected_site_id = None
            st.session_state.selected_addr = None
            st.session_state.search_center = [lat, lng]
            st.rerun()

# ------------------------- Existing target ---------------------
selected_comp = None
if st.session_state.selected_site_id:
    matched = df_all[df_all["site_id"] == st.session_state.selected_site_id]
    if not matched.empty:
        selected_comp = matched.iloc[0]
    else:
        st.session_state.selected_site_id = None
        st.session_state.selected_addr = None

if selected_comp is not None:
    comp = selected_comp
    st.markdown("<br>", unsafe_allow_html=True)
    display_name = str(comp.get("상호명", "")) or "상호명 미상"
    st.markdown(f"**{html.escape(display_name)}**  ·  {float(comp['면적']):,.1f}㎡")
    st.caption(f"현장ID: {comp['site_id']}  |  최초 등록: {comp.get('등록일시','-')}  |  최근 수정: {comp.get('수정일시','-')}")
    st.code(str(comp.get("지번주소", "")), language="text")

    encoded_addr = urllib.parse.quote(str(comp.get("지번주소", "")))
    c1, c2, c3 = st.columns(3)
    with c1: st.link_button("네이버지도", f"https://map.naver.com/p/search/{encoded_addr}", use_container_width=True)
    with c2: st.link_button("카카오맵", f"https://map.kakao.com/link/search/{encoded_addr}", use_container_width=True)
    with c3: st.link_button("티맵(App)", f"tmap://search?name={encoded_addr}", use_container_width=True)

    st.divider()
    edited_name = st.text_input("상호명 (간판 기준)", value=str(comp.get("상호명", "")), key=f"edit_name_{comp['site_id']}")
    edited_area = st.number_input("지붕 실측 면적(㎡)", min_value=0.0, value=float(comp.get("면적", 0.0)), step=50.0, key=f"edit_area_{comp['site_id']}")

    is_installed = st.checkbox("태양광 기설치 완료 (또는 불가 현장)", value=str(comp.get("상태", "")) == "기설치", key=f"installed_{comp['site_id']}")
    current_method = str(comp.get("컨택방식", "미진행"))
    if current_method in METHOD_OPTIONS:
        method_idx = METHOD_OPTIONS.index(current_method)
        custom_val = ""
    else:
        method_idx = METHOD_OPTIONS.index("기타")
        custom_val = current_method
    selected_contact = st.radio("컨택방식", METHOD_OPTIONS, index=method_idx, horizontal=True, key=f"method_{comp['site_id']}")
    final_method = selected_contact
    if selected_contact == "기타":
        final_method = st.text_input("기타 방식 입력", value=custom_val, placeholder="예: 우편, 지인 소개 등", key=f"custom_{comp['site_id']}").strip() or "기타"

    if selected_contact == "미진행":
        final_status = "기설치" if is_installed else "미컨택"
    else:
        contact_status_options = [x for x in STATUS_OPTIONS if x not in ("미컨택", "기설치")]
        current_status = str(comp.get("상태", "협의중"))
        status_idx = contact_status_options.index(current_status) if current_status in contact_status_options else 0
        chosen_status = st.radio("상세 단계", contact_status_options, index=status_idx, horizontal=True, key=f"status_{comp['site_id']}")
        final_status = "기설치" if is_installed else chosen_status

    memo = st.text_area("현장 특이사항 및 미팅 노트", value=str(comp.get("메모", "")), key=f"memo_{comp['site_id']}")

    if st.button("변경사항 저장", use_container_width=True, type="primary", key=f"save_{comp['site_id']}"):
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
        # Keep a concise last-change summary for the existing UI.
        changes = []
        for label, key in [("상태", "상태"), ("방식", "컨택방식"), ("면적", "면적"), ("상호명", "상호명")]:
            if str(before.get(key, "")) != str(after.get(key, "")):
                changes.append(f"{label}({before.get(key,'')}→{after.get(key,'')})")
        if str(before.get("메모", "")).strip() != str(after.get("메모", "")).strip():
            changes.append("메모수정")
        after["최근수정내역"] = " | ".join(changes) if changes else "단순열람(수정없음)"

        updated = df_all.copy()
        mask = updated["site_id"] == comp["site_id"]
        for key, value in after.items():
            if key in updated.columns:
                updated.loc[mask, key] = value
        updated = normalize_df(updated)

        if save_target_data(st.session_state.current_tab, updated):
            append_activity(comp["site_id"], st.session_state.current_tab, before, after, "수정")
            st.session_state.target_data = updated
            st.session_state.save_success = True
            st.rerun()

# ------------------------- New target -------------------------
elif st.session_state.new_pin_coord:
    new_lat = float(st.session_state.new_pin_coord["lat"])
    new_lng = float(st.session_state.new_pin_coord["lng"])
    st.info("선택하신 위치에 신규 타겟을 등록합니다.")
    auto_address, auto_name = get_place_info_from_coords(new_lat, new_lng)

    with st.form("new_pin_form", clear_on_submit=True):
        new_addr = st.text_input("지번 주소", value=auto_address)
        new_name = st.text_input("상호명", value=auto_name)
        new_area = st.number_input("예상 지붕 면적(㎡)", min_value=0.0, value=float(min_area), step=100.0)
        if st.form_submit_button("신규 현장 등록", use_container_width=True):
            # Address duplicate check first.
            duplicate = df_all[df_all["지번주소"].astype(str).str.strip() == new_addr.strip()]
            if not duplicate.empty:
                st.warning(f"이미 등록된 주소입니다. 현장ID: {duplicate.iloc[0]['site_id']}")
                st.session_state.selected_site_id = duplicate.iloc[0]["site_id"]
                st.session_state.selected_addr = duplicate.iloc[0]["지번주소"]
                st.session_state.new_pin_coord = None
                st.rerun()
            else:
                sid = new_site_id(df_all)
                stamp = now_str()
                new_row = {
                    "site_id": sid, "상호명": new_name.strip(), "지번주소": new_addr.strip(),
                    "면적": float(new_area), "lat": new_lat, "lng": new_lng,
                    "상태": "미컨택", "컨택방식": "미진행", "등록일시": stamp,
                    "수정일시": stamp, "수동등록": True, "메모": "",
                    "최근수정내역": "신규 현장 발굴 및 등록",
                }
                updated = normalize_df(pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True))
                if save_target_data(st.session_state.current_tab, updated):
                    append_activity(sid, st.session_state.current_tab, {}, new_row, "신규등록")
                    st.session_state.target_data = updated
                    st.session_state.selected_site_id = sid
                    st.session_state.selected_addr = new_addr.strip()
                    st.session_state.new_pin_coord = None
                    st.session_state.save_success = True
                    if new_area < min_area:
                        st.warning("데이터는 저장되었지만 최소 면적 미달이라 현재 지도 필터에서는 표시되지 않습니다.")
                    st.rerun()

# ------------------------- Daily activity log -----------------
st.divider()
st.markdown('<div class="section-title">일자별 영업일지</div>', unsafe_allow_html=True)
selected_date = st.date_input("조회 일자 선택", value=datetime.today())
date_str = selected_date.strftime("%Y-%m-%d")

activity = load_activity_log()
if not activity.empty and "기록일시" in activity.columns:
    activity["기록일시"] = activity["기록일시"].fillna("").astype(str)
    daily = activity[activity["기록일시"].str.startswith(date_str)].copy().sort_values("기록일시")
    if daily.empty:
        st.info(f"{date_str} 기준 영업 이력이 없습니다.")
    else:
        st.success(f"조회 결과: 총 {len(daily):,}건의 활동이 있습니다.")
        for _, row in daily.iloc[::-1].iterrows():
            title = html.escape(str(row.get("상호명", "")) or "상호명 미상")
            addr = html.escape(str(row.get("지번주소", "")))
            changes = html.escape(str(row.get("변경내역", "")))
            memo = html.escape(str(row.get("메모", "")))
            st.markdown(f"**{title}** ({html.escape(str(row.get('상태','')))})")
            st.caption(f"{addr} | 접촉: {row.get('접촉방식','')} | 시간: {row.get('기록일시','')} | {row.get('site_id','')}")
            if changes:
                st.markdown(f"<div style='font-size:13px;color:#ea580c;font-weight:600;'>🔄 {changes}</div>", unsafe_allow_html=True)
            if memo:
                st.markdown(f"<div style='background:#f3f4f6;padding:10px;border-radius:6px;font-size:13px;color:#4b5563;margin-top:5px;'>{memo}</div>", unsafe_allow_html=True)
            st.markdown("<hr style='margin:15px 0;border-top:1px solid #e5e7eb;'>", unsafe_allow_html=True)
else:
    st.info("아직 누적 영업활동 이력이 없습니다. 현장을 수정/등록하면 이력에 쌓입니다.")

# Small status footer for deployment checks.
mode = "Google Sheets" if sheets_enabled() else "CSV(개발/임시)"
st.caption(f"저장 모드: {mode}  |  현재 지역: {sido} {sigungu} {dong}")
