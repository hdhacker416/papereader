import subprocess
import os
import sys
import time
import importlib.util

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
BACKEND_REQUIREMENTS = os.path.join(BACKEND_DIR, "requirements.txt")


def has_module(module_name):
    return importlib.util.find_spec(module_name) is not None


def check_backend_dependencies():
    required_modules = ["fastapi", "uvicorn", "sqlalchemy"]
    missing = [module for module in required_modules if not has_module(module)]
    if not missing:
        return True

    print("Error: backend Python dependencies are missing.")
    print(f"Missing modules: {', '.join(missing)}")
    print(
        f"Install them with: {sys.executable} -m pip install -r {BACKEND_REQUIREMENTS}"
    )
    return False


def ensure_frontend_executables():
    vite_bin = os.path.join(FRONTEND_DIR, "node_modules", ".bin", "vite")
    if not os.path.exists(vite_bin):
        return True

    if os.name != "nt" and not os.access(vite_bin, os.X_OK):
        try:
            current_mode = os.stat(vite_bin).st_mode
            os.chmod(vite_bin, current_mode | 0o111)
            print(f"Fixed execute permission for {vite_bin}")
        except OSError as exc:
            print(f"Failed to fix frontend executable permissions: {exc}")
            print("Try running: chmod +x frontend/node_modules/.bin/vite")
            return False

    return True

def start_services():
    # 0. Check Environment Variables
    if not os.environ.get("GEMINI_API_KEY"):
        # Try loading from .env file manually if python-dotenv is not yet loaded
        env_path = os.path.join(BACKEND_DIR, ".env")
        if os.path.exists(env_path):
            print(f"Loading environment variables from {env_path}")
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()
        
        if not os.environ.get("GEMINI_API_KEY"):
             print("Error: GEMINI_API_KEY environment variable is not set.")
             print("Please set it in your environment or create a .env file in the backend directory.")
             # We don't exit here, we just warn, so frontend can still start
             # return 

    if not check_backend_dependencies():
        return

    processes = []
    
    print(f"Starting Backend in {BACKEND_DIR}...")
    # Use python executable to run uvicorn
    backend_cmd = [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
    
    # Start backend process
    # shell=True is generally not recommended but sometimes needed on Windows if PATH is tricky, 
    # but for sys.executable it should be fine without shell=True.
    try:
        backend_proc = subprocess.Popen(backend_cmd, cwd=BACKEND_DIR)
        processes.append(backend_proc)
    except Exception as e:
        print(f"Failed to start backend: {e}")
        return

    print(f"Starting Frontend in {FRONTEND_DIR}...")
    # On Windows, npm is npm.cmd
    npm_cmd = "npm.cmd" if os.name == 'nt' else "npm"
    
    # Check if node_modules exists
    if not os.path.exists(os.path.join(FRONTEND_DIR, "node_modules")):
        print("node_modules not found. Running npm install...")
        try:
            subprocess.run([npm_cmd, "install"], cwd=FRONTEND_DIR, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to install frontend dependencies: {e}")
            backend_proc.terminate()
            return

    if not ensure_frontend_executables():
        backend_proc.terminate()
        return
            
    frontend_cmd = [npm_cmd, "run", "dev"]
    
    try:
        frontend_proc = subprocess.Popen(frontend_cmd, cwd=FRONTEND_DIR)
        processes.append(frontend_proc)
    except Exception as e:
        print(f"Failed to start frontend: {e}")
        # Cleanup backend if frontend fails
        backend_proc.terminate()
        return
    
    print("Services started. Press Ctrl+C to stop.")
    print(f"Backend: http://localhost:8000")
    print(f"Frontend: http://localhost:5173") # Vite default
    
    try:
        # Keep main process alive and monitor children
        while True:
            time.sleep(1)
            # Check if processes are still alive
            if backend_proc.poll() is not None:
                print("Backend process ended unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend process ended unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        print("Terminating processes...")
        for p in processes:
            if p.poll() is None:
                # Try terminate first
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    print("Force killing process...")
                    p.kill()
        print("All services stopped.")

if __name__ == "__main__":
    start_services()
