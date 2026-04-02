from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt6.QtCore import pyqtSignal, Qt, QRectF
import audio_utils

class WaveformWidget(QWidget):
    selectionChanged = pyqtSignal(int, int)
    seekRequested = pyqtSignal(int)
    zoomRequested = pyqtSignal(float, float)
    selectionFinished = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self.samples = []
        self.duration_ms = 0
        self.start_ms = 0
        self.end_ms = 0
        self.playhead_ms = 0

        self.dragging_marker = None
        self.marker_hit_tolerance = 15
        self.is_creating_selection = False
        self.drag_start_time = 0
        
        self.press_x = 0
        self.has_dragged = False
        self.is_playing = False 

        self.zoom_factor = 1.0
        self.is_snap_enabled = True 
        self.wav_path = ""
        
        self.min_sel_ms = 100 

        # DAW 스타일 컬러셋
        self.color_bg = QColor(25, 25, 25)
        self.color_waveform = QColor(75, 120, 210, 200)
        self.color_selection = QColor(255, 255, 255, 35)
        self.color_start_marker = QColor(46, 204, 113) 
        self.color_end_marker = QColor(231, 76, 60)   
        self.color_playhead = QColor(241, 196, 15)   

    def set_waveform(self, samples, duration_sec, wav_path):
        self.samples = samples
        self.duration_ms = int(duration_sec * 1000)
        self.start_ms, self.end_ms = 0, self.duration_ms
        self.playhead_ms = 0
        self.wav_path = wav_path
        self.update()

    def set_selection(self, start_ms, end_ms):
        self.start_ms = max(0, min(start_ms, self.duration_ms))
        self.end_ms = max(0, min(end_ms, self.duration_ms))
        self.update()

    def set_playhead(self, position_ms):
        # 💡 방어 로직: 마우스로 헤드를 드래그 중일 때는 시스템의 자동 위치 업데이트를 무시함
        if self.dragging_marker == 'playhead':
            return
        self.playhead_ms = max(0, min(position_ms, self.duration_ms))
        self.update()

    def time_to_x(self, time_ms):
        return (time_ms / self.duration_ms) * self.width() if self.duration_ms > 0 else 0

    def x_to_time(self, x):
        return max(0, min(int((x / self.width()) * self.duration_ms), self.duration_ms)) if self.width() > 0 else 0

    def mousePressEvent(self, event):
        if self.duration_ms == 0: return
        x = event.pos().x()
        t = self.x_to_time(x)
        s_x, e_x, p_x = self.time_to_x(self.start_ms), self.time_to_x(self.end_ms), self.time_to_x(self.playhead_ms)

        self.press_x = x
        self.has_dragged = False

        is_selection_active = (self.end_ms - self.start_ms) >= min(self.min_sel_ms, self.duration_ms)
        
        if is_selection_active and abs(x - s_x) <= self.marker_hit_tolerance:
            self.dragging_marker = 'start'
        elif is_selection_active and abs(x - e_x) <= self.marker_hit_tolerance:
            self.dragging_marker = 'end'
        elif abs(x - p_x) <= self.marker_hit_tolerance:
            self.dragging_marker = 'playhead'
            # 💡 잡는 순간부터 무조건 구간 내부로 강제 정렬
            if is_selection_active:
                self.playhead_ms = max(self.start_ms, min(t, self.end_ms))
                self.seekRequested.emit(self.playhead_ms)
        else:
            self.is_creating_selection = True
            self.drag_start_time = t
            self.playhead_ms = t
            self.seekRequested.emit(t)
            
        self.update()

    def mouseMoveEvent(self, event):
        if self.duration_ms == 0: return
        x = event.pos().x()
        t = self.x_to_time(x)
        min_len = min(self.min_sel_ms, self.duration_ms)

        if abs(x - self.press_x) >= 5:
            self.has_dragged = True

        if self.dragging_marker == 'start':
            self.start_ms = min(t, self.end_ms - min_len)
            self.selectionChanged.emit(self.start_ms, self.end_ms)
        elif self.dragging_marker == 'end':
            self.end_ms = max(t, self.start_ms + min_len)
            self.selectionChanged.emit(self.start_ms, self.end_ms)
        elif self.dragging_marker == 'playhead':
            # 💡 재생/정지 여부 상관없이 마우스 이동(Move) 중 무조건 구간 내에 클리핑
            is_selection_active = (self.end_ms - self.start_ms) >= min_len
            if is_selection_active:
                self.playhead_ms = max(self.start_ms, min(t, self.end_ms))
            else:
                self.playhead_ms = t
            self.seekRequested.emit(self.playhead_ms)
        elif self.is_creating_selection and self.has_dragged:
            s = min(self.drag_start_time, t)
            e = max(self.drag_start_time, t)
            if e - s < min_len:
                e = min(s + min_len, self.duration_ms)
                s = max(0, e - min_len)
            self.start_ms, self.end_ms = s, e
            self.selectionChanged.emit(self.start_ms, self.end_ms)
        
        self.update()

    def mouseReleaseEvent(self, event):
        if self.duration_ms == 0: return
        
        if self.is_snap_enabled and self.wav_path and self.has_dragged:
            if self.dragging_marker in ['start', 'end'] or self.is_creating_selection:
                self.start_ms = audio_utils.find_nearest_zero_crossing(self.wav_path, self.start_ms)
                self.end_ms = audio_utils.find_nearest_zero_crossing(self.wav_path, self.end_ms)
                
                min_len = min(self.min_sel_ms, self.duration_ms)
                if self.end_ms - self.start_ms < min_len:
                    self.end_ms = min(self.start_ms + min_len, self.duration_ms)
                    
                self.update()
                self.selectionChanged.emit(self.start_ms, self.end_ms)

        self.dragging_marker = None
        self.is_creating_selection = False
        self.has_dragged = False
        self.selectionFinished.emit(self.start_ms, self.end_ms)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid_y = h / 2
        painter.fillRect(0, 0, w, h, self.color_bg)
        if not self.samples: return

        path = QPainterPath()
        num = len(self.samples)
        step = max(1, num // (w * 2))
        for i in range(0, num, step):
            x = (i / num) * w
            amp = self.samples[i] * (mid_y - 10)
            if i == 0: path.moveTo(x, mid_y - amp)
            else: path.lineTo(x, mid_y - amp)
        for i in reversed(range(0, num, step)):
            x = (i / num) * w
            amp = self.samples[i] * (mid_y - 10)
            path.lineTo(x, mid_y + amp)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(self.color_waveform); painter.drawPath(path)

        is_selection_active = (self.end_ms - self.start_ms) >= min(self.min_sel_ms, self.duration_ms)
        if is_selection_active:
            s_x, e_x = self.time_to_x(self.start_ms), self.time_to_x(self.end_ms)
            painter.fillRect(QRectF(s_x, 0, e_x - s_x, h), self.color_selection)
            painter.setPen(QPen(self.color_start_marker, 2)); painter.drawLine(int(s_x), 0, int(s_x), h)
            painter.setPen(QPen(self.color_end_marker, 2)); painter.drawLine(int(e_x), 0, int(e_x), h)
        
        p_x = self.time_to_x(self.playhead_ms)
        painter.setPen(QPen(self.color_playhead, 2)); painter.drawLine(int(p_x), 0, int(p_x), h)

    def wheelEvent(self, event):
        if self.duration_ms == 0: return
        old_zoom = self.zoom_factor
        self.zoom_factor = min(30.0, max(1.0, self.zoom_factor * (1.2 if event.angleDelta().y() > 0 else 0.833)))
        if old_zoom != self.zoom_factor:
            self.zoomRequested.emit(self.zoom_factor, event.position().x())