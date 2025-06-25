import subprocess
import sys
import importlib.util
import os

REQUIRED_PACKAGES = [
    "telethon",
    "python-telegram-bot",  # ou autre version utilisée
]

def is_installed(package_name):
    return importlib.util.find_spec(package_name) is not None

def install_package(package):
    print(f"[📦] Installation de {package}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def install_dependencies():
    for package in REQUIRED_PACKAGES:
        pkg_name = package.split("==")[0] if "==" in package else package
        if not is_installed(pkg_name):
            install_package(package)

def run_main_script():
    print("[🚀] Lancement du bot...")
    os.system(f"{sys.executable} bot_v7.py")

if __name__ == "__main__":
    install_dependencies()
    run_main_script()
