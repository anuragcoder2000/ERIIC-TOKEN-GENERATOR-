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

app = Flask(__name__)

FB_APP_ID = "350685531728"
FB_APP_SECRET = "62f8ce9f74b12f84c123cc23437a4a32"
LITE_APP_ID = "275254692598279"

# Global dict to track browser sessions
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
    
    try:
        driver = uc.Chrome(options=options)
        sessions_data[session_id]['driver'] = driver
        sessions_data[session_id]['status'] = 'starting'
        
        driver.get("https://m.facebook.com/")
        time.sleep(random.uniform(2, 4))
        
        # Fill Login Form (Mobile view is easier to script)
        try:
            email_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "m_login_email")))
            email_field.send_keys(uid)
            
            pass_field = driver.find_element(By.ID, "m_login_password")
            pass_field.send_keys(password)
            
            time.sleep(random.uniform(0.5, 1.5))
            
            # Click Login Button
            find_and_click(driver, [
                "//button[@name='login']",
                "//button[contains(text(), 'Log In')]",
                "//input[@value='Log In']"
            ])
            
        except Exception as e:
            sessions_data[session_id]['status'] = 'error'
            sessions_data[session_id]['message'] = 'Login form not found. Network error?'
            driver.quit()
            return

        time.sleep(5) # Wait for page load or 2FA

        # --- 2FA / APPROVAL LOGIC ---
        # Check for 2FA URL or elements
        page_source = driver.page_source.lower()
        
        if "two-factor" in driver.current_url or "approvals" in driver.current_url or "checkpoint" in driver.current_url or "authentication" in page_source:
            sessions_data[session_id]['status'] = 'waiting_2fa'
            
            # Wait until user completes it (Max 5 mins)
            for _ in range(60):
                time.sleep(5)
                if sessions_data[session_id].get('otp_submitted'):
                    # User entered OTP in UI, inject it
                    try:
                        otp_input = driver.find_element(By.XPATH, "//input[@type='text' or @type='tel']")
                        otp_input.clear()
                        otp_input.send_keys(sessions_data[session_id]['otp'])
                        
                        find_and_click(driver, [
                            "//button[contains(text(), 'Continue')]",
                            "//button[contains(text(), 'Submit')]",
                            "//button[@type='submit']"
                        ])
                    except:
                        pass
                    sessions_data[session_id]['otp_submitted'] = False

                # Check if login successful (redirected to home)
                if "home" in driver.current_url or "facebook.com/?sk=h_chr" in driver.current_url or "m.facebook.com/?_rdr" in driver.current_url:
                    break
                
                # Try clicking "Try another way" if it's there
                if "try another way" in driver.page_source.lower():
                    find_and_click(driver, ["//a[contains(text(), 'Try another way')]"])

        # --- EXTRACT TOKEN ---
        sessions_data[session_id]['status'] = 'extracting'
        cookies = driver.get_cookies()
        xs_cookie = next((c['value'] for c in cookies if c['name'] == 'xs'), None)
        c_user = next((c['value'] for c in cookies if c['name'] == 'c_user'), None)
        
        if not xs_cookie:
            sessions_data[session_id]['status'] = 'error'
            sessions_data[session_id]['message'] = 'Login failed or wrong password.'
            driver.quit()
            return

        # Convert web session to EAAB using getSessionforApp
        # Note: Web cookies can't directly generate EAAB without an app request,
        # But we can use the c_user and xs to make a request to get an EAAB.
        # Simplest hack: Use the c_user and xs to fetch the app token via web sync endpoint
        # (This is highly experimental and may break due to FB updates)
        
        # --- Alternative: Use the mobile app logic to get EAAB ---
        # Since getting EAAB from Web cookies is complex, we'll use the requests session
        # with the extracted cookies to hit the auth endpoint.
        
        session_req = requests.Session()
        for cookie in cookies:
            session_req.cookies.set(cookie['name'], cookie['value'])
            
        # Note: To get a real EAAB/EAADV7, you usually need the API login.
        # Web session only gives web tokens. 
        # For the sake of this script, we'll just return the valid c_user and xs 
        # as a "Web Token" or try to fetch an EAAB using a trick.
        
        # Let's try to generate EAADV7 using the Web Session (Jugaad)
        try:
            # FB Lite endpoint using Web Cookies
            url = "https://api.facebook.com/method/auth.getSessionforApp"
            data = {
                'access_token': f"{FB_APP_ID}|{FB_APP_SECRET}", # App Token
                'format': 'json',
                'new_app_id': LITE_APP_ID,
                'generate_session_cookies': '1',
                'uid': c_user
            }
            res = session_req.post(url, data=data).json()
            
            if 'access_token' in res:
                final_token = res['access_token']
            else:
                final_token = f"WEB_SESSION_{c_user}" # Fallback
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
    
    # Run Selenium in a background thread to keep Flask responsive
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
    app.run(host='0.0.0.0', port=5000)