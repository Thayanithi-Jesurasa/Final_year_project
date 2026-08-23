import json
import sqlite3
import socket
import threading
import os

# -------------------------
# AUTO DETECT DATABASE PATH
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "database", "smartar.db")
DB_PATH = os.path.normpath(DB_PATH)

HOST = "127.0.0.1"
PORT = 5055

# -------------------------
# TEMP SESSION STORE (in-memory)
# -------------------------
current_session = {
    "trainee_id": None,
    "jumpingjack_crt": 0, "jumpingjack_wrg": 0,
    "pushup_crt": 0, "pushup_wrg": 0,
    "plank_time": 0.0,
    "crunches_crt": 0, "crunches_wrg": 0,
    "squat_crt": 0, "squat_wrg": 0,
    "cobrastretch_time": 0.0,
    "completed": False
}

# -------------------------
# CALL THIS when user clicks "Start Workout Session"
# -------------------------
def start_new_session(trainee_id: int):
    current_session["trainee_id"] = trainee_id
    current_session["jumpingjack_crt"] = 0
    current_session["jumpingjack_wrg"] = 0
    current_session["pushup_crt"] = 0
    current_session["pushup_wrg"] = 0
    current_session["plank_time"] = 0.0
    current_session["crunches_crt"] = 0
    current_session["crunches_wrg"] = 0
    current_session["squat_crt"] = 0
    current_session["squat_wrg"] = 0
    current_session["cobrastretch_time"] = 0.0
    current_session["completed"] = False
    print(" New session started for trainee:", trainee_id)

# -------------------------
# SAVE TO DB ONLY AT END (after Cobra Stretch)
# -------------------------
def save_session_to_db():
    if current_session["trainee_id"] is None:
        print(" trainee_id not set. Cannot save.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO workout_session
        (trainee_id,
         pushup_crt, pushup_wrg,
         jumpingjack_crt, jumpingjack_wrg,
         plank_time,
         crunches_crt, crunches_wrg,
         squat_crt, squat_wrg,
         cobrastretch_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        current_session["trainee_id"],
        current_session["pushup_crt"], current_session["pushup_wrg"],
        current_session["jumpingjack_crt"], current_session["jumpingjack_wrg"],
        current_session["plank_time"],
        current_session["crunches_crt"], current_session["crunches_wrg"],
        current_session["squat_crt"], current_session["squat_wrg"],
        current_session["cobrastretch_time"],
    ))

    conn.commit()
    conn.close()
    current_session["completed"] = True
    print(" Session saved into DB!")

# -------------------------
# UPDATE TEMP STORE from Unity payload
# -------------------------
def apply_unity_result(payload: dict):
    ex = payload.get("exercise")

    if ex == "jumpingjack":
        current_session["jumpingjack_crt"] = int(payload.get("correct", 0))
        current_session["jumpingjack_wrg"] = int(payload.get("wrong", 0))

    elif ex == "pushup":
        current_session["pushup_crt"] = int(payload.get("correct", 0))
        current_session["pushup_wrg"] = int(payload.get("wrong", 0))

    elif ex == "plank":
        current_session["plank_time"] = float(payload.get("correctTime", 0.0))

    elif ex == "crunches":
        current_session["crunches_crt"] = int(payload.get("correct", 0))
        current_session["crunches_wrg"] = int(payload.get("wrong", 0))

    elif ex == "squat":
        current_session["squat_crt"] = int(payload.get("correct", 0))
        current_session["squat_wrg"] = int(payload.get("wrong", 0))

    elif ex == "cobrastretch":
        current_session["cobrastretch_time"] = float(payload.get("correctTime", 0.0))
        #  LAST EXERCISE → now save the whole session
        save_session_to_db()

    print(" Updated temp session:", current_session)

# -------------------------
# TCP SERVER
# -------------------------
def handle_client(conn, addr):
    try:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk

        text = data.decode("utf-8", errors="ignore").strip()

        # Allow multiple JSON lines
        for line in text.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            print(" Received from Unity:", payload)
            apply_unity_result(payload)

    except Exception as e:
        print(" Client error:", e)
    finally:
        conn.close()

def start_tcp_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(5)
    print(f"Unity TCP server running on {HOST}:{PORT}")

    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

# Run server directly for testing
if __name__ == "__main__":
    # TEST: simulate logged-in trainee
    start_new_session(trainee_id=1)
    start_tcp_server()