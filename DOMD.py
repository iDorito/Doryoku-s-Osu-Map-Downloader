#!/usr/bin/env python # 
"""\
Main controller for the Osu Map Downloader.

By: Ricardo Faria
Osu User: Doryoku

Usage: run the script: run.sh
"""

# ----------------------------------------------------------------------
# Standard libraries
from concurrent.futures import thread
import socket
import os
import sys
from urllib.parse import urlencode
import webbrowser
# ----------------------------------------------------------------------
# 3rd party libraries
import requests
import json
import PyQt6 as PQT6
import PyQt6.QtCore as QtCore
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QTextEdit, QLineEdit, QHBoxLayout, QLabel, QComboBox, QDateEdit
from PyQt6.QtCore import QThread, pyqtSignal
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# VARIABLES
# ----------------------------------------------------------------------
ACCESS_TOKEN = ""
CLIENT_ID = '46676'
CLIENT_SECRET = '7qRBCgwTQDEMTe0DiZ5Tb9QgpYt0lzEAIJ0fqXrC'
REDIRECT_URL = 'http://localhost:8080'
PORT = 8080
BEATMAPSET_ID = 2201473
# ----------------------------------------------------------------------
# DIRS
FILE_PATH = os.path.abspath(__file__)
FULL_PATH = os.path.dirname(FILE_PATH)
DOWNLOAD_PATH = os.path.join(os.path.dirname(FILE_PATH), "maps")
OSU_LAZER_APPIMAGE = os.path.join(os.path.expanduser("~"), "Osu_Lazer.appimage")

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# ---------------------
# --- BEATMAPSET MIRRORS ---
CHIMU="https://api.chimu.moe/v1/download/{set_id}?n=1"
SAYO_BOT="https://dl.sayobot.cn/beatmaps/download/full/{set_id}"
NERINYAN="https://api.nerinyan.moe/d/{set_id}"
    



# ----------------------------------------------------------------------
class OsuLoginWorker(QThread):
    on_token_obtained_signal = pyqtSignal(str)

    def run(self):
        print("Logging in Osu and obtaining token.")

        # Auth URL for app code
        auth_url = 'https://osu.ppy.sh/oauth/authorize?' + urlencode({
            'client_id': CLIENT_ID,
            'REDIRECT_URL': REDIRECT_URL,
            'response_type': 'code',
            'scope': 'public'
        })

        # Open the browser for authentication
        print("Opening browser...")
        webbrowser.open(auth_url)

        # Opening a server to listen for responde. 127.0.0.1:8080
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('localhost', PORT))
        server.listen(1)

        print(f"Waiting callback for {REDIRECT_URL}...")
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
            print(f"Code obtained: {code}")
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
            print(f"Error canjeando token: {response.text}")
            return None

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
                    # Save to ./downloads/prueba_mirror.osz
                    filename = os.path.join(DOWNLOAD_PATH, f"{set_id}.osz")
                    with open(filename, 'wb') as f:
                        f.write(download_response.content)

                    # Open in Osu Lazer
                    self.downloaded_map_signal.emit(filename)

                    self.log_signal.emit(f"Downloaded and saved as: {set_id}")
                else:
                    self.log_signal.emit(f"Failed to download from {download_url}: Status code {download_response.status_code}")
            except Exception as e:
                self.log_signal.emit(f"Exception occurred while downloading from {download_url}: {e}")
        

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

        # Token button
        self.token_button = QPushButton()
        self.token_button.setText("Get Token")
        self.token_button.clicked.connect(self.startLogin)
        self.main_layout.addWidget(self.token_button)

        # Mirror dropdown
        self.mirror_label = QLabel()
        self.mirror_label.setText("Select Mirror:")
        self.main_layout.addWidget(self.mirror_label)

        self.mirror_dropdown = QComboBox()
        self.mirror_dropdown.addItem("Chimu")
        self.mirror_dropdown.addItem("SayoBot")
        self.mirror_dropdown.addItem("Nerinyan")
        self.main_layout.addWidget(self.mirror_dropdown)

        # ------------------------------------------------------
        # Beatmap filters section
        # ------------------------------------------------------
        self.layout_filters = QHBoxLayout()
        self.layout_filters.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        # ------------------------------------------------------
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

        # ------------------------------------------------------
        # Date filter
        self.layout_date_filter = QHBoxLayout()
        self.layout_date_filter.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        self.date_filter_label = QLabel()
        self.date_filter_label.setText("Date:")
        self.date_filter_label.setFixedWidth(40)
        self.layout_date_filter.addWidget(self.date_filter_label)

        self.date_filter = QDateEdit()
        self.date_filter.setDate(QtCore.QDate.currentDate())
        self.date_filter.setDisplayFormat("dd-MM-yyyy")
        self.date_filter.setCalendarPopup(True)
        self.layout_date_filter.addWidget(self.date_filter)

        self.date_filter_since_button = QPushButton()
        self.date_filter_since_button.setText("Since")
        self.date_filter_since_button.setFixedWidth(60)
        self.date_filter_since_button.clicked.connect(lambda: self.on_date_filter_button_click(1))
        self.layout_date_filter.addWidget(self.date_filter_since_button)

        self.date_filter_until_button = QPushButton()
        self.date_filter_until_button.setText("Until")
        self.date_filter_until_button.setFixedWidth(60)
        self.date_filter_until_button.clicked.connect(lambda: self.on_date_filter_button_click(2))
        self.layout_date_filter.addWidget(self.date_filter_until_button)

        self.main_layout.addLayout(self.layout_date_filter)

        # ------------------------------------------------------
        # Beatmapset status
        self.layout_status_filter = QHBoxLayout()
        self.layout_status_filter.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

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

    def startLogin(self):
        self.token_button.setEnabled(False)
        self.token_button.setText("Obtaining access token")

        self.login_worker = OsuLoginWorker()
        self.login_worker.on_token_obtained_signal.connect(self.onAccessTokenObtained)

        self.login_worker.start()

    def onAccessTokenObtained(self, token):
        global ACCESS_TOKEN
        ACCESS_TOKEN = token

        self.token_button.setText("Successful!")

        print(f"Token obtained {ACCESS_TOKEN}")
   
    def on_diff_button_click(self, button_type):
        """
        Handles the difficulty filter buttons
        
        if one is clicked, the others are unclicked
        1 = higher than
        2 = equals
        3 = less than
        """
        
        if button_type == 1:
            self.beatmap_difficulty_higher_than_check_button.setEnabled(False)
            self.beatmap_difficulty_equals_check_button.setEnabled(True)
            self.beatmap_difficulty_less_than_check_button.setEnabled(True)
        elif button_type == 2:
            self.beatmap_difficulty_higher_than_check_button.setEnabled(True)
            self.beatmap_difficulty_equals_check_button.setEnabled(False)
            self.beatmap_difficulty_less_than_check_button.setEnabled(True)
        elif button_type == 3:
            self.beatmap_difficulty_higher_than_check_button.setEnabled(True)
            self.beatmap_difficulty_equals_check_button.setEnabled(True)
            self.beatmap_difficulty_less_than_check_button.setEnabled(False)

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
        elif button_type == 2:
            self.date_filter_since_button.setEnabled(True)
            self.date_filter_until_button.setEnabled(False)

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

        # Build curl call for logging
        # Build the query string for the search
        query_string = " ".join(self.params)
        self.response = requests.get(
            "https://osu.ppy.sh/api/v2/beatmapsets/search",
            headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"
            },
            params={
            "q": query_string
            }
        )

        self.log_area.append("Params used: " + query_string)

        self.log_area.append(f"Response code: {self.response.status_code}")

        if self.response.status_code != 200:
            self.log_area.append(f"Error obtaining beatmapsets: {self.response.text}")
            return False
        
        self.beatmapsets = self.response.json()['beatmapsets']
        self.log_area.append(f"Found {len(self.beatmapsets)} beatmapsets matching the criteria.")

        self.beatmapsets_ids = [str(beatmapset['id']) for beatmapset in self.beatmapsets]
        self.log_area.append("Beatmapset IDs: " + ", ".join(self.beatmapsets_ids))

        # Build download URLs based on selected mirror
        selected_mirror = self.mirror_dropdown.currentIndex()
        self.log_area.append(f"Selected mirror index: {selected_mirror}")
        self.download_urls = {}

        for set_id in self.beatmapsets_ids:
            mirror_url = self._get_mirror_url(set_id)
            if mirror_url:
                self.download_urls[set_id] = mirror_url
                self.log_area.append(f"Download URL for set ID {set_id}: {mirror_url}")

        self.log_area.append("Download URLs generated successfully.")

        # Download the beatmaps
        self.downloadWorker = DownloadWorker(self.download_urls)
        self.downloadWorker.log_signal.connect(self.log_area.append)
        self.downloadWorker.downloaded_map_signal.connect(self._open_map_in_osu_lazer)
        self.downloadWorker.start()

        return True
        
    def _open_map_in_osu_lazer(self, map_path):
        """Opens the downloaded map in Osu Lazer using the AppImage."""
        if os.path.exists(OSU_LAZER_APPIMAGE):
            os.system(f'"{OSU_LAZER_APPIMAGE}" "{map_path}" &')
            self.log_area.append(f"Opened map in Osu Lazer: {map_path}")
        else:
            self.log_area.append("Error: Osu Lazer AppImage not found.")

    def _get_mirror_url(self, set_id):
        """Returns the download URL for the selected mirror and beatmapset ID."""
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

    def _add_difficulty_filter(self):
        """Handles the difficulty filter logic for the search parameters."""
        difficulty_text = self.beatmap_difficulty_label.text()
        if difficulty_text != "":
            try:
                difficulty_value = float(difficulty_text)
                if not self.beatmap_difficulty_higher_than_check_button.isEnabled():
                    # Higher than
                    self.params.append('stars>=' + str(difficulty_value))
                elif not self.beatmap_difficulty_equals_check_button.isEnabled():
                    # Equals
                    self.params.append('stars=' + str(difficulty_value))
                elif not self.beatmap_difficulty_less_than_check_button.isEnabled():
                    # Less than
                    self.params.append('stars<=' + str(difficulty_value))
                else:
                    self.log_area.append("No difficulty filter selected. Using equals by default.")
                    self.params.append('stars=' + str(difficulty_value))
            except ValueError:
                self.log_area.append("Error: Difficulty must be a number.")
                return False
        return True

    def _add_date_filter(self):
        """Handles the date filter logic for the search parameters."""
        date_value = self.date_filter.date()
        if date_value.year() == 2000 and date_value.month() == 1 and date_value.day() == 1:
            self.log_area.append("No date filter selected, doing 1 month old maps onwards")
            date_value.setDate(QtCore.QDate.currentDate() - QtCore.QDate.months(1))
            date_value = date_value.toString("yyyy-MM-dd")
        else:
            date_value = date_value.toString("yyyy-MM-dd")

        if not self.date_filter_since_button.isEnabled():
            # Since
            self.params.append('created>=' + date_value)
        elif not self.date_filter_until_button.isEnabled():
            # Until
            self.params.append('created<' + date_value)
        else:
            self.log_area.append("No date filter selected. Using since by default.")
            self.params.append('created>=' + date_value)
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