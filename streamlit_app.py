import streamlit as st
import os
import time
import pandas as pd
from audio_generator import AudioGenerator

st.set_page_config(page_title="Gemini Audio Generator", layout="wide")

st.title("Gemini Audio Generator (Zephyr)")

# Sidebar for configuration
with st.sidebar:
    st.header("設定")
    
    st.markdown("""
    ### 🔑 APIキーの準備
    1. [Google AI Studio](https://aistudio.google.com/app/apikey) にアクセス
    2. "Create API key" をクリック
    3. キーをコピーして下に貼り付け
    """)
    
    api_key = st.text_input("Gemini API Key", type="password", help="AIzaSy...で始まるキーを入力してください")
    
    # Directory Picker (Simplified)
    st.subheader("保存先")
    
    # Always use Desktop/voice_output_zephyr
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "voice_output_zephyr")
    
    # Create directory if it doesn't exist
    if not os.path.exists(desktop_path):
        try:
            os.makedirs(desktop_path, exist_ok=True)
        except:
            pass

    st.session_state.current_path = desktop_path
    st.info(f"ファイルはデスクトップの `{desktop_path}` に保存されます。")
    
    if st.button("📂 保存先フォルダを開く"):
        import subprocess
        try:
            subprocess.run(["open", desktop_path])
        except Exception as e:
            st.error(f"フォルダを開けませんでした: {e}")

    output_dir = desktop_path

    variations = st.slider("生成数 (バリエーション)", min_value=1, max_value=10, value=1)
    st.info(f"推定コスト: 無料 (Previewモデル)")

# Main area
st.header("ファイル選択")
uploaded_file = st.file_uploader("Excelファイルを選択してください", type=["xlsx"])

# Initialize Session State
if "processing" not in st.session_state:
    st.session_state.processing = False
if "paused" not in st.session_state:
    st.session_state.paused = False
if "df" not in st.session_state:
    st.session_state.df = None
if "current_index" not in st.session_state:
    st.session_state.current_index = 1 # Start from 1 (skip header)
if "current_variation" not in st.session_state:
    st.session_state.current_variation = 0
if "total_rows" not in st.session_state:
    st.session_state.total_rows = 0
if "unique_output_dir" not in st.session_state:
    st.session_state.unique_output_dir = ""
if "log_text" not in st.session_state:
    st.session_state.log_text = ""
if "generator" not in st.session_state:
    st.session_state.generator = None

# UI Containers
progress_container = st.empty()
status_container = st.empty()
log_container = st.container()
log_placeholder = log_container.empty()

def update_log(message):
    st.session_state.log_text += message + "\n"
    log_placeholder.code(st.session_state.log_text)

# Display Log (Always)
log_placeholder.code(st.session_state.log_text)

if uploaded_file and api_key:
    # Start Button
    if not st.session_state.processing and not st.session_state.paused:
        if st.button("生成開始", type="primary"):
            # Initialize
            try:
                df = pd.read_excel(uploaded_file, header=None)
                
                # Pre-scan for valid rows (Column C = index 2)
                valid_rows_count = 0
                target_column_index = 2
                
                # Start from index 1 (skip header)
                for i in range(1, len(df)):
                    text = str(df.iloc[i, target_column_index])
                    if not text or text.lower() == "nan" or text.strip() == "":
                        break
                    valid_rows_count += 1
                
                if valid_rows_count == 0:
                    st.error("有効なデータが見つかりませんでした（C列が空、またはヘッダーのみ）。")
                    st.stop()

                # Limit df to valid rows + header
                # We keep the original df structure but will only iterate up to valid_rows_count
                st.session_state.df = df
                st.session_state.total_rows = valid_rows_count # Actual data rows
                st.session_state.current_index = 1 # Skip header
                st.session_state.current_variation = 0
                st.session_state.processing = True
                st.session_state.paused = False
                st.session_state.log_text = "" # Clear log
                
                # Create output dir
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                unique_output_dir = os.path.join(output_dir, f"output_{timestamp}")
                os.makedirs(unique_output_dir, exist_ok=True)
                st.session_state.unique_output_dir = unique_output_dir
                
                st.session_state.generator = AudioGenerator(api_key)
                
                total_ops = valid_rows_count * variations
                update_log(f"📄 Excel読み込み完了: 有効データ{valid_rows_count}行 (x{variations}パターン = 計{total_ops}回生成)")
                update_log(f"今回の保存先: {unique_output_dir}")
                st.rerun()
            except Exception as e:
                st.error(f"初期化エラー: {e}")

    # Stop/Pause Buttons (Only when processing or paused)
    if st.session_state.processing or st.session_state.paused:
        col_stop, col_pause = st.columns(2)
        with col_stop:
            if st.button("⏹ 完全停止", type="primary"):
                st.session_state.processing = False
                st.session_state.paused = False
                update_log("🛑 ユーザーにより停止されました。")
                st.rerun()
        
        with col_pause:
            if st.session_state.paused:
                if st.button("▶ 再開"):
                    st.session_state.paused = False
                    st.session_state.processing = True
                    update_log("▶ 再開します...")
                    st.rerun()
            else:
                if st.button("⏸ 一時停止"):
                    st.session_state.paused = True
                    st.session_state.processing = False
                    update_log("⏸ 一時停止しました。")
                    st.rerun()

    # Processing Loop (One step per rerun)
    if st.session_state.processing and not st.session_state.paused:
        df = st.session_state.df
        idx = st.session_state.current_index
        var_idx = st.session_state.current_variation
        total_valid_rows = st.session_state.total_rows
        target_column_index = 2 # C column

        # Progress Bar
        total_ops = total_valid_rows * variations
        # Current op: (rows done so far * variations) + current variation
        # rows done so far = idx - 1
        current_op = (idx - 1) * variations + var_idx
        
        progress = min(1.0, current_op / max(1, total_ops))
        progress_container.progress(progress)
        status_container.text(f"処理中: 行 {idx}/{total_valid_rows} (Excel行:{idx+1}) - バリエーション {var_idx+1}/{variations}")

        # Check limits (idx starts at 1. If we have 2 valid rows, we process idx=1 and idx=2. So stop if idx > total_valid_rows)
        if idx > total_valid_rows:
            st.session_state.processing = False
            progress_container.progress(1.0)
            status_container.text("完了")
            update_log("🎉 すべて完了しました！")
            st.balloons()
            st.rerun()

        row = df.iloc[idx]
        text = str(row.iloc[target_column_index])

        # Double check empty (should not happen with pre-scan but good for safety)
        if not text or text.lower() == "nan" or text.strip() == "":
            st.session_state.processing = False
            update_log("🛑 (予期せぬ) 空白セル検出。終了します。")
            st.balloons()
            st.rerun()
        else:
            # Generate
            safe_text = "".join(x for x in text[:10] if x.isalnum())
            suffix = f"_v{var_idx+1}" if variations > 1 else ""
            file_name_base = f"{idx}_{safe_text}{suffix}" # Use data index (1-based relative to data) or Excel row? Let's use Excel row index for clarity -> idx+1 is Excel row index if header is 1. Wait, idx is 1-based index of df. df has header at 0. So idx=1 is row 2.
            # Let's use a simple counter for file name to match user expectation: 1, 2, 3...
            # The user wants "sequential_number...". 
            # If we start at idx=1 (Row 2), that is the 1st data row.
            file_number = idx 
            file_name_base = f"{file_number}_{safe_text}{suffix}"
            
            update_log(f"⏳ 生成中 ({idx}/{total_valid_rows} - {var_idx+1}/{variations}): {text[:10]}...")
            
            result = st.session_state.generator.generate_single_step(
                text, 
                st.session_state.unique_output_dir, 
                file_name_base, 
                log_callback=update_log
            )

            if result == "FATAL_ERROR":
                st.session_state.processing = False
                st.error("APIの利用制限（Quota）に達したため、処理を停止しました。")
                st.balloons() # Optional: maybe not balloons for error
                st.rerun()

            # Wait logic
            if result is True:
                time.sleep(5) 
            else:
                time.sleep(5) # Error wait

            # Increment counters
            var_idx += 1
            if var_idx >= variations:
                var_idx = 0
                idx += 1
            
            st.session_state.current_variation = var_idx
            st.session_state.current_index = idx
            st.rerun()

elif not uploaded_file:
    st.warning("Excelファイルをアップロードしてください。")
elif not api_key:
    st.warning("APIキーを入力してください。")
