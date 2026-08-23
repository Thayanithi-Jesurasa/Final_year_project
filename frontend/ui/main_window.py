"""
Main Window for SmartARTrainer
Central navigation controller using QStackedWidget.
"""

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QMessageBox, QStackedWidget
from PyQt6.QtCore import Qt

from frontend.utils.styles import get_main_stylesheet
from frontend.ui.login_screen import LoginScreen
from frontend.ui.fitness_form import FitnessForm
from frontend.ui.Workout import Workout
from frontend.ui.workout_session import WorkoutSession
from frontend.ui.workout_demo import WorkoutDemo
from frontend.ui.profile_screen import ProfileScreen
from frontend.ui.analytics_screen import AnalyticsScreen

from backend.models.data_manager import get_trainee_info, register_user
from backend.utils.email_service import generate_otp, send_otp, OTPInputDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_user = None
        self.signup_data = {}
        self.fitness_data_cache = {}

        # Used for returning when leaving WorkoutDemo
        self._demo_return_widget = None

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("SmartARTrainer")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(get_main_stylesheet())

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # ================= Screens =================
        self.login_screen = LoginScreen(self)
        self.stack.addWidget(self.login_screen)

        self.fitness_form = FitnessForm(self)
        self.stack.addWidget(self.fitness_form)

        self.Workout = Workout(self)
        self.stack.addWidget(self.Workout)

        self.workout_demo = WorkoutDemo(self)
        self.stack.addWidget(self.workout_demo)

        self.workout_session = WorkoutSession(self)
        self.stack.addWidget(self.workout_session)

        self.profile_screen = ProfileScreen(self)
        self.stack.addWidget(self.profile_screen)

        self.analytics_screen = AnalyticsScreen(self)
        self.stack.addWidget(self.analytics_screen)

        # ================= Signals =================
        self.login_screen.loginSuccess.connect(self.on_login_success)
        self.login_screen.registerContinue.connect(self.on_register_continue)

        self.fitness_form.backRequested.connect(self.on_fitness_back)
        self.fitness_form.formCompleted.connect(self.on_fitness_completed)

        self.Workout.logoutSignal.connect(self.on_logout)
        self.analytics_screen.logoutRequested.connect(self.on_logout)

        # Workout session:
        self.workout_session.sessionEnded.connect(self.show_Workout)
        self.workout_session.nextWorkoutRequested.connect(self.on_next_workout_requested)

        self.profile_screen.backRequested.connect(self.show_Workout)
        self.analytics_screen.backRequested.connect(self.show_Workout)

        # Default start screen
        self.stack.setCurrentWidget(self.login_screen)

    # =====================================================
    # Auth + user setup
    # =====================================================
    def on_login_success(self, user_data: dict):
        """After login, show Analytics first."""
        self.current_user = user_data

        # Update screens that depend on user
        self.Workout.set_user(user_data)
        self.analytics_screen.set_user(user_data)
        self.profile_screen.set_user(user_data)

        self.show_analytics()

    def on_logout(self):
        self.current_user = None
        self.signup_data = {}
        self.fitness_data_cache = {}

        self.login_screen.clear_inputs()
        self.login_screen.show_login_tab()
        self.stack.setCurrentWidget(self.login_screen)

        # Reset camera permission correctly
        if hasattr(self, "workout_demo"):
            self.workout_demo.camera_permission_granted = False

        if hasattr(self, "workout_session"):
            self.workout_session.camera_permission_granted = False
            self.workout_session.camera_active = False

    # =====================================================
    # Top-level navigation helpers
    # =====================================================
    def show_Workout(self):
        if self.current_user:
            # refresh latest user data from DB if available
            fresh_user = get_trainee_info(self.current_user.get("trainee_id"))
            if fresh_user:
                self.current_user = fresh_user

            self.Workout.set_user(self.current_user)

        self.stack.setCurrentWidget(self.Workout)

    def show_profile(self):
        if self.current_user:
            fresh_user = get_trainee_info(self.current_user.get("trainee_id"))
            if fresh_user:
                self.current_user = fresh_user

            self.profile_screen.set_user(self.current_user)
            self.stack.setCurrentWidget(self.profile_screen)

    def show_analytics(self):
        if self.current_user:
            fresh_user = get_trainee_info(self.current_user.get("trainee_id"))
            if fresh_user:
                self.current_user = fresh_user

            self.analytics_screen.set_user(self.current_user)
            self.stack.setCurrentWidget(self.analytics_screen)

    # =====================================================
    # Workout Demo navigation (return to previous screen)
    # =====================================================
    def show_workout_demo(self, workout_id: int):
        """Open workout demo. Return goes back to the previous screen."""
        self._demo_return_widget = self.stack.currentWidget()
        self.workout_demo.load_workout(workout_id)
        self.stack.setCurrentWidget(self.workout_demo)

    def back_from_workout_demo(self):
        """WorkoutDemo -> previous screen (usually WorkoutSession)."""
        if self._demo_return_widget is None:
            self._demo_return_widget = self.Workout
        self.stack.setCurrentWidget(self._demo_return_widget)

    # =====================================================
    # Workout Session navigation
    # =====================================================
    def show_workout_session(self, workout_id: int, workout_name: str | None = None, user_gender: str = "Male"):
        """Open WorkoutSession for a given workout."""
        if not workout_name:
            workout_name = getattr(self.workout_demo, "title_label", None)
            workout_name = workout_name.text() if workout_name else "Workout"

        # Find this workout in the plan list -> get target + index
        target_val = None
        index_in_plan = 0
        workouts = getattr(self.Workout, "workouts", [])

        try:
            for i, w in enumerate(workouts):
                if int(w.get("workout_id", -1)) == int(workout_id):
                    target_val = w.get("target")
                    index_in_plan = i
                    break
        except Exception:
            target_val = None
            index_in_plan = 0

        # pass current workout details
        self.workout_session.set_workout(
            {"workout_id": workout_id, "name": workout_name, "target": target_val},
            index_in_plan
        )
        # ✅ NEW: send user gender to workout session
        if hasattr(self.workout_session, "set_user_gender"):
            self.workout_session.set_user_gender(user_gender)

        self.stack.setCurrentWidget(self.workout_session)

    def on_next_workout_requested(self, current_index: int):
        """
        This signal carries the current exercise index (0..5),
        so we go to next_index directly.
        """
        workouts = getattr(self.Workout, "workouts", [])
        if not workouts:
            self.show_Workout()
            return

        # mark current exercise as completed
        if hasattr(self.Workout, "mark_exercise_completed"):
            self.Workout.mark_exercise_completed(current_index)

        next_index = current_index + 1

        # if finished all workouts
        if next_index >= len(workouts):
            self.show_analytics()
            return

        next_workout = workouts[next_index]
        next_id = next_workout.get("workout_id")
        next_name = next_workout.get("name", "Workout")

        # ✅ NEW: keep same gender for next workout too
        user_gender = "Male"
        try:
            trainee = getattr(self.Workout, "trainee", None)
            if trainee:
                user_gender = trainee.get("gender", "Male")
        except Exception:
            pass

        if next_id is not None:
            self.show_workout_session(next_id, next_name, user_gender)
        else:
            self.show_Workout()

    # =====================================================
    # Signup -> Fitness form -> Analytics
    # =====================================================
    def on_register_continue(self, signup_data: dict):
        self.signup_data = signup_data
        self.fitness_form.set_data(self.fitness_data_cache)
        self.stack.setCurrentWidget(self.fitness_form)

    def on_fitness_back(self):
        self.fitness_data_cache = self.fitness_form.get_data()
        self.stack.setCurrentWidget(self.login_screen)

    def on_fitness_completed(self, fitness_data: dict):
        email = self.signup_data.get("email")
        otp, created_at = generate_otp()

        send_otp(email, otp, parent=self, purpose="Email Verification")

        def _resend():
            nonlocal otp, created_at
            otp, created_at = generate_otp()
            send_otp(email, otp, parent=self, purpose="Email Verification")

        otp_input, ok = OTPInputDialog.get_otp(
            email,
            title="Verify Email",
            description=f"Enter the 6-digit code sent to {email}. (Valid for 5 minutes)",
            parent=self,
            resend_callback=_resend
        )

        if not ok:
            return

        from backend.utils.email_service import verify_otp
        verified, v_msg = verify_otp(otp_input, otp, created_at, expiry_mins=5)

        if not verified:
            QMessageBox.critical(self, "Verification Failed", v_msg)
            return

        success, message, trainee_id = register_user(
            self.signup_data.get("name"),
            email,
            self.signup_data.get("password"),
            fitness_data
        )

        if not success:
            QMessageBox.critical(self, "Registration Failed", message)
            return

        QMessageBox.information(
            self,
            "Registration Successful",
            "Account created successfully. Please login."
        )

        self.signup_data = {}
        self.fitness_data_cache = {}
        self.current_user = None

        self.login_screen.clear_inputs()
        self.login_screen.show_login_tab()
        self.stack.setCurrentWidget(self.login_screen)