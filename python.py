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

st.title("Ứng dụng Phân Tích Báo Cáo Tài chính 📊")

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
        raise ValueError("Không tìm thấy chỉ tiêu 'TỔNG CỘNG TÀI SỐN'.")

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

# --- Hàm gọi API Gemini ---
def get_ai_analysis(data_for_ai, api_key, user_question=None):
    """Gửi dữ liệu phân tích hoặc câu hỏi chat đến Gemini API và nhận nhận xét/trả lời."""
    try:
        client = genai.Client(api_key=api_key)
        model_name = 'gemini-2.5-flash' 
        
        # Xây dựng prompt dựa trên ngữ cảnh
        if user_question:
            # Prompt cho chế độ Chat
            prompt = f"""
            Bạn là một chuyên gia phân tích tài chính chuyên nghiệp và am hiểu về dữ liệu đã cung cấp.
            Dữ liệu tài chính mà bạn cần tham khảo là:
            {data_for_ai}
            
            Hãy trả lời câu hỏi sau của người dùng một cách chính xác, chuyên nghiệp và súc tích, dựa trên dữ liệu đã cho và kiến thức chuyên môn của bạn: "{user_question}"
            """
        else:
            # Prompt gốc cho chế độ Phân tích
            prompt = f"""
            Bạn là một chuyên gia phân tích tài chính chuyên nghiệp. Dựa trên các chỉ số tài chính sau, hãy đưa ra một nhận xét khách quan, ngắn gọn (khoảng 3-4 đoạn) về tình hình tài chính của doanh nghiệp. Đánh giá tập trung vào tốc độ tăng trưởng, thay đổi cơ cấu tài sản và khả năng thanh toán hiện hành.
            
            Dữ liệu thô và chỉ số:
            {data_for_ai}
            """

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text

    except APIError as e:
        return f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}"
    except KeyError:
        return "Lỗi: Không tìm thấy Khóa API 'GEMINI_API_KEY'. Vui lòng kiểm tra cấu hình Secrets trên Streamlit Cloud."
    except Exception as e:
        return f"Đã xảy ra lỗi không xác định: {e}"

# --- Khởi tạo State cho Chat ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "data_for_ai_markdown" not in st.session_state:
    st.session_state.data_for_ai_markdown = None

# --- Chức năng 1: Tải File ---
uploaded_file = st.file_uploader(
    "1. Tải file Excel Báo cáo Tài chính (Chỉ tiêu | Năm trước | Năm sau)",
    type=['xlsx', 'xls']
)

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
                # Lọc giá trị cho Chỉ số Thanh toán Hiện hành
                
                # Lấy Tài sản ngắn hạn
                tsnh_row = df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)]
                tsnh_n = tsnh_row['Năm sau'].iloc[0]
                tsnh_n_1 = tsnh_row['Năm trước'].iloc[0]

                # Lấy Nợ ngắn hạn
                no_ngan_han_row = df_processed[df_processed['Chỉ tiêu'].str.contains('NỢ NGẮN HẠN', case=False, na=False)]
                no_ngan_han_N = no_ngan_han_row['Năm sau'].iloc[0]  
                no_ngan_han_N_1 = no_ngan_han_row['Năm trước'].iloc[0]

                # Xử lý chia cho 0 cho chỉ số
                no_ngan_han_N_safe = no_ngan_han_N if no_ngan_han_N != 0 else 1e-9
                no_ngan_han_N_1_safe = no_ngan_han_N_1 if no_ngan_han_N_1 != 0 else 1e-9
                
                # Tính toán
                thanh_toan_hien_hanh_N = tsnh_n / no_ngan_han_N_safe
                thanh_toan_hien_hanh_N_1 = tsnh_n_1 / no_ngan_han_N_1_safe
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        label="Chỉ số Thanh toán Hiện hành (Năm trước)",
                        value=f"{thanh_toan_hien_hanh_N_1:.2f} lần"
                    )
                with col2:
                    st.metric(
                        label="Chỉ số Thanh toán Hiện hành (Năm sau)",
                        value=f"{thanh_toan_hien_hanh_N:.2f} lần",
                        delta=f"{thanh_toan_hien_hanh_N - thanh_toan_hien_hanh_N_1:.2f}"
                    )
                    
            except IndexError:
                 st.warning("Thiếu chỉ tiêu 'TÀI SẢN NGẮN HẠN' hoặc 'NỢ NGẮN HẠN' để tính chỉ số.")
                 thanh_toan_hien_hanh_N = "N/A" 
                 thanh_toan_hien_hanh_N_1 = "N/A"
            
            # --- Chức năng 5: Nhận xét AI ---
            st.subheader("5. Nhận xét Tình hình Tài chính (AI)")
            
            # Chuẩn bị dữ liệu để gửi cho AI và lưu vào session_state
            st.session_state.data_for_ai_markdown = pd.DataFrame({
                'Chỉ tiêu': [
                    'Toàn bộ Bảng phân tích (dữ liệu thô)', 
                    'Tăng trưởng Tài sản ngắn hạn (%)', 
                    'Thanh toán hiện hành (N-1)', 
                    'Thanh toán hiện hành (N)'
                ],
                'Giá trị': [
                    df_processed.to_markdown(index=False),
                    f"{df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)]['Tốc độ tăng trưởng (%)'].iloc[0]:.2f}%", 
                    f"{thanh_toan_hien_hanh_N}", 
                    f"{thanh_toan_hien_hanh_N}"
                ]
            }).to_markdown(index=False) 

            if st.button("Yêu cầu AI Phân tích", key="analysis_button"):
                api_key = st.secrets.get("GEMINI_API_KEY") 
                
                if api_key:
                    with st.spinner('Đang gửi dữ liệu và chờ Gemini phân tích...'):
                        # Gọi hàm phân tích gốc
                        ai_result = get_ai_analysis(st.session_state.data_for_ai_markdown, api_key, user_question=None)
                        st.markdown("**Kết quả Phân tích từ Gemini AI:**")
                        st.info(ai_result)
                else:
                     st.error("Lỗi: Không tìm thấy Khóa API. Vui lòng cấu hình Khóa 'GEMINI_API_KEY' trong Streamlit Secrets.")

            # --- Chức năng 6: Khung Chat Q&A với Gemini ---
            st.subheader("6. Chat Hỏi & Đáp với AI Phân tích")
            
            if st.session_state.data_for_ai_markdown:
                
                # Hiển thị lịch sử chat
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])

                # Xử lý input từ người dùng
                if prompt := st.chat_input("Hỏi Gemini bất kỳ điều gì về báo cáo tài chính này..."):
                    
                    # 1. Thêm tin nhắn của người dùng vào lịch sử chat
                    st.session_state.messages.append({"role": "user", "content": prompt})
                    with st.chat_message("user"):
                        st.markdown(prompt)
                        
                    # 2. Xử lý câu hỏi và gọi API
                    api_key = st.secrets.get("GEMINI_API_KEY") 

                    if api_key:
                        with st.chat_message("assistant"):
                            with st.spinner('Gemini đang suy nghĩ...'):
                                # Gọi hàm với câu hỏi của người dùng và dữ liệu đã phân tích
                                full_response = get_ai_analysis(
                                    data_for_ai=st.session_state.data_for_ai_markdown, 
                                    api_key=api_key, 
                                    user_question=prompt
                                )
                                st.markdown(full_response)
                                
                            # 3. Thêm phản hồi của AI vào lịch sử chat
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                    else:
                        st.error("Không có API Key. Không thể chat với Gemini.")
                        
            else:
                st.info("Vui lòng tải file và chạy Phân tích (Mục 5) trước khi bắt đầu Chat.")


    except ValueError as ve:
        st.error(f"Lỗi cấu trúc dữ liệu: {ve}")
        # Xóa dữ liệu cũ nếu lỗi
        st.session_state.messages = []
        st.session_state.data_for_ai_markdown = None
    except Exception as e:
        st.error(f"Có lỗi xảy ra khi đọc hoặc xử lý file: {e}. Vui lòng kiểm tra định dạng file.")
        # Xóa dữ liệu cũ nếu lỗi
        st.session_state.messages = []
        st.session_state.data_for_ai_markdown = None

else:
    st.info("Vui lòng tải lên file Excel để bắt đầu phân tích.")
    # Đảm bảo chat bị ẩn khi chưa có file
    st.session_state.messages = []
    st.session_state.data_for_ai_markdown = None
