import requests
from bs4 import BeautifulSoup
import time
import smtplib
from email.mime.text import MIMEText
import logging
import os
from datetime import datetime
import json
import random
from pathlib import Path

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"nido_scraper_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

# URL to monitor
URL = "https://www.nidoliving.com/en-gb/netherlands/maastricht/randwyck"

# Configure email notification settings
EMAIL_ENABLED = False  # Set to True to enable email notifications
SENDER_EMAIL = "your_email@gmail.com"  # Replace with your email
RECEIVER_EMAIL = "omernidam21@gmail.com"  # Email to receive notifications
EMAIL_PASSWORD = ""  # Replace with your email password or app password

# Telegram notification settings (recommended for phone notifications)
TELEGRAM_ENABLED = True
    # Your personal chat ID

# How often to check the website (in seconds)
CHECK_INTERVAL = 3600  # Check every hour by default
# Add some randomness to avoid detection (±10%)
CHECK_INTERVAL_VARIATION = 0.1

# Store the last check result to avoid duplicate notifications
LAST_STATE_FILE = "last_check_state.json"

def send_email_notification(subject, message):
    """Send an email notification when rooms become available."""
    if not EMAIL_ENABLED:
        logging.info("Email notifications are disabled. Enable by setting EMAIL_ENABLED to True.")
        return False
    
    try:
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL

        # Connect to Gmail's SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        logging.info("Email notification sent successfully!")
        return True
    except Exception as e:
        logging.error(f"Failed to send email notification: {e}")
        return False

def send_telegram_notification(message):
    """Send a Telegram notification to your phone."""
    if not TELEGRAM_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.info("Telegram notifications are disabled or not configured properly.")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, data=data)
        
        if response.status_code == 200:
            logging.info("Telegram notification sent successfully!")
            return True
        else:
            logging.error(f"Failed to send Telegram notification: {response.text}")
            return False
    except Exception as e:
        logging.error(f"Error sending Telegram notification: {e}")
        return False

def save_last_state(state_data):
    """Save the last check state to avoid duplicate notifications."""
    try:
        with open(LAST_STATE_FILE, 'w') as f:
            json.dump(state_data, f)
    except Exception as e:
        logging.error(f"Failed to save last state: {e}")

def load_last_state():
    """Load the last check state."""
    try:
        if os.path.exists(LAST_STATE_FILE):
            with open(LAST_STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load last state: {e}")
    
    return {"last_check_time": None, "was_available": False}

def check_availability():
    """Check if rooms are available on the Nido website."""
    last_state = load_last_state()
    
    try:
        # Rotate user agents to avoid detection
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59'
        ]
        
        # Add headers to mimic a browser request
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        # Add a retry mechanism
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                response = requests.get(URL, headers=headers, timeout=30)
                response.raise_for_status()
                break  # Success, exit retry loop
            except (requests.RequestException, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Request failed (attempt {attempt+1}/{max_retries}): {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise  # Re-raise the last exception if all retries failed
        
        # Save a copy of the HTML for debugging
        debug_dir = Path("debug")
        debug_dir.mkdir(exist_ok=True)
        with open(debug_dir / f"last_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html", 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for indicators of availability using multiple methods
        sold_out_indicators = [
            "Sold Out",
            "sold out",
            "No rooms available",
            "Join the waiting list",
            "We're currently sold out",
            "waiting list"
        ]
        
        # Method 1: Check page text
        page_text = soup.get_text().lower()
        text_indicates_sold_out = any(indicator.lower() in page_text for indicator in sold_out_indicators)
        
         # Method 2: Look for specific HTML elements that indicate availability status
        availability_elements = soup.find_all(["button", "a", "div"], string=lambda text: text and any(indicator.lower() in text.lower() for indicator in sold_out_indicators))
        elements_indicate_sold_out = len(availability_elements) > 0
        
        # Method 3: Check for booking buttons or forms
        booking_elements = soup.find_all(["button", "a", "input"], string=lambda text: text and ("book" in text.lower() or "reserve" in text.lower() or "apply" in text.lower()))
        booking_available = len(booking_elements) > 0
        
        # Combine methods for a more robust check
        is_sold_out = text_indicates_sold_out or elements_indicate_sold_out
        
        # If booking elements are found, it's a strong indicator rooms might be available
        if booking_available and not is_sold_out:
            is_sold_out = False
        
        # Save current state
        current_state = {
            "last_check_time": datetime.now().isoformat(),
            "was_available": not is_sold_out
        }
        
        # Check if state changed from sold out to available
        state_changed = last_state.get("was_available", False) != (not is_sold_out)
        became_available = not is_sold_out and state_changed
        
        if not is_sold_out:
            # Rooms might be available!
            logging.info("ROOMS MAY BE AVAILABLE! Website no longer shows 'Sold Out'")
            
            # Only send notifications if state changed to avoid spam
            if became_available:
                # Send notification
                subject = "Nido Randwyck: Rooms May Be Available!"
                message = f"""
                Good news! The Nido Randwyck website no longer shows as 'Sold Out'.
                
                Rooms may now be available. Please check the website immediately:
                {URL}
                
                This notification was sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
                
                # Try multiple notification methods
                email_sent = send_email_notification(subject, message)
                
                # Send Telegram notification (best for phone notifications)
                telegram_message = f"""
                *Nido Randwyck: Rooms Available!*
                
                Good news! The Nido Randwyck website no longer shows as 'Sold Out'.
                
                Rooms may now be available. Check the website immediately:
                {URL}
                
                Notification sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
                telegram_sent = send_telegram_notification(telegram_message)
                
                # Create a desktop notification file
                notification_file = Path("ROOMS_AVAILABLE.txt")
                with open(notification_file, "w") as f:
                    f.write(f"Rooms may be available at Nido Randwyck as of {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}!\n")
                    f.write(f"Check the website immediately: {URL}\n")
                    f.write(f"Notification methods: Email {'✓' if email_sent else '✗'}, Telegram {'✓' if telegram_sent else '✗'}\n")
            
            save_last_state(current_state)
            return True
        else:
            logging.info("No rooms available yet. Website still shows as 'Sold Out'.")
            save_last_state(current_state)
            return False
            
    except Exception as e:
        logging.error(f"Error checking availability: {e}")
        # Don't update the last state on error to ensure we retry
        return False

def main():
    """Main function to run the scraper."""
    logging.info("Starting Nido Randwyck Room Availability Scraper")
    logging.info(f"Monitoring URL: {URL}")
    logging.info(f"Base check interval: {CHECK_INTERVAL} seconds (with ±{CHECK_INTERVAL_VARIATION*100}% variation)")
    
    if TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        logging.info("Telegram notifications are enabled")
    else:
        logging.info("Telegram notifications are disabled or not configured")
    
    if EMAIL_ENABLED:
        logging.info("Email notifications are enabled")
    else:
        logging.info("Email notifications are disabled")
    
    # Send a startup notification to verify everything is working
    if TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram_notification("*Nido Room Scraper Started*\n\nThe Nido Randwyck room availability scraper has started and is now monitoring for available rooms.")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    try:
        while True:
            try:
                logging.info("Checking for room availability...")
                rooms_available = check_availability()
                
                if rooms_available:
                    logging.info("Rooms appear to be available! Continuing to monitor for changes...")
                
                # Reset error counter on success
                consecutive_errors = 0
                
                # Add some randomness to the check interval to avoid detection
                variation = random.uniform(1 - CHECK_INTERVAL_VARIATION, 1 + CHECK_INTERVAL_VARIATION)
                actual_interval = int(CHECK_INTERVAL * variation)
                
                logging.info(f"Sleeping for {actual_interval} seconds before next check...")
                time.sleep(actual_interval)
                
            except Exception as e:
                consecutive_errors += 1
                logging.error(f"Error during check cycle: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logging.critical(f"Too many consecutive errors ({consecutive_errors}). Sending alert and continuing...")
                    
                    # Alert about repeated errors
                    if TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                        send_telegram_notification(f"*Nido Scraper Error Alert*\n\nThe scraper has encountered {consecutive_errors} consecutive errors. The last error was: {str(e)}\n\nThe scraper will continue running, but please check the logs.")
                    
                    # Reset counter after alerting
                    consecutive_errors = 0
                
                # Wait a shorter time before retrying after an error
                time.sleep(min(300, CHECK_INTERVAL / 2))
    
    except KeyboardInterrupt:
        logging.info("Scraper stopped by user.")
        if TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            send_telegram_notification("*Nido Room Scraper Stopped*\n\nThe Nido Randwyck room availability scraper has been stopped manually.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        if TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            send_telegram_notification(f"*Nido Room Scraper Crashed*\n\nThe Nido Randwyck room availability scraper has crashed with error: {str(e)}")
        
if __name__ == "__main__":
    main()