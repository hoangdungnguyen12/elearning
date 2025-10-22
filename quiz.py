# quiz.py
"""
Streamlit Quiz (Chế độ Thi - Từng Câu) - Phiên bản tối ưu cho Streamlit >= 1.32
- Thay đổi: Chọn 1 chủ đề (1-16): 75 câu; Chủ đề 17: 25 câu (Cơ cấu mới)
- Thời gian thi: 45 phút (2700 giây)
- Tối ưu: Giảm kích thước URL, cải thiện đồng hồ đếm ngược, thêm hằng số, tăng cường xử lý lỗi
- Lưu tạm trạng thái quiz qua URL (base64 JSON, tối ưu dữ liệu)
- Cache khi load câu hỏi
"""

import streamlit as st
import random
import time
import json
import base64
import copy

# Import các hàm & dữ liệu chung (giả định có file utils.py)
from utils import AVAILABLE_FILES, load_questions, get_file_number

# ---------- Constants ----------
N_SELECTED_QUESTIONS = 75
N_TOPIC_17_QUESTIONS = 25
QUIZ_DURATION_SECONDS = 45 * 60
TOPIC_17_RANGES = [
    (0, 65, 3),   # 1-65: 3 questions
    (65, 95, 3),  # 66-95: 3 questions
    (95, 105, 3), # 96-105: 3 questions
    (105, 220, 4),# 106-220: 4 questions
    (220, 250, 4),# 221-250: 4 questions
    (250, 350, 8),# 251-350: 8 questions
]

# ---------- Helpers: save/load state via URL ----------
_STATE_QPARAM_KEY = "qs"  # Query param key for quiz state
_SELECTED_TOPIC_KEY = "st"  # Query param key for selected topic

def _encode_state_for_url(state_dict: dict) -> str:
    """
    Encode a dictionary to base64 URL-safe string.
    
    Args:
        state_dict (dict): Dictionary to encode.
    
    Returns:
        str: Base64 URL-safe encoded string.
    """
    raw = json.dumps(state_dict, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")

def _decode_state_from_url(encoded: str) -> dict | None:
    """
    Decode a base64 URL-safe string to a dictionary.
    
    Args:
        encoded (str): Base64 URL-safe encoded string.
    
    Returns:
        dict | None: Decoded dictionary or None if decoding fails.
    """
    try:
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except (base64.binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as e:
        st.error(f"Không thể nạp trạng thái từ URL: {str(e)}")
        return None

def save_quiz_state_to_url():
    """Save minimal quiz state to URL query params (base64 JSON)."""
    if 'quiz_state' not in st.session_state:
        return
    minimal = {
        "user_choices": [q["user_choice"] for q in st.session_state['quiz_state']],
        "quiz_start_time": st.session_state.get('quiz_start_time'),
        "quiz_duration": st.session_state.get('quiz_duration'),
        "quiz_current_q_index": st.session_state.get('quiz_current_q_index'),
        "quiz_submitted": st.session_state.get('quiz_submitted', False),
        "quiz_score": st.session_state.get('quiz_score', 0),
        "selected_topic_path": st.session_state.get('selected_topic_path'),
    }
    encoded = _encode_state_for_url(minimal)
    st.query_params.update({_STATE_QPARAM_KEY: encoded})

def load_quiz_state_from_url(selected_topic_path: str):
    """
    Load quiz state from URL and reconstruct quiz_state.
    
    Args:
        selected_topic_path (str): Path to the selected topic file.
    
    Returns:
        bool: True if state is loaded successfully, False otherwise.
    """
    params = st.query_params
    if _STATE_QPARAM_KEY not in params:
        return False
    decoded = _decode_state_from_url(params[_STATE_QPARAM_KEY])
    if not decoded or decoded.get('selected_topic_path') != selected_topic_path:
        return False
    
    # Reconstruct quiz_state from user_choices
    quiz_questions = get_all_questions_for_quiz(selected_topic_path)
    if len(quiz_questions) != len(decoded.get('user_choices', [])):
        st.error("Trạng thái không hợp lệ: Số câu hỏi không khớp.")
        return False
    
    for i, choice in enumerate(decoded['user_choices']):
        quiz_questions[i]['user_choice'] = choice
        if choice is not None:
            quiz_questions[i]['is_correct'] = choice == quiz_questions[i]['question_data']['correct_index']
    
    st.session_state['quiz_state'] = quiz_questions
    st.session_state['quiz_start_time'] = decoded.get('quiz_start_time', time.time())
    st.session_state['quiz_duration'] = decoded.get('quiz_duration', QUIZ_DURATION_SECONDS)
    st.session_state['quiz_current_q_index'] = decoded.get('quiz_current_q_index', 0)
    st.session_state['quiz_submitted'] = decoded.get('quiz_submitted', False)
    st.session_state['quiz_score'] = decoded.get('quiz_score', 0)
    st.session_state['selected_topic_path'] = decoded.get('selected_topic_path')
    st.session_state['quiz_total_q'] = len(quiz_questions)
    st.session_state['quiz_view_result'] = st.session_state.get('quiz_submitted', False)
    return True

def clear_quiz_query_param():
    """Clear all query parameters."""
    st.query_params.clear()

# ---------- Cache wrapper ----------
@st.cache_data
def cached_load_questions(file_path: str) -> list:
    """
    Load questions from a file with caching.
    
    Args:
        file_path (str): Path to the question file.
    
    Returns:
        list: List of question dictionaries.
    """
    try:
        return load_questions(file_path)
    except Exception as e:
        st.error(f"Không thể tải câu hỏi từ {file_path}: {str(e)}")
        return []

def get_all_questions_for_quiz(selected_topic_path: str) -> list:
    """
    Select 100 questions: 75 from the chosen topic and 25 from Topic 17.
    
    Args:
        selected_topic_path (str): File path to the selected topic's question file.
    
    Returns:
        list: List of quiz state dictionaries with question data, user choice, and correctness.
    """
    pool_selected_topic = cached_load_questions(selected_topic_path)
    selected_topic_name = next((name for name, path in AVAILABLE_FILES.items() if path == selected_topic_path), "Chủ đề đã chọn")
    
    # Validate selected topic questions
    if len(pool_selected_topic) < N_SELECTED_QUESTIONS:
        st.warning(f"Cảnh báo: Chỉ có {len(pool_selected_topic)} câu trong **{selected_topic_name}**. Sẽ lấy tất cả.")
    
    # Select questions from chosen topic
    quiz_q_selected = random.sample(pool_selected_topic, min(N_SELECTED_QUESTIONS, len(pool_selected_topic))) if pool_selected_topic else []
    
    # Find Topic 17
    topic_17_path = None
    topic_17_name = "Chủ đề 17"
    for display_name, file_path in AVAILABLE_FILES.items():
        if get_file_number(display_name) == 17:
            topic_17_path = file_path
            topic_17_name = display_name
            break
    
    if not topic_17_path:
        st.error("Không tìm thấy Chủ đề 17. Vui lòng kiểm tra file dữ liệu.")
        return []
    
    pool_17 = cached_load_questions(topic_17_path)
    
    # Select questions from Topic 17
    quiz_q_17 = []
    if pool_17:
        qlist_17_indexed = copy.deepcopy(pool_17)
        for start, end, count in TOPIC_17_RANGES:
            sub_list = qlist_17_indexed[start:end]
            if not sub_list:
                continue
            if len(sub_list) < count:
                st.warning(f"Cảnh báo: Chỉ có {len(sub_list)} câu trong Chủ đề 17 (câu {start+1}-{end}). Sẽ lấy tất cả.")
            quiz_q_17.extend(random.sample(sub_list, min(count, len(sub_list))))
    
    if len(quiz_q_17) < N_TOPIC_17_QUESTIONS:
        st.warning(f"Cảnh báo: Chỉ lấy được {len(quiz_q_17)} câu từ Chủ đề 17.")
    
    final_quiz_questions = quiz_q_selected + quiz_q_17
    random.shuffle(final_quiz_questions)
    
    if not final_quiz_questions:
        st.error("Không có câu hỏi nào được chọn. Vui lòng kiểm tra lại file dữ liệu.")
        return []
    
    quiz_state = []
    for q in final_quiz_questions:
        if 'source' not in q:
            q['source'] = selected_topic_name if q in quiz_q_selected else topic_17_name
        quiz_state.append({
            "question_data": q,
            "user_choice": None,
            "is_correct": None,
        })
    return quiz_state

# ---------- Init / Reset ----------
def init_quiz_state(reset: bool = False):
    """
    Initialize or reset quiz state.
    
    Args:
        reset (bool): If True, force reset of quiz state.
    """
    selected_topic_path = st.session_state.get('selected_topic_path')
    if not selected_topic_path:
        return
    
    if not reset and load_quiz_state_from_url(selected_topic_path):
        return
    
    st.session_state['quiz_state'] = get_all_questions_for_quiz(selected_topic_path)
    st.session_state['quiz_total_q'] = len(st.session_state['quiz_state'])
    st.session_state['quiz_start_time'] = time.time()
    st.session_state['quiz_duration'] = QUIZ_DURATION_SECONDS
    st.session_state['quiz_submitted'] = False
    st.session_state['quiz_score'] = 0
    st.session_state['quiz_view_result'] = False
    st.session_state['quiz_current_q_index'] = 0
    st.session_state['selected_topic_path'] = selected_topic_path
    save_quiz_state_to_url()

# ---------- Answer + Submit ----------
def update_quiz_answer(q_index: int, options_list: list):
    """
    Save user's answer choice.
    
    Args:
        q_index (int): Index of the current question.
        options_list (list): List of answer options.
    """
    radio_key = f"quiz_q_{st.session_state['quiz_current_q_index']}"
    if radio_key not in st.session_state:
        return
    selected_option_text = st.session_state[radio_key]
    try:
        user_selected_index = options_list.index(selected_option_text)
        st.session_state['quiz_state'][q_index]['user_choice'] = user_selected_index
    except ValueError:
        st.session_state['quiz_state'][q_index]['user_choice'] = None
    save_quiz_state_to_url()

def submit_quiz():
    """Calculate score and finalize quiz."""
    score = 0
    for q_data in st.session_state['quiz_state']:
        user_choice = q_data['user_choice']
        correct_index = q_data['question_data']['correct_index']
        q_data['is_correct'] = user_choice is not None and user_choice == correct_index
        if q_data['is_correct']:
            score += 1
    st.session_state['quiz_score'] = score
    st.session_state['quiz_submitted'] = True
    st.session_state['quiz_view_result'] = True
    save_quiz_state_to_url()

# ---------- Navigation ----------
def next_question():
    """Move to the next question."""
    max_index = st.session_state['quiz_total_q'] - 1
    if st.session_state['quiz_current_q_index'] < max_index:
        st.session_state['quiz_current_q_index'] += 1
    save_quiz_state_to_url()

def prev_question():
    """Move to the previous question."""
    if st.session_state['quiz_current_q_index'] > 0:
        st.session_state['quiz_current_q_index'] -= 1
    save_quiz_state_to_url()

# ---------- Display Results ----------
def display_quiz_result(quiz_state: list, total_q: int):
    """
    Display quiz results with detailed feedback.
    
    Args:
        quiz_state (list): List of question state dictionaries.
        total_q (int): Total number of questions.
    """
    score = st.session_state['quiz_score']
    st.header("✨ Kết Quả Bài Thi")
    st.success(f"Điểm số của bạn: **{score}/{total_q}**")
    st.metric("Tỷ lệ đúng", f"{(score/total_q*100):.0f}%")
    st.progress(score / total_q if total_q else 0)

    if st.button("Thử lại Bài Thi", key="retake_quiz_btn"):
        topic_path = st.session_state.get('selected_topic_path')
        init_quiz_state(reset=True)
        st.session_state['selected_topic_path'] = topic_path
        clear_quiz_query_param()
        st.rerun()

    st.markdown("---")
    st.subheader("Xem lại bài làm chi tiết")

    for i, q_data in enumerate(quiz_state):
        q_num = i + 1
        q = q_data['question_data']
        correct_index = q['correct_index']
        user_choice = q_data['user_choice']
        is_correct = q_data['is_correct']
        show_correct_detail = True

        icon = "✅" if is_correct else "❌"
        header_color = "green" if is_correct else "red"
        st.markdown(f"<h4 style='color:{header_color};'>{icon} Câu {q_num}/{total_q} (Nguồn: {q.get('source', 'N/A')})</h4>", unsafe_allow_html=True)
        st.markdown(f"**Câu hỏi:** {q['question']}")

        for idx, option in enumerate(q['options']):
            prefix = ""
            style = "padding:6px; border-radius:6px; margin-bottom:4px;"
            if is_correct and idx == user_choice:
                prefix = "✔️ BẠN CHỌN: "
                style += "background-color:#d4edda; color:#155724; font-weight:bold;"
            elif show_correct_detail:
                if idx == correct_index:
                    prefix = "✔️ ĐÁP ÁN ĐÚNG: "
                    style += "background-color:#d4edda; color:#155724; font-weight:bold;"
                elif idx == user_choice:
                    prefix = "❌ BẠN CHỌN SAI: "
                    style += "background-color:#f8d7da; color:#721c24; font-weight:bold;"
            elif not is_correct and idx == user_choice:
                prefix = "❌ BẠN CHỌN: "
                style += "background-color:#f8d7da; color:#721c24; font-weight:bold;"

            st.markdown(f"<div style='{style}'>{prefix}{option}</div>", unsafe_allow_html=True)

        st.markdown("---")

# ---------- Main Display ----------
def display_quiz_mode():
    """Display the quiz interface with timer and navigation."""
    if 'quiz_state' not in st.session_state or not st.session_state['quiz_state']:
        st.info("Vui lòng chọn chủ đề và nhấn 'Bắt đầu Bài Thi' để bắt đầu.")
        return

    total_q = st.session_state['quiz_total_q']
    if st.session_state['quiz_submitted']:
        display_quiz_result(st.session_state['quiz_state'], total_q)
        return

    col_time, col_submit = st.columns([2, 1])
    time_elapsed = time.time() - st.session_state['quiz_start_time']
    time_remaining = st.session_state['quiz_duration'] - time_elapsed

    if time_remaining <= 0:
        submit_quiz()
        st.rerun()
        return

    minutes = int(time_remaining // 60)
    seconds = int(time_remaining % 60)
    time_color = "red" if time_remaining <= 300 else "orange" if time_remaining <= 600 else "green"
    col_time.markdown(f"**⏰ Thời gian còn lại:** <span style='color:{time_color}; font-size:1.4em;'>{minutes:02}:{seconds:02}</span>", unsafe_allow_html=True)

    if col_submit.button("Nộp bài & Kết thúc", use_container_width=True, type="primary"):
        if st.session_state.get("confirm_submit", False):
            submit_quiz()
            st.rerun()
        else:
            st.warning("Bạn có chắc muốn nộp bài? Nhấn lại để xác nhận.")
            st.session_state["confirm_submit"] = True

    st.markdown("---")

    current_q_index = st.session_state['quiz_current_q_index']
    q_data = st.session_state['quiz_state'][current_q_index]
    q = q_data['question_data']

    st.subheader(f"Câu hỏi {current_q_index + 1}/{total_q}")
    st.info(f"Nguồn: {q.get('source', 'N/A')}")
    st.markdown(f"**{q['question']}**")

    default_index = q_data['user_choice'] if q_data['user_choice'] is not None else None
    radio_key = f"quiz_q_{current_q_index}"
    st.radio(
        "Chọn đáp án:",
        options=q['options'],
        index=default_index,
        key=radio_key,
        on_change=update_quiz_answer,
        args=(current_q_index, q['options']),
    )

    col_nav_1, col_nav_2, col_nav_3 = st.columns([1, 1, 1])
    col_nav_1.button("⬅️ Câu trước", on_click=prev_question, disabled=(current_q_index == 0), use_container_width=True)

    answered_count = sum(1 for qd in st.session_state['quiz_state'] if qd['user_choice'] is not None)
    col_nav_2.markdown(f"<div style='text-align:center;'>**Đã trả lời:** {answered_count}/{total_q}</div>", unsafe_allow_html=True)
    st.progress(answered_count / total_q)

    if current_q_index < total_q - 1:
        col_nav_3.button("Câu tiếp theo ➡️", on_click=next_question, type="primary", use_container_width=True)
    else:
        col_nav_3.button("Hoàn thành & Nộp bài ✅", on_click=submit_quiz, type="primary", use_container_width=True)

# ---------- Main ----------
def main():
    """Main function to run the quiz application."""
    st.set_page_config(layout="centered", page_title="Thi Trắc Nghiệm (100 Câu)")
    st.title("🏆 Chế Độ Thi Trắc Nghiệm (100 câu / 45 phút)")

    if not AVAILABLE_FILES:
        st.error("Không tìm thấy file CSV câu hỏi.")
        st.stop()

    topic_1_16 = {name: path for name, path in AVAILABLE_FILES.items() if 1 <= get_file_number(name) <= 16}
    if not topic_1_16:
        st.error("Không tìm thấy chủ đề nào từ 1 đến 16.")
        st.stop()

    topic_names = list(topic_1_16.keys())
    selected_name_from_state = st.session_state.get('selected_topic_name')
    default_index = topic_names.index(selected_name_from_state) if selected_name_from_state in topic_names else 0

    st.sidebar.header("Tùy chọn Thi")
    selected_name = st.sidebar.selectbox(
        "Chọn Chủ đề chính (75 câu):",
        options=topic_names,
        index=default_index,
        key='quiz_topic_selectbox'
    )

    selected_topic_path = topic_1_16[selected_name]
    st.session_state['selected_topic_path'] = selected_topic_path
    st.session_state['selected_topic_name'] = selected_name

    st.sidebar.markdown(f"**Cấu trúc bài thi:**")
    st.sidebar.markdown(f"* **{N_SELECTED_QUESTIONS} câu** từ **{selected_name}**")
    st.sidebar.markdown(f"* **{N_TOPIC_17_QUESTIONS} câu** từ **Chủ đề 17** (Cơ cấu mới)")
    st.sidebar.markdown(f"* **Tổng:** {N_SELECTED_QUESTIONS + N_TOPIC_17_QUESTIONS} câu / {QUIZ_DURATION_SECONDS // 60} phút")

    st.sidebar.slider("Thời gian cảnh báo (phút)", 1, 10, 5, key="warning_time")

    if st.sidebar.button("Bắt đầu Bài Thi Mới (100 câu)", help="Lấy 100 câu ngẫu nhiên mới và reset thời gian", type="primary"):
        init_quiz_state(reset=True)
        clear_quiz_query_param()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.info("💡 Bạn có thể F5 mà không mất bài (trạng thái lưu trong URL).")

    if 'quiz_state' not in st.session_state:
        init_quiz_state(reset=False)

    if 'quiz_state' in st.session_state and st.session_state['quiz_state']:
        display_quiz_mode()
    else:
        st.info(f"Vui lòng chọn chủ đề và nhấn **'Bắt đầu Bài Thi Mới (100 câu)'** ở thanh bên để bắt đầu bài thi 100 câu với {N_SELECTED_QUESTIONS} câu từ **{selected_name}** và {N_TOPIC_17_QUESTIONS} câu từ **Chủ đề 17**.")

if __name__ == "__main__":
    main()