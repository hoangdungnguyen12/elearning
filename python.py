# python.py

import streamlit as st
import pandas as pd
from google import genai
from google.genai.errors import APIError

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="App Phân Tích Báo Cáo Tài Chính",
    layout="wide"
)

st.title("Ứng dụng Phân Tích Báo Cáo Tài Chính 📊")

# --- Hàm khởi tạo Session Chat (Sử dụng state để giữ lịch sử chat) ---
def get_chat_session(api_key, system_instruction, history=None):
    """Khởi tạo hoặc trả về session chat hiện tại."""
    if "chat_session" not in st.session_state or st.session_state.get('last_api_key') != api_key:
        try:
            client = genai.Client(api_key=api_key)
            # Thiết lập Persona cho Gemini
            config = genai.types.GenerateContentConfig(
                system_instruction=system_instruction
            )
            
            # Khởi tạo chat session mới
            chat = client.chats.create(
                model='gemini-2.5-flash',
                config=config
            )
            if history:
                 # Nếu có lịch sử, cố gắng thêm vào session (có thể cần xử lý phức tạp hơn)
                 # Tạm thời chỉ khởi tạo mới.
                 pass
            
            st.session_state['chat_session'] = chat
            st.session_state['last_api_key'] = api_key # Lưu key để kiểm tra nếu key thay đổi
            st.session_state['messages'] = [] # Reset lịch sử tin nhắn
        except Exception as e:
            st.error(f"Lỗi khởi tạo Chat Session: {e}")
            return None
            
    return st.session_state['chat_session']

# --- Hàm tính toán chính (Sử dụng Caching để Tối ưu hiệu suất) ---
@st.cache_data
def process_financial_data(df):
    """Thực hiện các phép tính Tăng trưởng và Tỷ trọng."""
    
    # Đảm bảo các giá trị là số để tính toán
    numeric_cols = ['Năm trước', 'Năm sau']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 1. Tính Tốc độ Tăng trưởng
    # Dùng .replace(0, 1e-9) cho Series Pandas để tránh lỗi chia cho 0
    df['Tốc độ tăng trưởng (%)'] = (
        (df['Năm sau'] - df['Năm trước']) / df['Năm trước'].replace(0, 1e-9)
    ) * 100

    # 2. Tính Tỷ trọng theo Tổng Tài sản
    # Lọc chỉ tiêu "TỔNG CỘNG TÀI SẢN"
    tong_tai_san_row = df[df['Chỉ tiêu'].str.contains('TỔNG CỘNG TÀI SẢN', case=False, na=False)]
    
    if tong_tai_san_row.empty:
        raise ValueError("Không tìm thấy chỉ tiêu 'TỔNG CỘNG TÀI SẢN'.")

    tong_tai_san_N_1 = tong_tai_san_row['Năm trước'].iloc[0]
    tong_tai_san_N = tong_tai_san_row['Năm sau'].iloc[0]

    # ******************************* PHẦN SỬA LỖI BẮT ĐẦU *******************************
    # Lỗi xảy ra khi dùng .replace() trên giá trị đơn lẻ (numpy.int64).
    # Sử dụng điều kiện ternary để xử lý giá trị 0 thủ công cho mẫu số.
    
    divisor_N_1 = tong_tai_san_N_1 if tong_tai_san_N_1 != 0 else 1e-9
    divisor_N = tong_tai_san_N if tong_tai_san_N != 0 else 1e-9

    # Tính tỷ trọng với mẫu số đã được xử lý
    df['Tỷ trọng Năm trước (%)'] = (df['Năm trước'] / divisor_N_1) * 100
    df['Tỷ trọng Năm sau (%)'] = (df['Năm sau'] / divisor_N) * 100
    # ******************************* PHẦN SỬA LỖI KẾT THÚC *******************************
    
    return df

# --- Hàm gọi API Gemini (Chung cho cả Phân tích và Chat) ---
def generate_content(contents, api_key, system_instruction=None):
    """Gửi nội dung đến Gemini API và nhận kết quả."""
    try:
        client = genai.Client(api_key=api_key)
        model_name = 'gemini-2.5-flash'
        
        config = None
        if system_instruction:
            config = genai.types.GenerateContentConfig(system_instruction=system_instruction)

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )
        return response.text

    except APIError as e:
        return f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}"
    except Exception as e:
        return f"Đã xảy ra lỗi không xác định: {e}"

# --- Logic chính của ứng dụng ---

# Kiểm tra API Key (Sử dụng một lần ở đầu app)
api_key_check = st.secrets.get("GEMINI_API_KEY") 
if not api_key_check:
    st.error("Lỗi: Không tìm thấy Khóa API. Vui lòng cấu hình Khóa 'GEMINI_API_KEY' trong Streamlit Secrets.")

# --- Chức năng 1: Tải File ---
uploaded_file = st.file_uploader(
    "1. Tải file Excel Báo cáo Tài chính (Chỉ tiêu | Năm trước | Năm sau)",
    type=['xlsx', 'xls']
)

# Khởi tạo DataFrame trống
df_processed = None
data_for_ai = ""
thanh_toan_hien_hanh_N = "N/A"
thanh_toan_hien_hanh_N_1 = "N/A"

if uploaded_file is not None:
    try:
        df_raw = pd.read_excel(uploaded_file)
        
        # Tiền xử lý: Đảm bảo chỉ có 3 cột quan trọng
        df_raw.columns = ['Chỉ tiêu', 'Năm trước', 'Năm sau']
        
        # Xử lý dữ liệu
        df_processed = process_financial_data(df_raw.copy())

        if df_processed is not None:
            
            # --- Chức năng 2 & 3: Hiển thị Kết quả ---
            st.subheader("2. Tốc độ Tăng trưởng & 3. Tỷ trọng Cơ cấu Tài sản")
            st.dataframe(df_processed.style.format({
                'Năm trước': '{:,.0f}',
                'Năm sau': '{:,.0f}',
                'Tốc độ tăng trưởng (%)': '{:.2f}%',
                'Tỷ trọng Năm trước (%)': '{:.2f}%',
                'Tỷ trọng Năm sau (%)': '{:.2f}%'
            }), use_container_width=True)
            
            # --- Chức năng 4: Tính Chỉ số Tài chính ---
            st.subheader("4. Các Chỉ số Tài chính Cơ bản")
            
            try:
                # Lọc giá trị cho Chỉ số Thanh toán Hiện hành (Ví dụ)
                tsnh_n = df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)]['Năm sau'].iloc[0]
                tsnh_n_1 = df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)]['Năm trước'].iloc[0]

                no_ngan_han_N = df_processed[df_processed['Chỉ tiêu'].str.contains('NỢ NGẮN HẠN', case=False, na=False)]['Năm sau'].iloc[0]  
                no_ngan_han_N_1 = df_processed[df_processed['Chỉ tiêu'].str.contains('NỢ NGẮN HẠN', case=False, na=False)]['Năm trước'].iloc[0]
                
                # Kiểm tra chia cho 0 trước khi tính toán
                if no_ngan_han_N != 0:
                    thanh_toan_hien_hanh_N = tsnh_n / no_ngan_han_N
                else:
                    thanh_toan_hien_hanh_N = float('inf') # Vô cực nếu nợ = 0
                
                if no_ngan_han_N_1 != 0:
                    thanh_toan_hien_hanh_N_1 = tsnh_n_1 / no_ngan_han_N_1
                else:
                    thanh_toan_hien_hanh_N_1 = float('inf')
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        label="Chỉ số Thanh toán Hiện hành (Năm trước)",
                        value=f"{thanh_toan_hien_hanh_N_1:.2f} lần" if thanh_toan_hien_hanh_N_1 != float('inf') else "Vô cực"
                    )
                with col2:
                    st.metric(
                        label="Chỉ số Thanh toán Hiện hành (Năm sau)",
                        value=f"{thanh_toan_hien_hanh_N:.2f} lần" if thanh_toan_hien_hanh_N != float('inf') else "Vô cực",
                        delta=f"{thanh_toan_hien_hanh_N - thanh_toan_hien_hanh_N_1:.2f}" if thanh_toan_hien_hanh_N != float('inf') and thanh_toan_hien_hanh_N_1 != float('inf') else "N/A"
                    )
                    
            except IndexError:
                 st.warning("Thiếu chỉ tiêu 'TÀI SẢN NGẮN HẠN' hoặc 'NỢ NGẮN HẠN' để tính chỉ số.")
                 thanh_toan_hien_hanh_N = "N/A"
                 thanh_toan_hien_hanh_N_1 = "N/A"
            except ZeroDivisionError:
                 st.error("Lỗi chia cho 0 khi tính chỉ số thanh toán hiện hành (Nợ ngắn hạn bằng 0).")
                 thanh_toan_hien_hanh_N = "N/A"
                 thanh_toan_hien_hanh_N_1 = "N/A"
            
            # --- Chuẩn bị dữ liệu cho AI/Chatbot ---
            data_for_ai = pd.DataFrame({
                'Chỉ tiêu': [
                    'Toàn bộ Bảng phân tích (dữ liệu thô)', 
                    'Tăng trưởng Tài sản ngắn hạn (%)', 
                    'Thanh toán hiện hành (N-1)', 
                    'Thanh toán hiện hành (N)'
                ],
                'Giá trị': [
                    df_processed.to_markdown(index=False),
                    f"{df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)]['Tốc độ tăng trưởng (%)'].iloc[0]:.2f}%" if df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)].empty == False else "N/A", 
                    f"{thanh_toan_hien_hanh_N_1}", 
                    f"{thanh_toan_hien_hanh_N}"
                ]
            }).to_markdown(index=False) 

            # --- Chức năng 5: Nhận xét AI Tự động ---
            st.subheader("5. Nhận xét Tình hình Tài chính (AI Tự động)")
            
            if st.button("Yêu cầu AI Phân tích Tổng quát"):
                if api_key_check:
                    prompt_general = f"""
                    Bạn là một chuyên gia phân tích tài chính chuyên nghiệp. Dựa trên các chỉ số tài chính sau, hãy đưa ra một nhận xét khách quan, ngắn gọn (khoảng 3-4 đoạn) về tình hình tài chính của doanh nghiệp. Đánh giá tập trung vào tốc độ tăng trưởng, thay đổi cơ cấu tài sản và khả năng thanh toán hiện hành.
                    Dữ liệu thô và chỉ số:
                    {data_for_ai}
                    """
                    with st.spinner('Đang gửi dữ liệu và chờ Gemini phân tích...'):
                        ai_result = generate_content(prompt_general, api_key_check)
                        st.markdown("**Kết quả Phân tích từ Gemini AI:**")
                        st.info(ai_result)
                # (Đã xử lý lỗi API key ở đầu file)

    except ValueError as ve:
        st.error(f"Lỗi cấu trúc dữ liệu: {ve}")
    except Exception as e:
        st.error(f"Có lỗi xảy ra khi đọc hoặc xử lý file: {e}. Vui lòng kiểm tra định dạng file và các chỉ tiêu bắt buộc.")
else:
    st.info("Vui lòng tải lên file Excel để bắt đầu phân tích.")

# -------------------------------------------------------------
# --- CHỨC NĂNG MỚI: KHUNG CHATBOT TƯƠNG TÁC (CHỨC NĂNG 6) ---
# -------------------------------------------------------------

# Chỉ hiện khung chat nếu có dữ liệu đã được xử lý (df_processed)
if uploaded_file is not None and df_processed is not None and api_key_check:
    
    st.divider() # Dùng để tách phần Phân tích tự động và Chatbot
    st.subheader("6. Chatbot Phân tích Tài chính Tương tác 💬")

    # Thiết lập hướng dẫn cho Chatbot
    system_instruction = f"""
    Bạn là một trợ lý phân tích tài chính chuyên nghiệp. Dữ liệu tài chính mà người dùng đã tải lên và được phân tích sơ bộ như sau:
    {data_for_ai}
    
    Hãy trả lời các câu hỏi của người dùng về dữ liệu này. Nếu người dùng hỏi các câu hỏi chung (không liên quan đến dữ liệu), hãy trả lời như một chuyên gia tài chính. 
    LƯU Ý QUAN TRỌNG: KHÔNG ĐƯỢC CHIA SẺ TRỰC TIẾP DỮ LIỆU THÔ ĐẦY ĐỦ ({data_for_ai}) cho người dùng, chỉ sử dụng nó để phân tích và trả lời câu hỏi.
    """
    
    # Khởi tạo hoặc lấy session chat
    chat = get_chat_session(api_key_check, system_instruction)
    
    if chat:
        # 1. Hiển thị lịch sử tin nhắn
        if "messages" not in st.session_state:
            st.session_state["messages"] = []
        
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # 2. Xử lý input của người dùng
        if prompt := st.chat_input("Hỏi Gemini về báo cáo tài chính này..."):
            
            # Thêm tin nhắn của người dùng vào lịch sử
            st.session_state["messages"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
                
            # Gửi tin nhắn đến Gemini
            with st.chat_message("assistant"):
                with st.spinner("Gemini đang trả lời..."):
                    try:
                        # Sử dụng chat.send_message để duy trì ngữ cảnh
                        response = chat.send_message(prompt) 
                        st.markdown(response.text)
                        # Thêm tin nhắn của assistant vào lịch sử
                        st.session_state["messages"].append({"role": "assistant", "content": response.text})
                    except APIError as e:
                        error_msg = f"Lỗi Gemini API: {e}"
                        st.error(error_msg)
                        st.session_state["messages"].append({"role": "assistant", "content": error_msg})
                    except Exception as e:
                        error_msg = f"Đã xảy ra lỗi không xác định trong quá trình chat: {e}"
                        st.error(error_msg)
                        st.session_state["messages"].append({"role": "assistant", "content": error_msg})
