# ============================
# AnalyticsScreen.py (UPDATED)
# Matplotlib charts -> Offline Chart.js (NO CDN)
# ✅ ALL LOGIC remains SAME
# ✅ Only chart rendering parts changed
# ============================

import os
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QPushButton, QSizePolicy, QGridLayout, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QStackedWidget
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWebEngineCore import QWebEnginePage

# ✅ Chart.js offline rendering via WebEngine
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

from backend.models.data_manager import session_analytics, get_trainee_info
from backend.models.data_manager import get_workout_plan

from backend.utils.activity_tracker import is_inactive_30_days, update_last_activity
from backend.models.data_manager import reset_sessions_after_promotion
from backend.models.data_manager import plan_level_and_index


# ============================================================
# ✅ Offline Chart.js Widget (NO INTERNET)
# Put file here:
#   assets/chart.umd.min.js
# ============================================================
class ChartJsView(QWebEngineView):
    """
    Offline Chart.js renderer for PyQt6 (NO CDN)
    ✅ Embeds chart.umd.min.js directly into HTML to avoid file:// blocking
    """
    def __init__(self, parent=None, height=450):
        super().__init__(parent)
        self.setMinimumHeight(height)

        self._loaded = False
        self._pending_config = None

        # your file: frontend/assets/chart.umd.min.js
        base_dir = os.path.dirname(os.path.abspath(__file__))  # frontend/ui
        project_dir = os.path.dirname(base_dir)                # frontend

        chart_path = os.path.join(project_dir, "assets", "chart.umd.min.js")
        datalabel_path = os.path.join(project_dir, "assets", "chartjs-plugin-datalabels.min.js")

        # ----- Chart.js file check -----
        if not os.path.exists(chart_path):
            self.setHtml(f"<h2>Chart.js file not found:</h2><pre>{chart_path}</pre>")
            return

        # ----- DataLabels plugin file check -----
        if not os.path.exists(datalabel_path):
            self.setHtml(f"<h2>ChartDataLabels plugin not found:</h2><pre>{datalabel_path}</pre>")
            return

        # ✅ Read JS files and embed them
        with open(chart_path, "r", encoding="utf-8") as f:
            chart_js = f.read()

        with open(datalabel_path, "r", encoding="utf-8") as f:
            datalabel_js = f.read()

        html = f"""
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8"/>
          <style>
            html, body {{
              margin: 0;
              padding: 0;
              height: 100%;
              background: transparent;
              overflow: hidden;
            }}
            #wrap {{
              height: 100%;
              padding: 12px;
              box-sizing: border-box;
            }}
            canvas {{
              width: 100% !important;
              height: 100% !important;
              background: rgba(255,255,255,0.02);
              border-radius: 12px;
            }}
          </style>

          <!-- ✅ Embedded Chart.js -->
          <script>
          {chart_js}
          </script>

          <!-- ✅ Embedded ChartDataLabels plugin -->
          <script>
          {datalabel_js}
          </script>
        </head>

        <body>
          <div id="wrap">
            <canvas id="c"></canvas>
          </div>

          <script>
            // ✅ Register plugin globally (IMPORTANT)
            if (typeof ChartDataLabels !== "undefined") {{
              Chart.register(ChartDataLabels);
            }}

            let chart = null;

            function renderChart(cfg) {{
              try {{
                // ✅ Attach REAL JS functions (not strings) so % text works

                // datalabels formatter -> shows "85%"
                if (cfg && cfg.options && cfg.options.plugins && cfg.options.plugins.datalabels) {{
                  cfg.options.plugins.datalabels.formatter = (value) => {{
                    if (value === null || value === undefined) return "";
                    return value + "%";
                  }};
                }}

                // x-axis ticks callback -> shows real category labels only for category axes
                if (cfg && cfg.options && cfg.options.scales && cfg.options.scales.x &&
                    cfg.options.scales.x.type === "category" &&
                    cfg.options.scales.x.ticks) {{
                cfg.options.scales.x.ticks.callback = function(value, index) {{
                    if (cfg.data && cfg.data.labels && cfg.data.labels[index] !== undefined) {{
                    return cfg.data.labels[index];
                    }}
                    return value;
                }};
                }}
                const ctx = document.getElementById("c").getContext("2d");
                if (chart) chart.destroy();
                chart = new Chart(ctx, cfg);

              }} catch (e) {{
                document.body.innerHTML =
                  "<pre style='color:red; padding:12px; white-space:pre-wrap;'>" + e + "</pre>";
              }}
            }}
          </script>
        </body>
        </html>
        """

        self.setHtml(html)
        self.loadFinished.connect(self._on_loaded)

    def _on_loaded(self, ok: bool):
        self._loaded = ok
        if ok and self._pending_config is not None:
            self.set_config(self._pending_config)
            self._pending_config = None

    def set_config(self, config: dict):
        if not self._loaded:
            self._pending_config = config
            return

        js = f"renderChart({json.dumps(config)});"
        self.page().runJavaScript(js)
    
    
    def contextMenuEvent(self, event):
        """Show only Reload in right-click menu."""
        menu = QMenu(self)

        reload_action = menu.addAction("Reload")
        chosen = menu.exec(event.globalPos())

        if chosen == reload_action:
            # safest reload (doesn't break anything)
            self.page().triggerAction(QWebEnginePage.WebAction.Reload)

        event.accept()


class AnalyticsScreen(QWidget):
    """Analytics screen showing workout completion summary and charts"""

    backRequested = pyqtSignal()
    logoutRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trainee_id = None
        self.reset_popup_shown = False
        self.rep_totals = {}
        self.init_ui()

    def set_user(self, user_data):
        """Set user and refresh analytics data"""
        self.trainee_id = user_data.get("trainee_id")

        trainee = get_trainee_info(self.trainee_id)
        if trainee:
            self.welcome_label.setText(f"Trainee: {trainee['name']}")

            plan_id = trainee.get("plan_id", 3)
            main_level, _ = plan_level_and_index(plan_id)
            self.plan_label.setText(f"Plan: {main_level}")

            plan_id = trainee.get("plan_id", 1)
            plan_data = get_workout_plan(plan_id)

            self.plan_targets = self.build_plan_target_map(plan_data)

            # Convert plan_data into format expected by calculate_plan_max_points
            plan_dict = {}
            for ex in plan_data:
                name = ex["name"]
                target = ex["target"]
                # Time-based
                if "Time" in name or "Plank" in name or "Cobra" in name:
                    plan_dict[name] = {"duration": target}
                else:
                    plan_dict[name] = {"reps": target}
            self.plan_max_points = self.calculate_plan_max_points(plan_dict)

        self.refresh_data()

    def init_ui(self):
        """Initialize the UI"""
        self.setStyleSheet("background: transparent;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top Navigation Bar
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

        self.analytics_btn = QPushButton("Dashboard")
        self.analytics_btn.setStyleSheet(btn_style % ("rgba(102, 126, 234, 0.8)", "none"))

        self.dash_btn = QPushButton("Workout")
        self.dash_btn.setStyleSheet(btn_style % ("transparent", "1px solid rgba(255, 255, 255, 0.4)"))
        self.dash_btn.clicked.connect(self.backRequested.emit)

        self.profile_btn = QPushButton("Profile")
        self.profile_btn.setStyleSheet(btn_style % ("transparent", "1px solid rgba(255, 255, 255, 0.4)"))
        self.profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_btn.clicked.connect(self.on_profile_clicked)

        nav_layout.addWidget(self.analytics_btn)
        nav_layout.addSpacing(10)
        nav_layout.addWidget(self.dash_btn)
        nav_layout.addSpacing(10)
        nav_layout.addWidget(self.profile_btn)
        main_layout.addWidget(nav_bar)

        # Page Content Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(50, 30, 50, 40)
        content_layout.setSpacing(25)

        # Header: User Info & Logout
        header_layout = QHBoxLayout()
        titles_layout = QVBoxLayout()

        self.welcome_label = QLabel("Trainee: Loading...")
        self.welcome_label.setFont(QFont("Segoe UI", 50, QFont.Weight.Bold))
        self.welcome_label.setStyleSheet("""
            QLabel {
                color: white;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(102,126,234,0.35),
                    stop:1 rgba(118,75,162,0.35));
                border-left: 10px solid #667eea;
                border-radius: 18px;
                padding: 18px 28px;
                margin-bottom: 12px;
                font-size: 24px;
                letter-spacing: 2px;
            }
        """)
        titles_layout.addWidget(self.welcome_label)

        self.plan_label = QLabel("Plan: Personalized")
        self.plan_label.setFont(QFont("Segoe UI", 32))
        self.plan_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background: rgba(102,126,234,0.22);
                border: 3px solid rgba(102,126,234,0.6);
                border-radius: 16px;
                padding: 14px 24px;
                font-size: 24px;
                letter-spacing: 1.5px;
            }
        """)
        titles_layout.addWidget(self.plan_label)

        header_layout.addLayout(titles_layout)
        header_layout.addStretch()

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setFixedSize(120, 45)
        self.logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: white;
                border-radius: 10px;
                font-weight: bold;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QPushButton:hover {
                background: rgba(255, 107, 107, 0.15);
                border-color: #ff6b6b;
                color: #ff6b6b;
            }
        """)
        self.logout_btn.clicked.connect(self.logoutRequested.emit)
        header_layout.addWidget(self.logout_btn, alignment=Qt.AlignmentFlag.AlignTop)

        content_layout.addLayout(header_layout)

        # Title
        title = QLabel("Workout Completion Summary")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setStyleSheet("color: white; background: transparent;")
        content_layout.addWidget(title)

        # Summary Cards Layout
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)

        self.total_score_card = self.create_summary_card("Total Score", "0/4800")
        cards_layout.addWidget(self.total_score_card)

        self.remaining_score_card = self.create_summary_card("Remaining Score", "4800")
        cards_layout.addWidget(self.remaining_score_card)

        cards_layout.addStretch()
        content_layout.addLayout(cards_layout)

        # WORKOUT CALENDAR / TRACKER
        tracker_section_box = QFrame()
        tracker_section_box.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border-radius: 20px;
                border: 1px solid rgba(255,255,255,0.08);
            }
        """)

        tracker_layout = QVBoxLayout(tracker_section_box)
        tracker_layout.setContentsMargins(25, 25, 25, 25)
        tracker_layout.setSpacing(15)

        title = QLabel("Workout Sessions Tracker")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        tracker_layout.addWidget(title)

        grid_frame = QFrame()
        grid_frame.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(grid_frame)
        grid_layout.setSpacing(10)

        self.session_marks = []

        for row in range(4):
            for col in range(15):
                session_number = row * 15 + col + 1
                label = QLabel(str(session_number))
                label.setFixedSize(50, 50)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))

                label.setStyleSheet("""
                    QLabel {
                        background-color: rgba(255,255,255,0.08);
                        border-radius: 12px;
                    }
                """)

                self.session_marks.append(label)
                grid_layout.addWidget(label, row, col)

        tracker_layout.addWidget(grid_frame)
        content_layout.addWidget(tracker_section_box)

        # Insight Label
        self.insight_label = QLabel("")
        self.insight_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.insight_label.setStyleSheet("color: #e2e8f0; padding: 10px;")
        content_layout.addWidget(self.insight_label)
        # ✅ No-data message (shown when trainee has 0 sessions)
        self.no_data_label = QLabel("Complete your first three workout sessions to see charts and analytics.")
        self.no_data_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.no_data_label.setStyleSheet("color: #fbbf24; padding: 10px;")
        self.no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.no_data_label)

        scroll.setWidget(content_wrapper)
        main_layout.addWidget(scroll)

        # ---------- LINE CHARTS SECTION ----------
        self.charts_section_box = QFrame()
        self.charts_section_box.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border-radius: 20px;
                border: 1px solid rgba(255,255,255,0.08);
            }
        """)

        charts_layout = QVBoxLayout(self.charts_section_box)
        charts_layout.setContentsMargins(25, 25, 25, 25)
        charts_layout.setSpacing(20)

        title = QLabel("Workout Progress Trends")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        charts_layout.addWidget(title)

        # ✅ Chart switch buttons row
        self.chart_btn_row = QHBoxLayout()
        self.chart_btn_row.setSpacing(10)

        self.chart_buttons = []
        chart_names = ["Jumping Jack", "Push-up", "Plank", "Crunches", "Squat", "Cobra Stretch"]

        for i, name in enumerate(chart_names):
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.06);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.2);
                    padding: 8px 14px;
                    border-radius: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: rgba(102,126,234,0.25);
                    border-color: rgba(102,126,234,0.8);
                }
            """)
            btn.clicked.connect(lambda checked, idx=i: self.switch_chart(idx))
            self.chart_buttons.append(btn)
            self.chart_btn_row.addWidget(btn)

        charts_layout.addLayout(self.chart_btn_row)

        # ✅ ONLY ONE CHART visible (stack)
        self.chart_stack = QStackedWidget()
        self.chart_stack.setMinimumHeight(550)
        charts_layout.addWidget(self.chart_stack)

        content_layout.addWidget(self.charts_section_box)

        # ================= ACCURACY BAR CHART SECTION =================
        self.accuracy_section_box = QFrame()
        self.accuracy_section_box.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border-radius: 20px;
                border: 1px solid rgba(255,255,255,0.08);
            }
        """)

        accuracy_layout_main = QVBoxLayout(self.accuracy_section_box)
        accuracy_layout_main.setContentsMargins(25, 25, 25, 25)
        accuracy_layout_main.setSpacing(20)

        title = QLabel("Exercise Accuracy Overview")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        accuracy_layout_main.addWidget(title)

        # ✅ this is required because refresh_data uses self.accuracy_layout
        self.accuracy_layout = QVBoxLayout()
        accuracy_layout_main.addLayout(self.accuracy_layout)

        content_layout.addWidget(self.accuracy_section_box)

        # Rep-Based Workout Table
        self.rep_section_box = QFrame()
        self.rep_section_box.setStyleSheet(
            "background: rgba(255, 255, 255, 0.04); border-radius: 20px; border: 1px solid rgba(255,255,255,0.08);"
        )
        rep_sec_layout = QVBoxLayout(self.rep_section_box)
        rep_sec_layout.setContentsMargins(25, 25, 25, 25)

        rep_section = QLabel("Rep-Based Workouts")
        rep_section.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        rep_section.setStyleSheet("color: white; border: none;")
        rep_sec_layout.addWidget(rep_section)
        rep_sec_layout.addSpacing(15)

        self.rep_table = self.create_workout_table(
            ["Workout", "Total Reps", "Correct Reps", "Wrong Reps"]
        )
        self.rep_table.setMinimumHeight(250)
        rep_sec_layout.addWidget(self.rep_table)
        

        # Time-Based Workout Table
        self.time_section_box = QFrame()
        self.time_section_box.setStyleSheet(
            "background: rgba(255, 255, 255, 0.04); border-radius: 20px; border: 1px solid rgba(255,255,255,0.08);"
        )
        time_sec_layout = QVBoxLayout(self.time_section_box)
        time_sec_layout.setContentsMargins(25, 25, 25, 25)

        time_section = QLabel("Time-Based Workouts")
        time_section.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        time_section.setStyleSheet("color: white; border: none;")
        time_sec_layout.addWidget(time_section)
        time_sec_layout.addSpacing(15)

        self.time_table = self.create_workout_table(
            ["Workout", "Total Time Held (sec)"]
        )
        self.time_table.setMinimumHeight(150)
        time_sec_layout.addWidget(self.time_table)
        
        # ✅ Rep + Time tables side-by-side (60:40)
        tables_row = QHBoxLayout()
        tables_row.setSpacing(20)

        tables_row.addWidget(self.rep_section_box)
        tables_row.addWidget(self.time_section_box)

        # ✅ 60:40 ratio
        tables_row.setStretch(0, 60)  # rep table
        tables_row.setStretch(1, 40)  # time table

        content_layout.addLayout(tables_row)
        

    def show_popup_message(self, title: str, message: str, icon=QMessageBox.Icon.Information):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def create_summary_card(self, label, value):
        card = QFrame()
        card.setMinimumWidth(220)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                           stop:0 rgba(102, 126, 234, 0.15),
                                           stop:1 rgba(118, 75, 162, 0.15));
                border: 2px solid rgba(102, 126, 234, 0.3);
                border-radius: 20px;
                padding: 20px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        val_widget = QLabel(value)
        val_widget.setObjectName("value")
        val_widget.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
        val_widget.setStyleSheet("color: white; border: none;")
        val_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(val_widget)

        lbl_widget = QLabel(label.upper())
        lbl_widget.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_widget.setStyleSheet("color: #fbbf24; letter-spacing: 1px; border: none;")
        lbl_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_widget)

        return card

    def create_workout_table(self, headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        table.setStyleSheet("""
            QTableWidget {
                background: transparent;
                border: none;
                gridline-color: rgba(255, 255, 255, 0.05);
                color: #e2e8f0;
                font-size: 14px;
                font-weight: bold;
                outline: none;
            }
            QTableWidget::item {
                padding: 15px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QHeaderView::section {
                background: rgba(102, 126, 234, 0.1);
                color: #fbbf24;
                padding: 12px;
                border: none;
                font-weight: bold;
                font-size: 13px;
                text-transform: uppercase;
                border-bottom: 2px solid rgba(102, 126, 234, 0.4);
            }
        """)

        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(headers)):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        return table

    def build_plan_target_map(self, plan_data):
        targets = {}
        for ex in plan_data:
            targets[ex["name"]] = ex["target"]
        return targets

    # =================== PROMOTION LOGIC ===================

    def calculate_plan_max_points(self, plan):
        total = 0
        for _, val in plan.items():
            if "reps" in val:
                total += val["reps"] * 2
            elif "duration" in val:
                total += val["duration"] * 2
        total *= 40
        return total

    def calculate_total_points(self):
        total_points = 0

        for name, stats in self.rep_totals.items():
            total = stats[0]
            correct = stats[1]
            wrong = stats[2]
            total_points += (correct * 2)
            total_points += (wrong * -1)

        for session in session_analytics.sessions:
            if session.duration > 0:
                total_points += session.duration * 2

        return total_points

    def calculate_success_rates(self):
        rates = {}

        for name, stats in self.rep_totals.items():
            total = stats[0]
            correct = stats[1]
            if total > 0:
                rates[name] = (correct / total) * 100
            else:
                rates[name] = 0

        time_totals = {}
        session_counts = {}

        for s in session_analytics.sessions:
            if s.duration > 0:
                time_totals.setdefault(s.exercise_name, 0)
                time_totals[s.exercise_name] += s.duration

                session_counts.setdefault(s.exercise_name, 0)
                session_counts[s.exercise_name] += 1

        for name, actual_time in time_totals.items():
            target = self.plan_targets.get(name, 0)
            count = session_counts.get(name, 0)

            if target > 0 and count > 0:
                expected_total = target * count
                rates[name] = (actual_time / expected_total) * 100
            else:
                rates[name] = 0

        return rates

    def check_promotion_status(self):
        total_points = self.calculate_total_points()
        rates = self.calculate_success_rates()

        points_ok = total_points >= getattr(self, "plan_max_points", 4800)
        exercises_ok = all(rate >= 60 for rate in rates.values())

        return points_ok and exercises_ok, total_points, rates

    def refresh_data(self):
        if not self.trainee_id:
            return
        
        session_analytics.load_sessions(self.trainee_id)
        self.apply_visibility_rules()

        

        # ===== 30 DAYS INACTIVITY RESET =====
        if is_inactive_30_days(self.trainee_id):
            from backend.models.data_manager import reset_sessions_after_inactivity

            reset_sessions_after_inactivity(self.trainee_id)

            session_analytics.sessions.clear()
            session_analytics.total_sessions = 0
            self.rep_totals = {}

            self.update_session_tracker(0)

            self.total_score_card.findChild(QLabel, "value").setText(f"0/{self.plan_max_points}")
            self.remaining_score_card.findChild(QLabel, "value").setText(str(self.plan_max_points))

            if not self.reset_popup_shown:
                self.show_popup_message(
                    "Restarted",
                    "⚠ Inactive for 30 days – progress restarted!",
                    icon=QMessageBox.Icon.Warning
                )
                self.reset_popup_shown = True

            return

        rep_totals = {}
        time_totals = {}
        total_correct_all = 0
        total_wrong_all = 0

        for s in session_analytics.sessions:
            if s.reps_completed > 0:
                if s.exercise_name not in rep_totals:
                    rep_totals[s.exercise_name] = [0, 0, 0]
                rep_totals[s.exercise_name][0] += s.reps_completed
                rep_totals[s.exercise_name][1] += s.correct_reps
                rep_totals[s.exercise_name][2] += s.wrong_reps

                total_correct_all += s.correct_reps
                total_wrong_all += s.wrong_reps

            elif s.duration > 0:
                if s.exercise_name not in time_totals:
                    time_totals[s.exercise_name] = 0
                time_totals[s.exercise_name] += s.duration

        self.rep_totals = rep_totals

        self.update_session_tracker(session_analytics.total_sessions)

        # ================= REP BASED TABLE =================
        rep_totals2 = {}
        for s in session_analytics.sessions:
            if s.reps_completed > 0:
                name = s.exercise_name
                if name not in rep_totals2:
                    rep_totals2[name] = {"total": 0, "correct": 0, "wrong": 0}
                rep_totals2[name]["total"] += s.reps_completed
                rep_totals2[name]["correct"] += s.correct_reps
                rep_totals2[name]["wrong"] += s.wrong_reps

        self.rep_table.setRowCount(0)
        self.rep_table.setRowCount(len(rep_totals2))

        for row, (name, data) in enumerate(rep_totals2.items()):
            item = self._create_item(name)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.rep_table.setItem(row, 0, item)
            self.rep_table.setItem(row, 1, self._create_item(str(data["total"])))
            self.rep_table.setItem(row, 2, self._create_item(str(data["correct"]), color="#48bb78"))
            self.rep_table.setItem(row, 3, self._create_item(str(data["wrong"]), color="#f56565"))

        # ================= TIME BASED TABLE =================
        self.time_table.setRowCount(len(time_totals))
        for row, (name, duration) in enumerate(time_totals.items()):
            self.time_table.setItem(row, 0, self._create_item(name, Qt.AlignmentFlag.AlignLeft))
            self.time_table.setItem(row, 1, self._create_item(f"{duration:.2f} sec"))

        promoted, total_points, rates = self.check_promotion_status()

        # ================= RESET LEVEL IF FAILED AFTER 60 SESSIONS =================
        if session_analytics.total_sessions >= 60:
            if not promoted:
                from backend.models.data_manager import reset_sessions_after_promotion

                reset_sessions_after_promotion(self.trainee_id)

                session_analytics.sessions.clear()
                session_analytics.total_sessions = 0
                self.rep_totals = {}

                self.update_session_tracker(0)

                self.total_score_card.findChild(QLabel, "value").setText(f"0/{self.plan_max_points}")
                self.remaining_score_card.findChild(QLabel, "value").setText(str(self.plan_max_points))

                self.show_popup_message(
                    "Level Restarted",
                    "⚠ You completed 60 sessions but did not meet promotion criteria.\nLevel restarted from Session 1!",
                    icon=QMessageBox.Icon.Warning
                )
                return

        # ================= AUTO PROMOTION LOGIC =================
        if promoted:
            trainee = get_trainee_info(self.trainee_id)
            current_plan = trainee.get("plan_id", 1)

            next_plan = self.get_next_plan(current_plan)

            if next_plan != current_plan:
                from backend.models.data_manager import (
                    promote_trainee_plan,
                    reset_sessions_after_promotion,
                    update_fitness_level,
                    plan_level_and_index
                )

                ok, msg = promote_trainee_plan(self.trainee_id, next_plan)

                if ok:
                    reset_sessions_after_promotion(self.trainee_id)
                    update_fitness_level(self.trainee_id, next_plan)

                    session_analytics.sessions.clear()
                    session_analytics.total_sessions = 0
                    self.rep_totals = {}

                    trainee = get_trainee_info(self.trainee_id)
                    plan_id = trainee.get("plan_id", next_plan)
                    main_level, _ = plan_level_and_index(plan_id)
                    self.plan_label.setText(f"Plan: {main_level}")

                    plan_data = get_workout_plan(next_plan)
                    self.plan_targets = self.build_plan_target_map(plan_data)

                    plan_dict = {}
                    for ex in plan_data:
                        name = ex["name"]
                        target = ex["target"]
                        if "Plank" in name or "Cobra" in name:
                            plan_dict[name] = {"duration": target}
                        else:
                            plan_dict[name] = {"reps": target}

                    self.plan_max_points = self.calculate_plan_max_points(plan_dict)

                    self.update_session_tracker(0)

                    total_points = 0
                    self.total_score_card.findChild(QLabel, "value").setText(f"0/{self.plan_max_points}")
                    self.remaining_score_card.findChild(QLabel, "value").setText(str(self.plan_max_points))

                    self.show_popup_message(
                        "Promotion",
                        f"🎉 Congratulations! Promoted to next level: {main_level} 🎉",
                        icon=QMessageBox.Icon.Information
                    )

        # ✅ CHARTS UPDATE (NOW Chart.js)
        if session_analytics.total_sessions >= 3:
            self.update_line_charts_from_sessions()

        # clear old accuracy chart
        while self.accuracy_layout.count():
            item = self.accuracy_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        chart = self.create_accuracy_bar_chart()
        if chart:
            self.accuracy_layout.addWidget(chart)

        # ----- Update Total Score & Remaining Score Cards -----
        if session_analytics.total_sessions == 0:
            total_points = 0

        display_total_points = max(round(total_points), 0)
        display_plan_max_points = round(self.plan_max_points)

        self.total_score_card.findChild(QLabel, "value").setText(
            f"{display_total_points}/{display_plan_max_points}"
        )

        trainee = get_trainee_info(self.trainee_id)
        plan_id = trainee.get("plan_id", 1) if trainee else 1

        if plan_id >= 11 and total_points >= self.plan_max_points:
            self.remaining_score_card.findChild(QLabel, "value").setText("MAX LEVEL")
        else:
            remaining = max(self.plan_max_points - total_points, 0)
            display_remaining = round(remaining)
            self.remaining_score_card.findChild(QLabel, "value").setText(str(display_remaining))

    # ============================================================
    # ✅ CHARTS (Matplotlib removed) -> Offline Chart.js
    # ============================================================

    def update_line_charts_from_sessions(self):
        # ✅ CLEAR OLD CHARTS FROM STACK (NOT grid)
        if hasattr(self, "chart_stack"):
            while self.chart_stack.count():
                w = self.chart_stack.widget(0)
                self.chart_stack.removeWidget(w)
                w.deleteLater()

        # ✅ REQUIRED ORDER (as you requested)
        order = ["Jumping Jack", "Push-up", "Plank", "Crunches", "Squat", "Cobra Stretch"]

        rep_exercises = ["Jumping Jack", "Push-up", "Crunches", "Squat"]
        time_exercises = ["Plank", "Cobra Stretch"]

        rep_data = {e: {"c": [], "w": []} for e in rep_exercises}
        time_data = {e: [] for e in time_exercises}

        sessions = list(reversed(session_analytics.sessions))

        # -------- COLLECT DATA (SAME LOGIC) --------
        for s in sessions:
            if s.exercise_name in rep_exercises:
                rep_data[s.exercise_name]["c"].append(s.correct_reps)
                rep_data[s.exercise_name]["w"].append(s.wrong_reps)
            elif s.exercise_name in time_exercises and s.duration > 0:
                time_data[s.exercise_name].append(s.duration)

        # ✅ Flexible height helper
        def calc_height(n_points: int, kind: str) -> int:
            base = 600 if kind == "time" else 560   # a bit higher to prevent clipping
            extra = max(0, n_points - 12) * 10
            return max(520, min(base + extra, 900))

        self._chart_heights = []  # store heights for switch_chart()

        # ✅ Build charts in requested order and add to STACK
        for ex in order:

            # -------------------------
            # REP CHARTS
            # -------------------------
            if ex in rep_exercises:
                y_correct = rep_data[ex]["c"]
                y_wrong = rep_data[ex]["w"]

                n = max(len(y_correct), len(y_wrong))
                x_labels = [str(i) for i in range(1, n + 1)]

                plan_name = self.normalize_exercise_name(ex)
                target = self.plan_targets.get(plan_name, max(y_correct + [0]) + 1)

                h = calc_height(n, "rep")
                view = ChartJsView(height=h)
                view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

                cfg = {
                    "type": "line",
                    "data": {
                        "labels": x_labels,
                        "datasets": [
                            {"label": "Correct Reps", "data": y_correct, "tension": 0.3, "pointRadius": 4},
                            {"label": "Wrong Reps",   "data": y_wrong,   "tension": 0.3, "pointRadius": 4}
                        ]
                    },
                    "options": {
                        "responsive": True,
                        "maintainAspectRatio": False,

                        # ✅ IMPORTANT: add padding so “Session” never gets cut
                        "layout": {"padding": {"left": 10, "right": 10, "top": 10, "bottom": 10}},

                        "plugins": {
                            "title": {"display": True, "text": f"{ex} (Target: {target})"},
                            "legend": {"display": True},
                            "datalabels": {"display": False}
                        },
                        "scales": {
                            "y": {"beginAtZero": True, "suggestedMax": target},
                            "x": {
                                "type": "category",
                                "title": {"display": True, "text": "Session", "padding": 12},
                                "ticks": {"padding": 8}
                            }
                        }
                    }
                }

                view.set_config(cfg)
                if hasattr(self, "chart_stack"):
                    self.chart_stack.addWidget(view)
                self._chart_heights.append(h)

            # -------------------------
            # TIME CHARTS
            # -------------------------
            elif ex in time_exercises:
                y = time_data[ex]
                n = len(y)
                x_labels = [str(i) for i in range(1, n + 1)]

                plan_name = self.normalize_exercise_name(ex)
                target = self.plan_targets.get(plan_name, max(y + [0]) + 1)

                h = calc_height(n, "time")
                view = ChartJsView(height=h)
                view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

                cfg = {
                    "type": "line",
                    "data": {
                        "labels": x_labels,
                        "datasets": [
                            {"label": "Time (sec)", "data": y, "tension": 0.3, "pointRadius": 4}
                        ]
                    },
                    "options": {
                        "responsive": True,
                        "maintainAspectRatio": False,

                        # ✅ IMPORTANT: bottom padding (fixes Plank/Cobra Stretch Session title)
                        "layout": {"padding": {"left": 10, "right": 10, "top": 10, "bottom": 30}},

                        "plugins": {
                            "title": {"display": True, "text": f"{ex} (Target: {target} sec)"},
                            "legend": {"display": True},
                            "datalabels": {"display": False}
                        },
                        "scales": {
                            "y": {"beginAtZero": True, "suggestedMax": target},
                            "x": {
                                "type": "category",
                                "title": {"display": True, "text": "Session", "padding": 12},
                                "ticks": {"padding": 8}
                            }
                        }
                    }
                }

                view.set_config(cfg)
                if hasattr(self, "chart_stack"):
                    self.chart_stack.addWidget(view)
                self._chart_heights.append(h)

        # ✅ default show first chart + highlight first button
        if hasattr(self, "chart_stack") and self.chart_stack.count() > 0:
            self.switch_chart(0)

    def create_accuracy_bar_chart(self):
        """
        SAME LOGIC:
        - Uses calculate_success_rates()
        - Red < 60%
        - Green >= 60%
        - Same fixed order
        ✅ Fix mixed-gap issue by STACKING (no empty reserved bar slot)
        ✅ Show % labels
        ✅ Legend Good / Needs Improve
        """
        rates = self.calculate_success_rates()

        order = ["Jumping Jack", "Push-up", "Plank", "Crunches", "Squat", "Cobra Stretch"]

        exercises = []
        good_vals = []
        improve_vals = []

        for ex in order:
            acc = rates.get(ex, 0)
            acc = min(100, round(acc, 1))
            exercises.append(ex)

            # ✅ SAME logic, just split into 2 datasets
            if acc >= 60:
                good_vals.append(acc)
                improve_vals.append(None)
            else:
                good_vals.append(None)
                improve_vals.append(acc)

        view = ChartJsView(height=380)
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        cfg = {
            "type": "bar",
            "data": {
                "labels": exercises,
                "datasets": [
                    {
                        "label": "Good (≥ 60%)",
                        "data": good_vals,
                        "backgroundColor": "rgba(72, 187, 120, 0.85)",
                        "borderRadius": 12,
                        "borderSkipped": False,
                        "barThickness": 22,
                        "maxBarThickness": 26,
                        "stack": "acc"  # ✅ IMPORTANT: stack to remove mixed-gap issue
                    },
                    {
                        "label": "Needs Improve (< 60%)",
                        "data": improve_vals,
                        "backgroundColor": "rgba(245, 101, 101, 0.85)",
                        "borderRadius": 12,
                        "borderSkipped": False,
                        "barThickness": 22,
                        "maxBarThickness": 26,
                        "stack": "acc"  # ✅ IMPORTANT: stack to remove mixed-gap issue
                    }
                ]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "indexAxis": "y",
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Exercise Accuracy Overview",
                        "padding": {"top": 8, "bottom": 12},
                        "font": {"size": 16, "weight": "bold"}
                    },
                    "legend": {
                        "display": True,
                        "position": "top"
                    },

                    # ✅ Needs ChartDataLabels plugin loaded (you already embedded it)
                    "datalabels": {
                        "anchor": "end",
                        "align": "right",
                        "offset": 6,
                        "clamp": True,
                        "formatter": "function(value){ return (value === null || value === undefined) ? '' : value + '%'; }",
                        "font": {"weight": "bold", "size": 12}
                    }
                },
                "scales": {
                    "x": {
                        "beginAtZero": True,
                        "max": 100,

                        # ✅ IMPORTANT: stacked = true so two datasets share ONE bar lane
                        "stacked": True,

                        "ticks": {
                            "stepSize": 20,
                            "callback": "function(value){ return value + '%'; }"
                        },
                        "grid": {"drawBorder": False}
                    },
                    "y": {
                        # ✅ IMPORTANT: stacked = true so no empty reserved slots per category
                        "stacked": True,

                        "grid": {"display": False},
                        "ticks": {"autoSkip": False}
                    }
                },
                "layout": {
                    "padding": {"left": 10, "right": 40, "top": 0, "bottom": 0}
                }
            }
        }

        view.set_config(cfg)
        return view
    
    
    def switch_chart(self, index: int):
        if not hasattr(self, "chart_stack"):
            return
        if self.chart_stack.count() == 0:
            return

        self.chart_stack.setCurrentIndex(index)

        # ✅ flexible height per chart
        if hasattr(self, "_chart_heights") and index < len(self._chart_heights):
            self.chart_stack.setMinimumHeight(self._chart_heights[index])

        # ✅ highlight selected button
        for i, btn in enumerate(self.chart_buttons):
            if i == index:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(102,126,234,0.6);
                        color: white;
                        border: none;
                        padding: 8px 14px;
                        border-radius: 10px;
                        font-weight: bold;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255,255,255,0.06);
                        color: white;
                        border: 1px solid rgba(255,255,255,0.2);
                        padding: 8px 14px;
                        border-radius: 10px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: rgba(102,126,234,0.25);
                        border-color: rgba(102,126,234,0.8);
                    }
                """)
                
    
    
    def set_post_session_widgets_visible(self, visible: bool):
        # Sections to hide/show
        if hasattr(self, "charts_section_box"):
            self.charts_section_box.setVisible(visible)

        if hasattr(self, "accuracy_section_box"):
            self.accuracy_section_box.setVisible(visible)

        if hasattr(self, "rep_section_box"):
            self.rep_section_box.setVisible(visible)

        if hasattr(self, "time_section_box"):
            self.time_section_box.setVisible(visible)

        # No-data label is opposite
        if hasattr(self, "no_data_label"):
            self.no_data_label.setVisible(not visible)

        # Optional: when hiding, clear old visuals so nothing “stale” remains
        if not visible:
            if hasattr(self, "chart_stack"):
                while self.chart_stack.count():
                    w = self.chart_stack.widget(0)
                    self.chart_stack.removeWidget(w)
                    w.deleteLater()

            if hasattr(self, "accuracy_layout"):
                while self.accuracy_layout.count():
                    item = self.accuracy_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

            if hasattr(self, "rep_table"):
                self.rep_table.setRowCount(0)

            if hasattr(self, "time_table"):
                self.time_table.setRowCount(0)
                
    
    def apply_visibility_rules(self):
        """
        UI-only rule (no logic change):
        - 0 sessions: hide charts, accuracy, tables
        - 1-2 sessions: show accuracy + tables, hide line charts
        - 3+ sessions: show everything
        """
        n = session_analytics.total_sessions

        # 0 sessions -> hide all post-session widgets
        if n <= 0:
            self.set_post_session_widgets_visible(False)
            return

        # At least 1 session -> show accuracy + tables
        self.set_post_session_widgets_visible(True)

        # Line charts need at least 3 sessions
        if hasattr(self, "charts_section_box"):
            self.charts_section_box.setVisible(n >= 3)
    

    # ============================================================

    def update_session_tracker(self, completed_sessions):
        completed_sessions = min(completed_sessions, 60)

        for i, label in enumerate(self.session_marks):
            if i < completed_sessions:
                label.setStyleSheet("""
                    QLabel {
                        background-color: #667eea;
                        border-radius: 25px;
                        color: white;
                        font-weight: bold;
                    }
                """)
            else:
                label.setStyleSheet("""
                    QLabel {
                        background-color: rgba(255,255,255,0.08);
                        border-radius: 12px;
                    }
                """)

    def get_next_plan(self, current_plan):
        from backend.models.data_manager import get_next_plan_same_index
        return get_next_plan_same_index(current_plan)

    def normalize_exercise_name(self, name):
        name_map = {
            "Jumping Jack": "Jumping Jacks",
            "Push-up": "Push Ups",
            "Squat": "Squats",
            "Crunches": "Crunches",
            "Plank": "Plank",
            "Cobra Stretch": "Cobra Stretch"
        }
        return name_map.get(name, name)

    def _create_item(self, text, alignment=Qt.AlignmentFlag.AlignCenter, color=None):
        item = QTableWidgetItem(text)
        item.setTextAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
        if color:
            item.setForeground(QColor(color))
        return item

    def on_profile_clicked(self):
        """Notify main window to show profile"""
        main_win = self.window()
        if hasattr(main_win, "show_profile"):
            main_win.show_profile()