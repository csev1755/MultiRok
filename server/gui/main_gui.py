import datetime
import logging
import os
import queue
import subprocess
import sys
import time

from PyQt6.QtCore import QEvent, QTimer, QUrl
from PyQt6.QtGui import QAction, QBrush, QColor, QDesktopServices, QIcon, QPalette
from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHeaderView,
    QLabel,
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from server.gui.settings_gui import SettingsEditorDialog


class GUILogHandler(logging.Handler):
    """
    Custom logging handler that parses and queues log records.
    """

    def __init__(self):
        super().__init__()
        self.log_queue = queue.Queue()

    def emit(self, record):
        try:
            time_str = datetime.datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            level = record.levelname
            name = record.name
            msg = record.getMessage()
            self.log_queue.put((time_str, level, name, msg))
        except Exception:
            self.handleError(record)


class MultiRokGUI(QMainWindow):
    """
    PyQt main window for control of MultiRok server.

    Attributes:
        play_manager (PlayManager): MultiRok server's PlayManager object.
        go2rtc (Go2RTC): MultiRok server's Go2RTC process.
        bundle_dir (str): Program root directory for serving favicon.
        config_file (str): Path to config file used by __main__.
        listen_port (int): Webserver port used by __main__.
    """

    LOG_COLORS_DARK = {
        "DEBUG": QColor("#009DFF"),
        "INFO": QColor("#FFFFFF"),
        "WARNING": QColor("#FFF000"),
        "ERROR": QColor("#FF0000"),
        "CRITICAL": QColor("#B00000"),
    }

    LOG_COLORS_LIGHT = {
        "DEBUG": QColor("#003CFF"),
        "INFO": QColor("#000000"),
        "WARNING": QColor("#BA7C00"),
        "ERROR": QColor("#FF0000"),
        "CRITICAL": QColor("#B00000"),
    }

    def __init__(self, play_manager, go2rtc=None, bundle_dir=".", config_file="settings.ini", listen_port=5001):
        """
        Initializes the main window.
        """

        super().__init__()
        self.play_manager = play_manager
        self.go2rtc = go2rtc
        self.bundle_dir = bundle_dir
        self.config_file = config_file
        self.listen_port = listen_port

        self.setWindowTitle("MultiRok Server")
        self.resize(650, 650)
        self.setMinimumSize(300, 300)

        # Set Main Window Icon
        icon_path = os.path.join(self.bundle_dir, "server", "web", "favicon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Menu Bar Setup
        top_menubar = self.menuBar()
        if top_menubar:
            top_menubar.setStyleSheet("""
                QMenuBar {
                    padding: 2px 4px;
                }
                QMenuBar::item {
                    padding: 4px 12px;
                }
                QMenuBar::item:selected {
                    background-color: rgba(255, 255, 255, 30);
                    border-radius: 3px;
                }
            """)

            # Play Menu
            play_menu = top_menubar.addMenu("Play")
            if play_menu:
                open_client_action = QAction("Open Client", self)
                open_client_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(f"http://localhost:{self.listen_port}")))
                play_menu.addAction(open_client_action)

            # Server Menu
            server_menu = top_menubar.addMenu("Server")
            if server_menu:
                stop_action = QAction("Stop", self)
                stop_action.triggered.connect(self.close)
                server_menu.addAction(stop_action)

                restart_action = QAction("Restart", self)
                restart_action.triggered.connect(self.restart_application)
                server_menu.addAction(restart_action)

            # Settings Menu
            settings_menu = top_menubar.addMenu("Settings")
            if settings_menu:
                settings_editor_action = QAction("Settings Editor", self)
                settings_editor_action.triggered.connect(self.open_settings_dialog)
                settings_menu.addAction(settings_editor_action)

            # Help Menu
            help_menu = top_menubar.addMenu("Help")
            if help_menu:
                github_action = QAction("MultiRok GitHub", self)
                github_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/csev1755/MultiRok")))
                help_menu.addAction(github_action)

                doc_action = QAction("MultiRok Documentation", self)
                doc_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://csev1755.github.io/MultiRok/")))
                help_menu.addAction(doc_action)

        # Central Widget & Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 0, 15, 15)
        main_layout.setSpacing(10)

        # Status Group Box
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        self.uptime_label = QLabel("Uptime: 00:00:00")
        status_layout.addWidget(self.uptime_label)
        main_layout.addWidget(status_group)

        # Connected Players Group
        self.player_list_group = QGroupBox("Connected Players: 0 / 0")
        player_list_layout = QVBoxLayout(self.player_list_group)

        self.player_list_tree = QTreeWidget()
        self.player_list_tree.setColumnCount(5)
        self.player_list_tree.setHeaderLabels(["Player ID", "Player Name", "Vehicle ID", "Vehicle Name", "Buttons"])
        self.player_list_tree.setRootIsDecorated(False)
        self.player_list_tree.setIndentation(0)

        player_list_tree_header = self.player_list_tree.header()
        if player_list_tree_header:
            player_list_tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            player_list_tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            player_list_tree_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            player_list_tree_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
            player_list_tree_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.player_list_tree.setColumnWidth(0, 65)
        self.player_list_tree.setColumnWidth(1, 130)
        self.player_list_tree.setColumnWidth(2, 65)
        self.player_list_tree.setColumnWidth(3, 130)

        player_list_layout.addWidget(self.player_list_tree)
        main_layout.addWidget(self.player_list_group)

        # Server Logs Group
        log_group = QGroupBox("Server Logs")
        log_layout = QVBoxLayout(log_group)

        self.log_tree = QTreeWidget()
        self.log_tree.setColumnCount(4)
        self.log_tree.setHeaderLabels(["Time", "Level", "Name", "Message"])
        self.log_tree.setRootIsDecorated(False)
        self.log_tree.setIndentation(0)

        log_tree_header = self.log_tree.header()
        if log_tree_header:
            log_tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            log_tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            log_tree_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            log_tree_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.log_tree.setColumnWidth(0, 65)
        self.log_tree.setColumnWidth(1, 70)
        self.log_tree.setColumnWidth(2, 100)

        log_layout.addWidget(self.log_tree)
        main_layout.addWidget(log_group, stretch=1)

        # Logging Handler Setup
        self.log_handler = GUILogHandler()
        self.log_colors = self._get_log_colors()

        # Track start time for uptime calculation
        self.start_time = time.time()

        # GUI & Log Refresh Timers for Polling
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.update_gui)
        self.ui_timer.start(100)

        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.update_logs)
        self.log_timer.start(100)

    def open_settings_dialog(self):
        """
        Opens the settings editor dialog and restarts the server if necessary.
        """
        dialog = SettingsEditorDialog(config_file=self.config_file, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.restart_requested:
            self.restart_application()

    def restart_application(self):
        """Cleanly stop services and relaunch the app or frozen executable."""
        if self.go2rtc:
            self.go2rtc.stop()

        env = os.environ.copy()
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, *sys.argv[1:]]
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        else:
            cmd = [sys.executable, *sys.argv]

        subprocess.Popen(cmd, env=env)
        QApplication.quit()

    def changeEvent(self, event):
        """
        Qt built-in event handler called whenever changes occur to widget.
        """
        if event.type() == QEvent.Type.PaletteChange:
            # Refreshes the colors of logging items in the level column upon theme change.
            self.log_colors = self._get_log_colors()
            for item_index in range(self.log_tree.topLevelItemCount()):
                log_item = self.log_tree.topLevelItem(item_index)
                if log_item:
                    level = log_item.text(1)
                    color = self.log_colors.get(level, self.log_colors.get("INFO"))
                    log_item.setForeground(1, QBrush(color))

        super().changeEvent(event)

    def _get_log_colors(self):
        """
        Determines whether the current palette is dark or light based on background lightness.
        """
        is_dark = self.palette().color(QPalette.ColorRole.Base).lightness() < 128
        return self.LOG_COLORS_DARK if is_dark else self.LOG_COLORS_LIGHT

    def update_gui(self):
        """
        Polls the necessary information from the play_manager to update the GUI.
        """

        # Uptime Counter
        elapsed_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.uptime_label.setText(f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}")

        if not self.play_manager:
            return

        # Player List
        self.player_list_tree.clear()
        connected_player_count = 0

        for player_id, player in self.play_manager.players.items():
            if player.socket_id:
                connected_player_count += 1
                name = player.player_name or "No Name"

                selection_id_text = "None"
                vehicle_name_text = "None"

                if player.selection:
                    selection_id_text = str(player.selection)
                    vehicle = self.play_manager.get_vehicle_from_id(player.selection)
                    if vehicle:
                        vehicle_name_text = vehicle.name

                active_buttons = [str(b) for b in player.buttons if b != "UPDATE"] if player.buttons else []
                buttons_text = ", ".join(sorted(active_buttons)) if active_buttons else ""

                self.player_list_tree.addTopLevelItem(
                    QTreeWidgetItem([str(player_id), name, selection_id_text, vehicle_name_text, buttons_text])
                )

        # Total Player Count
        self.player_list_group.setTitle(f"Connected Players: {connected_player_count} / {self.play_manager.max_player_count}")

    def update_logs(self):
        """
        Polls the custom log handler queue to update the log display on the GUI.
        """
        new_logs = []
        while True:
            try:
                new_logs.append(self.log_handler.log_queue.get_nowait())
            except queue.Empty:
                break

        if not new_logs:
            return

        scrollbar = self.log_tree.verticalScrollBar()
        scrollbar_at_bottom = True
        if scrollbar:
            scrollbar_at_bottom = (scrollbar.maximum() - scrollbar.value()) <= 5

        # Color Logs According to Severity
        colored_new_logs = []
        for log_entry in new_logs:
            item = QTreeWidgetItem(log_entry)
            color = self.log_colors.get(log_entry[1], self.log_colors.get("INFO"))
            item.setForeground(1, QBrush(color))
            colored_new_logs.append(item)

        self.log_tree.addTopLevelItems(colored_new_logs)

        # Limit Total Number of Log Entries
        while self.log_tree.topLevelItemCount() > 256:
            self.log_tree.takeTopLevelItem(0)

        if scrollbar_at_bottom:
            self.log_tree.scrollToBottom()

    def closeEvent(self, event):
        """
        Handle closing the main window.
        """
        if self.go2rtc:
            self.go2rtc.stop()
        event.accept()
