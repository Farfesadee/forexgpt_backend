import os
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_key:
    print("Error: SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
    exit(1)

supabase = create_client(supabase_url, supabase_key)

test_email = "test_verify_unique_123@example.com"
test_password = "SecurePassword123!"

def log(message):
    print(message)
    with open("diagnostic_results.txt", "a") as f:
        f.write(message + "\n")

# Clear old results
if os.path.exists("diagnostic_results.txt"):
    os.remove("diagnostic_results.txt")

log(f"Attempting to register test user: {test_email}")

try:
    # Attempt to sign up
    res = supabase.auth.sign_up({
        "email": test_email,
        "password": test_password,
        "options": {
            "email_redirect_to": "http://localhost:3000/auth/confirm"
        }
    })
    
    log("\nRegistration response:")
    log(f"User ID: {res.user.id if res.user else 'None'}")
    log(f"Email: {res.user.email if res.user else 'None'}")
    log(f"Session established: {res.session is not None}")
    
    if res.user:
        log("\nSUCCESS: User object returned. Check if email was sent.")
    else:
        log("\nFAILURE: No user object returned.")

except Exception as e:
    log("\nCaught Exception during sign_up:")
    log(f"Error type: {type(e).__name__}")
    log(f"Error message: {str(e)}")
    
    # Check for common Supabase SMTP errors
    err_str = str(e).lower()
    if "smtp" in err_str:
        log("\nDIAGNOSIS: Possible SMTP configuration issue in Supabase.")
    elif "rate limit" in err_str:
        log("\nDIAGNOSIS: Supabase email rate limit exceeded.")
    elif "already registered" in err_str:
        log("\nDIAGNOSIS: Email already in use. Try a different one.")
    else:
        log("\nDIAGNOSIS: Unknown registration error. Check Supabase Dashboard for logs.")
