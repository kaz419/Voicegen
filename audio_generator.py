import os
import time
import pandas as pd
import struct
from google import genai
from google.genai import types

# Constants
VOICE_NAME = "Zephyr"
MODEL_NAME = "gemini-2.5-pro-preview-tts"

def save_binary_file(file_name, data):
    with open(file_name, "wb") as f:
        f.write(data)

def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """PCMデータをWAV形式のヘッダー付きデータに変換する関数"""
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", chunk_size, b"WAVE", b"fmt ", 16, 1, num_channels,
        sample_rate, byte_rate, block_align, bits_per_sample,
        b"data", data_size
    )
    return header + audio_data

def parse_audio_mime_type(mime_type: str) -> dict:
    """MIMEタイプからサンプリングレートなどを解析する関数"""
    bits_per_sample = 16
    rate = 24000
    parts = mime_type.split(";")
    for param in parts:
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate = int(param.split("=", 1)[1])
            except: pass
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except: pass
    return {"bits_per_sample": bits_per_sample, "rate": rate}

class AudioGenerator:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.is_running = False

    def stop(self):
        self.is_running = False

    def generate_single_step(self, text, output_dir, file_name_base, log_callback=print):
        """1つのバリエーションを生成するメソッド"""
        final_path = os.path.join(output_dir, f"{file_name_base}.wav")

        # 既にファイルがあればスキップ
        if os.path.exists(final_path):
            log_callback(f"⏩ Skip: {os.path.basename(final_path)}")
            return True # Success (skipped)

        try:
            generate_content_config = types.GenerateContentConfig(
                temperature=1,
                response_modalities=["audio"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=VOICE_NAME
                        )
                    )
                ),
            )

            # 非ストリーミング生成
            response = self.client.models.generate_content(
                model=MODEL_NAME,
                contents=[types.Content(role="user", parts=[types.Part.from_text(text=text)])],
                config=generate_content_config,
            )

            audio_buffer = bytearray()
            mime_type = "audio/wav"

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        audio_buffer.extend(part.inline_data.data)
                        mime_type = part.inline_data.mime_type
            
            if len(audio_buffer) > 0:
                final_audio = convert_to_wav(audio_buffer, mime_type)
                save_binary_file(final_path, final_audio)
                log_callback(f"💾 Saved: {os.path.basename(final_path)}")
                return True
            else:
                log_callback(f"⚠️ 失敗: 音声データが空でした")
                return False

        except Exception as e:
            error_str = str(e)
            log_callback(f"❌ エラー: {error_str}")
            
            # Check for fatal errors (Quota exceeded)
            if "429" in error_str and "RESOURCE_EXHAUSTED" in error_str:
                if "limit: 0" in error_str or "Day" in error_str:
                    log_callback("🛑 1日の割り当て制限（Quota）を超過しました。本日の生成はこれ以上できません。")
                    return "FATAL_ERROR"
            
            return False
