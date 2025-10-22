# learn.py (Chế độ Học)

import streamlit as st
import time
# Import các hàm dùng chung
from utils import AVAILABLE_FILES, load_questions 

# --- HÀM HỖ TRỢ CHẾ ĐỘ HỌC ---

def init_learn_state(total_questions=0, reset=False):
    """Khởi tạo hoặc reset các biến trạng thái Học."""
    if reset or 'current_question_index' not in st.session_state:
        st.session_state['current_question_index'] = 0
        st.session_state['correct_answers'] = 0
        st.session_state['question_order'] = list(range(total_questions))
        st.session_state['show_result'] = False
        st.session_state['user_choice'] = None
        st.session_state['total_questions'] = total_questions

def start_from_question(start_num):
    """Bắt đầu học từ câu hỏi đã chọn."""
    start_index = start_num - 1 
    
    if 'questions_data' in st.session_state:
        total_questions = len(st.session_state['questions_data']) 
    else:
        st.warning("Dữ liệu câu hỏi chưa được tải.")
        return

    st.session_state['total_questions'] = total_questions 
    
    if start_index < 0 or start_index >= total_questions:
        return

    st.session_state['correct_answers'] = 0
    st.session_state['current_question_index'] = start_index
    st.session_state['show_result'] = False
    st.session_state['user_choice'] = None
    st.session_state['question_order'] = list(range(total_questions))
    
    st.rerun()

def display_learn_mode(QUESTIONS_DATA, selected_display_name):
    """Hiển thị giao diện cho chế độ Học."""
    
    current_index = st.session_state['current_question_index']
    total_questions = st.session_state['total_questions']

    if current_index >= total_questions:
        st.header(f"🎉 Hoàn Thành Bộ: {selected_display_name}!")
        st.info(f"Bạn đã trả lời đúng **{st.session_state['correct_answers']}** trên tổng số **{total_questions}** câu hỏi.")
        
        if st.button("Làm lại từ đầu (Câu 1)", help="Bắt đầu lại bài kiểm tra theo thứ tự tuần tự."):
            st.session_state['current_question_index'] = 0
            st.session_state['correct_answers'] = 0
            st.session_state['show_result'] = False
            st.session_state['user_choice'] = None
            st.rerun()
        return

    question_map_index = st.session_state['question_order'][current_index]
    question_data = QUESTIONS_DATA[question_map_index]
    question_text = question_data['question']
    options = question_data['options']
    
    st.subheader(f"Câu hỏi {question_map_index + 1}/{total_questions} (Bộ: {selected_display_name})")
    st.markdown(f"**{question_text}**")

    # Radio buttons
    selected_option = st.radio(
        "Chọn đáp án:",
        options=options,
        index=None, 
        key=f"q_{current_index}_choice",
        disabled=st.session_state['show_result'] 
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        if selected_option is not None and not st.session_state['show_result']:
            try:
                user_index = options.index(selected_option)
                
                # Helper function for learn mode to check answer
                def learn_check_answer(user_index):
                    current_map_index = st.session_state['question_order'][st.session_state['current_question_index']]
                    correct_idx = QUESTIONS_DATA[current_map_index]['correct_index']
                    
                    st.session_state['user_choice'] = user_index
                    st.session_state['show_result'] = True
                
                    if user_index == correct_idx:
                        st.session_state['correct_answers'] += 1
                
                st.button("Kiểm tra đáp án", on_click=learn_check_answer, args=(user_index,), use_container_width=True)
            except ValueError:
                st.session_state['show_result'] = False

    # --- Hiển thị Kết quả và Giải thích ---
    if st.session_state['show_result']:
        
        user_choice_idx = st.session_state['user_choice']
        correct_index = question_data['correct_index']
        
        if user_choice_idx == correct_index:
            st.success("✅ **Chính xác!**")
        else:
            correct_option_text = options[correct_index]
            st.error(f"❌ **Sai rồi!** Đáp án đúng là: **{correct_option_text}**")
            
        if question_data['explanation']:
            st.info(f"**Trích dẫn/Giải thích:** {question_data['explanation']}")
            
        with col2:
            def next_question():
                st.session_state['show_result'] = False
                st.session_state['user_choice'] = None
                st.session_state['current_question_index'] += 1
            st.button("Câu hỏi kế tiếp >>", on_click=next_question, type="primary", use_container_width=True)

    st.markdown("---")
    st.info(f"**Đang học:** Câu {question_map_index + 1} | **Số câu đúng:** {st.session_state['correct_answers']} (Từ lúc bắt đầu)")

# --- HÀM CHÍNH ---

def main():
    st.set_page_config(layout="centered", page_title="Học Trắc Nghiệm")
    st.title("📚 Chế Độ Học Trắc Nghiệm")

    if not AVAILABLE_FILES:
        st.error("Không tìm thấy file CSV nào trong thư mục này.")
        st.stop()

    # --- Sidebar ---
    st.sidebar.header("Tùy chọn Học")
    
    # 1. Chọn File Dữ Liệu
    selected_display_name = st.sidebar.selectbox(
        "Chọn Tập Dữ Liệu:",
        options=list(AVAILABLE_FILES.keys()),
        key='file_select'
    )
    file_path = AVAILABLE_FILES[selected_display_name]

    # 2. Tải dữ liệu và xử lý file thay đổi
    QUESTIONS_DATA = load_questions(file_path)
    TOTAL_QUESTIONS = len(QUESTIONS_DATA)

    # Kiểm tra trạng thái và khởi tạo/reset nếu cần
    if ('last_loaded_file' not in st.session_state or st.session_state['last_loaded_file'] != file_path or 
        'questions_data' not in st.session_state or st.session_state.get('total_questions') != TOTAL_QUESTIONS or
        'current_question_index' not in st.session_state): # Kiểm tra state Học
        
        st.session_state['last_loaded_file'] = file_path
        st.session_state['questions_data'] = QUESTIONS_DATA
        init_learn_state(TOTAL_QUESTIONS, reset=True) 

    if TOTAL_QUESTIONS == 0:
        st.error(f"Không có câu hỏi nào được tải từ file: **{file_path}**.")
        st.stop()
        
    current_index = st.session_state['current_question_index']
    
    # KIỂM TRA ĐIỀU KIỆN HOÀN THÀNH BÀI TRƯỚC KHI TRUY CẬP DANH SÁCH
    if current_index >= TOTAL_QUESTIONS:
        display_learn_mode(QUESTIONS_DATA, selected_display_name)
        return

    # 3. Chọn Câu hỏi Bắt đầu
    selected_start_num = st.sidebar.number_input(
        f"Bắt đầu/Tiếp tục từ Câu hỏi số (1 - {TOTAL_QUESTIONS}):",
        min_value=1,
        max_value=TOTAL_QUESTIONS,
        value=current_index + 1,
        step=1,
        key='start_num_input'
    )

    # Nút Bắt đầu
    if st.sidebar.button(f"Bắt đầu từ Câu {selected_start_num}", type="primary"):
        start_from_question(int(selected_start_num))
        
    st.markdown("---") 

    display_learn_mode(QUESTIONS_DATA, selected_display_name)

if __name__ == "__main__":
    # Để đảm bảo chương trình không bị lỗi khi người dùng cố gắng chạy file này
    # trong khi file kia đã được chạy
    if 'quiz_state' in st.session_state:
        # Xóa các state quiz cũ nếu có
        for key in list(st.session_state.keys()):
             if key.startswith('quiz'):
                del st.session_state[key]
    
    main()