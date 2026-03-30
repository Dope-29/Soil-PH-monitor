import serial
import time
import os
import json
import threading
from supabase import create_client
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import google.genai as genai
from urllib.parse import urlparse, parse_qs

# Load environment variables from .env file
load_dotenv()

# 1. Your Supabase Credentials (from .env)
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

# 2. Configure Gemini API (using new google-genai package)
gemini_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=gemini_key)

# Store the latest pH reading for API access
latest_data = {"ph_level": None, "timestamp": None}

# 3. HTTP API Handler
class DataHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/latest':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(latest_data).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/api/ai-analysis':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            try:
                request_data = json.loads(body.decode('utf-8'))
                ph_level = request_data.get('ph_level')
                soil_type = request_data.get('soil_type', 'loam')
                
                print(f"🤖 AI Analysis requested: pH={ph_level}, Soil={soil_type}")
                analysis = generate_ai_analysis(ph_level, soil_type)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response_data = {"analysis": analysis}
                self.wfile.write(json.dumps(response_data).encode())
                print(f"✓ AI Analysis sent ({len(analysis)} chars)")
            except Exception as e:
                print(f"❌ Error in AI analysis: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logging

def generate_ai_analysis(ph_level, soil_type):
    """Generate AI analysis using Gemini 2.5 Flash API"""
    prompt = f"""You are a soil analysis expert. Provide a BRIEF single-paragraph recommendation for this soil condition. 

Soil Type: {soil_type}
Current pH Level: {ph_level}

Respond with ONLY a short, concise single paragraph (3-4 sentences max). Format as simple bullet points separated by ' • '. 
Include only: pH status, what to add/adjust, and one best practice. Be direct and practical."""

    try:
        print(f"  Calling Gemini 2.5 Flash API...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        analysis_text = response.text.strip()
        print(f"  ✓ Gemini API returned: {analysis_text[:100]}...")
        
        return analysis_text
    except Exception as e:
        print(f"  ❌ Gemini API error: {e}")
        import traceback
        traceback.print_exc()
        return f"⚠️ Error: {str(e)}"

# 4. Start API server in background thread
def start_api_server():
    server = HTTPServer(('localhost', 5000), DataHandler)
    print("API Server running on http://localhost:5000")
    server.serve_forever()

api_thread = threading.Thread(target=start_api_server, daemon=True)
api_thread.start()

# 5. Find and Connect to ESP32/Arduino
def find_available_ports():
    """Find available serial ports"""
    try:
        import serial.tools.list_ports
        ports = [port.device for port in serial.tools.list_ports.comports()]
        return ports
    except:
        return []

available_ports = find_available_ports()
print(f"Available COM ports: {available_ports if available_ports else 'None detected'}")

ser = None
SERIAL_PORT = 'COM5'  # Default port

try:
    # Try to connect to COM5
    ser = serial.Serial(SERIAL_PORT, 115200, timeout=1)
    time.sleep(2)
    print(f"✓ Serial connection established on {SERIAL_PORT}")
except Exception as e:
    print(f"⚠ Cannot connect to {SERIAL_PORT}: {e}")
    print(f"   Available ports: {available_ports if available_ports else 'None'}")
    print(f"   The API server will still run and provide mock data for testing.")
    ser = None

# 6. Main loop: Read from sensor and push to Supabase
def sensor_loop():
    """Main sensor reading loop"""
    while True:
        try:
            if ser and ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                
                # Look for the "pH:" string from Arduino output
                # Arduino format: "Raw: 1234 | pH: 6.5"
                if "pH:" in line:
                    try:
                        # Extract the pH value calculated by Arduino
                        ph_value = float(line.split("pH: ")[1])
                        print(f"📊 Sensor: {line.strip()}")

                        # Update local data
                        latest_data["ph_level"] = round(ph_value, 2)
                        latest_data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

                        # Push to Supabase
                        data = {"ph_level": ph_value}
                        supabase.table("soil_logs").insert(data).execute()
                        print("✓ Synced to Supabase")
                        
                    except Exception as e:
                        print(f"Error parsing data: {e}")
            else:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n⏹ Shutting down...")
            break
        except Exception as e:
            print(f"Error in sensor loop: {e}")
            time.sleep(1)

# Start sensor loop in background thread
sensor_thread = threading.Thread(target=sensor_loop, daemon=True)
sensor_thread.start()

# Keep main thread alive
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n⏹ Bridge shutting down...")
    if ser:
        ser.close()