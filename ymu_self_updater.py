import os
import sys
import shutil
import logging
import requests
import time
import atexit
import tempfile
import subprocess

# 尝试导入 psutil，如果失败则提供备用方案
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("Warning: psutil module not found. Process management features will be limited.")
    print("Install with: pip install psutil")

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


def safe_input(prompt=""):
    """
    安全的输入函数，处理stdin可能被关闭的情况。
    对于更新器，我们显示提示后自动继续。
    """
    try:
        # 显示提示
        if prompt:
            print(prompt)
        
        # 检查stdin是否可用且是交互式终端
        stdin_available = (sys.stdin and 
                          hasattr(sys.stdin, 'isatty') and 
                          sys.stdin.isatty())
        
        # 检查stdout是否可用
        stdout_available = (sys.stdout and 
                           hasattr(sys.stdout, 'isatty') and 
                           sys.stdout.isatty())
        
        # 如果stdin/stdout都可用，尝试真正的input
        if stdin_available and stdout_available:
            try:
                return input()
            except (RuntimeError, EOFError, IOError, OSError) as e:
                log.debug(f"Standard input failed: {e}")
                # 继续使用备用方案
                pass
        
        # 备用方案：显示倒计时并自动继续
        countdown = 5
        print(f"(Auto-continuing in {countdown} seconds...)")
        for i in range(countdown, 0, -1):
            print(f"\r{i}...", end="", flush=True)
            time.sleep(1)
        print("\rContinuing...")
        return ""
        
    except Exception as e:
        log.warning(f"Input handling failed: {e}")
        # 终极备用：直接等待
        time.sleep(5)
        return ""


def cleanup_temp():
    """
    清理PyInstaller创建的临时目录。
    """
    try:
        # 清理PyInstaller的临时目录
        if hasattr(sys, '_MEIPASS'):
            temp_dir = sys._MEIPASS
            if os.path.exists(temp_dir):
                log.info(f"Attempting to cleanup PyInstaller temp directory: {temp_dir}")
                for attempt in range(3):
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        if not os.path.exists(temp_dir):
                            log.info(f"Cleaned up temporary directory: {temp_dir}")
                            break
                        time.sleep(0.5)
                    except Exception as e:
                        log.debug(f"Cleanup attempt {attempt + 1} failed: {e}")
        
        # 清理当前用户临时目录中以_MEI开头的目录
        temp_base = tempfile.gettempdir()
        try:
            for item in os.listdir(temp_base):
                if item.startswith("_MEI") and os.path.isdir(os.path.join(temp_base, item)):
                    temp_path = os.path.join(temp_base, item)
                    # 尝试删除，忽略错误
                    try:
                        shutil.rmtree(temp_path, ignore_errors=True)
                        log.debug(f"Cleaned up orphaned temp directory: {temp_path}")
                    except Exception:
                        pass
        except Exception as e:
            log.debug(f"Could not scan temp directory: {e}")
            
    except Exception as e:
        log.warning(f"Failed to cleanup temp directory: {e}")


def kill_ymu_process():
    """终止所有正在运行的ymu.exe进程"""
    if not HAS_PSUTIL:
        log.warning("psutil not available, cannot terminate processes")
        return False
    
    killed = False
    try:
        current_pid = os.getpid()
        
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                # 跳过当前进程
                if proc.pid == current_pid:
                    continue
                    
                proc_name = proc.info['name']
                proc_exe = proc.info['exe']
                
                # 检查是否是ymu.exe
                is_ymu = False
                if proc_name and 'ymu.exe' in proc_name.lower():
                    is_ymu = True
                elif proc_exe and 'ymu.exe' in proc_exe.lower():
                    is_ymu = True
                
                if is_ymu:
                    log.info(f"Found ymu.exe process (PID: {proc.pid}), terminating...")
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                        log.info(f"Successfully terminated ymu.exe (PID: {proc.pid})")
                        killed = True
                    except psutil.TimeoutExpired:
                        log.warning(f"Process {proc.pid} did not terminate, forcing kill...")
                        proc.kill()
                        killed = True
                    except psutil.NoSuchProcess:
                        pass  # 进程已经结束
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
                
    except Exception as e:
        log.error(f"Error while terminating processes: {e}")
    
    if killed:
        time.sleep(1)  # 给系统一点时间释放文件锁
    
    return killed


def is_file_locked(filepath):
    """检查文件是否被其他进程锁定"""
    if not HAS_PSUTIL:
        # 如果没有psutil，使用简单的文件访问测试
        try:
            with open(filepath, "a+"):
                pass
            return False
        except (PermissionError, IOError):
            return True
    
    try:
        if not os.path.exists(filepath):
            return False
            
        # 使用psutil检查
        for proc in psutil.process_iter(['pid']):
            try:
                open_files = proc.open_files()
                if open_files:
                    for open_file in open_files:
                        if filepath.lower() == open_file.path.lower():
                            log.info(f"File {filepath} is locked by process {proc.pid}")
                            return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        log.debug(f"Error checking file lock: {e}")
    
    return False


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
        safe_input("Press Enter to exit...")
        sys.exit(1)


def display_banner():
    """显示程序横幅"""
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except:
        pass  # 如果清屏失败，继续执行
    
    print("\033[1;36;40m YMU Self-Updater\033[0m")
    print("\033[1;32;40m https://github.com/tommylam120/YMU\033[0m")
    print("-" * 50)
    print()


def wait_for_file_release(filepath, timeout=15):
    """Waits until the file is writable (process exited)."""
    log.info(f"Waiting for {filepath} to be released...")
    
    # 首先终止可能占用文件的进程
    kill_ymu_process()
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # 检查文件锁
        if is_file_locked(filepath):
            # 如果有锁，尝试终止进程
            kill_ymu_process()
            time.sleep(1)
            continue
        
        # 尝试访问文件
        try:
            # 测试读取
            with open(filepath, "rb") as f:
                f.read(1)
            
            # 测试写入
            test_time = str(time.time()).encode()
            with open(filepath, "r+b") as f:
                pos = f.tell()
                f.write(test_time)
                f.seek(pos)
                f.write(test_time)
            
            log.info(f"File {filepath} is now accessible")
            return True
            
        except (PermissionError, IOError) as e:
            # 等待重试
            time.sleep(0.5)
        except Exception as e:
            log.debug(f"Unexpected error while testing file: {e}")
            time.sleep(0.5)
    
    log.error(f"Timeout waiting for file release after {timeout} seconds")
    return False


def perform_update(version_tag, download_url):
    """Handles the backup, download, and replacement of ymu.exe."""
    exe_path = PATHS["exe_path"]
    backup_dir = PATHS["backup_dir"]
    backup_exe_path = os.path.join(backup_dir, "ymu.exe")

    if not os.path.isfile(exe_path):
        print(f"\033[91mError: Main executable '{exe_path}' not found! Aborting.\033[0m")
        log.error(f"Main executable '{exe_path}' not found. Cannot update.")
        time.sleep(3)
        return

    if not wait_for_file_release(exe_path):
        print("\033[91mError: Could not access ymu.exe. Is it still running?\033[0m")
        print("\033[93mTry closing any open YMU windows and run the updater again.\033[0m")
        log.error("Timeout waiting for file release.")
        safe_input("Press Enter to exit...")
        sys.exit(1)

    log.info(f"Backing up '{exe_path}' to '{backup_exe_path}'")
    os.makedirs(backup_dir, exist_ok=True)
    
    try:
        shutil.copy2(exe_path, backup_exe_path)
        log.info("Backup created successfully")
    except Exception as e:
        print(f"\033[91mError creating backup: {e}\033[0m")
        log.exception("Failed to create backup")
        safe_input("Press Enter to exit...")
        sys.exit(1)

    try:
        log.info(f"Starting download from {download_url}")
        print(f"\nDownloading YMU {version_tag}...")
        
        with requests.get(download_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            downloaded_size = 0
            start_time = time.time()
            
            with open(exe_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # 显示进度（每10%或每秒更新一次）
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            current_time = time.time()
                            if current_time - start_time >= 1 or progress >= 100:
                                print(f"\r  Progress: {progress:.1f}% ({downloaded_size / 1024 / 1024:.1f} MB)", 
                                      end="", flush=True)
                                start_time = current_time
        
        print("\n\033[92mDownload completed successfully!\033[0m")
        log.info("Download finished successfully.")

    except (requests.exceptions.RequestException, IOError) as e:
        print(f"\n\033[91mDownload failed: {e}\033[0m")
        log.exception("Download failed. Reverting from backup.")

        if os.path.isfile(backup_exe_path):
            try:
                print("Restoring original executable...")
                shutil.copy2(backup_exe_path, exe_path)
                log.info("Restored from backup.")
                print("\033[92mRestored original executable from backup.\033[0m")
            except Exception as restore_error:
                log.error(f"Failed to restore from backup: {restore_error}")
                print(f"\033[91mFailed to restore from backup: {restore_error}\033[0m")
        else:
            log.critical("Backup file missing! Cannot restore.")
            print("\033[91mBackup file missing! Cannot restore.\033[0m")

        safe_input("Press Enter to exit...")
        sys.exit(1)

    # 清理备份目录
    try:
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)
            log.info("Cleaned up backup directory.")
    except Exception as e:
        log.warning(f"Could not clean up backup directory: {e}")

    print(f"\n\033[1;32;40m✓ YMU has been successfully updated to {version_tag}\033[0m")
    log.info(f"Update to {version_tag} complete. Launching new version.")
    
    # 启动新版本前做最后的清理
    cleanup_temp()
    
    print("\nLaunching new version...")
    time.sleep(2)
    
    # 使用subprocess启动新进程
    try:
        # 尝试以管理员权限运行（如果需要）
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        
        subprocess.Popen([exe_path], 
                        close_fds=True,
                        startupinfo=startupinfo)
        
        log.info("Launched new version of ymu.exe")
        print("\033[92m✓ New version launched successfully\033[0m")
        
        # 等待新进程启动
        time.sleep(3)
        
    except Exception as e:
        log.error(f"Failed to launch new version: {e}")
        print(f"\033[91mFailed to launch new version: {e}\033[0m")
        print(f"\033[93mYou can manually run: {exe_path}\033[0m")
        safe_input("Press Enter to exit...")


def on_interrupt():
    """Handles Ctrl+C to safely restore the backup."""
    print("\n\033[93mOperation canceled by user. Reverting changes...\033[0m")
    log.warning("Operation canceled by user.")
    
    # 清理临时目录
    cleanup_temp()
    
    backup_exe_path = os.path.join(PATHS["backup_dir"], "ymu.exe")
    if os.path.isfile(backup_exe_path):
        try:
            print("Restoring original executable...")
            shutil.copy2(backup_exe_path, PATHS["exe_path"])
            log.info("Successfully restored from backup.")
            print("\033[92m✓ Successfully restored original executable\033[0m")
        except Exception as e:
            log.error(f"Failed to restore backup during interrupt: {e}")
            print(f"\033[91mFailed to restore backup: {e}\033[0m")
    
    # 清理备份目录
    try:
        if os.path.exists(PATHS["backup_dir"]):
            shutil.rmtree(PATHS["backup_dir"], ignore_errors=True)
            log.debug("Cleaned up backup directory")
    except Exception as e:
        log.warning(f"Could not clean up backup directory: {e}")
    
    # 等待用户确认
    safe_input("Press Enter to exit...")
    sys.exit(0)


def main():
    """Main execution flow."""
    log.info("--- YMU Self-Updater Initialized ---")
    
    # 注册退出时的清理函数
    atexit.register(lambda: log.info("--- YMU Self-Updater Shutting Down ---"))
    atexit.register(cleanup_temp)
    
    # 显示横幅
    display_banner()
    
    # 获取最新版本信息
    try:
        version_tag, download_url = get_latest_release_info()
    except Exception as e:
        log.error(f"Failed to get release info: {e}")
        print(f"\033[91mFailed to check for updates: {e}\033[0m")
        safe_input("Press Enter to exit...")
        sys.exit(1)
    
    # 显示当前版本和最新版本
    print(f"Current directory: {os.getcwd()}")
    print(f"Target executable: {PATHS['exe_path']}")
    print(f"Latest version available: {version_tag}")
    print("-" * 50)
    
    try:
        # 执行更新
        perform_update(version_tag, download_url)
        
    except KeyboardInterrupt:
        on_interrupt()
        
    except Exception as e:
        log.exception("Unexpected error during update")
        print(f"\n\033[91m✗ An unexpected error occurred:\033[0m")
        print(f"\033[93m{e}\033[0m")
        print("\n\033[93mCheck the log file for details:\033[0m")
        print(f"\033[93m{PATHS['log_file']}\033[0m")
        
        # 确保临时目录被清理
        cleanup_temp()
        
        safe_input("\nPress Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    # 设置异常处理
    sys.excepthook = lambda exc_type, exc_value, exc_traceback: None
    
    # 运行主程序
    try:
        main()
    except SystemExit:
        pass  # 正常退出
    except:
        # 最后的异常处理
        print("\n\033[91mA critical error occurred. The updater will now exit.\033[0m")
        time.sleep(3)