#!/usr/bin/env python # 
"""\
Main controller for the Osu Map Downloader.

By: Ricardo Faria
Osu User: Doryoku

Usage: run the script in cmd/terminal: python get_existing_ids_lazer.py
"""

# ----------------------------------------------------------------------
# Standard libraries
from concurrent.futures import thread
import socket
import os
import subprocess
import sys
from urllib.parse import urlencode
import webbrowser
from pathlib import Path
# ----------------------------------------------------------------------
# 3rd party libraries
import requests
import json
import PyQt6.QtCore as QtCore
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtWidgets import QLabel, QComboBox, QTextEdit, QLineEdit, QHBoxLayout, QDateEdit
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop
# ----------------------------------------------------------------------
import config
# ----------------------------------------------------------------------
# VARIABLES
# ----------------------------------------------------------------------
ACCESS_TOKEN = ""
CLIENT_ID = '46676'
CLIENT_SECRET = '7qRBCgwTQDEMTe0DiZ5Tb9QgpYt0lzEAIJ0fqXrC'
REDIRECT_URL = 'http://localhost:8080'
PORT = 8080
# ----------------------------------------------------------------------
# DIRS
DOWNLOAD_PATH = config.DOWNLOAD_PATH
OSU_EXECUTABLE = None
DB_JSON_DIR = config.DB_JSON 
DB_JSON = DB_JSON_DIR / "db.json"
LASER_FILES_PATH = config.LASER_FILES_PATH

print(DOWNLOAD_PATH)
print(DB_JSON_DIR)
print(LASER_FILES_PATH)

# Create if dont exist
DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
LASER_FILES_PATH.mkdir(parents=True, exist_ok=True)
DB_JSON_DIR.mkdir(parents=True, exist_ok=True)   # Crea la carpeta domd


# ---------------------
# --- BEATMAPSET MIRRORS ---
CHIMU="https://api.chimu.moe/v1/download/{set_id}?n=1"
SAYO_BOT="https://dl.sayobot.cn/beatmaps/download/full/{set_id}"
NERINYAN="https://api.nerinyan.moe/d/{set_id}"

# ----------------------------------------------------------------------
class OsuLoginWorker(QThread):
    on_token_obtained_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)

    def run(self):
        self.log_signal.emit("Logging in Osu and obtaining token.")

        # Auth URL for app code
        auth_url = 'https://osu.ppy.sh/oauth/authorize?' + urlencode({
            'client_id': CLIENT_ID,
            'REDIRECT_URL': REDIRECT_URL,
            'response_type': 'code',
            'scope': 'public'
        })

        # Open the browser for authentication
        self.log_signal.emit("Opening browser...")
        # webbrowser.open(auth_url)

        self.open_navigator(auth_url)

        # Opening a server to listen for responde. 127.0.0.1:8080
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('localhost', PORT))
        server.listen(1)

        self.log_signal.emit(f"Waiting callback for {REDIRECT_URL}...")
        client, addr = server.accept() # Wait until server response

        # Read response and format/decode to utf
        request = client.recv(1024).decode('utf-8')

        # Change browser status and notifying success
        http_response = "HTTP/1.1 200 OK\r\n\r\nSuccess! You can now close this window."
        client.send(http_response.encode('utf-8'))
        client.close()
        server.close()

        # Extract code
        try:
            url_line = request.splitlines()[0] # First line of the json response
            code = url_line.split('code=')[1].split(' ')[0] # Finding the code= keyword and splitting the coe
        except IndexError:
            print("Error: Code not received.")
            return None

        # Now trade  the code for the authorization token
        token_url = 'https://osu.ppy.sh/oauth/token'
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'REDIRECT_URL': REDIRECT_URL
        }

        # Send the post call and wait for the access token
        response = requests.post(token_url, data=data)
        if response.status_code == 200:
            token_info = response.json()
            access_token = token_info['access_token']

            # send the signal and the token
            self.on_token_obtained_signal.emit(access_token)
        else:
            self.log_signal.emit(f"Error trading for token: {response.text}")
            return None
        
    def open_navigator(self, url):
        if sys.platform == 'linux':
            # 1. Hacemos una copia del entorno actual
            env = os.environ.copy()
            
            # 2. ELIMINAMOS la variable problemática que pone PyInstaller
            # Esto hace que el subproceso busque librerías en el sistema, no en el .exe
            if 'LD_LIBRARY_PATH' in env:
                del env['LD_LIBRARY_PATH']
                
            # 3. Lanzamos el navegador manualmente con el entorno limpio
            # xdg-open es el comando estándar en Linux para abrir la app default
            subprocess.Popen(['xdg-open', url], env=env)
        else:
            # En Windows/Mac no suele dar este problema
            webbrowser.open(url)

class DownloadWorker(QThread):
    log_signal = pyqtSignal(str)
    downloaded_map_signal = pyqtSignal(str)
    downloads_finished_signal = pyqtSignal()

    def __init__(self, download_urls):
        super().__init__()
        self.download_urls = download_urls

    def run(self):
        for set_id, download_url in self.download_urls.items():
            self.log_signal.emit(f"Downloading from: {download_url}")
            
            try:
                download_response = requests.get(download_url, allow_redirects=True)
                if download_response.status_code == 200:
                    # Save to ./maps/set_id.osz
                    filename = os.path.join(DOWNLOAD_PATH, f"{set_id}.osz")
                    with open(filename, 'wb') as f:
                        f.write(download_response.content)

                    # Open in Osu
                    self.downloaded_map_signal.emit(filename)

                    self.log_signal.emit(f"Downloaded and saved as: {set_id}")
                else:
                    self.log_signal.emit(f"Failed to download from {download_url}: Status code {download_response.status_code}")
            except Exception as e:
                print(f"Exception occurred while downloading from {download_url}: {e}")

class BeatmatsetIdsWorker(QThread):
    log_signal = pyqtSignal(str)
    fetched_signal = pyqtSignal()
    finished_signal = pyqtSignal(list)

    def __init__(self, this_params):
        super().__init__()
        self.call_params = this_params
        self.dest_list = [] 
        self.current_page = 1

        

    def run(self):
        # Set to detect duplicates
        session_ids = set()
        cursor = None

        self.log_signal.emit("Starting beatmapset ids worker...")
        self.log_signal.emit(f"Working with params: {self.call_params}")

        while True:
            # Copy params so cursor doesnt repeat
            current_params = self.call_params.copy()

            # after the 2nd run, if cursor exists, it should copy the params
            if cursor:
                for key, value in cursor.items():
                    current_params[f"cursor[{key}]"] = value
            
            # Call for beatmapset ids from OSU API
            try:
                self.response = requests.get(
                    "https://osu.ppy.sh/api/v2/beatmapsets/search",
                    headers={
                        "Authorization": f"Bearer {ACCESS_TOKEN}",
                        "Accept": "application/json"
                    },
                    params=current_params
                )

                # if good response
                if self.response.status_code != 200:
                    self.log_signal.emit(f"Error API: {self.response.status_code} - {self.response.text}")
                    break
                
                # converting to JSON
                data = self.response.json()
                self.beatmapsets = data.get('beatmapsets', [])
                

                if not self.beatmapsets:
                    self.log_signal.emit("Nothing was found.")
                    break
                
                # Check for repeated list
                first_id = int(self.beatmapsets[0]['id'])
                
                if first_id in session_ids:
                    self.log_signal.emit(f"⚠️ STOPPED: Api returned the page {self.current_page} - repeated.")
                    break
                
                # Process ids
                new_beatmapset_ids_in_page = 0
                for beatmapset in self.beatmapsets:
                    b_id = int(beatmapset['id']) # Secure the id is taken as an int

                    # History to avoid repeated or infinite loops
                    session_ids.add(b_id)

                    # Adding to the final list to return
                    if b_id not in self.dest_list:
                        self.dest_list.append(b_id)
                        new_beatmapset_ids_in_page += 1

                self.log_signal.emit(f"Page {self.current_page}: Received {len(self.beatmapsets)}. New Ids: {new_beatmapset_ids_in_page}. Total: {len(self.dest_list)}")

                # Update cursor for next run
                cursor = data.get('cursor')
                self.current_page += 1
                if not cursor:
                    self.log_signal.emit("End of results (Cursor empty).")
                    break
                    
            except Exception as e:
                print(f"Critic exception in the thread: {e}")
                break
        
        # While ended, emit signal with list
        self.log_signal.emit(f"Search finished, total beatmatset ids found: {len(self.dest_list)}")
        self.finished_signal.emit(self.dest_list)

class StarRatingFilterWidget(QWidget):
    def __init__(self):
        super().__init__()

        # Layout
        self.layout = QHBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        # Stars label
        self.stars_label = QLabel()
        self.stars_label.setText("Stars: ")
        self.stars_label.setFixedWidth(40)
        self.layout.addWidget(self.stars_label)

        # Beatmap difficulty
        self.difficulty_label = QLineEdit()
        self.difficulty_label.setPlaceholderText("(e.g., 8)")
        self.difficulty_label.setFixedWidth(50)
        self.layout.addWidget(self.difficulty_label)
        
        # Boolean check buttons
        self.higher_than_check_button = QPushButton()
        self.higher_than_check_button.setText(">")
        self.higher_than_check_button.setCheckable(True)
        self.higher_than_check_button.setFixedWidth(30)
        self.higher_than_check_button.clicked.connect(lambda: self.on_diff_button_click(1))
        self.layout.addWidget(self.higher_than_check_button)

        self.equals_check_button = QPushButton()
        self.equals_check_button.setText("=")
        self.equals_check_button.setCheckable(True)
        self.equals_check_button.setFixedWidth(30)
        self.equals_check_button.clicked.connect(lambda: self.on_diff_button_click(2))
        self.layout.addWidget(self.equals_check_button)

        self.less_than_check_button = QPushButton()
        self.less_than_check_button.setText("<")
        self.less_than_check_button.setCheckable(True)
        self.less_than_check_button.setFixedWidth(30)
        self.less_than_check_button.clicked.connect(lambda: self.on_diff_button_click(3))
        self.layout.addWidget(self.less_than_check_button)

        self.setLayout(self.layout)
    
    def on_diff_button_click(self, button_type):
        """
        Handles the difficulty filter buttons
        
        if one is clicked, the others are unclicked
        1 = higher than
        2 = equals
        3 = less than
        """
        
        if button_type == 1:
            self.higher_than_check_button.setEnabled(False)
            self.equals_check_button.setEnabled(True)
            self.less_than_check_button.setEnabled(True)
        elif button_type == 2:
            self.higher_than_check_button.setEnabled(True)
            self.equals_check_button.setEnabled(False)
            self.less_than_check_button.setEnabled(True)
        elif button_type == 3:
            self.higher_than_check_button.setEnabled(True)
            self.equals_check_button.setEnabled(True)
            self.less_than_check_button.setEnabled(False)

class DateFilterWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = QHBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        self.date_filter_label = QLabel()
        self.date_filter_label.setText("Date:")
        self.date_filter_label.setFixedWidth(40)
        self.layout.addWidget(self.date_filter_label)

        self.date_filter = QDateEdit()
        self.date_filter.setDate(QtCore.QDate.currentDate())
        self.date_filter.setDisplayFormat("dd-MM-yyyy")
        self.date_filter.setCalendarPopup(True)
        self.layout.addWidget(self.date_filter)

        self.date_filter_since_button = QPushButton()
        self.date_filter_since_button.setText(">=")
        self.date_filter_since_button.setFixedWidth(60)
        self.date_filter_since_button.setCheckable(True)
        self.date_filter_since_button.clicked.connect(lambda: self.on_date_filter_button_click(1))
        self.layout.addWidget(self.date_filter_since_button)

        self.date_filter_until_button = QPushButton()
        self.date_filter_until_button.setText("<=")
        self.date_filter_until_button.setFixedWidth(60)
        self.date_filter_until_button.setCheckable(True)
        self.date_filter_until_button.clicked.connect(lambda: self.on_date_filter_button_click(2))
        self.layout.addWidget(self.date_filter_until_button)

        self.setLayout(self.layout)

    def on_date_filter_button_click(self, button_type):
        """
        Handles the date filter buttons
        
        if one is clicked, the other is unclicked
        1 = since
        2 = until
        """
        
        if button_type == 1:
            self.date_filter_since_button.setEnabled(False)
            self.date_filter_until_button.setEnabled(True)

            # Re enable check for <= button
            self.date_filter_until_button.setChecked(False)
        elif button_type == 2:
            self.date_filter_since_button.setEnabled(True)
            self.date_filter_until_button.setEnabled(False)

            # Re enable check for >= button
            self.date_filter_since_button.setChecked(False)

class CheckableComboBox(QComboBox):
    def __init__(self):
        super().__init__()

        # Making it editable by the script but not by the user
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)

        # Qstardard item boxes for a checkable item
        self.model = QStandardItemModel(self)
        self.setModel(self.model)

        # Event for QComboBox view click
        self.view().pressed.connect(self.handle_item_pressed)

        # First line
        self.lineEdit().setPlaceholderText("Select Mode")

    def handle_item_pressed(self, index):
        item = self.model.itemFromIndex(index)

        item.setCheckState(not item.checkState())

        self.update_display_text()

    def update_display_text(self):
        # Selected items
        self.selected_items = []

        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                self.selected_items.append(item.text())


    def addItem(self, text, data=None):
        item = QStandardItem(text)
        item.setData(data)
        item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(QtCore.Qt.CheckState.Unchecked)
        self.model.appendRow(item)

    def get_checked_items(self):
        """Returns a list with the text of the selected items"""
        checked_items = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                checked_items.append(item.text())
        return checked_items
    
    def get_checked_data(self):
        """Return an array of the selected items"""
        checked_data = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                checked_data.append(item.data())
        return checked_data

# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Window settings
        self.setWindowTitle("Doryoku's Map Downloader")
        self.setGeometry(100, 100, 600, 400)
        self.setMinimumSize(400, 600)
        self.setMaximumSize(800, 600)

        # Main layout
        self.main_layout = QVBoxLayout()

        # ------------------------------------------------------
        # Main controls section
        # ------------------------------------------------------
        # Layout
        self.controls_layout = QHBoxLayout()

        # Token button
        self.token_button = QPushButton()
        self.token_button.setText("Get Token")
        self.token_button.setFixedWidth(100)
        self.token_button.clicked.connect(self.startLogin)
        self.controls_layout.addWidget(self.token_button)

        # Download Mirror dropdown
        self.mirror_label = QLabel()
        self.mirror_label.setText("Select Mirror:")
        self.mirror_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.controls_layout.addWidget(self.mirror_label)

        self.mirror_dropdown = QComboBox()
        self.mirror_dropdown.setFixedWidth(150)
        self.mirror_dropdown.addItem("Chimu")
        self.mirror_dropdown.addItem("SayoBot")
        self.mirror_dropdown.addItem("Nerinyan")
        self.controls_layout.addWidget(self.mirror_dropdown)

        # Osu exe/app image selection
        self.select_osu_executable = QLabel()
        self.select_osu_executable.setText("Select Osu Executable:")
        self.controls_layout.addWidget(self.select_osu_executable)

        self.select_osu_executable_button = QPushButton("Browse")
        self.select_osu_executable_button.clicked.connect(self.browse_osu_executable)
        self.controls_layout.addWidget(self.select_osu_executable_button)

        self.main_layout.addLayout(self.controls_layout)
        # ------------------------------------------------------
        # Beatmap filters section
        # ------------------------------------------------------

        # ------------------------------------------------------
        # Star rating filter
        self.star_rating_layout = QHBoxLayout()
        self.star_rating_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        # + button to add extra star rating filter (put first, left-aligned)
        self.extra_star_rating_info = QPushButton()
        self.extra_star_rating_info.setText("+")
        self.extra_star_rating_info.setFixedWidth(30)
        self.extra_star_rating_info.setCheckable(True)
        self.star_rating_layout.addWidget(self.extra_star_rating_info)

        # First star rating filter
        self.star_rating_filter_1 = StarRatingFilterWidget()
        self.star_rating_layout.addWidget(self.star_rating_filter_1)

        # Second star rating filter (hidden by default)
        self.star_rating_filter_2 = StarRatingFilterWidget()
        self.star_rating_filter_2.setVisible(False)
        self.star_rating_layout.addWidget(self.star_rating_filter_2)

        # The lambda toggles the visibility of the second filter
        self.extra_star_rating_info.clicked.connect(
            lambda: self.star_rating_filter_2.setVisible(not self.star_rating_filter_2.isVisible())
        )

        # Add to main layout
        self.main_layout.addLayout(self.star_rating_layout)

        # ------------------------------------------------------
        # Date filter
        self.date_filter_layout = QHBoxLayout()
        self.date_filter_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        # Extra date filter
        # + button to add extra date filter (put first, left-aligned)
        self.date_filter_extra_button = QPushButton()
        self.date_filter_extra_button.setText("+")
        self.date_filter_extra_button.setFixedWidth(30)
        self.date_filter_extra_button.setCheckable(True)
        self.date_filter_layout.addWidget(self.date_filter_extra_button)

        # First date filter
        self.date_filter_1 = DateFilterWidget()
        self.date_filter_layout.addWidget(self.date_filter_1)

        # Second date filter
        self.date_filter_2 = DateFilterWidget()
        self.date_filter_2.setVisible(False)
        self.date_filter_layout.addWidget(self.date_filter_2)

        # Toggle second date filter
        self.date_filter_extra_button.clicked.connect(lambda:
            self.date_filter_2.setVisible(not self.date_filter_2.isVisible())                                              
        )

        self.main_layout.addLayout(self.date_filter_layout)

        # ------------------------------------------------------
        # Beatmapset status And mode
        self.layout_status_filter = QHBoxLayout()
        self.layout_status_filter.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        # STATUS
        self.status_filter_label = QLabel()
        self.status_filter_label.setText("Status:")

        self.status_filter_ranked = QPushButton()
        self.status_filter_ranked.setText("R")
        self.status_filter_ranked.setFixedWidth(30)
        self.status_filter_ranked.setCheckable(True)

        self.status_filter_loved = QPushButton()
        self.status_filter_loved.setText("L")
        self.status_filter_loved.setFixedWidth(30)
        self.status_filter_loved.setCheckable(True)

        self.status_filter_pending = QPushButton()
        self.status_filter_pending.setText("P")
        self.status_filter_pending.setFixedWidth(30)
        self.status_filter_pending.setCheckable(True)

        self.status_filter_unknown = QPushButton()
        self.status_filter_unknown.setText("U")
        self.status_filter_unknown.setFixedWidth(30)
        self.status_filter_unknown.setCheckable(True)

        self.status_filter_approved = QPushButton()
        self.status_filter_approved.setText("A")
        self.status_filter_approved.setFixedWidth(30)
        self.status_filter_approved.setCheckable(True)

        self.layout_status_filter.addWidget(self.status_filter_label)
        self.layout_status_filter.addWidget(self.status_filter_ranked)
        self.layout_status_filter.addWidget(self.status_filter_loved)
        self.layout_status_filter.addWidget(self.status_filter_pending)
        self.layout_status_filter.addWidget(self.status_filter_unknown)
        self.layout_status_filter.addWidget(self.status_filter_approved)

        # ---------------------------
        # MODE

        # Label
        self.mode_filter_label = QLabel()
        self.mode_filter_label.setText("Mode Select:")
        self.layout_status_filter.addWidget(self.mode_filter_label)

        self.mode_filter = QComboBox()
        self.mode_filter.setFixedWidth(150)
        self.mode_filter.addItem("Osu")
        self.mode_filter.addItem("Catch The Beat")
        self.mode_filter.addItem("Taiko")
        self.mode_filter.addItem("Mania")

        self.layout_status_filter.addWidget(self.mode_filter)

        self.main_layout.addLayout(self.layout_status_filter)

        # Main text area for logs
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.main_layout.addWidget(self.log_area)

        # Main call button
        self.download_button = QPushButton("Download Maps")
        self.download_button.clicked.connect(self.on_download_maps_button_click)
        self.main_layout.addWidget(self.download_button)

        # Set central widget
        self.central_widget = QWidget()
        self.central_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.central_widget)

    def create_star_rating_filter(self):
        # Stars label
        self.beatmap_difficulty_stars_label = QLabel()
        self.beatmap_difficulty_stars_label.setText("Stars: ")
        self.beatmap_difficulty_stars_label.setFixedWidth(40)
        self.layout_filters.addWidget(self.beatmap_difficulty_stars_label)

        # Beatmap difficulty
        self.beatmap_difficulty_label = QLineEdit()
        self.beatmap_difficulty_label.setPlaceholderText("(e.g., 8)")
        self.beatmap_difficulty_label.setFixedWidth(50)
        self.layout_filters.addWidget(self.beatmap_difficulty_label)
        
        # Boolean check buttons
        self.beatmap_difficulty_higher_than_check_button = QPushButton()
        self.beatmap_difficulty_higher_than_check_button.setText(">")
        self.beatmap_difficulty_higher_than_check_button.setFixedWidth(30)
        self.beatmap_difficulty_higher_than_check_button.clicked.connect(lambda: self.on_diff_button_click(1))
        self.layout_filters.addWidget(self.beatmap_difficulty_higher_than_check_button)

        self.beatmap_difficulty_equals_check_button = QPushButton()
        self.beatmap_difficulty_equals_check_button.setText("=")
        self.beatmap_difficulty_equals_check_button.setFixedWidth(30)
        self.beatmap_difficulty_equals_check_button.clicked.connect(lambda: self.on_diff_button_click(2))
        self.layout_filters.addWidget(self.beatmap_difficulty_equals_check_button)

        self.beatmap_difficulty_less_than_check_button = QPushButton()
        self.beatmap_difficulty_less_than_check_button.setText("<")
        self.beatmap_difficulty_less_than_check_button.setFixedWidth(30)
        self.beatmap_difficulty_less_than_check_button.clicked.connect(lambda: self.on_diff_button_click(3))
        self.layout_filters.addWidget(self.beatmap_difficulty_less_than_check_button)

        self.main_layout.addLayout(self.layout_filters)

    def browse_osu_executable(self):
            global OSU_EXECUTABLE
            file_dialog = QFileDialog(self)
            file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            file_dialog.setNameFilter("Executable Files (*.exe *.AppImage);;All Files (*)")
            if file_dialog.exec():
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    OSU_EXECUTABLE = selected_files[0]
                    self.log_area.append(f"Selected Osu executable: {OSU_EXECUTABLE}")

    def startLogin(self):
        self.token_button.setEnabled(False)
        self.token_button.setText("Obtaining access token")

        self.login_worker = OsuLoginWorker()
        self.login_worker.on_token_obtained_signal.connect(self.onAccessTokenObtained)
        self.login_worker.log_signal.connect(self.log_area.append)

        self.login_worker.start()

    def onAccessTokenObtained(self, token):
        global ACCESS_TOKEN
        ACCESS_TOKEN = token

        self.token_button.setText("Successful!")
        self.log_area.append("Token obtained")

    def on_download_maps_button_click(self):
        """Generates the full download URL based on the selected mirror and filters."""

        if ACCESS_TOKEN == "":
            self.log_area.append("Error: You must obtain an access token first.")
            return False
        
        self.log_area.append("Building curl call to search for beatmapsets ids...")

        self.params = []

        # Extracted difficulty filter logic
        if not self._add_difficulty_filter():
            return False

        # Extracted date filter logic
        if not self._add_date_filter():
            return False
        
        # Extracted mods filter logic
        if not self._add_mode_filter():
            return False

        # Build curl call for logging
        self.call_cursor = None
        self.current_page = 1

        # Build the query string for the search
        query_string = " ".join(self.params)

        call_params = {
            "q": query_string
            }
        
        # Initialize wait loop
        loop = QEventLoop()

        # Curl caller that will collect all the beatmapsets ids with the filters
        self.beatmapset_ids_worker = BeatmatsetIdsWorker(call_params)
        self.beatmapset_ids_worker.log_signal.connect(self.log_area.append)
        self.beatmapset_ids_worker.finished_signal.connect(loop.quit)
        self.beatmapset_ids_worker.start()

        self.log_area.append("Looking for beatmaps, wait!")

        loop.exec()

        # Reasigning for reutilization
        self.beatmapset_ids = self.beatmapset_ids_worker.dest_list

        # Build download URLs based on selected mirror
        selected_mirror = self.mirror_dropdown.currentIndex()
        self.log_area.append(f"Selected mirror index: {selected_mirror}")
        self.download_urls = {}
        self._build_download_urls()

        self.log_area.append("Download URLs generated successfully.")

        # Download the beatmaps
        self.downloadWorker = DownloadWorker(self.download_urls)
        self.downloadWorker.log_signal.connect(self.log_area.append)
        self.downloadWorker.downloaded_map_signal.connect(self._open_map_in_osu)
        self.downloadWorker.start()
        
    def _build_download_urls(self):
        """Builds download URLs for each beatmapset ID based on the selected mirror."""
        try:
            for set_id in self.beatmapset_ids:
                self.log_area.append(f"Building current set_id mirror url for {set_id}")
                mirror_url = self._get_mirror_url(set_id)
                if mirror_url and not self.isMapAlreadyDownloaded(set_id):
                    self.download_urls[set_id] = mirror_url
                    self.log_area.append(f"Download URL for set ID {set_id}: {mirror_url}")
                else:
                    self.log_area.append(f"Mirror url already exist or map is already downloaded {set_id}")
        except Exception as ex:
            print(f"Exception caugh on _build_download_urls {ex}")

    def isMapAlreadyDownloaded(self, map_id):
        """Checks if a map ID is already in the db.json file."""
        if not os.path.exists(DB_JSON):
            return False


        with open(DB_JSON, "r") as f:
            data = json.load(f)

        # Ensure "downloaded_maps" key exists
        if "downloaded_maps" not in data:
            data["downloaded_maps"] = []
            with open(DB_JSON, "w") as f:
                json.dump(data, f, indent=4)

            return False

        return map_id in data["downloaded_maps"]

    def _update_json_file(self, map_path):
        """Updates the db.json file with the newly downloaded maps."""

        self.current_set_id = os.path.splitext(os.path.basename(map_path))[0]

        if not os.path.exists(DB_JSON):
            with open(DB_JSON, "w") as f:
                json.dump({"downloaded_maps": []}, f)

        with open(DB_JSON, "r") as f:
            data = json.load(f)

        if "downloaded_maps" not in data:
            data["downloaded_maps"] = []

        # Add newly downloaded maps to the list
        data["downloaded_maps"].append(int(self.current_set_id))

        with open(DB_JSON, "w") as f:
            json.dump(data, f, indent=4)

        self.log_area.append("db.json updated with newly downloaded maps.")
        
    def _open_map_in_osu(self, map_path):
        """Opens the downloaded map in Osu Lazer using the AppImage."""
        # If on Windows, let the OS open the file with its associated app
        if sys.platform.startswith("win") or os.name == "nt":
            try:
                os.startfile(map_path)
                self.log_area.append(f"Opened map with default app: {map_path}")
                self._update_json_file(map_path)
            except Exception as e:
                self.log_area.append(f"Error opening map with default app: {e}")
                return
        # On macOS, use the 'open' command to let the OS handle the association
        elif sys.platform == "darwin":
            try:
                subprocess.Popen(["open", map_path])
                self.log_area.append(f"Opened map with default app: {map_path}")
                self._update_json_file(map_path)
            except Exception as e:
                self.log_area.append(f"Error opening map with default app: {e}")
                return
        elif sys.platform == "linux":
            if os.path.exists(OSU_EXECUTABLE):
                os.system(f'"{OSU_EXECUTABLE}" "{map_path}" &')
                self.log_area.append(f"Opened map in Osu: {map_path}")

                # Update the JSON file with the downloaded maps
                self._update_json_file(map_path)
            else:
                self.log_area.append("Error: Osu executable not found.")

    def _get_mirror_url(self, set_id):
        """Returns the download URL for the selected mirror and beatmapset ID."""
        try:
            self.log_area.append("LOG - Getting mirror url")
            selected_mirror = self.mirror_dropdown.currentIndex()
            if selected_mirror == 0:
                return CHIMU.format(set_id=set_id)
            elif selected_mirror == 1:
                return SAYO_BOT.format(set_id=set_id)
            elif selected_mirror == 2:
                return NERINYAN.format(set_id=set_id)
            else:
                self.log_area.append("Error: Invalid mirror selected.")
                return None
        except Exception as ex:
            print(f"Exception caugh on _get_mirror_url {ex}")
    
    def _add_difficulty_filter(self):
        """Handles the difficulty filter logic for the search parameters."""

        def handle_single_difficulty_filter(star_rating_obj):
            difficulty_text = star_rating_obj.difficulty_label.text()

            if difficulty_text != "":
                try:
                    difficulty_value = float(difficulty_text)
                    if star_rating_obj.higher_than_check_button.isChecked():
                        # Higher than
                        self.params.append('stars>=' + str(difficulty_value))
                    elif star_rating_obj.equals_check_button.isChecked():
                        # Equals
                        self.params.append('stars=' + str(difficulty_value))
                    elif star_rating_obj.less_than_check_button.isChecked():
                        # Less than
                        self.params.append('stars<=' + str(difficulty_value))
                    else:
                        self.log_area.append("No difficulty filter selected. Using equals by default.")
                        self.params.append('stars=' + str(difficulty_value))
                except ValueError:
                    self.log_area.append("Error: Difficulty must be a number.")
                    return False
            return True

        if not handle_single_difficulty_filter(self.star_rating_filter_1):
            return False
        if not handle_single_difficulty_filter(self.star_rating_filter_2):
            return False
        return True

    def _add_date_filter(self):
        """Handles the date filter logic for the search parameters."""
        def handle_single_date_filter(date_filter_widget):
            if not date_filter_widget.isVisible():
                return None
            date_value = date_filter_widget.date_filter.date()
            date_str = date_value.toString("yyyy-MM-dd")
            if date_filter_widget.date_filter_since_button.isChecked():
                # Since
                return ('created>=' + date_str)
            elif date_filter_widget.date_filter_until_button.isChecked():
                # Until
                return ('created<=' + date_str)
            else:
                # Default to since
                return ('created>=' + date_str)

        filter1 = handle_single_date_filter(self.date_filter_1)
        filter2 = handle_single_date_filter(self.date_filter_2)

        # If both filters exist, ensure since <= until
        if filter1 and filter2:
            if self.date_filter_1.date_filter.date() > self.date_filter_2.date_filter.date():
                self.log_area.append("Invalid date range: 'Since' date is after 'Until' date.")
                return False
            self.params.append(filter1)
            self.params.append(filter2)
        else:
            self.params.append(filter1)
        # If neither is visible, do nothing

        return True

    def _add_status_filters(self):
        """Adds status filters to the search parameters."""
        # Example: Only include ranked and loved maps

        self.status_param = "status="
        self.status_params = []
        
        if self.status_filter_ranked.isChecked():
            self.status_params.append('r')
        if self.status_filter_loved.isChecked():
            self.status_params.append('l')
        if self.status_filter_pending.isChecked():
            self.status_params.append('p')
        if self.status_filter_unknown.isChecked():
            self.status_params.append('u')
        if self.status_filter_approved.isChecked():
            self.status_params.append('a')

        if len(self.status_params) > 0:
            self.status_param += ",".join(self.status_params)
            self.params.append(self.status_param)

    def _add_mode_filter(self):
        """
        Extracts modes to download beatmaps from
        """

        selected_item_index = self.mode_filter.currentIndex()
        
        if selected_item_index == 0:
            self.params.append("mode=osu")
        elif selected_item_index == 1:
            self.params.append("mode=ctb")
        elif selected_item_index == 2:
            self.params.append("mode=taiko")
        elif selected_item_index == 3:
            self.params.append("mode=mania")
        else:
            self.log_area.append("Wrong Mode selected in _add_mode_filter")
        
        return True

def main():
    '''
    Main entry for the application.
    '''

    try:

        # Initialize QT Application
        app = QApplication(sys.argv)

        # Create main window
        window = MainWindow()

        # Show after all widgets are added
        window.show()



        app.exec()
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()