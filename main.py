import firebase_admin
from firebase_admin import credentials, auth, firestore, db
import paho.mqtt.client as mqtt
import signal
import sys
import time
import json

# Firebase configuration from firebase.ts
firebase_config = {
    "apiKey": "AIzaSyDWOfGlXKb2XZ0gqgKDOAAFh9ZdIq9Z6RE",
    "authDomain": "smartguard-system.firebaseapp.com",
    "databaseURL": "https://smartguard-system-default-rtdb.asia-southeast1.firebasedatabase.app",
    "projectId": "smartguard-system",
    "storageBucket": "smartguard-system.firebasestorage.app",
    "messagingSenderId": "481987146929",
    "appId": "1:481987146929:web:212e9df1f277a7bb485e90"
}

# MQTT configuration
MQTT_SERVER = "broker.emqx.io"
MQTT_PORT = 1883
MQTT_TOPICS = {
    "card": "smartguard/verify/card",
    "fingerprint": "smartguard/verify/fingerprint",
    "lock_open": "smartguard/lock/open"
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
        cred = credentials.Certificate("smartguard-system-firebase-adminsdk-fbsvc-aa6bccbad0.json")

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
