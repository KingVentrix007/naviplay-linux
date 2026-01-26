import os
import sys
from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication

from naviplay import NavidromeClient
from gui import MusicPlayerGUI

def main():
    load_dotenv()  # loads .env into os.environ

    base_url = os.getenv("NAVIDROME_URL")
    username = os.getenv("NAVIDROME_USER")
    password = os.getenv("NAVIDROME_PASS")
    client_name = os.getenv("NAVIDROME_CLIENT", "myscript")

    if not all([base_url, username, password]):
        print("❌ Missing Navidrome configuration.")
        print("Please set NAVIDROME_URL, NAVIDROME_USER, NAVIDROME_PASS")
        sys.exit(1)

    client = NavidromeClient(
        base_url=base_url,
        username=username,
        password=password,
        client=client_name,
        cache_path="./cache.json"
    )

    app = QApplication(sys.argv)
    window = MusicPlayerGUI(client)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
