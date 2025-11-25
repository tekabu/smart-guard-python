# Smart Guard Python - Installation Guide

This guide will help you set up and run the Smart Guard Python application on Windows.

## Prerequisites

- **Git** installed on your system
- **Conda** (Anaconda or Miniconda) installed on your system
- **Python 3.12** (will be installed via Conda)
- **Firebase Admin SDK service account key** (JSON file)

## Installation Steps

### 1. Clone the Repository

Open Command Prompt or PowerShell and clone the repository:

```bash
git clone https://github.com/tekabu/smart-guard-python.git
```

### 2. Navigate to Source Folder

Navigate into the cloned project folder:

```bash
cd smart-guard-python
```

### 3. Create Conda Environment

Create a new conda environment with Python 3.12 in the project directory:

```bash
conda create --prefix ./env python=3.12 -y
```

### 4. Activate the Environment

Activate the newly created environment (make sure you're in the source folder):

```bash
conda activate ./env
```

Or use the full path if needed:

```bash
conda activate <your-path-to-project>\smart-guard-python\env
```

### 5. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

This will install:
- `firebase-admin` - Firebase Admin SDK for Python
- `paho-mqtt` - MQTT client library
- `python-dotenv` - Environment variable management

### 6. Configure Environment Variables

1. Copy the `.env.example` file to `.env`:

   ```bash
   copy .env.example .env
   ```

2. Edit the `.env` file and update the configuration values:

   ```env
   # Firebase Configuration
   FIREBASE_API_KEY=your_api_key_here
   FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
   FIREBASE_DATABASE_URL=https://your_project.firebasedatabase.app
   FIREBASE_PROJECT_ID=your_project_id
   FIREBASE_STORAGE_BUCKET=your_project.firebasestorage.app
   FIREBASE_MESSAGING_SENDER_ID=your_sender_id
   FIREBASE_APP_ID=your_app_id

   # Firebase Admin SDK
   FIREBASE_ADMIN_SDK_PATH=./adminsdk.json

   # MQTT Configuration
   MQTT_SERVER=broker.emqx.io
   MQTT_PORT=1883

   # MQTT Topics
   MQTT_TOPIC_CARD=smartguard/verify/card
   MQTT_TOPIC_FINGERPRINT=smartguard/verify/fingerprint
   MQTT_TOPIC_LOCK_OPEN=smartguard/lock/open
   ```

### 7. Add Firebase Admin SDK Key

1. Download your Firebase Admin SDK service account key from Firebase Console:
   - Go to **Firebase Console** > **Project Settings** > **Service Accounts**
   - Click **Generate New Private Key**
   - Save the JSON file

2. Rename the file to `adminsdk.json` and place it in the project root directory, or update the `FIREBASE_ADMIN_SDK_PATH` in your `.env` file to point to your JSON file location.

### 8. Verify Configuration

Your project directory should now look like this:

```
smart-guard-python/
├── env/                          # Conda environment (created)
├── main.py                       # Main application
├── requirements.txt              # Python dependencies
├── .env                          # Your environment variables (created)
├── .env.example                  # Environment variables template
├── adminsdk.json                 # Firebase Admin SDK key (added)
└── INSTALL.md                    # This file
```

## Running the Application

1. **Navigate to source folder** (if not already there):

   ```bash
   cd smart-guard-python
   ```

2. **Activate the environment** (if not already activated):

   ```bash
   conda activate ./env
   ```

   Or use the full path:

   ```bash
   conda activate <your-path-to-project>\smart-guard-python\env
   ```

3. **Run the application**:

   ```bash
   python main.py
   ```

4. **Expected output**:

   ```
   ============================================================
   Smart Guard - Firebase & MQTT Connection
   ============================================================

   Initializing connections...
   ✓ Connected to Firebase project: smartguard-system
   ✓ Realtime Database URL: https://...

   Connecting to MQTT broker: broker.emqx.io:1883...

   ============================================================
   System running. Press Ctrl+C to terminate.
   ============================================================

   ✓ Connected to MQTT broker at broker.emqx.io:1883
   ✓ Subscribed to topic: smartguard/verify/card
   ✓ Subscribed to topic: smartguard/verify/fingerprint
   ```

5. **Stop the application**:

   Press `Ctrl+C` to gracefully shut down the application.

## How It Works

### RFID Card Verification

When a message is received on `smartguard/verify/card`:

```json
{
    "card_reader": 1,
    "card_id": "137FF539"
}
```

The system will:
1. Validate the message format
2. Query Firebase for the RFID in `users/students/{card_id}`
3. Display student information
4. If registered, publish "OK" to `smartguard/lock/open`

### Fingerprint Verification

When a message is received on `smartguard/verify/fingerprint`:

```json
{
    "fingerprint_reader": 1,
    "fingerprint_id": 3
}
```

The system will:
1. Validate the message format
2. Search all students for matching fingerprint ID in `fprints` node
3. Display student information
4. If registered, publish "OK" to `smartguard/lock/open`

## Troubleshooting

### Firebase Connection Error

**Error:** `Failed to initialize a certificate credential`

**Solution:**
- Ensure `adminsdk.json` exists and path is correct in `.env`
- Verify the JSON file is valid and downloaded from Firebase Console
- Check file permissions

### MQTT Connection Failed

**Error:** `Failed to connect to MQTT broker`

**Solution:**
- Check your internet connection
- Verify `MQTT_SERVER` and `MQTT_PORT` in `.env`
- Try a different MQTT broker if `broker.emqx.io` is down

### Environment Variables Not Loading

**Error:** Configuration values are `None`

**Solution:**
- Ensure `.env` file exists in the project root
- Check that variable names in `.env` match exactly (case-sensitive)
- Verify `python-dotenv` is installed: `pip list | grep python-dotenv`

### Conda Environment Not Found

**Error:** `conda activate` not working

**Solution:**
- Use the full absolute path to the environment
- Initialize conda for Command Prompt: `conda init cmd.exe`
- Initialize conda for PowerShell: `conda init powershell`
- Restart your terminal after initialization

## Development

### Testing with MQTT

You can test the system by publishing messages to the MQTT topics using an MQTT client like:

- **MQTT Explorer** (GUI)
- **mosquitto_pub** (CLI)
- **Online MQTT Client** (Web)

Example using `mosquitto_pub`:

```bash
# Test card verification
mosquitto_pub -h broker.emqx.io -t "smartguard/verify/card" -m '{"card_reader":1,"card_id":"137FF539"}'

# Test fingerprint verification
mosquitto_pub -h broker.emqx.io -t "smartguard/verify/fingerprint" -m '{"fingerprint_reader":1,"fingerprint_id":3}'
```

### Deactivating the Environment

When you're done:

```bash
conda deactivate
```

## Security Notes

- **Never commit `.env` file** to version control (it's in `.gitignore`)
- **Never commit `adminsdk.json`** to version control
- **Keep your Firebase credentials secure**
- **Use secure MQTT connections (TLS)** in production

## Support

For issues or questions:
- Check Firebase Console for database structure
- Verify MQTT topic names match your hardware
- Review application logs for error messages

## License

This project is part of the Smart Guard System.
