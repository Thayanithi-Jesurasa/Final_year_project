# =========================================
# workout_session.py  (FULLY CORRECTED + BACKGROUND MUSIC + AUDIBLE BEEP)
# =========================================


import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QDialog, QApplication, QScrollArea, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QTime, QUrl, QSize
from PyQt6.QtGui import QFont, QMovie, QIcon, QPixmap
from PyQt6.QtMultimedia import (
    QCamera, QMediaCaptureSession, QAudioOutput, QMediaPlayer
)
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QStackedWidget
import subprocess
import time
import ctypes
from ctypes import wintypes
import win32gui
import win32con
import win32process
import socket
import time


class WorkoutSession(QWidget):
    """Real-time workout session page with camera monitoring"""

    sessionEnded = pyqtSignal()
    nextWorkoutRequested = pyqtSignal(int)

    # Exercise name → media file mapping
    GIF_MAP = {
        "squats": "Squats.mp4",
        "push ups": "Push ups.mp4",
        "crunches": "Crunches.mp4",
        "jumping jacks": "Jumping jacks.mp4",
        "plank": "Plank.mp4",
        "cobra stretch": "Cobra stretch.mp4"
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_workout = None
        self.current_index = -1   # workout_id
        self.current_workout_id = None
        self.user_gender = "Male"
        self.camera_permission_granted = False
        self.camera_active = False
        self.movie = None

        # ---------- Unity AR Integration ----------
        self.unity_process = None
        self.unity_window_handle = None
        self.unity_check_timer = QTimer(self)
        self.unity_check_timer.timeout.connect(self.find_unity_window)

        # Countdown timer for the 8-second startup delay
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_remaining = 0
        self._countdown_callback = None
        
        # ---------- Camera / Multimedia ----------
        self.camera = QCamera()
        self.capture_session = QMediaCaptureSession()
        self.capture_session.setCamera(self.camera)

        # Stopwatch
        self.stopwatch_timer = QTimer(self)
        self.stopwatch_timer.timeout.connect(self.update_stopwatch)
        self.session_time = QTime(0, 0)

        # Target time
        self.target_seconds = None
        self.target_reached = False

        # Demo player (ALWAYS MUTED)
        self.demo_player = QMediaPlayer(self)
        self.demo_audio = QAudioOutput(self)
        self.demo_audio.setVolume(0.0)
        self.demo_player.setAudioOutput(self.demo_audio)
        self.demo_player.errorOccurred.connect(self.on_demo_media_error)
        self.demo_player.setLoops(QMediaPlayer.Loops.Infinite)

        # ✅ Background music player (NOT muted)
        self.music_player = QMediaPlayer(self)
        self.music_audio = QAudioOutput(self)

        # keep your original music level as "normal"
        self._music_normal_volume = 0.35
        self.music_audio.setVolume(self._music_normal_volume)

        self.music_player.setAudioOutput(self.music_audio)
        self.music_player.setLoops(QMediaPlayer.Loops.Infinite)

        # Resolve music path (same style as other assets)
        self.music_path = self._asset_path("audio.mp3")

        # 1) Reliable beep player using QMediaPlayer (MP3 works reliably here)
        self.beep_player = QMediaPlayer(self)
        self.beep_audio = QAudioOutput(self)
        self.beep_audio.setVolume(1.0)  # max allowed (0.0 - 1.0)
        self.beep_player.setAudioOutput(self.beep_audio)

        self.beep_path = self._asset_path("beep.mp3")
        if os.path.exists(self.beep_path):
            self.beep_player.setSource(QUrl.fromLocalFile(self.beep_path))

        self.init_ui()

    # ---------------- Path Helper ----------------
    def _asset_path(self, filename: str) -> str:
        """Return absolute path of ../assets/<filename>"""
        frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        return os.path.join(frontend_dir, "assets", filename)

    # ---------------- Background music helpers ----------------
    def _start_music(self):
        """Start looping background music (only if file exists)."""
        if not self.music_path or not os.path.exists(self.music_path):
            return

        # If already playing, do nothing
        if self.music_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return

        self.music_player.setSource(QUrl.fromLocalFile(self.music_path))
        self.music_player.play()

    def _stop_music(self):
        """Stop background music safely."""
        try:
            if self.music_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
                self.music_player.stop()
        except Exception:
            pass

    def _pause_music(self):
        """Pause background music safely."""
        try:
            if self.music_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.music_player.pause()
        except Exception:
            pass

    # ---------------- ✅ Music ducking + beep helpers (new, minimal) ----------------
    def _duck_music_for_beep(self):
        """Reduce music so beep is clearly audible."""
        try:
            # lower to a small value temporarily
            self.music_audio.setVolume(0.05)
        except Exception:
            pass

    def _restore_music_after_beep(self):
        """Restore music to normal volume."""
        try:
            self.music_audio.setVolume(self._music_normal_volume)
        except Exception:
            pass

    def _play_beep_audible(self):
        """
        Play beep loudly and reliably using QMediaPlayer.
        """
        # Duck background music first
        self._duck_music_for_beep()

        try:
            if os.path.exists(self.beep_path):
                # QMediaPlayer: stop->play to ensure it restarts every time
                self.beep_player.stop()
                self.beep_audio.setVolume(1.0)
                self.beep_player.play()
            else:
                # Absolute fallback if file is missing
                QApplication.beep()
        except Exception:
            # Final fallback
            QApplication.beep()

        # Restore music shortly after beep starts
        QTimer.singleShot(1200, self._restore_music_after_beep)

    # ---------------- UI ----------------
    def init_ui(self):
        self.setStyleSheet("background-color: #0f0c29;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------------- Target reached toast (NON-BLOCKING, bottom-right) ----------------
        self.target_toast = QFrame(self)
        self.target_toast.setVisible(False)
        self.target_toast.setStyleSheet("""
        QFrame {
            background: rgba(10, 20, 40, 220);
            border: 2px solid #10b981;
            border-radius: 14px;
        }
        """)
        self.target_toast.setMinimumWidth(420)
        self.target_toast.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        toast_layout = QHBoxLayout(self.target_toast)
        toast_layout.setContentsMargins(16, 12, 16, 12)
        toast_layout.setSpacing(10)

        self.target_toast_label = QLabel("")
        self.target_toast_label.setWordWrap(True)
        self.target_toast_label.setStyleSheet("""
        QLabel {
            color: white;
            font-weight: 700;
            font-size: 16px;
            border: none;
            background: transparent;
            padding: 0px;
            line-height: 22px;
        }
        """)
        self.target_toast_label.setMinimumHeight(48)
        self.target_toast_label.setFixedWidth(380)
        toast_layout.addWidget(self.target_toast_label)

        # Make sure toast overlays on top of the UI
        self.target_toast.raise_()

        # ---------------- Top Navbar ----------------
        nav_bar = QFrame()
        nav_bar.setFixedHeight(80)
        nav_bar.setStyleSheet("""
            QFrame {
                background: rgba(15, 12, 41, 0.4);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(50, 0, 50, 0)

        app_title = QLabel("SmartARTrainer")
        app_title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        app_title.setStyleSheet("color: #667eea; background: transparent;")
        nav_layout.addWidget(app_title)

        nav_layout.addStretch()

        btn_style = """
            QPushButton {
                background: transparent;
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.3);
            }
        """

        self.dash_btn = QPushButton("Workout")
        self.dash_btn.setStyleSheet(
            btn_style.replace("transparent", "rgba(102, 126, 234, 0.8)")
                     .replace("1px solid rgba(255, 255, 255, 0.4)", "none")
        )
        self.dash_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dash_btn.clicked.connect(lambda: self.sessionEnded.emit())

        self.analytics_btn = QPushButton("Dashboard")
        self.analytics_btn.setStyleSheet(btn_style)
        self.analytics_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.analytics_btn.clicked.connect(self.on_analytics_clicked)

        self.profile_btn = QPushButton("Profile")
        self.profile_btn.setStyleSheet(btn_style)
        self.profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_btn.clicked.connect(self.on_profile_clicked)

        nav_layout.addWidget(self.dash_btn)
        nav_layout.addSpacing(10)
        nav_layout.addWidget(self.analytics_btn)
        nav_layout.addSpacing(10)
        nav_layout.addWidget(self.profile_btn)

        main_layout.addWidget(nav_bar)

        # ---------------- Scrollable Content Area (Responsive) ----------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        # Create content widget for scroll area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        content_layout.setContentsMargins(50, 20, 50, 40)
        content_layout.setSpacing(15)

        # Header: Workout Name + Timer
        header_layout = QHBoxLayout()

        self.workout_label = QLabel("Workout Name")
        self.workout_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.workout_label.setStyleSheet("color: white; background: transparent;")
        header_layout.addWidget(self.workout_label)

        header_layout.addStretch()

        self.timer_label = QLabel("00:00")
        self.timer_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.timer_label.setStyleSheet("color: #667eea; background: transparent;")
        header_layout.addWidget(self.timer_label)

        content_layout.addLayout(header_layout)

        # Main Split Container (Demo | Camera)
        split_layout = QHBoxLayout()
        split_layout.setSpacing(20)
        self.split_layout = split_layout

        # --- Left: Demo Container ---
        self.demo_container = QFrame()
        self.demo_container.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border-radius: 20px;
                border: 2px solid rgba(255, 255, 255, 0.05);
            }
        """)
        self.demo_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.demo_container.setMinimumHeight(320)

        demo_main_layout = QVBoxLayout(self.demo_container)
        demo_main_layout.setContentsMargins(10, 10, 10, 15)
        demo_main_layout.setSpacing(10)

        demo_header = QHBoxLayout()
        demo_header.addStretch()

        self.close_demo_btn = QPushButton()
        self.close_demo_btn.setFixedSize(30, 30)
        self.close_demo_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        icon_path = self._asset_path("cancel_icon.png")
        if os.path.exists(icon_path):
            self.close_demo_btn.setIcon(QIcon(icon_path))
            self.close_demo_btn.setIconSize(QSize(24, 24))
        else:
            self.close_demo_btn.setText("✕")

        self.close_demo_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: white;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
            }
        """)
        self.close_demo_btn.clicked.connect(self.close_demo_pane)
        demo_header.addWidget(self.close_demo_btn)
        demo_main_layout.addLayout(demo_header)

        # Demo (GIF/Image) widget
        self.demo_widget = QLabel("Demo Video")
        self.demo_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.demo_widget.setStyleSheet("color: #666; font-size: 14px; border: none; background: transparent;")
        self.demo_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.demo_widget.setScaledContents(True)
        demo_main_layout.addWidget(self.demo_widget, stretch=1)

        # Demo (MP4) widget
        self.demo_video_widget = QVideoWidget()
        self.demo_video_widget.setMinimumHeight(240)
        self.demo_video_widget.setStyleSheet("background: transparent;")
        self.demo_video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.demo_video_widget.setVisible(False)
        self.demo_player.setVideoOutput(self.demo_video_widget)
        demo_main_layout.addWidget(self.demo_video_widget, stretch=1)

        self.tutorial_btn = QPushButton("Tutorial")
        self.tutorial_btn.setFixedHeight(40)
        self.tutorial_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tutorial_btn.setStyleSheet("""
            QPushButton {
                background: rgba(102, 126, 234, 0.1);
                color: #667eea;
                border: 1px solid rgba(102, 126, 234, 0.3);
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.2);
            }
        """)
        self.tutorial_btn.clicked.connect(self.open_tutorial)
        demo_main_layout.addWidget(self.tutorial_btn)

        # --- Right: Camera Container ---
        self.video_container = QFrame()
        self.video_container.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border-radius: 20px;
                border: 2px solid rgba(255, 255, 255, 0.05);
            }
        """)
        self.video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_container.setMinimumHeight(320)

        # ✅ FIX: prevent native window stacking issues so toast can overlay above camera
        self.video_container.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.video_container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, False)

        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()

        # ✅ FIX: allow overlay widgets (toast) to appear above the video
        self.video_widget.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.video_widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, False)

        self.video_widget.setStyleSheet("background: transparent; border-radius: 18px;")
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.capture_session.setVideoOutput(self.video_widget)
        
        # --- Stacked Widget for Camera / Unity ---
        self.display_stack = QStackedWidget()
        self.display_stack.setStyleSheet("background: transparent; border: none;")
        self.display_stack.addWidget(self.video_widget)
        
        self.unity_container = QWidget()
        # Ensure it has a native window handle for embedding
        self.unity_container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.unity_container.setStyleSheet("background: #000; border-radius: 18px;")
        self.display_stack.addWidget(self.unity_container)
        
        video_layout.addWidget(self.display_stack)

        split_layout.addWidget(self.demo_container, 40)
        split_layout.addWidget(self.video_container, 60)

        content_layout.addLayout(split_layout)

        # Controls Footer
        footer_layout = QHBoxLayout()

        self.open_demo_btn = QPushButton("Demo")
        self.open_demo_btn.setFixedHeight(55)
        self.open_demo_btn.setMinimumWidth(90)
        self.open_demo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_demo_btn.setStyleSheet("""
            QPushButton {
                background: #2d3748;
                color: white;
                border-radius: 12px;
                font-weight: bold;
                border: 1px solid rgba(255,255,255,0.1);
            }
            QPushButton:hover {
                background: #4a5568;
            }
        """)
        self.open_demo_btn.setVisible(False)
        self.open_demo_btn.clicked.connect(self.open_demo_pane)
        footer_layout.addWidget(self.open_demo_btn)

        self.control_btn = QPushButton("Start")
        self.control_btn.setFixedHeight(55)
        self.control_btn.setMinimumWidth(180)
        self.control_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_start_style()
        self.control_btn.clicked.connect(self.toggle_session)
        footer_layout.addWidget(self.control_btn)

        footer_layout.addStretch()

        self.next_btn = QPushButton("Next Workout")
        self.next_btn.setFixedHeight(50)
        self.next_btn.setMinimumWidth(160)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                   stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border-radius: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                   stop:0 #764ba2, stop:1 #667eea);
            }
        """)
        self.next_btn.setVisible(False)
        self.next_btn.clicked.connect(self.on_next_clicked)
        footer_layout.addWidget(self.next_btn)

        content_layout.addLayout(footer_layout)
        main_layout.addWidget(scroll, 1)

        # ✅ Ensure toast is always above everything after UI is built
        self.target_toast.raise_()

    # ---------------- Target toast helpers ----------------
    def _position_target_toast(self):
        """Place toast at bottom-right of this screen (non-blocking overlay)."""
        margin_x = 28
        margin_y = 28
        self.target_toast.adjustSize()

        w = self.target_toast.width()
        h = self.target_toast.height()
        x = max(0, self.width() - w - margin_x)
        y = max(0, self.height() - h - margin_y)

        self.target_toast.move(x, y)
        self.target_toast.raise_()

    def show_target_toast(self, text: str):
        self.target_toast_label.setText(text)
        self.target_toast_label.adjustSize()
        self.target_toast.adjustSize()
        self.target_toast.setVisible(True)
        self._position_target_toast()

    def hide_target_toast(self):
        self.target_toast.setVisible(False)
        self.target_toast_label.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.target_toast.isVisible():
            self._position_target_toast()
        self.resize_unity_window()

    # ---------------- Tutorial navigation ----------------
    def open_tutorial(self):
        """Tutorial button -> open WorkoutDemo screen for the current workout_id."""
        if self.camera_active:
            self.stop_session()

        self._pause_music()

        if self.demo_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.demo_player.pause()
        if self.movie and self.movie.state() == QMovie.MovieState.Running:
            self.movie.setPaused(True)

        workout_id = self.current_workout_id
        print("DEBUG current_workout_id in WorkoutSession:", workout_id)

        if workout_id is None:
            return

        main_win = self.window()
        if hasattr(main_win, "show_workout_demo"):
            main_win.show_workout_demo(workout_id)

    # ---------------- Demo Pane ----------------
    def close_demo_pane(self):
        """Hide demo pane, pause media, and expand camera"""
        self.demo_container.hide()
        self.open_demo_btn.setVisible(True)

        if self.demo_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.demo_player.pause()

        if self.movie and self.movie.state() == QMovie.MovieState.Running:
            self.movie.setPaused(True)

        self.split_layout.setStretch(0, 0)
        self.split_layout.setStretch(1, 1)

    def open_demo_pane(self):
        """Show demo pane, resume media, and restore split"""
        self.demo_container.show()
        self.open_demo_btn.setVisible(False)

        self.split_layout.setStretch(0, 40)
        self.split_layout.setStretch(1, 60)

        if self.demo_player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self.demo_player.play()

        if self.movie and self.movie.state() == QMovie.MovieState.Paused:
            self.movie.setPaused(False)

    # ---------------- Workout Flow ----------------
    def on_next_clicked(self):
        self.nextWorkoutRequested.emit(self.current_index)
    
    def set_user_gender(self, gender: str):
        self.user_gender = (gender or "Male").strip()
        print("WorkoutSession gender set to:", self.user_gender)

    def set_workout(self, workout: dict, index: int):
        self.current_workout = workout
        self.current_index = index
        self.current_workout_id = workout.get("workout_id")

        print("DEBUG workout dict in set_workout:", workout)
        print("DEBUG saved current_workout_id:", self.current_workout_id)

        name = workout.get("name", "Unknown Workout")
        self.workout_label.setText(name)
        self.preview_gif(name)

        target_val = workout.get("target")
        try:
            self.target_seconds = int(target_val) if target_val is not None else None
        except Exception:
            self.target_seconds = None

        self.target_reached = False
        self.hide_target_toast()
        self.reset_session()

    # ---------------- Demo Media ----------------
    def on_demo_media_error(self, error, error_string):
        self.demo_player.stop()
        self.demo_video_widget.setVisible(False)
        self.demo_widget.setVisible(True)
        self.demo_widget.setText(
            "Video preview unavailable on this PC.\n"
            "Tip: Install a media codec pack / Qt multimedia backend,\n"
            "or replace MP4 previews with GIFs."
        )

    # ---------------- Unity AR Logic ----------------
    def start_unity_ar(self):
        """Launch Unity AR executable and prepare for embedding."""
        try:
            # ✅ Ensure PyQt camera is stopped to avoid conflicts
            self.camera.stop()
            # Give the hardware a moment to release before Unity tries to grab it
            time.sleep(0.5)
            
            # Exercise name → Unity model mapping
            workout_name = (self.current_workout or {}).get("name", "").strip().lower()
            
            unity_models = {
                "plank": {
                    "folder": "PLANK_AR_EX",
                    "exe": "Plank.exe"
                },
                "jumping jacks": {
                    "folder": "JUMPING_JACK_AR_EXE",
                    "exe": "Jumping Jacks.exe"
                },
                "squats": {
                    "folder": "SQUAT_AR_EXE",
                    "exe": "Squat.exe"
                },
                "crunches": {
                    "folder": "CRUNCHES_AR_EXE",
                    "exe": "Crunches.exe"
                },
                "cobra stretch": {
                    "folder": "CobraStrech_AR_EXE",
                    "exe": "CobraStretch.exe"
                },
                "push ups": {
                    "folder": "PUSHUP_AR_EXE",
                    "exe": "Pushup.exe"
                }
            }
            
            model_info = unity_models.get(workout_name)
            if not model_info:
                print(f"No Unity model mapped for workout: {workout_name}")
                self.start_session()
                return

            exe_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", "..", "Unity", 
                model_info["folder"], model_info["exe"]
            ))

            if not os.path.exists(exe_path):
                print(f"Unity executable not found at: {exe_path}")
                self.start_session() # Fallback to normal camera
                return

            # ✅ Switch view to unity container immediately to ensure it's laid out
            self.display_stack.setCurrentWidget(self.unity_container)
            self.unity_container.update()
            
            # Use a slightly longer delay to ensure the OS has processed the widget appearance
            def _launch_after_layout():
                try:
                    winId = int(self.unity_container.winId())
                    rect_win32 = win32gui.GetClientRect(winId)
                    width = rect_win32[2] - rect_win32[0]
                    height = rect_win32[3] - rect_win32[1]
                    
                    if width <= 0 or height <= 0:
                        # Fallback for logical dimensions if client area is zero
                        width = max(640, self.unity_container.width())
                        height = max(480, self.unity_container.height())
                    
                    print(f"Launching Unity with -parentHWND {winId} at physical resolution: {width}x{height}")

                    # Launch Unity process with parentHWND for direct embedding
                    # ✅ Precise width/height matching physical window pixels
                    cmd = [
                        exe_path,
                        "-parentHWND", str(winId),
                        "-popupwindow",
                        "-force-d3d11",
                        "-screen-fullscreen", "0",
                        "-screen-width", str(width),
                        "-screen-height", str(height),
                        "-gender", self.user_gender
                    ]
                    
                    self.unity_process = subprocess.Popen(cmd, cwd=os.path.dirname(exe_path))
                    
                    # Unity process starts immediately, but the workout timer
                    # is held for 8 seconds to give the model time to load and the
                    # user time to get into position.
                    self.unity_check_timer.start(1000)
                    self.camera_active = True
                    self.set_stop_style()

                    def _begin_unity():
                        self.stopwatch_timer.start(1000)
                        self._start_music()

                    self._start_countdown(_begin_unity)
                except Exception as ex:
                    print(f"Error in delayed unity launch: {ex}")

            QTimer.singleShot(250, _launch_after_layout)
            
        except Exception as e:
            print(f"Error starting Unity AR initial step: {e}")
            self.start_session()

    def find_unity_window(self):
        """Attempt to find the Unity window belonging to our process."""
        if not self.unity_process:
            self.unity_check_timer.stop()
            return

        target_pid = self.unity_process.pid

        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                # Get PID of the window
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == target_pid:
                    text = win32gui.GetWindowText(hwnd)
                    # Ignore empty titles or common system wrappers if they appear
                    if text:
                        windows.append((hwnd, text))

        windows = []
        win32gui.EnumWindows(callback, windows)

        if windows:
            # Prefer windows that aren't just "Unity" or generic if multiple exist
            # Usually there is only one
            hwnd, text = windows[0]
            self.unity_window_handle = hwnd
            print(f"Found Unity window: {text} (HWND: {hwnd}) for PID: {target_pid}")
            self.unity_check_timer.stop()
            self.embed_unity_window()

    def embed_unity_window(self):
        """Embed the Unity window into PyQt container."""
        if not self.unity_window_handle:
            return

        try:
            # Re-parent the window
            winId = int(self.unity_container.winId())
            print(f"Embedding Unity HWND {self.unity_window_handle} into container winId {winId}")
            
            # 1) Set parent
            win32gui.SetParent(self.unity_window_handle, winId)
            
            # 2) Update style: add WS_CHILD, remove independent window styles
            # ✅ Added WS_CLIPSIBLINGS and WS_CLIPCHILDREN for cleaner embedding
            style = win32gui.GetWindowLong(self.unity_window_handle, win32con.GWL_STYLE)
            style |= (win32con.WS_CHILD | win32con.WS_CLIPSIBLINGS | win32con.WS_CLIPCHILDREN)
            style &= ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME | win32con.WS_MINIMIZEBOX | win32con.WS_MAXIMIZEBOX | win32con.WS_SYSMENU)
            win32gui.SetWindowLong(self.unity_window_handle, win32con.GWL_STYLE, style)
            
            # 3) Force style update and initial sizing
            # ✅ Use physical client rect for precise Win32 sizing
            rect_win32 = win32gui.GetClientRect(winId)
            w = rect_win32[2] - rect_win32[0]
            h = rect_win32[3] - rect_win32[1]
            
            win32gui.SetWindowPos(
                self.unity_window_handle, 
                win32con.HWND_TOP, 
                0, 0, w, h,
                win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW | win32con.SWP_ASYNCWINDOWPOS
            )
            
            # 4) Apply rounded corners (matching camera window styling)
            # We use ctypes for GDI functions often missing in standard pywin32 bindings
            try:
                # 18px matches the radius set in init_ui
                radius = 18
                hrgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w, h, radius, radius)
                ctypes.windll.user32.SetWindowRgn(self.unity_window_handle, hrgn, True)
            except Exception as rgn_ex:
                print(f"Styling (rounded corners) failed: {rgn_ex}")
            
            # Show the window and force a redraw
            win32gui.ShowWindow(self.unity_window_handle, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(self.unity_window_handle)
            win32gui.InvalidateRect(self.unity_window_handle, None, True)
            
            print("Unity window embedded and shown with styling.")
            
        except Exception as e:
            print(f"Error embedding Unity window: {e}")

    def resize_unity_window(self):
        """Resize embedded unity window to match container and update region styling."""
        if self.unity_window_handle and self.unity_container.isVisible():
            winId = int(self.unity_container.winId())
            rect_win32 = win32gui.GetClientRect(winId)
            w = rect_win32[2] - rect_win32[0]
            h = rect_win32[3] - rect_win32[1]
            
            if w <= 0 or h <= 0: return # Skip invalid size

            # Update the window position and flags for robust scaling
            win32gui.SetWindowPos(
                self.unity_window_handle, 
                win32con.HWND_TOP, 
                0, 0, w, h,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED | win32con.SWP_ASYNCWINDOWPOS
            )
            
            # Keep rounded corners during resize (matching 18px radius)
            try:
                radius = 18
                hrgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w, h, radius, radius)
                ctypes.windll.user32.SetWindowRgn(self.unity_window_handle, hrgn, True)
            except:
                pass
            
            # Force a redraw
            win32gui.InvalidateRect(self.unity_window_handle, None, True)

    def stop_unity_ar(self):
        """Terminate Unity AR process and reset view."""
        self.unity_check_timer.stop()

        # ✅ Ask Unity to send results + exit gracefully
        asked = self.request_unity_send_results_and_exit()

        # ✅ Give Unity a moment to send results to TCP server (5055)
        if asked:
            time.sleep(0.6)

        # ✅ Fallback: if Unity still alive, terminate
        if self.unity_process:
            try:
                self.unity_process.terminate()
            except:
                pass
            self.unity_process = None

        self.unity_window_handle = None
        self.display_stack.setCurrentWidget(self.video_widget)

    def preview_gif(self, workout_name: str):
        key = workout_name.strip().lower()
        media_file = self.GIF_MAP.get(key)

        if not media_file:
            self.demo_widget.setText("No Preview Available")
            self.demo_widget.setVisible(True)
            self.demo_video_widget.setVisible(False)
            return

        self.load_media(media_file)

    def load_media(self, filename: str):
        media_path = self._asset_path(filename)

        if not os.path.exists(media_path):
            self.demo_widget.setText(f"File Not Found:\n{filename}")
            self.demo_widget.setVisible(True)
            self.demo_video_widget.setVisible(False)
            return

        if self.movie:
            self.movie.stop()
            self.movie = None
        self.demo_player.stop()

        ext = os.path.splitext(filename)[1].lower()
        self.demo_audio.setVolume(0.0)

        if ext in [".mp4", ".avi", ".mov", ".mkv"]:
            self.demo_widget.setVisible(False)
            self.demo_video_widget.setVisible(True)
            self.demo_player.setSource(QUrl.fromLocalFile(media_path))
            self.demo_player.play()
        else:
            self.demo_video_widget.setVisible(False)
            self.demo_widget.setVisible(True)

            if ext == ".gif":
                self.movie = QMovie(media_path)
                self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
                self.demo_widget.setMovie(self.movie)
                self.movie.start()
            else:
                pixmap = QPixmap(media_path)
                if pixmap.isNull():
                    self.demo_widget.setText("Preview not supported")
                else:
                    self.demo_widget.setPixmap(pixmap)

            self.demo_widget.setScaledContents(True)

    # ---------------- Session Controls ----------------
    def set_start_style(self):
        self.control_btn.setText("Start")
        self.control_btn.setStyleSheet("""
            QPushButton {
                background: #48bb78;
                color: white;
                border-radius: 15px;
                font-weight: bold;
                font-size: 18px;
            }
            QPushButton:hover {
                background: #38a169;
            }
        """)

    def set_stop_style(self):
        self.control_btn.setText("Stop")
        self.control_btn.setStyleSheet("""
            QPushButton {
                background: #f56565;
                color: white;
                border-radius: 15px;
                font-weight: bold;
                font-size: 18px;
            }
            QPushButton:hover {
                background: #e53e3e;
            }
        """)

    def toggle_session(self):
        # If session is not running -> Start
        if not self.camera_active:
            # ✅ Check camera permission BEFORE starting any session
            if not self.ask_camera_permission_once():
                return

            workout_name = (self.current_workout or {}).get("name", "").strip().lower()

            # Hide NEXT while running
            self.next_btn.setVisible(False)

            # Launch Unity for supported exercises
            if any(ex in workout_name for ex in ["plank", "jumping jacks", "squat", "crunches", "cobra stretch", "push ups"]):
                self.start_unity_ar()
            else:
                self.start_session()

        else:
            # If session is running -> Stop
            self.stop_session()

            # Show NEXT after stopping
            self.next_btn.setVisible(True)
            
    def ask_camera_permission_once(self) -> bool:
        """
        Request camera permission from user on first camera access.
        Shows error message if permission is denied.
        Returns True if permission granted, False otherwise.
        """
        if self.camera_permission_granted:
            return True

        # Create permission dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Camera Permission Required")
        dialog.setFixedSize(480, 220)
        dialog.setModal(True)

        dialog.setStyleSheet("""
            QDialog { 
                background-color: #0f0f10; 
                border: 1px solid #2a2a2a; 
                border-radius: 10px; 
            }
            QLabel { 
                color: white; 
                font-size: 14px; 
                background: transparent;
            }
            QPushButton {
                background: transparent; 
                color: white; 
                font-size: 14px; 
                font-weight: 600;
                min-width: 80px; 
                min-height: 40px; 
                border: 1px solid rgba(255,255,255,0.75);
                border-radius: 8px;
            }
            QPushButton:hover { 
                background: rgba(255,255,255,0.12); 
            }
            QPushButton:pressed { 
                background: rgba(255,255,255,0.20); 
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Title
        title = QLabel("Camera Permission Required")
        title.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: 600; background: transparent;")
        layout.addWidget(title)

        # Message
        message = QLabel(
            "This workout application requires access to your camera to:\n"
            "• Monitor your exercise form and posture\n"
            "• Provide real-time feedback on your movements\n"
            "• Track your workout progress\n\n"
            "Allow camera access to proceed with your workout?"
        )
        message.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        message.setWordWrap(True)
        message.setStyleSheet("color: #b3b3b3; font-size: 13px; background: transparent;")
        layout.addWidget(message)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        allow_btn = QPushButton("Allow Camera Access")
        allow_btn.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.2); 
                color: #10b981; 
                font-size: 14px; 
                font-weight: 600;
                min-width: 120px; 
                min-height: 40px; 
                border: 1px solid #10b981;
                border-radius: 8px;
            }
            QPushButton:hover { 
                background: rgba(16, 185, 129, 0.3); 
            }
            QPushButton:pressed { 
                background: rgba(16, 185, 129, 0.4); 
            }
        """)

        deny_btn = QPushButton("Deny Access")
        deny_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.2); 
                color: #ef4444; 
                font-size: 14px; 
                font-weight: 600;
                min-width: 120px; 
                min-height: 40px; 
                border: 1px solid #ef4444;
                border-radius: 8px;
            }
            QPushButton:hover { 
                background: rgba(239, 68, 68, 0.3); 
            }
            QPushButton:pressed { 
                background: rgba(239, 68, 68, 0.4); 
            }
        """)

        btn_layout.addStretch()
        btn_layout.addWidget(allow_btn)
        btn_layout.addWidget(deny_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # Connect buttons
        allow_btn.clicked.connect(dialog.accept)
        deny_btn.clicked.connect(dialog.reject)

        # Show dialog and get result
        result = dialog.exec() == QDialog.DialogCode.Accepted

        if result:
            self.camera_permission_granted = True
        else:
            # Show error message if permission was denied
            self.show_camera_permission_error()

        return result

    def show_camera_permission_error(self):
        """Display error message when camera permission is denied"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Camera Permission Denied")
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText("Camera Permission Required")
        msg_box.setInformativeText(
            "Camera permission is required to run this workout session.\n\n"
            "The app needs camera access to:\n"
            "• Monitor your exercise form and posture\n"
            "• Provide real-time feedback on your movements\n"
            "• Track your workout progress\n\n"
            "Please enable camera permissions and try again."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #0f0f10;
            }
            QMessageBox QLabel {
                color: white;
                background: transparent;
            }
            QPushButton {
                background: rgba(102, 126, 234, 0.3);
                color: white;
                border: 1px solid rgba(102, 126, 234, 0.6);
                border-radius: 6px;
                padding: 6px 20px;
                min-width: 80px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.5);
            }
        """)
        msg_box.exec()

    def _start_countdown(self, callback):
        """Show an 8-second countdown on the UI then invoke callback."""
        self._countdown_remaining = 8
        self._countdown_callback = callback
        self._update_countdown_label()
        self._countdown_timer.start(1000)

    def _tick_countdown(self):
        """Decrement countdown and fire callback when it reaches zero."""
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            self._hide_countdown_label()
            if self._countdown_callback:
                self._countdown_callback()
                self._countdown_callback = None
        else:
            self._update_countdown_label()

    def _update_countdown_label(self):
        """Show the countdown overlay on the current view."""
        if hasattr(self, 'countdown_label'):
            self.countdown_label.setText(f"Starting in {self._countdown_remaining}...")
            self.countdown_label.setVisible(True)
        else:
            # Create a floating label over the camera/unity container
            self.countdown_label = QLabel(self)
            self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.countdown_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 32px;
                    font-weight: bold;
                    background: rgba(0, 0, 0, 160);
                    border-radius: 12px;
                    padding: 10px 24px;
                }
            """)
            self.countdown_label.setText(f"Starting in {self._countdown_remaining}...")
            self.countdown_label.adjustSize()
            # Center it over the camera widget
            self._reposition_countdown_label()
            self.countdown_label.raise_()
            self.countdown_label.setVisible(True)

    def _reposition_countdown_label(self):
        """Center the countdown label in the display area."""
        if hasattr(self, 'countdown_label') and hasattr(self, 'video_widget'):
            container = self.video_widget
            cx = container.x() + (container.width() - self.countdown_label.width()) // 2
            cy = container.y() + (container.height() - self.countdown_label.height()) // 2
            self.countdown_label.move(cx, cy)

    def _hide_countdown_label(self):
        """Hide the countdown overlay."""
        if hasattr(self, 'countdown_label'):
            self.countdown_label.setVisible(False)

    def start_session(self):
        # Camera permission already checked in toggle_session()
        # Start camera immediately so feed is ready, but hold the timer
        self.camera.start()
        self.camera_active = True
        self.set_stop_style()
        self.next_btn.setVisible(False)

        def _begin():
            self.stopwatch_timer.start(1000)
            self._start_music()

        self._start_countdown(_begin)

    def stop_session(self):
        # Hide toast when user stops
        self.hide_target_toast()

        # Stop music when user stops session
        self._stop_music()

        # Stop Unity if running
        self.stop_unity_ar()

        # Stop camera if it was running
        try:
            self.camera.stop()
        except Exception:
            pass

        self.camera_active = False
        self.stopwatch_timer.stop()

        # UI states
        self.set_start_style()
        self.next_btn.setVisible(True)

    def reset_session(self):
        if self.camera_active:
            self.camera.stop()
            self.stop_unity_ar()
            self.camera_active = False

        # ✅ Always stop music when resetting
        self._stop_music()

        self.stopwatch_timer.stop()
        self.set_start_style()
        self.next_btn.setVisible(False)

        self.session_time = QTime(0, 0)

        # Do NOT clear target_seconds here
        self.target_reached = False

        self.timer_label.setText("00:00")
        self.hide_target_toast()

    def update_stopwatch(self):
        self.session_time = self.session_time.addSecs(1)
        self.timer_label.setText(self.session_time.toString("mm:ss"))

        workout_name = (self.current_workout or {}).get("name", "").strip().lower()
        is_timed = ("plank" in workout_name) or ("cobra" in workout_name)

        if is_timed and self.target_seconds and not self.target_reached:
            elapsed = self.session_time.minute() * 60 + self.session_time.second()
            if elapsed >= int(self.target_seconds):
                self.target_reached = True

                # ✅ FIX: Duck music + play beep clearly
                self._play_beep_audible()

                # Non-blocking toast (no OK)
                self.show_target_toast("Target time reached!")

    # ---------------- Navigation Buttons ----------------
    def on_analytics_clicked(self):
        main_win = self.window()
        if hasattr(main_win, "show_analytics"):
            main_win.show_analytics()

    def on_profile_clicked(self):
        main_win = self.window()
        if hasattr(main_win, "show_profile"):
            main_win.show_profile()
            

    def request_unity_send_results_and_exit(self):
        """
        Ask Unity to send results to PyQt TCP server (5055) and quit gracefully.
        Unity listens on 6060.
        """
        try:
            with socket.create_connection(("127.0.0.1", 6060), timeout=0.6) as s:
                s.sendall(b"SEND_RESULTS_NOW\n")
                # optional read
                try:
                    s.settimeout(0.3)
                    _ = s.recv(64)
                except Exception:
                    pass
            return True
        except Exception as e:
            print("❌ Could not reach Unity control server:", e)
            return False