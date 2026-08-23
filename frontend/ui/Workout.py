"""
Workout Workout displaying workout plan
Connected to SQLite database using workout_session for unlocks
Professional UI with glassmorphism effects and high-quality layout
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QGridLayout, QMessageBox,
    QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from backend.models.data_manager import (
    get_trainee_info,
    get_workout_plan
)
from backend.models.data_manager import plan_level_and_index

from backend.utils.unity_session_server import start_new_session


class Workout(QWidget):
    logoutSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trainee_id = None
        self.trainee = None
        self.workouts = []
        self.completed_indices = set()
        self.session_completed = False
        self.init_ui()

    # ------------------- UI SETUP -------------------
    def init_ui(self):
        self.setStyleSheet("background: #0F0C29;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        nav_bar = QFrame()
        nav_bar.setFixedHeight(80)
        nav_bar.setStyleSheet("""
            QFrame {
                background: rgba(15, 12, 41, 0.45);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(50, 0, 50, 0)

        app_title = QLabel("SmartARTrainer")
        app_title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        app_title.setStyleSheet("color: #667eea; background: transparent; border: none;")
        nav_layout.addWidget(app_title)
        nav_layout.addStretch()

        btn_style = """
            QPushButton {
                background: %s;
                color: white;
                border: %s;
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.3);
            }
        """

        dash_btn = QPushButton("Workout")
        dash_btn.setStyleSheet(btn_style % ("rgba(102,126,234,0.8)", "none"))

        analytics_btn = QPushButton("Dashboard")
        analytics_btn.setStyleSheet(btn_style % ("transparent", "1px solid rgba(255,255,255,0.4)"))
        analytics_btn.clicked.connect(self.on_analytics_clicked)

        profile_btn = QPushButton("Profile")
        profile_btn.setStyleSheet(btn_style % ("transparent", "1px solid rgba(255,255,255,0.4)"))
        profile_btn.clicked.connect(self.on_profile_clicked)

        nav_layout.addWidget(analytics_btn)
        nav_layout.addSpacing(10)
        nav_layout.addWidget(dash_btn)
        nav_layout.addSpacing(10)
        nav_layout.addWidget(profile_btn)

        main_layout.addWidget(nav_bar)

        # Responsive scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.content_wrapper = QWidget()
        self.content_wrapper.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_wrapper)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Top row moved INSIDE scroll area
        top_row_container = QWidget()
        top_row_container.setStyleSheet("background: transparent; border: none;")
        top_row = QHBoxLayout(top_row_container)
        top_row.setContentsMargins(50, 20, 50, 0)
        top_row.setSpacing(18)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        self.welcome_label = QLabel("Trainee: Loading...")
        self.welcome_label.setObjectName("welcomeLabel")
        self.welcome_label.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self.welcome_label.setAutoFillBackground(False)
        self.welcome_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.plan_label = QLabel("Plan: Personalized")
        self.plan_label.setObjectName("planLabel")
        self.plan_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Medium))
        self.plan_label.setAutoFillBackground(False)
        self.plan_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        top_row_container.setStyleSheet("""
            QWidget { background: transparent; border: none; }

            QLabel#welcomeLabel {
                color: #ffffff;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }

            QLabel#planLabel {
                color: #a3bffa;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)

        info_col.addWidget(self.welcome_label)
        info_col.addWidget(self.plan_label)

        top_row.addLayout(info_col)
        top_row.addStretch()

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setFixedSize(130, 46)
        self.logout_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: white;
                border-radius: 12px;
                font-weight: bold;
                border: 1px solid rgba(255,255,255,0.12);
            }
            QPushButton:hover {
                background: rgba(255,107,107,0.16);
                border-color: #ff6b6b;
                color: #ff6b6b;
            }
        """)
        self.logout_btn.clicked.connect(self.logoutSignal.emit)
        top_row.addWidget(self.logout_btn)

        self.content_layout.addWidget(top_row_container)

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background: transparent;")

        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(30, 20, 30, 30)
        self.grid_layout.setSpacing(20)

        self.content_layout.addWidget(self.grid_container)

        scroll.setWidget(self.content_wrapper)
        main_layout.addWidget(scroll)

    # ------------------- DATA HANDLING -------------------
    def set_user(self, user_data: dict):
        self.trainee_id = user_data.get("trainee_id")
        self.load_Workout_data()

    def load_Workout_data(self):
        if not self.trainee_id:
            return

        self.trainee = get_trainee_info(self.trainee_id)
        print("DEBUG get_trainee_info result:", self.trainee)

        if not self.trainee:
            self.welcome_label.setText("Trainee: Not found")
            self.plan_label.setText("Plan: -")
            self.workouts = []
            self.refresh_cards()
            return

        self.welcome_label.setText(f"Trainee: {self.trainee.get('name', 'User')}")
        plan_id = self.trainee.get("plan_id", 1)
        main_level, _ = plan_level_and_index(plan_id)
        self.plan_label.setText(f"Plan: {main_level}")

        plan_id = self.trainee.get("plan_id")
        self.workouts = get_workout_plan(plan_id) if plan_id else []
        self.refresh_cards()

    def _format_target(self, workout):
        target_val = workout.get("target")
        if target_val is None:
            return "Target: -"

        try:
            target_val = int(target_val)
        except Exception:
            target_val = str(target_val)

        workout_name = str(workout.get("name", "")).strip().lower()

        time_based_workouts = {"plank", "cobra stretch"}
        if workout_name in time_based_workouts:
            return f"{target_val} Sec"

        return f"{target_val} Reps"

    # ------------------- Workout CARDS -------------------
    def refresh_cards(self):
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                w.setParent(None)

        card_layout = QHBoxLayout()
        card_layout.setSpacing(20)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 0, 10, 0)
        left_layout.setSpacing(12)

        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left.setMinimumWidth(260)

        left_layout.addStretch(2)

        quote_top = QLabel("Are you ready to beat your challenge today?")
        quote_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quote_top.setWordWrap(True)
        quote_top.setStyleSheet("""
            QLabel {
                color: rgba(255,255,255,0.90);
                font-size: 28px;
                font-weight: 200;
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)

        quote_bottom = QLabel("Let’s start 💪")
        quote_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quote_bottom.setWordWrap(True)
        quote_bottom.setStyleSheet("""
            QLabel {
                color: #a3bffa;
                font-size: 24px;
                font-weight: 200;
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)

        left_layout.addWidget(quote_top)
        left_layout.addWidget(quote_bottom)
        left_layout.addStretch(3)

        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(18)
        right_layout.setContentsMargins(12, 12, 12, 12)

        right.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 28px;
            }
        """)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right.setMinimumWidth(350)
        right.setMinimumHeight(420)

        title = QLabel("Today's Workout Plan")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 28px;
                font-weight: 800;
                background: transparent;
                border: none;
                padding-top: 8px;
            }
        """)
        right_layout.addWidget(title)

        subtitle = QLabel("Complete each exercise in sequence to finish your session.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("""
            QLabel {
                color: rgba(255,255,255,0.72);
                font-size: 14px;
                background: transparent;
                border: none;
                padding-bottom: 6px;
            }
        """)
        right_layout.addWidget(subtitle)

        plan_card = QFrame()
        plan_card.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 22px;
            }
        """)
        plan_layout = QVBoxLayout(plan_card)
        plan_layout.setContentsMargins(20, 20, 20, 20)
        plan_layout.setSpacing(12)

        if not self.workouts:
            empty = QLabel("No workout plan available.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("""
                QLabel {
                    color: rgba(255,255,255,0.75);
                    font-size: 16px;
                    background: transparent;
                    border: none;
                    padding: 20px;
                }
            """)
            plan_layout.addWidget(empty)
        else:
            for idx, workout in enumerate(self.workouts, start=1):
                row = QFrame()
                row.setStyleSheet("""
                    QFrame {
                        background: rgba(255,255,255,0.05);
                        border: 1px solid rgba(255,255,255,0.08);
                        border-radius: 16px;
                    }
                """)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 8, 10, 8)
                row_layout.setSpacing(8)
                num = QLabel(str(idx))
                num.setAlignment(Qt.AlignmentFlag.AlignCenter)
                num.setFixedSize(34, 34)
                num.setStyleSheet("""
                    QLabel {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                   stop:0 #667eea, stop:1 #764ba2);
                        color: white;
                        font-size: 15px;
                        font-weight: 800;
                        border-radius: 17px;
                        border: none;
                    }
                """)

                name = QLabel(workout.get("name", "Workout"))
                name.setWordWrap(True)
                name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                name.setStyleSheet("""
                    QLabel {
                        color: white;
                        font-size: 18px;
                        font-weight: 700;
                        background: transparent;
                        border: none;
                    }
                """)

                target = QLabel(self._format_target(workout))
                target.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                target.setStyleSheet("""
                    QLabel {
                        color: #a3bffa;
                        font-size: 14px;
                        font-weight: 600;
                        background: transparent;
                        border: none;
                    }
                """)

                row_layout.addWidget(num)
                row_layout.addWidget(name, 1)
                row_layout.addWidget(target)

                plan_layout.addWidget(row)

        right_layout.addWidget(plan_card)
        right_layout.addStretch()

        start_btn = QPushButton("Start Workout")
        start_btn.setFixedHeight(58)
        start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                           stop:0 #667eea, stop:1 #764ba2);
                color: white;
                font-size: 19px;
                font-weight: bold;
                border-radius: 18px;
                padding: 12px 18px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                           stop:0 #764ba2, stop:1 #667eea);
            }
        """)
        start_btn.clicked.connect(self.start_workout_safely)
        right_layout.addWidget(start_btn)

        card_layout.addWidget(left, 2)
        card_layout.addWidget(right, 3)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(card_layout)
        self.grid_layout.addWidget(container, 0, 0)

    def _extract_gender(self):
        if not self.trainee:
            return "Male"

        possible_keys = ["gender", "Gender", "sex", "Sex"]
        raw_gender = None

        for key in possible_keys:
            if key in self.trainee and self.trainee.get(key):
                raw_gender = self.trainee.get(key)
                break

        print("DEBUG trainee data:", self.trainee)
        print("DEBUG raw gender found:", raw_gender)

        if not raw_gender:
            return "Male"

        gender_text = str(raw_gender).strip().lower()

        if gender_text in ["female", "f", "woman", "girl"]:
            return "Female"

        if gender_text in ["male", "m", "man", "boy"]:
            return "Male"

        return str(raw_gender).strip()

    def start_workout_safely(self):
        """Start the first workout in the plan (unlocked)."""
        if not self.workouts:
            QMessageBox.information(self, "No Workouts", "No workout plan found for this user.")
            return

        if not self.trainee_id:
            QMessageBox.warning(self, "User Error", "Trainee ID not found.")
            return

        start_new_session(self.trainee_id)

        first = self.workouts[0]
        workout_id = first.get("workout_id")
        workout_name = first.get("name", "Workout")

        if workout_id is None:
            QMessageBox.warning(self, "Not Available", "Workout session screen is not connected.")
            return

        main_win = self.window()
        user_gender = self._extract_gender()

        print("DEBUG final gender passed to main_window:", user_gender)

        if hasattr(main_win, "show_workout_session"):
            main_win.show_workout_session(workout_id, workout_name, user_gender)
        else:
            QMessageBox.warning(self, "Not Available", "Workout session screen is not connected.")

    def finalize_session(self):
        """Show session completed popup when all exercises are done"""

        QMessageBox.information(
            self,
            "Session Saved",
            "Workout session completed and saved successfully!"
        )

        # Reset for next workout session
        self.completed_indices.clear()

    def mark_exercise_completed(self, index):
        """Call this when an exercise is completed"""

        # Add the completed exercise index
        self.completed_indices.add(index)

        # Check if all workouts are completed
        if len(self.completed_indices) == len(self.workouts):
            self.finalize_session()

    def on_profile_clicked(self):
        main_win = self.window()
        if hasattr(main_win, "show_profile"):
            main_win.show_profile()
        else:
            QMessageBox.information(self, "Not Available", "Profile screen is not connected.")

    def on_analytics_clicked(self):
        main_win = self.window()
        if hasattr(main_win, "show_analytics"):
            main_win.show_analytics()
        else:
            QMessageBox.information(self, "Not Available", "Analytics screen is not connected.")