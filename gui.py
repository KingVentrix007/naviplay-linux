import sys
import threading
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QListWidget, QLabel,
    QPushButton, QListWidgetItem, QHBoxLayout, QMessageBox
)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QByteArray
from sonicapi import NavidromeClient

class MusicPlayerGUI(QWidget):
    def __init__(self, client: NavidromeClient):
        super().__init__()
        self.client = client
        self.setWindowTitle("Navidrome Music Player")
        self.setGeometry(100, 100, 500, 700)
        self.current_player = None
        self.lock = threading.Lock()

        # Main layout
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Cover image
        self.cover_label = QLabel("Album Cover")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFixedHeight(250)
        self.layout.addWidget(self.cover_label)

        # Song list
        self.song_listbox = QListWidget()
        self.layout.addWidget(self.song_listbox)

        # Play button
        self.play_button = QPushButton("Play Selected Song")
        self.play_button.clicked.connect(self.play_selected_song)
        self.layout.addWidget(self.play_button)

        # Load songs
        self.songs = client.get_all_songs()
        for song in self.songs:
            item = QListWidgetItem(song.get("title", "Unknown Title"))
            self.song_listbox.addItem(item)

        # Change cover when selection changes
        self.song_listbox.currentRowChanged.connect(self.update_cover)

    def update_cover(self, index):
        if index < 0 or index >= len(self.songs):
            return
        song_id = self.songs[index]["id"]
        cover_bytes = self.client.get_cover_art(song_id)
        if cover_bytes:
            image = QImage.fromData(QByteArray(cover_bytes))
            pixmap = QPixmap.fromImage(image).scaled(
                self.cover_label.width(), self.cover_label.height(),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.cover_label.setPixmap(pixmap)
        else:
            self.cover_label.setText("No Cover Available")
            self.cover_label.setPixmap(QPixmap())  # clear previous

    def play_selected_song(self):
        index = self.song_listbox.currentRow()
        if index < 0:
            QMessageBox.warning(self, "No selection", "Please select a song to play.")
            return
        song_title = self.songs[index]["title"]

        # Stop current song if playing
        with self.lock:
            if self.current_player:
                self.current_player.terminate()
                self.current_player = None

        # Start playing in a thread
        threading.Thread(target=self.stream_song, args=(song_title,), daemon=True).start()

    def stream_song(self, song_title):
        try:
            with self.lock:
                self.current_player = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-i", "pipe:0"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            stream = self.client.get_bit_stream(song_title)
            for chunk in stream:
                if self.current_player.poll() is not None:
                    break
                self.current_player.stdin.write(chunk)

            if self.current_player:
                self.current_player.stdin.close()
                self.current_player.wait()

            with self.lock:
                self.current_player = None

        except BrokenPipeError:
            pass
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

