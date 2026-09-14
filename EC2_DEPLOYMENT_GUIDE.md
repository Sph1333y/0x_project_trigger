# 🚀 AWS EC2 Deployment & Flutter Integration Guide

This guide explains how to connect your **Flutter application** to the **FastAPI Backend** and deploy the backend to an **AWS EC2 instance**.

---

## 1. Flutter Frontend Integration

Your Flutter app can send toggle commands using the standard `http` package.

### API Endpoints

| Action | HTTP Method | Endpoint | Request Body | Response |
|---|---|---|---|---|
| **Turn ON** | `POST` | `/flag` | `{"flag": 1}` | `{"flag": 1, "status": "ok"}` |
| **Turn OFF** | `POST` | `/flag` | `{"flag": 0}` | `{"flag": 0, "status": "ok"}` |
| **Get Status** | `GET` | `/status` | _None_ | `{"flag": 0, "status": "ok"}` |

> **Note:** The server also supports query parameter format:
> * `GET /flag?flag=1` or `POST /flag?flag=1`
> * Shortcut endpoints: `POST /on` and `POST /off`

### Flutter (Dart) Implementation Example

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class AttendanceService {
  // Replace with your EC2 Public IP or domain
  static const String baseUrl = 'http://<YOUR_EC2_PUBLIC_IP>:8000';

  /// Send toggle command (1 for ON, 0 for OFF)
  static Future<Map<String, dynamic>?> toggleFlag(int flag) async {
    final url = Uri.parse('$baseUrl/flag');
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'flag': flag}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        print('Server response: $data');
        return data; // {"flag": 1, "status": "ok"} or {"flag": 0, "status": "ok"}
      } else {
        print('HTTP Error: ${response.statusCode}');
      }
    } catch (e) {
      print('Network Error: $e');
    }
    return null;
  }

  /// Get current flag status
  static Future<int> getStatus() async {
    final url = Uri.parse('$baseUrl/status');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return data['flag'] ?? 0;
      }
    } catch (e) {
      print('Network Error: $e');
    }
    return 0;
  }
}
```

---

## 2. AWS EC2 Setup & Deployment

### Step 2.1: Open Port 8000 on EC2 Security Group
1. Go to **AWS Console** $\rightarrow$ **EC2** $\rightarrow$ **Security Groups**.
2. Select the Security Group attached to your EC2 instance.
3. Click **Edit inbound rules** and add:
   * **Type**: Custom TCP
   * **Port range**: `8000`
   * **Source**: `0.0.0.0/0` (Anywhere IPv4)
4. Click **Save rules**.

---

### Step 2.2: Install Python & Google Chrome on EC2 (Ubuntu)
SSH into your EC2 instance:
```bash
ssh -i your-key.pem ubuntu@<YOUR_EC2_PUBLIC_IP>
```

Update system packages and install Python:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv wget curl unzip
```

Install Google Chrome (needed for headless submission):
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
google-chrome --version
```

---

### Step 2.3: Upload Backend Files & Install Dependencies
1. Copy the `cloud` folder to your EC2 instance using SCP:
   ```bash
   scp -i your-key.pem -r D:/Ai_space/cloud ubuntu@<YOUR_EC2_PUBLIC_IP>:/home/ubuntu/cloud
   ```
2. On EC2, set up a virtual environment:
   ```bash
   cd /home/ubuntu/cloud
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

### Step 2.4: Test the Server
Start the server manually:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
From your local terminal, verify with curl:
```bash
curl http://<YOUR_EC2_PUBLIC_IP>:8000/status
# Expected: {"flag":0,"status":"ok"}

curl -X POST http://<YOUR_EC2_PUBLIC_IP>:8000/flag -H "Content-Type: application/json" -d "{\"flag\": 1}"
# Expected: {"flag":1,"status":"ok"}
```

---

### Step 2.5: Keep Server Running 24/7 (systemd Service)
To keep FastAPI running permanently in the background:
```bash
sudo cp /home/ubuntu/cloud/attendance.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable attendance.service
sudo systemctl start attendance.service

# Check service status
sudo systemctl status attendance.service
```

Logs can be viewed anytime with:
```bash
sudo journalctl -u attendance.service -f
```
