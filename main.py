import firebase_admin
from firebase_admin import credentials, auth, firestore, db
import paho.mqtt.client as mqtt
import signal
import sys
import time
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Firebase configuration from environment variables
firebase_config = {
    "apiKey": os.getenv("FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.getenv("FIREBASE_DATABASE_URL"),
    "projectId": os.getenv("FIREBASE_PROJECT_ID"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
    "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
    "appId": os.getenv("FIREBASE_APP_ID")
}

# MQTT configuration from environment variables
MQTT_SERVER = os.getenv("MQTT_SERVER", "broker.emqx.io")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPICS = {
    "card": os.getenv("MQTT_TOPIC_CARD", "smartguard/verify/card"),
    "fingerprint": os.getenv("MQTT_TOPIC_FINGERPRINT", "smartguard/verify/fingerprint"),
    "lock_open": os.getenv("MQTT_TOPIC_LOCK_OPEN", "smartguard/lock/open")
}

# Global flag for graceful shutdown
running = True
firebase_connected = False

def signal_handler(sig, frame):
    """Handle Ctrl+C signal for graceful shutdown"""
    global running
    print("\n\nShutting down gracefully...")
    running = False

def validate_card_message(data):
    """Validate card verification message format"""
    required_fields = ["card_reader", "card_id"]

    if not all(field in data for field in required_fields):
        return False, f"Missing required fields. Expected: {required_fields}"

    if not isinstance(data["card_reader"], int):
        return False, "card_reader must be an integer"

    if not isinstance(data["card_id"], str):
        return False, "card_id must be a string"

    return True, "Valid card message"

def validate_fingerprint_message(data):
    """Validate fingerprint verification message format"""
    required_fields = ["fingerprint_reader", "fingerprint_id"]

    if not all(field in data for field in required_fields):
        return False, f"Missing required fields. Expected: {required_fields}"

    if not isinstance(data["fingerprint_reader"], int):
        return False, "fingerprint_reader must be an integer"

    if not isinstance(data["fingerprint_id"], int):
        return False, "fingerprint_id must be an integer"

    return True, "Valid fingerprint message"

def check_student_by_rfid(rfid):
    """Check if student exists in Firebase by RFID"""
    try:
        ref = db.reference(f'users/students/{rfid}')
        student_data = ref.get()

        if student_data:
            return True, student_data
        else:
            return False, None
    except Exception as e:
        print(f"Error checking Firebase: {e}")
        return False, None

def check_student_by_fingerprint(fingerprint_id):
    """Check if fingerprint exists in Firebase for any student"""
    try:
        ref = db.reference('users/students')
        all_students = ref.get()

        if all_students:
            # Search through all students for matching fingerprint
            for rfid, student_data in all_students.items():
                if 'fprints' in student_data:
                    fprints = student_data['fprints']
                    # Check if fingerprint_id exists in fprints and is True
                    if str(fingerprint_id) in fprints and fprints[str(fingerprint_id)] == True:
                        return True, student_data, rfid

        return False, None, None
    except Exception as e:
        print(f"Error checking Firebase: {e}")
        return False, None, None

def get_active_session():
    """Get the active session firebase key"""
    try:
        ref = db.reference('sessions/active')
        active_session = ref.get()

        if active_session and 'firebaseKey' in active_session:
            firebase_key = active_session['firebaseKey']
            print(f"  - Active Session Key: {firebase_key}")
            return firebase_key
        else:
            print(f"  - No active session found")
            return None
    except Exception as e:
        print(f"Error getting active session: {e}")
        return None

def save_attendance(firebase_key, rfid, student_data, method):
    """Save attendance data to Firebase"""
    try:
        # Check if session exists
        session_ref = db.reference(f'sessions/{firebase_key}')
        session_data = session_ref.get()

        if not session_data:
            print(f"  ✗ Session {firebase_key} does not exist")
            return False

        # Get session start time
        if 'started' not in session_data:
            print(f"  ✗ Session start time not found")
            return False

        # Parse session start time (ISO format: "2025-11-19T17:21:42.954Z")
        from datetime import datetime
        session_start_str = session_data['started']
        session_start_dt = datetime.fromisoformat(session_start_str.replace('Z', '+00:00'))
        session_start_ms = int(session_start_dt.timestamp() * 1000)

        # Get current time in milliseconds
        current_time_ms = int(time.time() * 1000)

        # Calculate time elapsed since session started (in milliseconds)
        time_in = str(current_time_ms - session_start_ms)

        # Prepare attendance data
        attendance_data = {
            "method": method,
            "name": student_data.get('name', 'Unknown'),
            "studentId": student_data.get('student_id', 'Unknown'),
            "timeIn": time_in
        }

        # Save to Firebase
        attendance_ref = db.reference(f'sessions/{firebase_key}/attendance/{rfid}')
        attendance_ref.set(attendance_data)

        # Convert milliseconds to minutes and seconds for display
        time_in_seconds = int(time_in) / 1000
        minutes = int(time_in_seconds // 60)
        seconds = int(time_in_seconds % 60)

        print(f"\n✓ Attendance Saved to Firebase!")
        print(f"  - Session: {firebase_key}")
        print(f"  - Student: {attendance_data['name']}")
        print(f"  - Student ID: {attendance_data['studentId']}")
        print(f"  - Method: {method}")
        print(f"  - Time In: {time_in} ms ({minutes}m {seconds}s after session start)")

        return True
    except Exception as e:
        print(f"✗ Error saving attendance: {e}")
        return False

def on_connect(client, userdata, flags, rc):
    """MQTT connection callback"""
    if rc == 0:
        print(f"✓ Connected to MQTT broker at {MQTT_SERVER}:{MQTT_PORT}")

        # Subscribe to topics
        for topic_name, topic_path in MQTT_TOPICS.items():
            client.subscribe(topic_path)
            print(f"✓ Subscribed to topic: {topic_path}")
    else:
        print(f"✗ Failed to connect to MQTT broker. Return code: {rc}")

def on_disconnect(client, userdata, rc):
    """MQTT disconnection callback"""
    if rc != 0:
        print(f"✗ Unexpected MQTT disconnection. Return code: {rc}")

def on_message(client, userdata, msg):
    """MQTT message callback"""
    topic = msg.topic
    payload = msg.payload.decode()

    print(f"\n{'='*60}")
    print(f"Received message on topic: {topic}")
    print(f"Raw payload: {payload}")

    try:
        # Parse JSON
        data = json.loads(payload)

        if topic in list(MQTT_TOPICS.values()):
            print(f"Parsed JSON: {json.dumps(data, indent=2)}")

        # Validate based on topic
        if topic == MQTT_TOPICS["card"]:
            is_valid, message = validate_card_message(data)
            if is_valid:
                print(f"✓ VALID: {message}")
                print(f"  - Card Reader: {data['card_reader']}")
                print(f"  - Card ID: {data['card_id']}")

                # Check Firebase for student info
                if firebase_connected:
                    print(f"\nChecking Firebase for RFID: {data['card_id']}...")
                    found, student_data = check_student_by_rfid(data['card_id'])

                    if found:
                        print(f"✓ Student Found in Firebase!")
                        print(f"  - Name: {student_data.get('name', 'N/A')}")
                        print(f"  - Student ID: {student_data.get('student_id', 'N/A')}")
                        print(f"  - Course: {student_data.get('course', 'N/A')}")
                        print(f"  - Year Level: {student_data.get('year_level', 'N/A')}")
                        print(f"  - Email: {student_data.get('email', 'N/A')}")
                        print(f"  - Registered: {student_data.get('registered', False)}")

                        # Check if user is registered
                        if student_data.get('registered', False):
                            print(f"\n✓ User is REGISTERED - Sending unlock command...")
                            result = client.publish(MQTT_TOPICS["lock_open"], "OK")
                            if result.rc == 0:
                                print(f"✓ Published 'OK' to {MQTT_TOPICS['lock_open']}")

                                # Get active session and save attendance
                                print(f"\nGetting active session...")
                                firebase_key = get_active_session()

                                if firebase_key:
                                    # Save attendance to Firebase
                                    save_attendance(firebase_key, data['card_id'], student_data, "RFID")
                                else:
                                    print(f"⚠ No active session - Attendance not saved")
                            else:
                                print(f"✗ Failed to publish unlock command")
                        else:
                            print(f"\n✗ User is NOT registered - Access DENIED")
                    else:
                        print(f"✗ Student NOT Found in Firebase")
                        print(f"  RFID {data['card_id']} is not registered in the system")
                else:
                    print(f"⚠ Firebase not connected, skipping database check")
            else:
                print(f"✗ INVALID: {message}")

        elif topic == MQTT_TOPICS["fingerprint"]:
            is_valid, message = validate_fingerprint_message(data)
            if is_valid:
                print(f"✓ VALID: {message}")
                print(f"  - Fingerprint Reader: {data['fingerprint_reader']}")
                print(f"  - Fingerprint ID: {data['fingerprint_id']}")

                # Check Firebase for fingerprint
                if firebase_connected:
                    print(f"\nChecking Firebase for Fingerprint ID: {data['fingerprint_id']}...")
                    found, student_data, rfid = check_student_by_fingerprint(data['fingerprint_id'])

                    if found:
                        print(f"✓ Student Found in Firebase!")
                        print(f"  - RFID: {rfid}")
                        print(f"  - Name: {student_data.get('name', 'N/A')}")
                        print(f"  - Student ID: {student_data.get('student_id', 'N/A')}")
                        print(f"  - Course: {student_data.get('course', 'N/A')}")
                        print(f"  - Year Level: {student_data.get('year_level', 'N/A')}")
                        print(f"  - Email: {student_data.get('email', 'N/A')}")
                        print(f"  - Registered: {student_data.get('registered', False)}")

                        # Display fingerprints
                        if 'fprints' in student_data:
                            fprints = student_data['fprints']
                            print(f"  - Registered Fingerprints: {', '.join([str(k) for k, v in fprints.items() if v])}")

                        # Check if user is registered
                        if student_data.get('registered', False):
                            print(f"\n✓ User is REGISTERED - Sending unlock command...")
                            result = client.publish(MQTT_TOPICS["lock_open"], "OK")
                            if result.rc == 0:
                                print(f"✓ Published 'OK' to {MQTT_TOPICS['lock_open']}")

                                # Get active session and save attendance
                                print(f"\nGetting active session...")
                                firebase_key = get_active_session()

                                if firebase_key:
                                    # Save attendance to Firebase
                                    save_attendance(firebase_key, rfid, student_data, "Fingerprint")
                                else:
                                    print(f"⚠ No active session - Attendance not saved")
                            else:
                                print(f"✗ Failed to publish unlock command")
                        else:
                            print(f"\n✗ User is NOT registered - Access DENIED")
                    else:
                        print(f"✗ Fingerprint NOT Found in Firebase")
                        print(f"  Fingerprint ID {data['fingerprint_id']} is not registered in the system")
                else:
                    print(f"⚠ Firebase not connected, skipping database check")
            else:
                print(f"✗ INVALID: {message}")

        else:
            print(f"⚠ Unknown topic: {topic}")

    except json.JSONDecodeError as e:
        print(f"✗ JSON Parse Error: {e}")
    except Exception as e:
        print(f"✗ Error processing message: {e}")

    print(f"{'='*60}\n")

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    try:
        # Initialize Firebase Admin SDK with service account key
        admin_sdk_path = os.getenv("FIREBASE_ADMIN_SDK_PATH", "./adminsdk.json")
        cred = credentials.Certificate(admin_sdk_path)

        firebase_admin.initialize_app(cred, {
            'databaseURL': firebase_config["databaseURL"]
        })

        print(f"✓ Connected to Firebase project: {firebase_config['projectId']}")
        print(f"✓ Realtime Database URL: {firebase_config['databaseURL']}")
        return True
    except Exception as e:
        print(f"✗ Firebase initialization error: {e}")
        print("\nNote: For full Firebase Admin SDK functionality, you need a service account key.")
        print("For now, continuing with MQTT connection only...")
        return False

def initialize_mqtt():
    """Initialize MQTT client"""
    try:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        print(f"\nConnecting to MQTT broker: {MQTT_SERVER}:{MQTT_PORT}...")
        client.connect(MQTT_SERVER, MQTT_PORT, 60)

        return client
    except Exception as e:
        print(f"✗ MQTT initialization error: {e}")
        return None

def main():
    """Main program loop"""
    global running, firebase_connected

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    print("=" * 60)
    print("Smart Guard - Firebase & MQTT Connection")
    print("=" * 60)
    print("\nInitializing connections...")

    # Initialize Firebase
    firebase_connected = initialize_firebase()

    # Initialize MQTT
    mqtt_client = initialize_mqtt()

    if mqtt_client is None:
        print("\n✗ Failed to initialize MQTT client. Exiting...")
        return

    # Start MQTT loop in background
    mqtt_client.loop_start()

    print("\n" + "=" * 60)
    print("System running. Press Ctrl+C to terminate.")
    print("=" * 60 + "\n")

    # Keep the program running until Ctrl+C
    try:
        while running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    # Cleanup
    print("\nCleaning up connections...")
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

    if firebase_connected:
        firebase_admin.delete_app(firebase_admin.get_app())

    print("✓ Shutdown complete. Goodbye!\n")

if __name__ == "__main__":
    main()
