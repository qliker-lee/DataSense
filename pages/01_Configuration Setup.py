# streamlit 기반 YAML Config Editor + Directory Inspector
# 2025.11.05  Qliker 
# (full editor: directories / source_directories / source_prefixes + advanced + inspector)
# -------------------------------------------------------------------
# 1. 경로 설정 (Streamlit warnings import 전에 필요)
# -------------------------------------------------------------------
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# -------------------------------------------------------------------
# 2. 컴파일 발생하는 Streamlit 경고 메시지 억제 설정 (Streamlit import 전에 호출)
# -------------------------------------------------------------------
from util.streamlit_warnings import setup_streamlit_warnings
setup_streamlit_warnings()

# from __future__ import annotations
import os
import sys
import shutil
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import datetime as dt

import streamlit as st
import yaml
import pandas as pd

# ------------------------------------------------------------
# 프로젝트 경로 & 기본 YAML 경로/파일 설정
# ------------------------------------------------------------
CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# ✅ 기본 YAML 위치/파일명
YAML_DIR_DEFAULT = PROJECT_ROOT / "util"
YAML_FILE_DEFAULT = "DataSense_Config.yaml"

# # ▶ 환경변수로 오버라이드 (선택)
# YAML_DIR_ENV = os.environ.get("DS_YAML_DIR")
# YAML_FILE_ENV = os.environ.get("DS_YAML_FILE")

# -------------------------------------------------------------------
# 폰트 크기 조정 및 색상 변경 (신규추가)
# -------------------------------------------------------------------
st.markdown("""<style> html, body, [class*="css"]  { font-size: 14px; } </style> """, unsafe_allow_html=True)
def load_css(file_name):
    path = Path(file_name)
    if not path.is_absolute():
        path = PROJECT_ROOT / file_name
    with open(path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css("styles/styles.css")
# -------------------------------------------------------------------
# App Config
# -------------------------------------------------------------------

APP_NAME = "Configuration Setup"
APP_DESC = "#### DataSense를 수행하기 위한 환경변수를 설정합니다. 초기에 수행합니다. "
APP_KOR_NAME = "환경 설정 편집기"
APP_VER = "2.4"

# ------------------------------------------------------------
# 외부 유틸(있으면 사용, 없으면 안전 폴백)
# ------------------------------------------------------------
try:
    from util.Files_FunctionV20 import set_page_config
except Exception:
    def set_page_config(meta: Any):
        if isinstance(meta, dict):
            st.set_page_config(
                page_title=meta.get("APP_NAME", "Configuration Setup"),
                layout="wide",
                page_icon="🛠️",
            )
        else:
            st.set_page_config(
                page_title=str(meta),
                layout="wide",
                page_icon="🛠️",
            )

# -------------------------------------------------------------------
# 유틸 함수
# -------------------------------------------------------------------
def _safe_load_yaml(p: Path) -> Dict[str, Any]:
    """안전한 Configuration File 로드 (여러 인코딩 시도)"""
    encs = ("utf-8", "utf-8-sig", "euc-kr", "cp949")
    last_err = None
    for enc in encs:
        try:
            with open(p, "r", encoding=enc) as f:
                obj = yaml.safe_load(f) or {}
            return obj
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Configuration File 로드 실패: {p} :: {last_err}")

def _auto_find_yaml() -> Optional[Path]:
    """
    DS_00_Main_Config.yaml 자동 탐색
    - CWD
    - CWD/util
    - 프로젝트 상위 추정 경로들
    - util
    """
    candidates = [
        Path.cwd() / "DS_00_Main_Config.yaml",
        Path.cwd() / "util" / "DS_00_Main_Config.yaml",
        Path.cwd().parent / "DS_00_Main_Config.yaml",
        Path.cwd().parent / "util" / "DS_00_Main_Config.yaml",
        Path.cwd() / "util" / "DS_00_Main_Config.yaml",
        Path.cwd().parent / "util" / "DS_00_Main_Config.yaml",
        PROJECT_ROOT / "util" / "DS_00_Main_Config.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

def _expand_path(base: Path, p: str) -> Path:
    """환경변수/홈(~)/상대경로를 포함할 수 있는 문자열을 절대경로로 정규화"""
    s = os.path.expandvars(str(p or "").strip())
    s = os.path.expanduser(s)
    q = Path(s)
    if not q.is_absolute():
        q = (base / q)
    return q.resolve()

def _fmt_bytes(n: int) -> str:
    """바이트를 인간이 읽기 쉬운 형식으로 변환"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.0f} PB"

def _safe_dump_yaml(data: Dict[str, Any]) -> str:
    """안전한 YAML 덤프"""
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

def _backup_file(path: Path) -> Path:
    """파일 백업"""
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak_{ts}")
    shutil.copy2(path, bak)
    return bak

def _atomic_write(path: Path, content: str) -> None:
    """원자적 파일 쓰기"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)

def _resolve_dir(root_path: str, value: str) -> Path:
    """ROOT_PATH + value(상대) → 절대경로, 이미 절대면 그대로"""
    value = (value or "").strip()
    if not value:
        return Path(root_path or "").resolve()
    if Path(value).is_absolute():
        return Path(value).resolve()
    base = Path(root_path or PROJECT_ROOT)
    return (base / value).resolve()

def _is_abs(p: str) -> bool:
    """절대 경로인지 확인"""
    try:
        return Path(p).is_absolute()
    except Exception:
        return False

# ------------------------------------------------------------
# 데이터 모델
# ------------------------------------------------------------
@dataclass
class ConfigFile:
    path: str
    data: Dict[str, Any]

# ------------------------------------------------------------
# 세션/경로 헬퍼
# ------------------------------------------------------------
def _init_session_defaults():
    """세션 상태 초기화"""
    if "yaml_dir" not in st.session_state:
        st.session_state.yaml_dir = str(YAML_DIR_DEFAULT)
    if "yaml_file" not in st.session_state:
        st.session_state.yaml_file = str(YAML_FILE_DEFAULT)
    if "yaml_path" not in st.session_state:
        st.session_state.yaml_path = ""
    if "yaml_data" not in st.session_state:
        st.session_state.yaml_data = {}

def _current_yaml_path() -> Path:
    """현재 설정된 YAML 경로 반환"""
    yaml_dir = YAML_DIR_DEFAULT
    yaml_file = YAML_FILE_DEFAULT
    return yaml_dir / yaml_file

# ------------------------------------------------------------
# 고급(전체 YAML) 재귀 에디터 유틸
# ------------------------------------------------------------
def _coerce(value_type_sample: Any, new_value_str: str) -> Any:
    """원래 값의 타입에 최대한 맞춰 캐스팅"""
    if isinstance(value_type_sample, bool):
        return str(new_value_str).strip().lower() in {"true", "1", "y", "yes", "on"}
    if isinstance(value_type_sample, int):
        try:
            return int(str(new_value_str).strip())
        except Exception:
            return new_value_str
    if isinstance(value_type_sample, float):
        try:
            return float(str(new_value_str).strip())
        except Exception:
            return new_value_str
    if value_type_sample is None:
        txt = str(new_value_str).strip().lower()
        return None if txt in {"none", "null", ""} else new_value_str
    return new_value_str

def _render_scalar_editor(label: str, value: Any, key: str):
    """스칼라 값 편집기"""
    if isinstance(value, bool):
        return st.checkbox(label, value=value, key=key)
    if isinstance(value, int):
        return st.number_input(label, value=value, step=1, key=key)
    if isinstance(value, float):
        return st.number_input(label, value=value, key=key)
    return st.text_input(label, value="" if value is None else str(value), key=key)

def _edit_node(node: Any, base_key: str, level: int = 0, allow_top_expanders: bool = True) -> Any:
    """dict/list/scalar 전부 편집 가능(재귀)"""
    # Dict
    if isinstance(node, dict):
        edited: Dict[str, Any] = {}
        for k, v in node.items():
            label = f"{k}"
            if level == 0 and allow_top_expanders:
                with st.expander(f"📂 {label}", expanded=False):
                    edited[k] = _edit_node(v, f"{base_key}.{k}", level + 1, allow_top_expanders=True)
            else:
                st.markdown(f"**{label}**")
                edited[k] = _edit_node(v, f"{base_key}.{k}", level + 1, allow_top_expanders=True)

        # 키 추가
        if level == 0 and allow_top_expanders:
            with st.expander("➕ 키 추가", expanded=False):
                new_k = st.text_input("새 키", key=f"{base_key}.__add_key__")
                new_v = st.text_input("새 값(문자열)", key=f"{base_key}.__add_val__")
                if st.button("추가", key=f"{base_key}.__add_btn__"):
                    if new_k.strip():
                        edited[new_k.strip()] = new_v
                        st.success("추가됨. 저장 버튼으로 반영하세요.")
        elif level == 0 and not allow_top_expanders:
            col_k, col_v, col_btn = st.columns([3, 6, 1])
            with col_k:
                new_k = st.text_input("새 키", key=f"{base_key}.__add_key__plain")
            with col_v:
                new_v = st.text_input("새 값(문자열)", key=f"{base_key}.__add_val__plain")
            with col_btn:
                if st.button("추가", key=f"{base_key}.__add_btn__plain"):
                    if new_k.strip():
                        edited[new_k.strip()] = new_v
                        st.success("추가됨. 저장 버튼으로 반영하세요.")
        return edited

    # List
    if isinstance(node, list):
        edited_list: List[Any] = list(node)
        for i, item in enumerate(list(edited_list)):
            title = f"[{i}] {type(item).__name__}"
            if level == 0 and allow_top_expanders:
                with st.expander(f"🔹 {title}", expanded=False):
                    if isinstance(item, (dict, list)):
                        edited_item = _edit_node(item, f"{base_key}[{i}]", level + 1, allow_top_expanders=True)
                    else:
                        edited_item_raw = _render_scalar_editor("값", item, key=f"{base_key}[{i}]")
                        edited_item = _coerce(item, str(edited_item_raw))
                    col_a, col_b = st.columns([1, 1])
                    with col_b:
                        if st.button("삭제", key=f"{base_key}.__del__{i}"):
                            edited_list.pop(i)
                            st.rerun()
                    if i < len(edited_list):
                        edited_list[i] = edited_item
            else:
                st.markdown(f"**{title}**")
                if isinstance(item, (dict, list)):
                    edited_item = _edit_node(item, f"{base_key}[{i}]", level + 1, allow_top_expanders=True)
                else:
                    edited_item_raw = _render_scalar_editor("값", item, key=f"{base_key}[{i}]")
                    edited_item = _coerce(item, str(edited_item_raw))
                col_a, col_b = st.columns([1, 1])
                with col_b:
                    if st.button("삭제", key=f"{base_key}.__del__{i}"):
                        edited_list.pop(i)
                        st.rerun()
                if i < len(edited_list):
                    edited_list[i] = edited_item

        # 항목 추가
        if level == 0 and allow_top_expanders:
            with st.expander("➕ 리스트 항목 추가", expanded=False):
                new_item = st.text_input("새 항목(문자열)", key=f"{base_key}.__append__")
                if st.button("추가", key=f"{base_key}.__append_btn__"):
                    edited_list.append(new_item)
                    st.rerun()
        else:
            col_add, col_btn = st.columns([6, 1])
            with col_add:
                new_item = st.text_input("새 항목(문자열)", key=f"{base_key}.__append__plain")
            with col_btn:
                if st.button("추가", key=f"{base_key}.__append_btn__plain"):
                    edited_list.append(new_item)
                    st.rerun()
        return edited_list

    # Scalar
    raw = _render_scalar_editor("값", node, key=f"{base_key}.__scalar__")
    return _coerce(node, str(raw))

# ------------------------------------------------------------
# 편집 매니저
# ------------------------------------------------------------
class ConfigEditorManager:
    """Configuration Editor 관리 클래스"""
    
    def __init__(self):
        self.config_file: Optional[ConfigFile] = None

    def load_config(self) -> bool:
        """세션의 yaml_dir/yaml_file을 합쳐 로드"""
        try:
            path = _current_yaml_path()
            if not path.exists():
                st.warning(f"YAML 파일을 찾을 수 없습니다: {path}")
                st.info("경로와 파일명을 확인하거나 아래에서 직접 파일을 선택하세요.")
                return False
            data = _safe_load_yaml(path)
            st.session_state.yaml_data = data
            st.session_state.yaml_path = str(path)
            self.config_file = ConfigFile(path=str(path), data=data)
            st.success(f"✅ 설정 로드: {path}")
            return True
        except Exception as e:
            st.error(f"YAML 로드 중 오류: {e}")
            return False

    def pick_file_ui(self) -> None:
        """경로/파일명을 사용자가 직접 조정"""
        with st.expander("🔧 Configuration File ", expanded=True):
            col1, col2, col3 = st.columns([3, 3, 1])
            with col1:
                # yaml_dir = st.text_input("폴더", value=st.session_state.get("yaml_dir", ""), key="inp_yaml_dir")
                yaml_dir = st.session_state.get("yaml_dir", "")
                st.text("폴더: " + yaml_dir)

            with col2:
                yaml_file = st.session_state.get("yaml_file", "")
                st.text("파일명: " + yaml_file)
            # with col3:
            #     if st.button("적용", key="btn_apply_yaml_path"):
            #         st.session_state.yaml_dir = yaml_dir.strip()
            #         st.session_state.yaml_file = yaml_file.strip()
            #         st.session_state.yaml_path = ""
            #         st.info(f"경로/파일 적용: {yaml_dir} / {yaml_file}")

            # col4, col5 = st.columns([1, 3])
            # with col4:
            if st.button("📂 로드", key="btn_try_load"):
                self.load_config()
            # with col5:
            #     st.caption(f"예상 파일 경로: `{_current_yaml_path()}`")

        with st.expander("📤 또는 파일 업로드로 편집", expanded=False):
            up = st.file_uploader("설정파일 업로드", type=["yaml", "yml"])
            if up is not None:
                try:
                    txt = up.read().decode("utf-8")
                    data = yaml.safe_load(txt) or {}
                    st.session_state.yaml_data = data
                    st.session_state.yaml_path = ""  # 업로드 세션
                    self.config_file = ConfigFile(path="", data=data)
                    st.success("업로드된 파일로 편집합니다. (저장 시 경로/파일명에 저장)")
                except Exception as e:
                    st.error(f"업로드 파일 파싱 실패: {e}")

    def _directories_like_editor(self, data: Dict[str, Any], section_key: str) -> Dict[str, Any]:
        """section_key('directories' or 'source_directories')를 경로형으로 편집"""
        root_path = str(data.get("ROOT_PATH", ""))
        sec: Dict[str, Any] = {}
        if isinstance(data.get(section_key), dict):
            sec = dict(data.get(section_key, {}))
        else:
            sec = {}

        st.markdown(f"### 📁 {section_key} 편집")
        st.caption("상대경로는 ROOT_PATH 기준으로 실제 경로를 계산합니다.")

        edited: Dict[str, str] = {}
        to_delete: List[str] = []
        colL, colR = st.columns([3, 4])

        with colL:
            st.write("**경로 키/값**")
            if not sec:
                st.info(f"{section_key} 항목이 없습니다. 아래에서 새 키를 추가하세요.")
            for k, v in sec.items():
                c1, c2, c3 = st.columns([3, 6, 1])
                with c1:
                    st.text_input("키", value=k, disabled=True, key=f"{section_key}_key_{k}")
                with c2:
                    new_v = st.text_input("값", value=str(v or ""), key=f"{section_key}_val_{k}")
                with c3:
                    if st.button("🗑", key=f"{section_key}_del_{k}", help="이 키를 삭제합니다"):
                        to_delete.append(k)
                edited[k] = new_v

        with colR:
            st.write("**실제 경로 미리보기 / 상태**")
            rows = []
            for k, v in edited.items():
                abs_path = _resolve_dir(root_path, v)
                exists = abs_path.exists()
                rows.append({
                    "key": k,
                    "value": v,
                    "resolved_path": str(abs_path),
                    "exists": "✅" if exists else "❌",
                })
            if rows:
                prev_df = pd.DataFrame(rows)
                st.dataframe(prev_df, hide_index=True, width='stretch')

            if rows and st.button("미존재 폴더 생성", key=f"btn_make_dirs_{section_key}"):
                created, failed = [], []
                for r in rows:
                    p = Path(r["resolved_path"])
                    if not p.exists():
                        try:
                            p.mkdir(parents=True, exist_ok=True)
                            created.append(str(p))
                        except Exception as e:
                            failed.append(f"{p} -> {e}")
                if created:
                    st.success(f"생성 완료: {len(created)}개")
                    with st.expander("생성된 경로 상세"):
                        st.write("\n".join(created))
                if failed:
                    st.error("다음 경로 생성에 실패했습니다.")
                    with st.expander("실패 목록"):
                        st.write("\n".join(failed))
                if not created and not failed:
                    st.info("모든 경로가 이미 존재합니다.")

        with st.expander(f"➕ {section_key} 키 추가", expanded=False):
            new_k = st.text_input("새 키", key=f"{section_key}_add_key")
            new_v = st.text_input("새 값(상대/절대 경로)", key=f"{section_key}_add_val")
            if st.button("추가", key=f"{section_key}_add_btn"):
                nk = (new_k or "").strip()
                if not nk:
                    st.warning("키를 입력하세요.")
                elif nk in edited:
                    st.warning("이미 존재하는 키입니다.")
                else:
                    edited[nk] = new_v
                    st.success(f"'{nk}' 키 추가됨. (저장 버튼으로 반영)")

        for k in to_delete:
            edited.pop(k, None)

        data_out = dict(data)
        data_out[section_key] = edited
        return data_out

    def _simple_dict_editor(self, data: Dict[str, Any], section_key: str, title: Optional[str] = None) -> Dict[str, Any]:
        """값이 문자열인 딕셔너리용 간단 편집기"""
        title = title or f"{section_key} 편집"
        sec: Dict[str, Any] = {}
        if isinstance(data.get(section_key), dict):
            sec = dict(data.get(section_key, {}))
        else:
            sec = {}

        st.markdown(f"### 🔤 {title}")
        edited: Dict[str, str] = {}
        to_delete: List[str] = []

        if not sec:
            st.info(f"{section_key} 항목이 없습니다. 아래에서 새 키를 추가하세요.")
        for k, v in sec.items():
            c1, c2, c3 = st.columns([3, 6, 1])
            with c1:
                st.text_input("키", value=k, disabled=True, key=f"{section_key}_key_{k}")
            with c2:
                new_v = st.text_input("값", value=str(v or ""), key=f"{section_key}_val_{k}")
            with c3:
                if st.button("🗑", key=f"{section_key}_del_{k}", help="이 키를 삭제합니다"):
                    to_delete.append(k)
            edited[k] = new_v

        with st.expander(f"➕ {section_key} 키 추가", expanded=False):
            new_k = st.text_input("새 키", key=f"{section_key}_add_key")
            new_v = st.text_input("새 값", key=f"{section_key}_add_val")
            if st.button("추가", key=f"{section_key}_add_btn"):
                nk = (new_k or "").strip()
                if not nk:
                    st.warning("키를 입력하세요.")
                elif nk in edited:
                    st.warning("이미 존재하는 키입니다.")
                else:
                    edited[nk] = new_v
                    st.success(f"'{nk}' 키 추가됨. (저장 버튼으로 반영)")

        for k in to_delete:
            edited.pop(k, None)

        data_out = dict(data)
        data_out[section_key] = edited
        return data_out

    def _advanced_editor(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """고급 편집기 (전체 YAML)"""
        st.markdown("### 🧪 고급 편집기 (전체 YAML)")
        st.caption("전 섹션을 재귀적으로 편집합니다. 복잡한 구조 수정에 사용하세요.")
        return _edit_node(data, base_key="root", level=0, allow_top_expanders=False)

    def display_editor(self):
        """메인 에디터 표시"""
        if not (self.config_file and self.config_file.data):
            st.warning("⚠ 설정을 먼저 로드하세요.")
            return

        st.markdown("### ⚙️ 환경설정 편집")
        st.caption("상단에서 경로/파일을 조정한 뒤 로드하세요. 편집 후 저장을 누르면 해당 경로/파일로 저장됩니다.")

        data = dict(self.config_file.data)  # 작업용 복사

        # 1) 최상위 스칼라(문자/숫자/불리언) 간단 편집 (ROOT_PATH 포함)
        st.subheader("🔧 기본 항목")
        edited_scalars: Dict[str, Any] = {}
        # DataSense_Password는 수정 금지 및 숨김 처리
        hidden_keys = {"DataSense_Password"}
        
        for k, v in data.items():
            # DataSense_Password는 표시하지 않고 원래 값 유지
            if k in hidden_keys:
                edited_scalars[k] = v  # 원래 값 유지
                continue
            # if k in {"directories", "source_directories", "source_prefixes"}: # old
            if k in {"directories"}:
                # 아래 전용 섹션에서 처리
                edited_scalars[k] = v
                continue
            if isinstance(v, (dict, list)):
                edited_scalars[k] = v
                continue
            # 스칼라 위젯
            if isinstance(v, bool):
                edited_scalars[k] = st.checkbox(k, value=v, key=f"yaml_{k}")
            elif isinstance(v, int):
                edited_scalars[k] = st.number_input(k, value=v, step=1, key=f"yaml_{k}")
            elif isinstance(v, float):
                edited_scalars[k] = st.number_input(k, value=v, key=f"yaml_{k}")
            else:
                edited_scalars[k] = st.text_input(k, value="" if v is None else str(v), key=f"yaml_{k}")

        data.update(edited_scalars)

        # 2) 경로형 섹션: directories / source_directories
        data = self._directories_like_editor(data, "directories")
        # data = self._directories_like_editor(data, "source_directories")

        # 3) 단순 문자열 딕셔너리 섹션: source_prefixes
        # data = self._simple_dict_editor(data, "source_prefixes", title="source_prefixes (소스 접두사)")

        # 4) 고급(전체 YAML) 편집기 (선택)
        with st.expander("🧪 고급(전체 YAML) 편집기 열기", expanded=False):
            data = self._advanced_editor(data)

        # 저장/재로드/경로 표시
        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            if st.button("💾 저장", key="btn_save_yaml"):
                self.save_config(data)
        with col_b:
            if st.button("⟲ 다시 읽기", key="btn_reload_yaml"):
                self.load_config()
        with col_c:
            if st.session_state.get("yaml_path"):
                st.info(f"현재 파일: `{st.session_state['yaml_path']}`")

    def save_config(self, data: Dict[str, Any]):
        """세션의 yaml_dir/yaml_file로 저장 (없으면 기본값)"""
        try:
            target = _current_yaml_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                bak = _backup_file(target)
                st.info(f"백업 생성: {bak.name}")
            _atomic_write(target, _safe_dump_yaml(data))

            st.session_state.yaml_data = data
            st.session_state.yaml_path = str(target)
            if self.config_file:
                self.config_file.path = str(target)
                self.config_file.data = data
            st.success(f"✅ 저장 완료: {target}")
        except Exception as e:
            st.error(f"저장 실패: {e}")

# # ------------------------------------------------------------
# # Directory Inspector
# # ------------------------------------------------------------
# class DirectoryInspector:
#     """Directory Inspector 클래스"""
    
#     def __init__(self):
#         self.yaml_data: Dict[str, Any] = {}
#         self.yaml_path_used: Optional[Path] = None
#         self.recursive = True
#         self.include_hidden = False
#         self.root_path: Optional[Path] = None
#         self.root_override = ""
    
#     def load_yaml(self) -> bool:
#         """YAML 파일 로드"""
#         # 자동 탐색 시도
#         yaml_path = _auto_find_yaml()
#         if yaml_path:
#             try:
#                 self.yaml_data = _safe_load_yaml(yaml_path)
#                 self.yaml_path_used = yaml_path
#                 return True
#             except Exception:
#                 pass
        
#         # 세션에서 YAML 데이터 확인
#         if st.session_state.get("yaml_data"):
#             self.yaml_data = st.session_state.get("yaml_data", {})
#             yaml_path_str = st.session_state.get("yaml_path", "")
#             if yaml_path_str:
#                 self.yaml_path_used = Path(yaml_path_str)
#             return True
        
#         return False
    
#     def _iter_children(self, root: Path, recursive: bool, include_hidden: bool):
#         """지정 디렉토리에서 파일/폴더를 순회하는 제너레이터"""
#         if not root.exists() or not root.is_dir():
#             return
#         if not recursive:
#             for entry in os.scandir(root):
#                 if not include_hidden and Path(entry.path).name.startswith("."):
#                     continue
#                 yield entry
#         else:
#             for dirpath, dirnames, filenames in os.walk(root):
#                 if not include_hidden:
#                     dirnames[:] = [d for d in dirnames if not d.startswith(".")]
#                     filenames[:] = [f for f in filenames if not f.startswith(".")]
#                 for fn in filenames:
#                     full = Path(dirpath) / fn
#                     yield full
    
#     @st.cache_data(show_spinner=False)
#     def scan_dir_stats(
#         self,
#         dir_path_str: str, recursive: bool, include_hidden: bool
#     ) -> Tuple[int, int, int]:
#         """디렉토리 집계 결과 캐시"""
#         p = Path(dir_path_str)
#         file_count = 0
#         dir_count = 0
#         total_size = 0

#         if not p.exists() or not p.is_dir():
#             return (0, 0, 0)

#         if not recursive:
#             for e in self._iter_children(p, recursive=False, include_hidden=include_hidden):
#                 try:
#                     if isinstance(e, os.DirEntry):
#                         if e.is_file():
#                             file_count += 1
#                             try:
#                                 total_size += e.stat().st_size
#                             except Exception:
#                                 pass
#                         elif e.is_dir():
#                             dir_count += 1
#                     else:
#                         if Path(e).is_file():
#                             file_count += 1
#                             try:
#                                 total_size += Path(e).stat().st_size
#                             except Exception:
#                                 pass
#                         elif Path(e).is_dir():
#                             dir_count += 1
#                 except Exception:
#                     pass
#         else:
#             for dirpath, dirnames, filenames in os.walk(p):
#                 if not include_hidden:
#                     dirnames[:] = [d for d in dirnames if not d.startswith(".")]
#                     filenames[:] = [f for f in filenames if not f.startswith(".")]
#                 dir_count += len(dirnames)
#                 file_count += len(filenames)
#                 for fn in filenames:
#                     fp = Path(dirpath) / fn
#                     try:
#                         total_size += fp.stat().st_size
#                     except Exception:
#                         pass

#         return (file_count, dir_count, total_size)
    
#     def build_section_table(
#         self,
#         section_name: str,
#         mapping: Dict[str, Any],
#         root_path: Path,
#         recursive: bool,
#         include_hidden: bool,
#     ) -> pd.DataFrame:
#         """section_name: 'directories' 또는 'source_directories'"""
#         rows = []
#         for k, rel in (mapping or {}).items():
#             try:
#                 abs_path = _expand_path(root_path, str(rel))
#                 exists = abs_path.exists()
#                 is_dir = abs_path.is_dir()
#                 if exists and is_dir:
#                     files, dirs, total = self.scan_dir_stats(str(abs_path), recursive, include_hidden)
#                 else:
#                     files, dirs, total = (0, 0, 0)
#                 rows.append({
#                     "section": section_name,
#                     "key": str(k),
#                     "path": str(rel),
#                     "resolved_path": str(abs_path),
#                     "exists": "Y" if exists else "N",
#                     "is_dir": "Y" if is_dir else "N",
#                     "file_count": files,
#                     "dir_count": dirs,
#                     "total_size": total,
#                     "total_size(human)": _fmt_bytes(total),
#                 })
#             except Exception as e:
#                 rows.append({
#                     "section": section_name,
#                     "key": str(k),
#                     "path": str(rel),
#                     "resolved_path": "",
#                     "exists": "N",
#                     "is_dir": "N",
#                     "file_count": 0,
#                     "dir_count": 0,
#                     "total_size": 0,
#                     "total_size(human)": "-",
#                     "error": str(e),
#                 })
#         return pd.DataFrame(rows)
    
#     def display_yaml_selector(self):
#         """YAML 파일 선택 UI"""
#         with st.expander("① YAML 선택", expanded=True):
#             col1, col2 = st.columns([3, 2])
#             with col1:
#                 yaml_path_txt = st.text_input(
#                     "YAML 경로 (미입력 시 자동 탐색 또는 Editor에서 로드된 파일 사용)",
#                     value=str(_auto_find_yaml() or ""),
#                     placeholder="예) C:/projects/myproject/QDQM/util/DS_00_Main_Config.yaml"
#                 )
#             with col2:
#                 uploaded = st.file_uploader("또는 업로드", type=["yaml", "yml"])

#             if uploaded is not None:
#                 try:
#                     self.yaml_data = yaml.safe_load(uploaded.read().decode("utf-8")) or {}
#                     self.yaml_path_used = None
#                     st.success("업로드 YAML 로드 성공")
#                 except Exception as e:
#                     st.error(f"업로드 파싱 실패: {e}")
#             else:
#                 if yaml_path_txt.strip():
#                     p = Path(yaml_path_txt.strip())
#                     if p.exists():
#                         try:
#                             self.yaml_data = _safe_load_yaml(p)
#                             self.yaml_path_used = p
#                             st.success(f"파일 로드 성공: {p}")
#                         except Exception as e:
#                             st.error(f"YAML 로드 실패: {e}")
#                     else:
#                         st.warning("지정한 경로가 존재하지 않습니다.")
#                 else:
#                     # 자동 탐색 또는 세션 데이터 사용
#                     if self.load_yaml():
#                         if self.yaml_path_used:
#                             st.info(f"자동 탐색으로 파일 발견: {self.yaml_path_used}")
#                         else:
#                             st.info("Editor에서 로드된 YAML 데이터를 사용합니다.")
#                     else:
#                         st.info("경로 미입력 → 자동 탐색을 시도했습니다. 필요 시 직접 입력/업로드 하세요.")
    
#     def display_options(self):
#         """옵션 설정 UI"""
#         with st.expander("② 옵션", expanded=True):
#             c1, c2, c3 = st.columns([1, 1, 2])
#             with c1:
#                 self.recursive = st.checkbox("하위 폴더 포함(재귀)", value=True)
#             with c2:
#                 self.include_hidden = st.checkbox("숨김 포함(.*)", value=False)
#             with c3:
#                 self.root_override = st.text_input(
#                     "ROOT_PATH 재정의(선택, 비우면 YAML의 ROOT_PATH 사용)",
#                     value=""
#                 )
    
#     def process_and_display(self):
#         """데이터 처리 및 표시"""
#         if not self.yaml_data:
#             st.warning("⚠️ YAML 데이터를 로드하세요.")
#             return
        
#         # ROOT_PATH 결정
#         self.root_path = Path(
#             self.root_override.strip() or 
#             self.yaml_data.get("ROOT_PATH") or 
#             (self.yaml_path_used.parent if self.yaml_path_used else Path.cwd())
#         )
#         st.info(f"ROOT_PATH: `{self.root_path}`")

#         directories = self.yaml_data.get("directories", {})
#         source_directories = self.yaml_data.get("source_directories", {})

#         t0 = time.time()
#         df_dirs = self.build_section_table("directories", directories, self.root_path, self.recursive, self.include_hidden)
#         df_src = self.build_section_table("source_directories", source_directories, self.root_path, self.recursive, self.include_hidden)
#         df_all = pd.concat([df_dirs, df_src], ignore_index=True)
#         dt_sec = time.time() - t0

#         # 결과 요약
#         st.markdown("### 결과 요약")
#         colA, colB, colC, colD = st.columns([1, 1, 1, 1])
#         with colA:
#             st.metric("총 항목수", f"{len(df_all):,}")
#         with colB:
#             st.metric("총 파일수", f"{int(df_all['file_count'].sum()):,}")
#         with colC:
#             st.metric("총 폴더수", f"{int(df_all['dir_count'].sum()):,}")
#         with colD:
#             st.metric("총 용량", _fmt_bytes(int(df_all["total_size"].sum())))
#         st.caption(f"스캔 시간: {dt_sec:.2f}s   (재귀={self.recursive}, 숨김포함={self.include_hidden})")

#         # 상세 표
#         st.markdown("### 상세 표")
#         st.dataframe(
#             df_all[[
#                 "section", "key", "path", "resolved_path", "exists", "is_dir",
#                 "file_count", "dir_count", "total_size(human)"
#             ]].sort_values(["section", "key"]),
#             width='stretch',
#             hide_index=True,
#         )

#         # 섹션별 필터 & 미존재 경로 하이라이트
#         with st.expander("필터 & 점검", expanded=False):
#             section_pick = st.multiselect(
#                 "섹션", 
#                 options=["directories", "source_directories"], 
#                 default=["directories", "source_directories"]
#             )
#             only_missing = st.checkbox("존재하지 않는 경로만 보기", value=False)
#             df_view = df_all[df_all["section"].isin(section_pick)].copy()
#             if only_missing:
#                 df_view = df_view[df_view["exists"] == "N"]
#             if df_view.empty:
#                 st.info("표시할 항목이 없습니다.")
#             else:
#                 st.dataframe(
#                     df_view.sort_values(["section", "key"]),
#                     width='stretch',
#                     hide_index=True
#                 )

# ------------------------------------------------------------
# 앱
# ------------------------------------------------------------
class ConfigEditorApp:
    """Configuration Setup 애플리케이션"""
    
    def __init__(self):
        self.manager = ConfigEditorManager()
        # self.inspector = DirectoryInspector()

    def initialize(self) -> bool:
        """초기화"""
        try:
            set_page_config({"APP_NAME": APP_NAME, "APP_KOR_NAME": APP_KOR_NAME})
            _init_session_defaults()
            st.title(f"{APP_NAME}")
            st.markdown(APP_DESC)
            st.subheader(f"{APP_KOR_NAME}")
            return True
        except Exception as e:
            st.error(f"페이지 초기화 오류: {e}")
            return False

    def run(self):
        """메인 실행"""
        self.manager.pick_file_ui()
        if st.session_state.get("yaml_data"):
            if not self.manager.config_file:
                self.manager.config_file = ConfigFile(
                    path=st.session_state.get("yaml_path", str(_current_yaml_path())),
                    data=st.session_state.get("yaml_data", {}),
                )
            self.manager.display_editor()

# ------------------------------------------------------------
# 단독 실행
# ------------------------------------------------------------
def main():
    app = ConfigEditorApp()
    if app.initialize():
        app.run()
    else:
        st.error("ConfigEditorApp 초기화 실패")

if __name__ == "__main__":
    main()
