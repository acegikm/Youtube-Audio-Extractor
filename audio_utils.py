import os
import re
import wave
import subprocess
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Callable
import numpy as np
import yt_dlp

@dataclass
class DownloadResult:
    success: bool
    title: str
    downloaded_path: str
    wav_cache_path: str
    duration_sec: float
    error_message: Optional[str] = None

def sanitize_filename(name: str) -> str:
    # 1. 유니코드 정규화 (NFC: 한글 자모 분리 현상 방지)
    name = unicodedata.normalize('NFC', name)
    # 2. 윈도우 파일명 불가 문자 제거
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name)
    # 3. 특수 공백(NBSP 등) 및 다중 연속 공백을 단일 공백으로 치환
    sanitized = re.sub(r'\s+', " ", sanitized)
    return sanitized.strip()

def make_output_filename(title: str, start_sec: float, end_sec: float) -> str:
    safe_title = sanitize_filename(title)
    def format_time(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}m{s:02d}s"
    start_str = format_time(start_sec)
    end_str = format_time(end_sec)
    return f"{safe_title}_{start_str}_{end_str}.wav"

def get_audio_duration(wav_path: str) -> float:
    try:
        with wave.open(wav_path, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception as e:
        raise RuntimeError(f"오디오 길이를 계산할 수 없습니다: {e}")

def convert_to_wav(input_path: str, output_path: str) -> str:
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", output_path
    ]
    
    # 윈도우 OS일 경우 콘솔창 숨김 플래그 적용
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
    if result.returncode != 0:
        raise RuntimeError(f"WAV 변환 실패: {result.stderr}")
    return output_path

def download_youtube_audio(url: str, output_dir: str, progress_callback: Callable[[int], None] = None) -> DownloadResult:
    os.makedirs(output_dir, exist_ok=True)
    
    def yt_dlp_hook(d):
        if progress_callback:
            if d['status'] == 'downloading':
                percent_str = d.get('_percent_str', '0%')
                percent_str = re.sub(r'\x1b\[[0-9;]*m', '', percent_str)
                try:
                    percent_float = float(percent_str.replace('%', '').strip())
                    progress_callback(int(percent_float))
                except Exception:
                    pass
            elif d['status'] == 'finished':
                progress_callback(100)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'progress_hooks': [yt_dlp_hook] if progress_callback else [],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_id = info.get('id')
            title = info.get('title', 'Unknown Title')
            
            wav_cache_path = os.path.join(output_dir, f"{video_id}_cache.wav")
            
            if os.path.exists(wav_cache_path):
                if progress_callback: progress_callback(100)
                duration_sec = get_audio_duration(wav_cache_path)
                return DownloadResult(
                    success=True, title=title, downloaded_path="",
                    wav_cache_path=wav_cache_path, duration_sec=duration_sec
                )
            
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            convert_to_wav(downloaded_path, wav_cache_path)
            duration_sec = get_audio_duration(wav_cache_path)
            
            return DownloadResult(
                success=True, title=title, downloaded_path=downloaded_path,
                wav_cache_path=wav_cache_path, duration_sec=duration_sec
            )
    except Exception as e:
        return DownloadResult(
            success=False, title="", downloaded_path="",
            wav_cache_path="", duration_sec=0.0, error_message=str(e)
        )

def extract_segment(input_path: str, output_path: str, start_sec: float, end_sec: float) -> str:
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ss", str(start_sec), "-to", str(end_sec),
        "-c:a", "pcm_s16le", output_path
    ]
    
    # 윈도우 OS일 경우 콘솔창 숨김 플래그 적용
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
    if result.returncode != 0:
        raise RuntimeError(f"구간 추출 실패: {result.stderr}")
    return output_path

def load_waveform_preview(wav_path: str, target_points: int = 1000) -> List[float]:
    with wave.open(wav_path, 'rb') as wf:
        n_frames = wf.getnframes()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        if sampwidth != 2: raise ValueError("16-bit WAV 파일만 지원합니다.")
        raw_data = wf.readframes(n_frames)
        samples = np.frombuffer(raw_data, dtype=np.int16)
        if channels > 1: samples = samples[::channels]

    chunk_size = max(1, len(samples) // target_points)
    peaks = []
    for i in range(target_points):
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size
        if start_idx >= len(samples):
            peaks.append(0.0)
            continue
        chunk = samples[start_idx:end_idx]
        peaks.append(float(np.max(np.abs(chunk))))
        
    max_val = max(peaks) if peaks else 1.0
    if max_val == 0: max_val = 1.0
    return [p / max_val for p in peaks]

def find_nearest_zero_crossing(wav_path: str, time_ms: int) -> int:
    try:
        with wave.open(wav_path, 'rb') as wf:
            fs = wf.getframerate()
            n_frames = wf.getnframes()
            channels = wf.getnchannels()
            
            target_frame = int((time_ms / 1000.0) * fs)
            search_frames = int(fs * 0.05) 
            start_frame = max(0, target_frame - search_frames)
            end_frame = min(n_frames, target_frame + search_frames)
            
            wf.setpos(start_frame)
            raw_data = wf.readframes(end_frame - start_frame)
            samples = np.frombuffer(raw_data, dtype=np.int16)
            
            if channels > 1:
                samples = samples[::channels]
            
            if len(samples) < 2: return time_ms
            
            signs = np.sign(samples.astype(np.float32))
            zero_crossings = np.where(np.diff(signs))[0]
            
            if len(zero_crossings) == 0: return time_ms
            
            relative_target = target_frame - start_frame
            closest_idx = zero_crossings[np.argmin(np.abs(zero_crossings - relative_target))]
            final_frame = start_frame + closest_idx
            return int((final_frame / fs) * 1000)
    except Exception:
        return time_ms