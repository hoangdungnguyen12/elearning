# utils.py

import streamlit as st
import pandas as pd
import glob 
import os
import re

# --- 1. TÌM KIẾM VÀ CẤU HÌNH FILE CSV ---

def get_available_files():
    """Tìm tất cả các file .csv trong thư mục hiện tại."""
    csv_files = glob.glob("*.csv") 
    available_files = {}
    for filename in csv_files:
        display_name = filename.replace('.csv', '')
        available_files[display_name] = filename
    
    # Sắp xếp các file theo tên (để file 1-16 hiển thị đúng thứ tự)
    return dict(sorted(available_files.items()))

AVAILABLE_FILES = get_available_files()

# --- 2. HÀM TẢI DỮ LIỆU TỪ CSV ---

@st.cache_data(show_spinner="Đang tải dữ liệu...")
def load_questions(file_path):
    """Tải dữ liệu câu hỏi từ file CSV và xử lý thành danh sách."""
    
    if not os.path.exists(file_path):
        return []
    
    # Thử đọc với các dấu phân cách phổ biến
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
    except Exception:
        try:
            df = pd.read_csv(file_path, encoding='utf-8', sep=';')
        except Exception:
            df = pd.read_csv(file_path, encoding='utf-8', sep='\t')
            
    EXPECTED_COLUMNS = 8
    if df.shape[1] != EXPECTED_COLUMNS:
        return []
    
    df.columns = ['id', 'cauhoi', 'dapan1', 'dapan2', 'dapan3', 'dapan4', 'dapandung', 'trichdan']
    
    questions_list = []
    for index, row in df.iterrows():
        try:
            # Lấy số đáp án (1, 2, 3, 4) và chuyển thành chỉ mục Python (0, 1, 2, 3)
            correct_index = int(str(row['dapandung']).strip()[0]) - 1
        except:
            correct_index = 0
            
        question = {
            "question": row['cauhoi'],
            "options": [row['dapan1'], row['dapan2'], row['dapan3'], row['dapan4']],
            "correct_index": correct_index,
            "explanation": row['trichdan'],
            "source": os.path.basename(file_path) # Thêm nguồn file
        }
        questions_list.append(question)
        
    return questions_list

def get_file_number(display_name):
    """Trích xuất số thứ tự từ tên file."""
    match = re.match(r'(\d+)\.', display_name)
    if match:
        return int(match.group(1))
    return None