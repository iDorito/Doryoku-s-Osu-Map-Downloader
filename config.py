import platform
import os
from pathlib import Path

HOME_PATH = Path.home()

# Files
json_file = "db.json"
settings_file = "settings.json"

# Plataforma
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX  = platform.system() == 'Linux'
IS_MAC = platform.system() == "darwin"
IS_ANDROID = platform.system() == "Java"

if IS_WINDOWS:
    APPDATA = Path(os.environ["APPDATA"])
    DOWNLOAD_PATH = APPDATA / "domd" / "downloads"
    DB_JSON = APPDATA / "domd"                  # Solo la carpeta
    LASER_FILES_PATH = APPDATA / "osu" / "files"
    SETTINGS_FILE_PATH = APPDATA / "domd"
elif IS_LINUX:
    # Linux paths
    DOWNLOAD_PATH = HOME_PATH / "Downloads"
    DB_JSON = HOME_PATH / ".local" / "share" / "domd"
    LASER_FILES_PATH = HOME_PATH / ".local" / "share" / "osu" / "files"
    SETTINGS_FILE_PATH = HOME_PATH / ".local" / "share" / "domd"
elif IS_MAC:
    # macOS paths
    DOWNLOAD_PATH = HOME_PATH / "Downloads"
    DB_JSON = HOME_PATH / "Library" / "Application Support" / "domd"
    LASER_FILES_PATH = HOME_PATH / "Library" / "Application Support" / "osu" / "files"
    SETTINGS_FILE_PATH = HOME_PATH / "Library" / "Application Support" / "domd"
elif IS_ANDROID:
    # Android (termux / Android filesystem)
    DOWNLOAD_PATH = HOME_PATH / "Downloads"
    DB_JSON = HOME_PATH / ".domd"
    LASER_FILES_PATH = Path("/storage/emulated/0/Android/data/sh.ppy.osulazer/files")
    SETTINGS_FILE_PATH = HOME_PATH / ".domd"
# else:
    # Fallback
    # DOWNLOAD_PATH = HOME_PATH / "Downloads"
    # DB_JSON = HOME_PATH / ".local" / "share" / "domd" / "db.json"
    # LASER_FILES_PATH = None
