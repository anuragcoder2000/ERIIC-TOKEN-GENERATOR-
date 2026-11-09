from flask import Flask, render_template, request, jsonify
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
import time
import uuid
import threading
import random
import os

app = Flask(__name__)

FB_APP_ID = "350685531728"
FB_APP_SECRET = "62f8ce9f74b12f84c123cc23437a4a32"
LITE_APP_ID = "275254692598279"

sessions_data = {}

def find_and_click(driver, xpaths, timeout=5):
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            return True
        except:
            continue
    return False

def selenium_login_task(session_id, uid, password):
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    # Desktop User-Agent taaki FB mobile block na kare
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36')
    
    try:
        driver = uc.Chrome(options=options, version_main=156)
        sessions_data[session_id]['driver'] = driver
        sessions_data[session_id]['status'] = 'starting'
        
        # Pehle Desktop version try karo
        driver.get("https://www.facebook.com/")
        time.sleep(random.uniform(3, 5))
        
        # Check if blocked
        if "checkpoint" in driver.current_url or "login/device-based" in driver.current_url:
             sessions_data[session_id]['status'] = 'error'
             sessions_data[session_id]['message'] = 'Facebook IP Block detected. Please try after some time or use a proxy.'
             driver.quit()
             return

        # Handle Cookie Consent Popup
        try:
            WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Allow all cookies') or contains(text(), 'Accept All') or contains(text(), 'Only allow essential cookies')]"))).click()
            time.sleep(1)
        except:
            pass

        # Try Desktop Login Form
        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            email_field.send_keys(uid)
            time.sleep(random.uniform(0.5, 1.0))
            
            pass_field = driver.find_element(By.ID, "pass")
            pass_field.send_keys(password)
            time.sleep(random.uniform(0.5, 1.0))
            
            driver.find_element(By.NAME, "login").click()
            
        except Exception as e:
            # Agar Desktop fail ho jaye, toh Mobile try karo
            try:
                driver.get("https://m.facebook.com/")
                time.sleep(2)
                email_field = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "m_login_email"))
                )
                email_field.send_keys(uid)
                pass_field = driver.find_element(By.ID, "m_login_password")
                pass_field.send_keys(password)
                driver.find_element(By.NAME, "login").click()
            except:
                sessions_data[session_id]['status'] = 'error'
                sessions_data[session_id]['message'] = f'Login form not found. Current URL: {driver.current_url}'
                driver.quit()
                return

        time.sleep(5) # Wait for 2FA or Redirect

        # --- 2FA / APPROVAL LOGIC ---
        page_source = driver.page_source.lower()
        
        if "two-factor" in driver.current_url or "approvals" in driver.current_url or "checkpoint" in driver.current_url or "authentication" in page_source or "two_factor" in page_source:
            sessions_data[session_id]['status'] = 'waiting_2fa'
            
            # Wait until user completes it (Max 5 mins)
            for _ in range(60):
                time.sleep(5)
                
                # Check if user submitted OTP on website
                if sessions_data[session_id].get('otp_submitted'):
                    try:
                        # Find input fields for OTP
                        otp_input = driver.find_element(By.XPATH, "//input[@type='text' or @type='tel' or @inputmode='numeric']")
                        otp_input.clear()
                        otp_input.send_keys(sessions_data[session_id]['otp'])
                        
                        find_and_click(driver, [
                            "//button[contains(text(), 'Continue')]",
                            "//button[contains(text(), 'Submit')]",
                            "//button[@type='submit']",
                            "//input[@type='submit']"
                        ])
                    except:
                        pass
                    sessions_data[session_id]['otp_submitted'] = False

                # Check if login successful
                current_url = driver.current_url.lower()
                if "home" in current_url or "facebook.com/?sk=h_chr" in current_url or "m.facebook.com/?_rdr" in current_url or "facebook.com/" == current_url.replace("https://", "").replace("www.", ""):
                    break
                
                # Try clicking "Try another way" if stuck
                if "try another way" in driver.page_source.lower():
                    find_and_click(driver, ["//a[contains(text(), 'Try another way')]"])

        # --- EXTRACT TOKEN ---
        sessions_data[session_id]['status'] = 'extracting'
        cookies = driver.get_cookies()
        xs_cookie = next((c['value'] for c in cookies if c['name'] == 'xs'), None)
        c_user = next((c['value'] for c in cookies if c['name'] == 'c_user'), None)
        
        if not xs_cookie or not c_user:
            sessions_data[session_id]['status'] = 'error'
            sessions_data[session_id]['message'] = 'Login failed. Wrong password or FB blocked the login.'
            driver.quit()
            return

        session_req = requests.Session()
        for cookie in cookies:
            session_req.cookies.set(cookie['name'], cookie['value'])
            
        # App ID & Secret ke through EAADV7 generate karne ki koshish
        try:
            url = "https://api.facebook.com/method/auth.getSessionforApp"
            data = {
                'access_token': f"{FB_APP_ID}|{FB_APP_SECRET}", 
                'format': 'json',
                'new_app_id': LITE_APP_ID,
                'generate_session_cookies': '1',
                'uid': c_user
            }
            res = session_req.post(url, data=data, timeout=10).json()
            
            if 'access_token' in res:
                final_token = res['access_token']
            else:
                final_token = f"WEB_SESSION_{c_user}"
        except:
            final_token = f"WEB_SESSION_{c_user}"
            
        sessions_data[session_id]['status'] = 'success'
        sessions_data[session_id]['token'] = final_token
        driver.quit()

    except Exception as e:
        sessions_data[session_id]['status'] = 'error'
        sessions_data[session_id]['message'] = str(e)
        try:
            driver.quit()
        except: pass

# ==========================================
# ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_selenium', methods=['POST'])
def start_selenium():
    uid = request.form.get('uid')
    password = request.form.get('password')
    
    if not uid or not password:
        return jsonify({'error': 'Email and Password required'})
        
    session_id = str(uuid.uuid4())
    sessions_data[session_id] = {
        'status': 'initializing',
        'message': 'Starting browser...',
        'otp': '',
        'otp_submitted': False
    }
    
    thread = threading.Thread(target=selenium_login_task, args=(session_id, uid, password))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'session_id': session_id})

@app.route('/check_status/<session_id>', methods=['GET'])
def check_status(session_id):
    if session_id not in sessions_data:
        return jsonify({'status': 'error', 'message': 'Session not found'})
        
    data = sessions_data[session_id]
    return jsonify({
        'status': data['status'],
        'message': data.get('message', ''),
        'token': data.get('token', '')
    })

@app.route('/submit_otp/<session_id>', methods=['POST'])
def submit_otp(session_id):
    otp = request.form.get('otp')
    if session_id in sessions_data:
        sessions_data[session_id]['otp'] = otp
        sessions_data[session_id]['otp_submitted'] = True
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid session'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)