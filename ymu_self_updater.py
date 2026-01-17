import os
import sys
import shutil
import logging
import requests
import time
import atexit

API_URL = "https://api.github.com/repos/tommylam120/YMU/releases/latest"


def get_appdata_dir():
    """Gets the path to the %APPDATA% directory."""
    return os.getenv("APPDATA")


def determine_paths():
    """
    Determines the correct paths for the YMU installation.
    It checks for the new AppData path first, then falls back to the old relative path.
    """
    appdata_path = get_appdata_dir()
    if not appdata_path:
        return {
            "log_dir": "./ymu",
            "log_file": "./ymu/ymu.log",
            "exe_path": "./ymu.exe",
            "backup_dir": "./_backup",
            "is_new_structure": False,
        }

    new_ymu_dir = os.path.join(appdata_path, "YMU")
    current_dir_exe = os.path.join(os.getcwd(), "ymu.exe")

    old_log_dir = "./ymu"

    if os.path.isdir(new_ymu_dir) and os.path.isfile(current_dir_exe):
        print("New directory structure detected.")
        return {
            "log_dir": new_ymu_dir,
            "log_file": os.path.join(new_ymu_dir, "ymu.log"),
            "exe_path": current_dir_exe,
            "backup_dir": os.path.join(os.getcwd(), "_backup"),
            "is_new_structure": True,
        }
    elif os.path.isdir(old_log_dir):
        print("Old directory structure detected.")
        return {
            "log_dir": old_log_dir,
            "log_file": os.path.join(old_log_dir, "ymu.log"),
            "exe_path": "./ymu.exe",
            "backup_dir": "./_backup",
            "is_new_structure": False,
        }
    else:
        print("No existing structure found. Assuming new installation.")
        return {
            "log_dir": new_ymu_dir,
            "log_file": os.path.join(new_ymu_dir, "ymu.log"),
            "exe_path": current_dir_exe,
            "backup_dir": os.path.join(os.getcwd(), "_backup"),
            "is_new_structure": True,
        }


PATHS = determine_paths()
os.makedirs(PATHS["log_dir"], exist_ok=True)

logging.basicConfig(
    filename=PATHS["log_file"],
    encoding="utf-8",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-8s] [YMU-SU] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def get_latest_release_info():
    """Fetches latest release info from the GitHub API."""
    try:
        log.info(f"Fetching release info from {API_URL}")
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        tag_name = data["tag_name"]
        asset_url = None
        for asset in data["assets"]:
            if asset["name"].lower() == "ymu.exe":
                asset_url = asset["browser_download_url"]
                break

        if not all([tag_name, asset_url]):
            raise ValueError("Could not find tag_name or asset_url in API response.")

        log.info(f"Latest YMU version: {tag_name}")
        return tag_name, asset_url
    except (requests.exceptions.RequestException, ValueError) as e:
        print(
            f"\nFailed to get the latest version from GitHub. Check your Internet connection.\nError: {e}"
        )
        log.exception("Failed to get latest release info.")
        sys.exit(1)


def display_banner():
    os.system("cls" if os.name == "nt" else "clear")
    print("\033[1;36;40m YMU Self-Updater\033[0m")
    print("\033[1;32;40m https://github.com/tommylam120/YMU\033[0m\n\n")


def wait_for_file_release(filepath, timeout=10):
    """Waits until the file is writable (process exited)."""
    log.info(f"Waiting for {filepath} to be released...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with open(filepath, "a+"):
                pass
            return True
        except PermissionError:
            time.sleep(0.5)
        except IOError as e:
            log.warning(f"Waiting for file release: {e}")
            time.sleep(0.5)

    return False


def perform_update(version_tag, download_url):
    """Handles the backup, download, and replacement of ymu.exe."""
    exe_path = PATHS["exe_path"]
    backup_dir = PATHS["backup_dir"]
    backup_exe_path = os.path.join(backup_dir, "ymu.exe")

    if not os.path.isfile(exe_path):
        print(
            f"\033[91mError: Main executable '{exe_path}' not found! Aborting.\033[0m"
        )
        log.error(f"Main executable '{exe_path}' not found. Cannot update.")
        time.sleep(3)
        return

    if not wait_for_file_release(exe_path):
        print("\033[91mError: Could not access ymu.exe. Is it still running?\033[0m")
        log.error("Timeout waiting for file release.")
        time.sleep(3)
        sys.exit(1)

    log.info(f"Backing up '{exe_path}' to '{backup_exe_path}'")
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(exe_path, backup_exe_path)

    try:
        log.info(f"Starting download from {download_url}")
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            downloaded_size = 0
            with open(exe_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = int((downloaded_size / total_size) * 100)
                        print(
                            f"\r  Downloading YMU {version_tag}: {progress} %",
                            end="",
                            flush=True,
                        )
        print("\n")
        log.info("Download finished successfully.")

    except (requests.exceptions.RequestException, IOError) as e:
        print(f"\n\033[91mDownload failed: {e}\033[0m")
        log.exception("Download failed. Reverting from backup.")

        if os.path.isfile(backup_exe_path):
            shutil.copy2(backup_exe_path, exe_path)
            log.info("Restored from backup.")
        else:
            log.critical("Backup file missing! Cannot restore.")

        sys.exit(1)

    log.info("Update successful. Cleaning up backup.")
    shutil.rmtree(backup_dir)

    print(f"\n\033[1;32;40mYMU has been successfully updated to {version_tag}.\033[0m")
    log.info(f"Update to {version_tag} complete. Launching new version.")
    input("Press Enter to start the new version...")
    os.execv(exe_path, [exe_path])


def on_interrupt():
    """Handles Ctrl+C to safely restore the backup."""
    print("\n\033[93mOperation canceled by user. Reverting changes...\033[0m")
    log.warning("Operation canceled by user.")
    backup_exe_path = os.path.join(PATHS["backup_dir"], "ymu.exe")
    if os.path.isfile(backup_exe_path):
        try:
            shutil.copy2(backup_exe_path, PATHS["exe_path"])
            shutil.rmtree(PATHS["backup_dir"])
            log.info("Successfully restored from backup.")
        except Exception as e:
            log.error(f"Failed to restore backup during interrupt: {e}")
    sys.exit(0)


def main():
    """Main execution flow."""
    log.info("--- YMU Self-Updater Initialized ---")
    atexit.register(lambda: log.info("--- YMU Self-Updater Shutting Down ---\n"))

    display_banner()
    version_tag, download_url = get_latest_release_info()

    try:
        perform_update(version_tag, download_url)
    except KeyboardInterrupt:
        on_interrupt()


if __name__ == "__main__":
    main()
