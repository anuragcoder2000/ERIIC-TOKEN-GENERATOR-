from flask import Flask, render_template, request, jsonify
import requests
import uuid
import time
import base64
import io
import struct
import random
import os
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

app = Flask(__name__)

# --- CONFIGURATION ---
FB_APP_ID = "350685531728"
FB_APP_SECRET = "62f8ce9f74b12f84c123cc23437a4a32"
LITE_APP_ID = "275254692598279"
API_GRAPH = "https://b-graph.facebook.com"
API_METHOD = "https://api.facebook.com/method"

# Device Profiles for Rotation (To avoid bot detection patterns)
DEVICE_PROFILES = [
    {
        "model": "Pixel 8 Pro", "brand": "google", "os": "14", "build": "AP1A.240405.002",
        "width": 1344, "height": 2992, "density": 3.0, "fbav": "460.0.0.42.109", "fbbv": "585672584"
    },
    {
        "model": "Pixel 7", "brand": "google", "os": "13", "build": "TQ2A.230605.010",
        "width": 1080, "height": 2400, "density": 2.625, "fbav": "455.0.0.28.111", "fbbv": "581000000"
    },
    {
        "model": "SM-S918B", "brand": "samsung", "os": "13", "build": "TP1A.220624.014",
        "width": 1440, "height": 3088, "density": 3.0, "fbav": "458.0.0.30.105", "fbbv": "583000000"
    }
]

class DeviceFingerprint:
    def __init__(self):
        profile = random.choice(DEVICE_PROFILES)
        
        # Unique IDs
        self.device_id = str(uuid.uuid4())
        self.family_device_id = str(uuid.uuid4())
        self.adid = str(uuid.uuid4())
        
        # Specs
        self.os_version = profile["os"]
        self.device_model = profile["model"]
        self.device_brand = profile["brand"]
        self.device_build = profile["build"]
        self.carrier = random.choice(["T-Mobile", "Verizon", "AT&T", "Jio"])
        self.locale = "en_US"
        self.fbav = profile["fbav"]
        self.fbbv = profile["fbbv"]
        self.arch = "arm64-v8a"
        self.density = profile["density"]
        self.width = profile["width"]
        self.height = profile["height"]
        
        # User-Agent
        self.user_agent = (
            f"Dalvik/2.1.0 (Linux; U; Android {self.os_version}; {self.device_model} Build/{self.device_build}) "
            f"[FBAN/FB4A;FBAV/{self.fbav};FBPN/com.facebook.katana;FBLC/{self.locale};FBBV/{self.fbbv};"
            f"FBCR/{self.carrier};FBMF/{self.device_brand};FBBD/{self.device_brand};FBDV/{self.device_model};"
            f"FBSV/{self.os_version};FBCA/{self.arch}:null;FBDM/density={self.density},width={self.width},height={self.height};"
            f"FB_FW/1;FBRV/0;]"
        )

    def get_headers(self):
        return {
            "User-Agent": self.user_agent,
            "X-FB-Connection-Quality": random.choice(["EXCELLENT", "GOOD"]),
            "X-FB-Connection-Type": "WIFI",
            "X-FB-Legacy-Httplib": "true",
            "X-Asbd-Url": "1",
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-FB-Friendly-Name": "com.facebook.katana",
            "X-FB-LDM": "1"
        }

    def get_base_params(self):
        return {
            "device_id": self.device_id,
            "family_device_id": self.family_device_id,
            "adid": self.adid,
            "format": "json",
            "generate_analytics_claim": "1",
            "cpl": "true",
            "try_num": "1",
            "credentials_type": "password",
            "source": "login",
            "error_detail_type": "button_with_disabled",
            "enroll_misauth": "false",
            "generate_session_cookies": "1",
            "generate_machine_id": "1",
            "currently_logged_in_userid": "0",
            "fb_api_req_friendly_name": "authenticate"
        }

class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key():
        try:
            url = f'{API_GRAPH}/pwd_key_fetch'
            params = {
                'version': '2',
                'flow': 'CONTROLLER_INITIALIZATION',
                'method': 'GET',
                'fb_api_req_friendly_name': 'pwdKeyFetch',
                'fb_api_caller_class': 'com.facebook.auth.login.AuthOperations',
                'access_token': f'{FB_APP_ID}|{FB_APP_SECRET}'
            }
            response = requests.post(url, params=params).json()
            return response.get('public_key'), str(response.get('key_id', '25'))
        except Exception as e:
            print(f"Key Fetch Error: {e}")
            return None, "25"

    @staticmethod
    def encrypt(password, public_key=None, key_id="25"):
        if public_key is None:
            public_key, key_id = FacebookPasswordEncryptor.get_public_key()
            if public_key is None: 
                return password
            
        try:
            rand_key = get_random_bytes(32)
            iv = get_random_bytes(12)
            pubkey = RSA.import_key(public_key)
            cipher_rsa = PKCS1_v1_5.new(pubkey)
            encrypted_rand_key = cipher_rsa.encrypt(rand_key)
            
            cipher_aes = AES.new(rand_key, AES.MODE_GCM, nonce=iv)
            current_time = int(time.time())
            cipher_aes.update(str(current_time).encode("utf-8"))
            encrypted_passwd, auth_tag = cipher_aes.encrypt_and_digest(password.encode("utf-8"))
            
            buf = io.BytesIO()
            buf.write(bytes([1, int(key_id)]))
            buf.write(iv)
            buf.write(struct.pack("<h", len(encrypted_rand_key)))
            buf.write(encrypted_rand_key)
            buf.write(auth_tag)
            buf.write(encrypted_passwd)
            
            encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"#PWD_FB4A:2:{current_time}:{encoded}"
        except Exception as e:
            print(f"Encryption Error: {e}")
            return password

sessions_data = {}

def human_delay(min_s=0.3, max_s=0.8):
    time.sleep(random.uniform(min_s, max_s))

def convert_to_lite_token(master_token, device, session):
    """
    Converts EAAB to EAADV7 with a 'warm up' step.
    """
    try:
        # Step 1: Warm up the token with a simple /me call
        human_delay(0.2, 0.5)
        headers = device.get_headers()
        headers['Authorization'] = f"OAuth {master_token}"
        
        # Simple /me call to activate session
        session.get(f"{API_GRAPH}/me", params={"fields": "id,name", "format": "json"}, headers=headers)
        
        # Step 2: Convert to Lite
        human_delay(0.5, 1.0)
        url = f"{API_METHOD}/auth.getSessionforApp"
        data = {
            'access_token': master_token,
            'format': 'json',
            'new_app_id': LITE_APP_ID,
            'generate_session_cookies': '1'
        }
        response = session.post(url, data=data, headers=headers)
        lite_data = response.json()
        
        if 'access_token' in lite_data:
            return lite_data['access_token']
        else:
            print(f"Lite Conversion Failed: {lite_data}")
            return master_token
            
    except Exception as e:
        print(f"Token Conversion Error: {e}")
        return master_token

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    uid = request.form.get('uid')
    password = request.form.get('password')
    
    if not uid or not password:
        return jsonify({'error': 'Email and Password are required'})

    device = DeviceFingerprint()
    session = requests.Session()
    session.headers.update(device.get_headers())
    session.headers['Authorization'] = f"OAuth {FB_APP_ID}|{FB_APP_SECRET}"

    human_delay()
    pub_key, key_id = FacebookPasswordEncryptor.get_public_key()
    encrypted_password = FacebookPasswordEncryptor.encrypt(password, pub_key, key_id)

    login_data = device.get_base_params()
    login_data.update({
        "email": uid,
        "password": encrypted_password
    })

    try:
        human_delay()
        response = session.post(f"{API_GRAPH}/auth/login", data=login_data)
        res_data = response.json()
        
        if 'access_token' in res_data:
            master_token = res_data['access_token']
            final_token = convert_to_lite_token(master_token, device, session)
            
            return jsonify({
                'success': True, 
                'token': final_token,
                'master_token': master_token,
                'device_id': device.device_id,
                'user_id': res_data.get('user_id')
            })

        if 'error' in res_data:
            err = res_data['error']
            err_code = err.get('code')
            err_msg = err.get('message', '').lower()
            err_data = err.get('error_data', {})
            
            is_2fa = err_code in [317, 459] or 'login_first_factor' in err_data or 'approval' in err_msg
            
            if is_2fa:
                session_id = str(uuid.uuid4())
                sessions_data[session_id] = {
                    'uid': uid,
                    'err_data': err_data,
                    'device': device,
                    'session': session,
                    'login_data': login_data
                }
                return jsonify({
                    'two_factor': True, 
                    'session_id': session_id,
                    'error_code': err_code
                })
            
            return jsonify({
                'success': False,
                'error': err.get('message', 'Login failed'),
                'error_code': err_code,
                'error_data': err_data
            })
            
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/two_factor', methods=['POST'])
def two_factor():
    session_id = request.form.get('session_id')
    otp = request.form.get('otp')
    
    if not session_id or session_id not in sessions_data:
        return jsonify({'error': 'Invalid or expired session'})
    
    s = sessions_data[session_id]
    device = s['device']
    session = s['session']
    login_data = s['login_data']
    err_data = s['err_data']
    
    login_data['twofactor_code'] = otp
    login_data['credentials_type'] = 'two_factor'
    
    if 'uid' in err_data:
        login_data['userid'] = err_data['uid']
    if 'login_first_factor' in err_data:
        login_data['first_factor'] = err_data['login_first_factor']
        login_data['machine_id'] = err_data['login_first_factor']

    try:
        human_delay()
        response = session.post(f"{API_GRAPH}/auth/login", data=login_data)
        res_data = response.json()
        
        if 'access_token' in res_data:
            master_token = res_data['access_token']
            del sessions_data[session_id]
            
            final_token = convert_to_lite_token(master_token, device, session)
            
            return jsonify({
                'success': True, 
                'token': final_token,
                'master_token': master_token,
                'user_id': res_data.get('user_id')
            })
            
        if 'error' in res_data:
            del sessions_data[session_id]
            err = res_data['error']
            return jsonify({
                'success': False,
                'error': err.get('message', '2FA Failed'),
                'error_code': err.get('code')
            })
            
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting FB Login Server on port {port}")
    app.run(host='0.0.0.0', port=port)