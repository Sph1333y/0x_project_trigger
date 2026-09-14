# 🚀 AWS EC2 (ARM64 / Graviton2) Deployment & Flutter Integration Guide

This guide details how to deploy the **FastAPI Attendance Automation Backend** on an **AWS EC2 ARM64 instance** (Ubuntu Server on `t4g.small` in `ap-south-1`) with **IPv6 public connectivity**, and how to integrate it with the **Flutter Frontend mobile application**.

---

## 🏗️ 1. Production Target Environment Specification

| Component | Specification |
|---|---|
| **Cloud Provider** | AWS (Amazon Web Services) |
| **Region** | `ap-south-1` (Mumbai) |
| **Instance Type** | `t4g.small` |
| **CPU Architecture** | **ARM64 / AWS Graviton2** (2 vCPUs) |
| **Memory** | 2 GiB RAM |
| **Storage** | 8 GiB gp3 EBS |
| **Operating System** | Ubuntu Server 22.04 / 24.04 LTS (ARM64) |
| **Networking** | Dual-Stack IPv4 / IPv6 (IPv6 default gateway configured) |
| **Runtime** | Python 3.10+ / Uvicorn (1 worker) / Chromium (Ubuntu ARM64) |

> ⚠️ **Important Architecture Notice**:
> This server runs on **ARM64 (aarch64)**. Do **NOT** attempt to download or install AMD64/x86_64 Google Chrome packages (`.deb` x86). Use the native Ubuntu ARM64-compatible `chromium` package provided by the operating system repository.

---

## 📱 2. Flutter Mobile Application Integration

The Flutter application controls the backend attendance trigger via HTTP requests protected by Header-only API key authentication (`X-API-Key`).

### 2.1 API Specification

| Action | HTTP Method | Endpoint | Headers Required | Request Body | Response Format |
|---|---|---|---|---|---|
| **Public Health** | `GET` | `/health` | _None_ | _None_ | `{"status": "ok"}` |
| **Turn ON** | `POST` | `/flag` | `X-API-Key: <API_KEY>`, `Content-Type: application/json` | `{"flag": 1}` | `{"flag": 1, "status": "ok"}` |
| **Turn OFF** | `POST` | `/flag` | `X-API-Key: <API_KEY>`, `Content-Type: application/json` | `{"flag": 0}` | `{"flag": 0, "status": "ok"}` |
| **Check Status** | `GET` | `/status` | `X-API-Key: <API_KEY>` | _None_ | `{"flag": 0, "status": "ok"}` |
| **Read Flag** | `GET` | `/flag` | `X-API-Key: <API_KEY>` | _None_ | `{"flag": 0, "status": "ok"}` |
| **Shortcut ON** | `POST` | `/on` | `X-API-Key: <API_KEY>` | `{"auto_trigger": false}` | `{"flag": 1, "status": "ok"}` |
| **Shortcut OFF** | `POST` | `/off` | `X-API-Key: <API_KEY>` | _None_ | `{"flag": 0, "status": "ok"}` |

---

### 2.2 Flutter (Dart) Service Implementation

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class AttendanceService {
  // During initial testing with EC2 Public IPv6:
  // Note: Literal IPv6 addresses MUST be enclosed in brackets [ ]
  static const String baseUrl = 'http://[<EC2_IPV6>]:8000';

  // In future production with domain name & HTTPS:
  // static const String baseUrl = 'https://api.example.com';

  static const String apiKey = '<API_KEY>';

  /// Sends toggle command (1 for ON, 0 for OFF)
  static Future<bool> setFlag(int flagValue) async {
    final uri = Uri.parse('$baseUrl/flag');
    try {
      final response = await http.post(
        uri,
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey,
        },
        body: jsonEncode({
          'flag': flagValue,
          'auto_trigger': false,
        }),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        print('Backend Response: $data'); // Output: {"flag": 1, "status": "ok"}
        return data['status'] == 'ok';
      } else {
        print('Server error: ${response.statusCode} - ${response.body}');
      }
    } catch (e) {
      print('Network exception: $e');
    }
    return false;
  }

  /// Fetches current flag status from backend
  static Future<int> getStatus() async {
    final uri = Uri.parse('$baseUrl/status');
    try {
      final response = await http.get(
        uri,
        headers: {
          'X-API-Key': apiKey,
        },
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return data['flag'] ?? 0;
      }
    } catch (e) {
      print('Network exception: $e');
    }
    return 0; // Default to OFF on connection failure
  }
}
```

---

### 2.3 Android Clear-Text HTTP Configuration (Testing Note)

During development and initial testing over HTTP (port 8000), Android may block cleartext HTTP traffic by default:
* If testing on Android over HTTP, ensure `android:usesCleartextTraffic="true"` is configured in `android/app/src/main/AndroidManifest.xml`.
* **Target Production Hardening**: In production, traffic should use **HTTPS (port 443)** with a domain name and TLS certificate (e.g., Let's Encrypt with Nginx reverse proxy), eliminating cleartext HTTP entirely.

---

## 🔒 3. AWS Security Group Configuration

Configure your AWS EC2 Security Group inbound rules:

### Current Testing Phase:
| Protocol | Port | Source | Purpose |
|---|---|---|---|
| **SSH (TCP)** | `22` | `<ADMIN_PUBLIC_IP>/32` | Secure remote administration (restricted to admin IP) |
| **Custom TCP** | `8000` | `::/0` (IPv6) and `0.0.0.0/0` (IPv4) | Direct FastAPI testing for Flutter app |

### Target Production Hardening Phase:
| Protocol | Port | Source | Purpose |
|---|---|---|---|
| **SSH (TCP)** | `22` | `<ADMIN_PUBLIC_IP>/32` | Secure remote administration |
| **HTTPS (TCP)** | `443` | `::/0` and `0.0.0.0/0` | Encrypted public mobile client traffic |
| **HTTP (TCP)** | `80` | `::/0` and `0.0.0.0/0` | Automatic redirect to HTTPS |
| **Port 8000** | — | **BLOCKED** | FastAPI bound to localhost only behind reverse proxy |

---

## ⚙️ 4. Step-by-Step EC2 Server Deployment (ARM64 Ubuntu)

### Step 4.1: Connect to EC2
```bash
ssh -i your-key.pem ubuntu@<EC2_IPV6>
# Or via IPv4: ssh -i your-key.pem ubuntu@<EC2_IPV4>
```

### Step 4.2: Update System & Install ARM64 Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-pip python3-venv chromium curl

# Verify Chromium is installed for ARM64:
chromium --version
```

### Step 4.3: Clone the Repository
```bash
git clone https://github.com/Sph1333y/0x_project_trigger.git /home/ubuntu/cloud
cd /home/ubuntu/cloud
```

### Step 4.4: Setup Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4.5: Create Secret Environment Configuration (`.env`)
> ⚠️ **CRITICAL SECURITY REQUIREMENT**:
> The `.env` file containing your secret API key must **NEVER** be committed to GitHub. Create it directly on the EC2 server:

```bash
cat << 'EOF' > /home/ubuntu/cloud/.env
# Attendance Backend Production Secrets
ATTENDANCE_API_KEY=<REAL_SECRET_CREATED_LOCALLY>
ATTENDANCE_VENUE=G4104
EOF

# Restrict file permissions to the ubuntu user:
chmod 600 /home/ubuntu/cloud/.env
```

---

## 🚀 5. Starting & Managing the 24/7 Background Service

### 5.1 Manual Launch (Testing)
```bash
bash start_server.sh
```

### 5.2 Production systemd Background Service (24/7 Auto-Restart)
```bash
# 1. Copy service unit to systemd
sudo cp /home/ubuntu/cloud/attendance.service /etc/systemd/system/

# 2. Reload systemd daemon
sudo systemctl daemon-reload

# 3. Enable and start the service
sudo systemctl enable attendance.service
sudo systemctl start attendance.service

# 4. Check status
sudo systemctl status attendance.service
```

### 5.3 Viewing Live Logs
```bash
sudo journalctl -u attendance.service -f
```

---

## 🧪 6. Testing the Live Server (cURL Examples)

### Test 1: Public Health Check
```bash
curl -6 http://[<EC2_IPV6>]:8000/health
# Expected: {"status":"ok"}
```

### Test 2: Authenticated Status Query
```bash
curl -6 \
  -H "X-API-Key: <API_KEY>" \
  http://[<EC2_IPV6>]:8000/status
# Expected: {"flag":0,"status":"ok"}
```

### Test 3: Set Flag to ON (`flag = 1`)
```bash
curl -6 -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_KEY>" \
  -d '{"flag": 1}' \
  http://[<EC2_IPV6>]:8000/flag
# Expected: {"flag":1,"status":"ok"}
```

### Test 4: Set Flag to OFF (`flag = 0`)
```bash
curl -6 -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_KEY>" \
  -d '{"flag": 0}' \
  http://[<EC2_IPV6>]:8000/flag
# Expected: {"flag":0,"status":"ok"}
```
