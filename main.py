import sys
import os
import ctypes
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QComboBox, QPushButton, QLabel, 
                             QFileDialog, QMessageBox, QSlider, QScrollArea, QStyle,
                             QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal, QUrl, Qt, QSize
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QIcon

import audio_utils
from waveform_widget import WaveformWidget

HISTORY_FILE = "history.json"

def resource_path(relative_path):
    """ PyInstaller 환경에서 절대 경로를 반환함 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class DownloadWorker(QThread):
    finished = pyqtSignal(object)
    progress = pyqtSignal(int) 
    
    def __init__(self, url, output_dir):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        
    def run(self):
        def progress_callback(val):
            self.progress.emit(val)
        result = audio_utils.download_youtube_audio(self.url, self.output_dir, progress_callback)
        self.finished.emit(result)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Audio Extractor Pro v1.0")
        self.resize(1000, 400)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        
        self.current_res = None
        self.sel_start = 0
        self.sel_end = 0
        self.duration_ms = 0 
        self.is_loop = False
        
        self.last_pos = 0      
        self.is_seeking = False 

        self.last_export_dir = ""

        self.player = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.player.setAudioOutput(self.audio_out)
        self.audio_out.setVolume(0.5)
        
        self.history = self.load_history()
        self.init_ui()
        self.bind_signals()

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return []

    def save_history(self, url, title):
        entry = f"{url} ({title})"
        if entry in self.history:
            self.history.remove(entry)
        self.history.insert(0, entry)
        self.history = self.history[:15]
        
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
            
        self.url_combo.clear()
        self.url_combo.addItems(self.history)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(15, 15, 15, 10)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.url_combo = QComboBox()
        self.url_combo.setEditable(True)
        self.url_combo.setPlaceholderText("YouTube URL을 입력하세요...")
        self.url_combo.addItems(self.history)
        
        self.btn_dl = QPushButton(" Download")
        self.btn_dl.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        
        top.addWidget(self.url_combo, 1)
        top.addWidget(self.btn_dl)
        layout.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.waveform = WaveformWidget()
        self.scroll.setWidget(self.waveform)
        layout.addWidget(self.scroll, 1)

        bot = QHBoxLayout()
        
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        
        self.btn_reset = QPushButton(" Reset")
        self.btn_reset.setToolTip("전체 구간 선택")
        
        self.btn_loop = QPushButton(" Loop")
        self.btn_loop.setCheckable(True)
        self.btn_loop.setToolTip("반복 재생 (L)")
        
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.setFixedWidth(100)
        
        self.lbl_time = QLabel("00:00.000 ~ 00:00.000")
        self.lbl_time.setStyleSheet("font-family: monospace; font-weight: bold; color: #444;")
        
        self.btn_export = QPushButton(" Export Selection")
        self.btn_export.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))

        for b in [self.btn_play_pause, self.btn_reset, self.btn_loop, self.btn_export]:
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        bot.addWidget(self.btn_play_pause)
        bot.addWidget(self.btn_reset)
        bot.addWidget(self.btn_loop)
        bot.addSpacing(20)
        bot.addWidget(QLabel("Vol:"))
        bot.addWidget(self.vol_slider)
        bot.addStretch()
        bot.addWidget(self.lbl_time)
        bot.addStretch()
        bot.addWidget(self.btn_export)
        layout.addLayout(bot)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(4)
        self.pbar.setTextVisible(False)
        self.pbar.hide()
        layout.addWidget(self.pbar)

        self.statusBar().showMessage("준비 완료.")

    def bind_signals(self):
        self.btn_dl.clicked.connect(self.on_dl)
        self.url_combo.lineEdit().returnPressed.connect(self.on_dl)
        self.btn_play_pause.clicked.connect(self.toggle_play)
        self.btn_reset.clicked.connect(self.reset_selection)
        self.btn_loop.clicked.connect(lambda v: setattr(self, 'is_loop', v))
        self.vol_slider.valueChanged.connect(lambda v: self.audio_out.setVolume(v/100))
        self.btn_export.clicked.connect(self.on_export)

        self.waveform.selectionChanged.connect(self.on_sel_changed)
        self.waveform.seekRequested.connect(self.seek_player)
        self.waveform.zoomRequested.connect(self.on_zoom)
        self.player.positionChanged.connect(self.on_pos_changed)
        self.player.playbackStateChanged.connect(self.update_ui)

    def seek_player(self, pos):
        self.is_seeking = True
        self.player.setPosition(pos)
        self.waveform.set_playhead(pos)
        self.last_pos = pos 
        self.is_seeking = False

    def keyPressEvent(self, e):
        if not self.current_res: return
        if e.key() == Qt.Key.Key_Space: self.toggle_play()
        elif e.key() == Qt.Key.Key_L: self.btn_loop.click()

    def toggle_play(self):
        if not self.current_res: return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def reset_selection(self):
        if self.duration_ms > 0:
            self.waveform.set_selection(0, self.duration_ms)
            self.on_sel_changed(0, self.duration_ms)
            self.seek_player(0)

    def on_sel_changed(self, s, e):
        self.sel_start, self.sel_end = s, e
        self.update_time_lbl()
        
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            cur = self.player.position()
            if s < e and (cur < s or cur >= e):
                if self.is_loop:
                    self.seek_player(s)
                else:
                    self.player.pause()
                    self.seek_player(e)

    def on_pos_changed(self, p):
        # 💡 핵심 방어: 마우스로 쥐고 조작 중일 때는 자동 루프/정지가 개입하지 못하게 차단
        if self.is_seeking or getattr(self.waveform, 'dragging_marker', None) == 'playhead':
            return
            
        # 💡 튕김 방지: UI에 그리기 전에 경계선 통과 여부를 "먼저" 확인
        if self.sel_start < self.sel_end:
            if p >= self.sel_end:
                if self.is_loop:
                    self.seek_player(self.sel_start)
                else:
                    self.player.pause()
                    self.seek_player(self.sel_end)
                return # 여기서 종료하여 밖으로 튀어나간 UI를 아예 안 그림
            elif p < self.sel_start:
                self.seek_player(self.sel_start)
                return
                
        # 아무 보정에도 걸리지 않은 정상 위치만 위젯에 업데이트
        self.waveform.set_playhead(p)
        self.last_pos = p

    def update_time_lbl(self):
        def fmt(ms):
            s = ms // 1000
            milis = ms % 1000
            return f"{s // 60:02d}:{s % 60:02d}.{milis:03d}"
        
        dur = max(0, self.sel_end - self.sel_start)
        self.lbl_time.setText(f"{fmt(self.sel_start)} ~ {fmt(self.sel_end)} ({fmt(dur)})")

    def on_zoom(self, z, ax):
        hbar = self.scroll.horizontalScrollBar()
        rel = (hbar.value() + ax) / self.waveform.width() if self.waveform.width() > 0 else 0
        
        new_width = int(self.scroll.viewport().width() * z)
        self.waveform.setMinimumWidth(new_width)
        self.waveform.resize(new_width, self.waveform.height())
        
        hbar.setValue(int(rel * new_width - ax))

    def on_dl(self):
        url = self.url_combo.currentText().split(" (")[0].strip()
        if not url: return
        
        self.btn_dl.setEnabled(False)
        self.pbar.setValue(0)
        self.pbar.show()
        self.statusBar().showMessage("다운로드 및 분석 중...")
        
        self.worker = DownloadWorker(url, "cache")
        self.worker.progress.connect(self.pbar.setValue)
        self.worker.finished.connect(self.on_dl_fin)
        self.worker.start()

    def on_dl_fin(self, res):
        self.btn_dl.setEnabled(True)
        self.pbar.hide()
        
        if not res.success:
            QMessageBox.warning(self, "오류", f"다운로드 실패: {res.error_message}")
            self.statusBar().showMessage("대기 중.")
            return
            
        self.current_res = res
        self.duration_ms = int(res.duration_sec * 1000)
        self.save_history(self.url_combo.currentText().split(" (")[0], res.title)
        
        viewport_width = self.scroll.viewport().width()
        self.waveform.setMinimumWidth(viewport_width)
        
        samples = audio_utils.load_waveform_preview(res.wav_cache_path, 2000)
        self.waveform.set_waveform(samples, res.duration_sec, res.wav_cache_path)
        
        self.reset_selection()
        
        self.player.setSource(QUrl.fromLocalFile(res.wav_cache_path))
        self.statusBar().showMessage(f"로드 완료: {res.title}")

    def update_ui(self):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        icon = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.btn_play_pause.setIcon(self.style().standardIcon(icon))
        self.waveform.is_playing = playing

    def on_export(self):
        if not self.current_res: return
        
        default_name = audio_utils.make_output_filename(
            self.current_res.title, self.sel_start/1000, self.sel_end/1000
        )
        
        # 이전 저장 경로가 존재하면 디렉터리와 파일명을 결합하여 기본값으로 설정
        default_path = os.path.join(self.last_export_dir, default_name) if self.last_export_dir else default_name
        
        path, _ = QFileDialog.getSaveFileName(self, "구간 저장", default_path, "WAV (*.wav)")
        
        if path:
            # 파일 저장이 승인되면 해당 디렉터리 경로를 저장해둠
            self.last_export_dir = os.path.dirname(path)
            
            try:
                self.statusBar().showMessage("추출 중...")
                audio_utils.extract_segment(self.current_res.wav_cache_path, path, 
                                          self.sel_start/1000, self.sel_end/1000)
                QMessageBox.information(self, "완료", "파일이 성공적으로 저장되었습니다.")
                self.statusBar().showMessage("추출 완료.")
            except Exception as e:
                QMessageBox.critical(self, "실패", str(e))
                self.statusBar().showMessage("추출 실패.")

if __name__ == "__main__":

    try:
        # 윈도우에게 별도의 앱 아이디를 등록하여 python.exe 아이콘과 분리함
        myappid = 'mycompany.myproduct.subproduct.version' # 임의의 문자열
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except:
        pass

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())