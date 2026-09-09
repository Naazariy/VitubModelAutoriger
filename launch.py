import os
import sys
import subprocess

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, "venv", "Scripts", "python.exe")
    
    if os.path.exists(venv_python):
        python_cmd = venv_python
    else:
        python_cmd = sys.executable

    main_py = os.path.join(script_dir, "main.py")
    print("=" * 60)
    print("  Live2D Geometry Deformation Prototype Launcher")
    print("=" * 60)
    print(f"[Launcher] Using Python interpreter: {python_cmd}")
    print(f"[Launcher] Starting {main_py}...\n")
    
    result = subprocess.run([python_cmd, main_py])
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
