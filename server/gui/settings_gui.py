import configparser
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from server.config import CONFIG_SCHEMA


def _parse_bool(value):
    """
    Safely convert schema values into a boolean.

    Args:
        value (Any): The value to be parsed.

    Returns:
        Bool: Output boolean from conversion.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in frozenset({"true", "1", "yes", "on"})
    return bool(value)


def _parse_int(value, fallback=0):
    """
    Safely convert schema values into integers.

    Args:
        value (Any): The value to be parsed.

    Returns:
        Int: Output integer from conversion.
    """
    if value is None:
        return fallback
    try:
        return int(value)
    except ValueError, TypeError:
        return fallback


class NoScrollSpinBox(QSpinBox):
    """
    QSpinBox that ignores wheel events so scrolling a tab won't change numbers.
    """

    def wheelEvent(self, event):
        event.ignore()


class SettingsEditorDialog(QDialog):
    """
    Settings editor dialog dynamically generated from `CONFIG_SCHEMA` and the settings file.

    Attributes:
        config_file (str): Path to config file used by __main__.
        parent (QWidget): Parent QWidget that opened the dialog.
        widgets_map (dict): Maps schema section keys or (section, option) tuples to (config_section_type, widget_or_table).
        _table_schemas (dict): Stores each table section's schema dict.
        restart_requested (bool): The parent widget checks this value after the dialog closes.
    """

    def __init__(self, config_file="settings.ini", parent=None):
        """
        Initializes the settings editor dialog.

        Args:
            config_file (str): Path to config file used by __main__.
            parent (QWidget): Parent QWidget that opened the dialog.
        """
        super().__init__(parent)
        self.config_file = config_file
        self.config = self._load_config_parser(config_file)

        self.widgets_map = {}
        self._table_schemas = {}
        self.restart_requested = False

        self.setWindowTitle("Settings Editor")
        self.resize(780, 550)

        self._init_ui()
        self._populate_ui()

    @staticmethod
    def _load_config_parser(path):
        """
        Create a ConfigParser and load it from the target path.

        Args:
            path (str): System path to the configuration file.

        Returns:
            ConfigParser: ConfigParser object loaded from the target path.
        """
        parser = configparser.ConfigParser()
        parser.optionxform = lambda optionstr: optionstr
        if path and os.path.exists(path):
            parser.read(path)
        return parser

    def _on_tree_item_changed(self, current_item, _previous_item):
        """
        Change the settings_page_stack to display the correct page based on nav tree input.
        """
        if current_item is None:
            return
        page_index = current_item.data(0, Qt.ItemDataRole.UserRole)
        if page_index is not None:
            self.settings_page_stack.setCurrentIndex(page_index)

    def _init_ui(self):
        """
        Build the splitter navigation layout and bottom action buttons.
        The navigation and pages are initially empty until _populate_ui() is called.
        """
        main_layout = QVBoxLayout(self)

        # Splitter for Seperating Nav Tree from Settings Pages
        self.settings_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.settings_splitter)

        # Settings Navigation Tree
        self.settings_nav_tree = QTreeWidget()
        self.settings_nav_tree.setHeaderHidden(True)
        self.settings_nav_tree.setIndentation(14)
        self.settings_nav_tree.currentItemChanged.connect(self._on_tree_item_changed)
        self.settings_splitter.addWidget(self.settings_nav_tree)

        # Stack of Settings Page Widgets
        self.settings_page_stack = QStackedWidget()
        self.settings_splitter.addWidget(self.settings_page_stack)

        # Buttons at Bottom of Dialog
        button_layout = QHBoxLayout()

        self.reload_button = QPushButton("Reload from File")
        button_layout.addWidget(self.reload_button)
        self.reload_button.clicked.connect(self.on_reload)

        self.defaults_button = QPushButton("Load Defaults")
        self.defaults_button.clicked.connect(self.on_defaults)
        button_layout.addWidget(self.defaults_button)

        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self.on_export)
        button_layout.addWidget(self.export_button)

        button_layout.addStretch()

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.on_save)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        main_layout.addLayout(button_layout)

    def _populate_ui(self):
        """
        Dynamically populate navigation tree and settings pages from CONFIG_SCHEMA.
        """

        def add_page_to_ui(page_widget, page_label, parent_tree_item=None):
            """
            Add page_widget to settings_page_stack and settings_nav_tree.

            Args:
                page_widget (QWidget): Settings page to be added to the UI.
                page_label (str): Label for the settings page.
                parent_tree_item (QTreeWidgetItem): The parent tree item (for nested items).

            Returns:
                QTreeWidgetItem: The item added to the navigation tree.
            """
            page_index = self.settings_page_stack.addWidget(page_widget)
            tree_item = QTreeWidgetItem([page_label])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, page_index)
            if parent_tree_item is None:
                self.settings_nav_tree.addTopLevelItem(tree_item)
            else:
                parent_tree_item.addChild(tree_item)
            return tree_item

        for item_name, item_contents in CONFIG_SCHEMA.items():
            item_type = item_contents.get("type", "settings_page")  # Fallback to "settings_page"
            item_label = item_contents.get("label", item_name)  # Fallback to item_name

            if item_type == "settings_page":
                settings_page = self.create_settings_page(item_name, item_contents)
                add_page_to_ui(settings_page, item_label)

            elif item_type == "vehicle_dynamic_map":
                vehicles_page = self.create_vehicle_dynamic_map_page(item_name, item_contents)
                vdm_tree_item = add_page_to_ui(vehicles_page, item_label)

                for vehicle_type, vehicle_contents in item_contents.get("vehicle_types", {}).items():  # Fallback to {}
                    if vehicle_contents.get("vehicle_options"):
                        vehicle_label = vehicle_contents.get("label", vehicle_type)  # Fallback to vehicle_type
                        vehicle_settings_page = self.create_settings_page(vehicle_type, vehicle_contents)
                        add_page_to_ui(vehicle_settings_page, vehicle_label, parent_tree_item=vdm_tree_item)

                vdm_tree_item.setExpanded(True)

            elif item_type == "dynamic_map":
                dynamic_map_page = self.create_dynamic_map_page(item_name, item_contents)
                add_page_to_ui(dynamic_map_page, item_label)

        self.settings_nav_tree.resizeColumnToContents(0)
        tree_width = max(self.settings_nav_tree.sizeHintForColumn(0) + 30, 150)
        self.settings_splitter.setSizes([tree_width, max(self.width() - tree_width, 400)])

        if self.settings_nav_tree.topLevelItemCount() > 0:
            self.settings_nav_tree.setCurrentItem(self.settings_nav_tree.topLevelItem(0))

    def create_settings_page(self, page_name, page_contents):
        """
        Create a scrollable form tab for standard key/value schema options.

        Args:
            page_name (str): Name of this settings page.
            page_contents (str): Raw contents of the config schema for this page.

        Returns:
            QScrollArea: Scrollable widget holding the contents of the settings page.
        """
        page_scroll_area = QScrollArea()
        page_scroll_area.setWidgetResizable(True)

        page_content_widget = QWidget()
        page_form_layout = QVBoxLayout(page_content_widget)
        page_form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        page_form_layout.setSpacing(16)

        for option_name, option_contents in page_contents.get("options", {}).items():  # Fallback to {}
            option_type = option_contents.get("type", "str")  # Fallback to "str"
            current_val = self._get_val_from_config(page_name, option_name, option_contents)
            option_widget = self._create_option_widget(option_type, option_contents, current_val)
            self.widgets_map[(page_name, option_name)] = (option_type, option_widget)

            option_container = QWidget()
            option_layout = QVBoxLayout(option_container)
            option_layout.setContentsMargins(0, 0, 0, 0)
            option_layout.setSpacing(4)

            option_label = QLabel(f"<b>{option_contents.get('label', option_name)}</b>")  # Fallback to option_name
            option_layout.addWidget(option_label)

            option_description = option_contents.get("description", "")  # Fallback to ""
            if option_description:
                description_label = QLabel(f"<small style='color: gray;'>{option_description}</small>")
                description_label.setWordWrap(True)
                option_layout.addWidget(description_label)

            if option_type != "bool":
                option_widget.setMaximumWidth(300)

            option_input_layout = QHBoxLayout()
            option_input_layout.setContentsMargins(0, 0, 0, 0)
            option_input_layout.addWidget(option_widget)
            option_input_layout.addStretch()
            option_layout.addLayout(option_input_layout)

            page_form_layout.addWidget(option_container)

        page_form_layout.addStretch()
        page_scroll_area.setWidget(page_content_widget)
        return page_scroll_area

    def _get_val_from_config(self, section_name, option_name, option_contents):
        """
        Get the saved value of an option from the settings (or fall back to default).

        Args:
            section_name (str): Name of the config schema section (settings page).
            option_name (str): Name of the option being targeted.
            option_contents (str): Raw contents of the config schema for this opton.

        Returns:
            Any: Value of the configuration item (or default if undefined).
        """
        if self.config.has_section(section_name) and self.config.has_option(section_name, option_name):
            return self.config.get(section_name, option_name)
        return option_contents.get("default")

    def _create_option_widget(self, option_type, option_contents, value):
        """
        Create the widget for an option in the schema.

        Args:
            option_type (str): The type of option being created (bool, int, choice, or str).
            option_contents (str): Raw contents of the config schema for this opton.
            value (Any): Initial value of that widget to be displayed.

        Returns:
            QCheckBox | NoScrollSpinBox | QComboBox | QLineEdit: Created widget.
        """
        if option_type == "bool":
            option_widget = QCheckBox()
        elif option_type == "int":
            option_widget = NoScrollSpinBox()
            option_widget.setRange(option_contents.get("min", 0), option_contents.get("max", 99999))
        elif option_type == "choice":
            option_widget = QComboBox()
            option_widget.addItems(option_contents.get("choices", []))
        else:  # option_type == "str"
            option_widget = QLineEdit()

        self._set_widget_value(option_type, option_contents, option_widget, value)
        return option_widget

    @staticmethod
    def _set_widget_value(option_type, option_contents, option_widget, value):
        """
        Set the value of an option widget.

        Args:
            option_type (str): The type of option (bool, int, choice, or str).
            option_contents (str): Raw contents of the config schema for this opton.
            option_widget: The widget being targeted.
            value (Any): Value to be set.
        """
        default_int = _parse_int(option_contents.get("default"), 0)

        if option_type == "bool" and isinstance(option_widget, QCheckBox):
            option_widget.setChecked(_parse_bool(value))
        elif option_type == "int" and isinstance(option_widget, QSpinBox):
            option_widget.setValue(_parse_int(value, fallback=default_int))
        elif option_type == "choice" and isinstance(option_widget, QComboBox):
            choices = option_contents.get("choices", [])
            str_val = str(value) if value is not None else ""
            if str_val in choices:
                option_widget.setCurrentText(str_val)
        elif isinstance(option_widget, QLineEdit):  # option_type == "str"
            option_widget.setText(str(value) if value is not None else "")

    @staticmethod
    def _get_widget_value(option_type, option_widget):
        """
        Get the current value of an option widget.

        Args:
            option_type (str): The type of option (bool, int, choice, or str).
            option_widget: The widget being targeted.

        Returns:
            Any: Value of the widget.
        """
        if option_type == "bool" and isinstance(option_widget, QCheckBox):
            return str(option_widget.isChecked()).lower()
        if option_type == "int" and isinstance(option_widget, QSpinBox):
            return str(option_widget.value())
        if option_type == "choice" and isinstance(option_widget, QComboBox):
            return option_widget.currentText()
        if isinstance(option_widget, QLineEdit):  # option_type == "str"
            return option_widget.text()
        return ""

    def _find_option_def(self, section_name, option_name):
        """
        Look up an option definition in top-level or nested sections.

        Args:
            section_name (str): Name of the config schema section (settings page).
            option_name (str): Name of the option being searched for.

        Returns:
            Str: The contents of the setting with that name.
        """
        for sec_name, sec_contents in CONFIG_SCHEMA.items():
            if sec_name == section_name and "options" in sec_contents:
                return sec_contents["options"].get(option_name, {})
            for veh_type, veh_contents in sec_contents.get("vehicle_types", {}).items():
                if veh_type == section_name and "options" in veh_contents:
                    return veh_contents["options"].get(option_name, {})
        return {}

    @staticmethod
    def _hide_vertical_header(table_widget):
        """Hides the vertical header (row count) of a table widget."""
        vertical_header = table_widget.verticalHeader()
        if vertical_header:
            vertical_header.setVisible(False)
            vertical_header.hide()
            vertical_header.setDefaultSectionSize(24)

    # STOPPED WORKING HEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEERE

    def _build_table_shell(self, section_name, section_def, headers, on_add, on_remove):
        """Create common scroll container, title/description, add/remove buttons, and table."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        content_widget = QWidget()
        table_page_layout = QVBoxLayout(content_widget)
        table_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        table_page_layout.setContentsMargins(8, 8, 8, 8)
        table_page_layout.setSpacing(6)

        label_text = section_def.get("label", section_name)
        heading_label = QLabel(f"<h2 style='margin-top: 0; margin-bottom: 0;'>{label_text}</h2>")
        table_page_layout.addWidget(heading_label)

        description = section_def.get("description", "")
        if description:
            description_label = QLabel(f"<small style='color: gray;'>{description}</small>")
            description_label.setWordWrap(True)
            table_page_layout.addWidget(description_label)

        table_widget = QTableWidget()
        table_widget.setColumnCount(len(headers))
        table_widget.setHorizontalHeaderLabels(headers)
        table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self._hide_vertical_header(table_widget)

        button_bar_layout = QHBoxLayout()
        add_entry_button = QPushButton("Add Entry")
        remove_entry_button = QPushButton("Remove Selected")
        add_entry_button.clicked.connect(on_add)
        remove_entry_button.clicked.connect(on_remove)
        button_bar_layout.addWidget(add_entry_button)
        button_bar_layout.addWidget(remove_entry_button)
        button_bar_layout.addStretch()

        table_page_layout.addLayout(button_bar_layout)
        table_page_layout.addWidget(table_widget)
        scroll_area.setWidget(content_widget)
        return scroll_area, table_widget

    @staticmethod
    def _make_readonly_item(text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def create_vehicle_dynamic_map_page(self, section_name, section_def):
        """Create a table editing numbered vehicles across `<source>.vehicles` INI sections."""
        sources = section_def.get("vehicle_types", {})
        finite_max_keys = [s.get("max_key") for s in sources.values() if s.get("max_key") is not None]
        global_max_rows = max(finite_max_keys) if (sources and len(finite_max_keys) == len(sources)) else None

        table_state = {}

        def add_row():
            vehicle_table = table_state["table_widget"]
            row_count = vehicle_table.rowCount()
            if global_max_rows is not None and row_count >= global_max_rows:
                QMessageBox.information(
                    self,
                    "Limit Reached",
                    f"Maximum of {global_max_rows} entries reached.",
                )
                return
            vehicle_table.insertRow(row_count)
            vehicle_table.setItem(row_count, 1, QTableWidgetItem(""))
            vehicle_table.setCellWidget(row_count, 2, QComboBox())
            table_state["refresh_rows"]()
            vehicle_table.selectRow(row_count)
            self._hide_vertical_header(vehicle_table)

        def del_row():
            vehicle_table = table_state["table_widget"]
            selected_row = vehicle_table.currentRow()
            if selected_row >= 0:
                vehicle_table.removeRow(selected_row)
                table_state["refresh_rows"]()
                if vehicle_table.rowCount() > 0:
                    vehicle_table.selectRow(min(selected_row, vehicle_table.rowCount() - 1))

        scroll_area, vehicle_table = self._build_table_shell(
            section_name,
            section_def,
            headers=["Number", "Name", "Type"],
            on_add=add_row,
            on_remove=del_row,
        )

        horizontal_header = vehicle_table.horizontalHeader()
        if horizontal_header:
            horizontal_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            horizontal_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            horizontal_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        vehicle_table.setColumnWidth(0, 60)
        vehicle_table.setColumnWidth(2, 160)

        refresh_rows = self._populate_vehicle_dynamic_map_table(vehicle_table, section_def)
        self._hide_vertical_header(vehicle_table)
        table_state["table_widget"] = vehicle_table
        table_state["refresh_rows"] = refresh_rows

        self._table_schemas[section_name] = section_def
        self.widgets_map[section_name] = ("unified_vehicles", vehicle_table)
        return scroll_area

    def _populate_vehicle_dynamic_map_table(self, vehicle_table, section_def):
        """Load numbered vehicle rows from `<source>.vehicles` sections and return `refresh_rows`."""
        sources = section_def.get("vehicle_types", {})
        label_to_key = {s_def.get("label", s_key): s_key for s_key, s_def in sources.items()}
        key_to_label = {s_key: s_def.get("label", s_key) for s_key, s_def in sources.items()}
        all_type_labels = list(label_to_key.keys())
        default_type_label = key_to_label.get(next(iter(sources.keys())), "") if sources else ""

        key_to_data = {}
        for s_key, expected_label in key_to_label.items():
            ini_section = f"{s_key}.vehicles"
            if self.config.has_section(ini_section):
                for key_str, val_str in self.config.items(ini_section):
                    try:
                        key_to_data[int(key_str)] = (val_str, expected_label)
                    except ValueError:
                        continue

        # Vehicle numbers start at 1 and run consecutively up to the highest configured ID
        total_rows = max(max(key_to_data.keys(), default=0), 1)
        rows_data = [key_to_data.get(i, ("", default_type_label)) for i in range(1, total_rows + 1)]

        vehicle_table.setRowCount(len(rows_data))

        def refresh_rows():
            for row_idx in range(vehicle_table.rowCount()):
                vehicle_table.setItem(row_idx, 0, self._make_readonly_item(str(row_idx + 1)))

                type_combo_box = vehicle_table.cellWidget(row_idx, 2)
                if not isinstance(type_combo_box, QComboBox):
                    type_combo_box = QComboBox()
                    vehicle_table.setCellWidget(row_idx, 2, type_combo_box)

                current_type = type_combo_box.currentText()
                allowed_labels = []
                for lbl in all_type_labels:
                    max_key = sources[label_to_key[lbl]].get("max_key")
                    if max_key is None or (row_idx + 1) <= max_key:
                        allowed_labels.append(lbl)

                type_combo_box.blockSignals(True)
                type_combo_box.clear()
                type_combo_box.addItems(allowed_labels)
                if current_type in allowed_labels:
                    type_combo_box.setCurrentText(current_type)
                elif allowed_labels:
                    type_combo_box.setCurrentIndex(0)
                type_combo_box.blockSignals(False)

        for row_idx, (name_val, _) in enumerate(rows_data):
            vehicle_table.setItem(row_idx, 1, QTableWidgetItem(name_val))
            vehicle_table.setCellWidget(row_idx, 2, QComboBox())

        refresh_rows()

        for row_idx, (_, type_val) in enumerate(rows_data):
            type_combo_box = vehicle_table.cellWidget(row_idx, 2)
            if isinstance(type_combo_box, QComboBox) and type_combo_box.findText(type_val) != -1:
                type_combo_box.setCurrentText(type_val)

        return refresh_rows

    def create_dynamic_map_page(self, section_name, section_def):
        """Create a key/value table tab for dynamic map sections such as `video_streams`."""
        key_range = section_def.get("key_range")
        table_state = {}

        def add_row():
            map_table = table_state["table_widget"]
            row_count = map_table.rowCount()

            if key_range:
                start_key, end_key = key_range
                max_entries = end_key - start_key + 1
                if row_count >= max_entries:
                    QMessageBox.information(
                        self,
                        "Limit Reached",
                        f"Maximum of {max_entries} entries ({start_key}–{end_key}) reached.",
                    )
                    return

                existing_keys = set()
                for row_idx in range(row_count):
                    key_item = map_table.item(row_idx, 0)
                    if key_item and key_item.text().strip():
                        existing_keys.add(key_item.text().strip())

                next_key = ""
                for candidate in range(start_key, end_key + 1):
                    if str(candidate) not in existing_keys:
                        next_key = str(candidate)
                        break

                key_item = self._make_readonly_item(next_key)
            else:
                key_item = QTableWidgetItem("")

            map_table.insertRow(row_count)
            map_table.setItem(row_count, 0, key_item)
            map_table.setItem(row_count, 1, QTableWidgetItem(""))
            map_table.selectRow(row_count)
            self._hide_vertical_header(map_table)

        def del_row():
            map_table = table_state["table_widget"]
            selected_row = map_table.currentRow()
            if selected_row >= 0:
                map_table.removeRow(selected_row)
                if map_table.rowCount() > 0:
                    map_table.selectRow(min(selected_row, map_table.rowCount() - 1))

        scroll_area, map_table = self._build_table_shell(
            section_name,
            section_def,
            headers=["Key", "Value"],
            on_add=add_row,
            on_remove=del_row,
        )

        horizontal_header = map_table.horizontalHeader()
        if horizontal_header:
            horizontal_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            horizontal_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        map_table.setColumnWidth(0, 150)

        self._populate_dynamic_map_table(map_table, section_name, section_def)
        self._hide_vertical_header(map_table)
        table_state["table_widget"] = map_table

        self._table_schemas[section_name] = section_def
        self.widgets_map[section_name] = ("dynamic_map", map_table)
        return scroll_area

    def _populate_dynamic_map_table(self, map_table, section_name, section_def):
        rows_data = list(self.config.items(section_name)) if self.config.has_section(section_name) else []
        has_key_range = "key_range" in section_def

        map_table.setRowCount(len(rows_data))
        for row_idx, (key_str, val_str) in enumerate(rows_data):
            key_item = self._make_readonly_item(key_str) if has_key_range else QTableWidgetItem(key_str)
            map_table.setItem(row_idx, 0, key_item)
            map_table.setItem(row_idx, 1, QTableWidgetItem(val_str))

    # ------------------------------------------------------------------
    # Config Sync & Dialog Actions
    # ------------------------------------------------------------------

    def _populate_config_from_ui(self):
        """Write current UI values into `self.config`."""
        for key_info, (config_section_type, target_widget) in self.widgets_map.items():
            if config_section_type == "unified_vehicles" and isinstance(target_widget, QTableWidget):
                sec_def = self._table_schemas.get(key_info, {})
                sources = sec_def.get("vehicle_types", {})
                label_to_key = {s_def.get("label", s_key): s_key for s_key, s_def in sources.items()}

                # Reset each `<source>.vehicles` section once so removed entries are cleared
                for s_key in sources:
                    ini_section = f"{s_key}.vehicles"
                    if self.config.has_section(ini_section):
                        self.config.remove_section(ini_section)
                    self.config.add_section(ini_section)

                for row_idx in range(target_widget.rowCount()):
                    key_item = target_widget.item(row_idx, 0)
                    name_item = target_widget.item(row_idx, 1)
                    type_combo_box = target_widget.cellWidget(row_idx, 2)
                    if not (key_item and name_item):
                        continue

                    s_key = label_to_key.get(type_combo_box.currentText()) if isinstance(type_combo_box, QComboBox) else None
                    if s_key:
                        self.config.set(f"{s_key}.vehicles", key_item.text().strip(), name_item.text().strip())

            elif config_section_type == "dynamic_map" and isinstance(target_widget, QTableWidget):
                section_name = key_info
                if self.config.has_section(section_name):
                    self.config.remove_section(section_name)
                self.config.add_section(section_name)

                for row_idx in range(target_widget.rowCount()):
                    key_item = target_widget.item(row_idx, 0)
                    val_item = target_widget.item(row_idx, 1)
                    if key_item and key_item.text().strip():
                        self.config.set(
                            section_name,
                            key_item.text().strip(),
                            val_item.text().strip() if val_item else "",
                        )

            else:
                section_name, option_name = key_info
                if not self.config.has_section(section_name):
                    self.config.add_section(section_name)
                self.config.set(section_name, option_name, self._get_widget_value(config_section_type, target_widget))

    def _refresh_ui_from_config(self):
        """Reload all widgets from `self.config` (falling back to schema defaults)."""
        for key_info, (config_section_type, target_widget) in self.widgets_map.items():
            if config_section_type == "unified_vehicles" and isinstance(target_widget, QTableWidget):
                self._populate_vehicle_dynamic_map_table(target_widget, self._table_schemas.get(key_info, {}))
                self._hide_vertical_header(target_widget)
            elif config_section_type == "dynamic_map" and isinstance(target_widget, QTableWidget):
                self._populate_dynamic_map_table(target_widget, key_info, self._table_schemas.get(key_info, {}))
                self._hide_vertical_header(target_widget)
            else:
                section_name, option_name = key_info
                option_contents = self._find_option_def(section_name, option_name)
                value = self._get_val_from_config(section_name, option_name, option_contents)
                self._set_widget_value(config_section_type, option_contents, target_widget, value)

    def _load_defaults_into_ui(self):
        """Reset all widgets to their schema default values without writing to disk."""
        for key_info, (config_section_type, target_widget) in self.widgets_map.items():
            if config_section_type == "unified_vehicles" and isinstance(target_widget, QTableWidget):
                sources = self._table_schemas.get(key_info, {}).get("vehicle_types", {})
                key_to_label = {s_key: s_def.get("label", s_key) for s_key, s_def in sources.items()}
                default_type = key_to_label.get(next(iter(sources.keys())), "") if sources else ""

                target_widget.setRowCount(1)
                target_widget.setItem(0, 0, self._make_readonly_item("1"))
                target_widget.setItem(0, 1, QTableWidgetItem(""))

                type_combo_box = QComboBox()
                type_combo_box.addItems(list(key_to_label.values()))
                if default_type and type_combo_box.findText(default_type) != -1:
                    type_combo_box.setCurrentText(default_type)
                target_widget.setCellWidget(0, 2, type_combo_box)
                self._hide_vertical_header(target_widget)

            elif config_section_type == "dynamic_map" and isinstance(target_widget, QTableWidget):
                sec_def = self._table_schemas.get(key_info, {})
                has_key_range = "key_range" in sec_def
                target_widget.setRowCount(1)
                key_item = self._make_readonly_item("1") if has_key_range else QTableWidgetItem("")
                target_widget.setItem(0, 0, key_item)
                target_widget.setItem(0, 1, QTableWidgetItem(""))
                self._hide_vertical_header(target_widget)

            else:
                section_name, option_name = key_info
                option_contents = self._find_option_def(section_name, option_name)
                self._set_widget_value(config_section_type, option_contents, target_widget, option_contents.get("default"))

    def _save_config_to_path(self, file_path):
        """Sync UI state into `self.config` and write it to `file_path`."""
        self._populate_config_from_ui()
        try:
            with open(file_path, "w") as configfile:
                self.config.write(configfile)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration file:\n{e}")
            return False

    def on_save(self):
        if not self._save_config_to_path(self.config_file):
            return

        reply = QMessageBox.question(
            self,
            "Settings Saved",
            "Settings have been successfully saved.\n\nWould you like to restart the application now for changes to take effect?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        self.restart_requested = reply == QMessageBox.StandardButton.Yes
        self.accept()

    def on_export(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Settings",
            self.config_file,
            "INI Files (*.ini);;All Files (*)",
        )
        if not file_path:
            return

        if self._save_config_to_path(file_path):
            QMessageBox.information(self, "Export Successful", f"Settings successfully exported to:\n{file_path}")

    def on_reload(self):
        confirm = QMessageBox.question(
            self,
            "Reload from File",
            "Are you sure you want to discard unsaved changes and reload from file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.config = self._load_config_parser(self.config_file)
        self._refresh_ui_from_config()
        QMessageBox.information(self, "Reloaded", "Settings reloaded from file successfully.")

    def on_defaults(self):
        confirm = QMessageBox.question(
            self,
            "Load Defaults",
            "Are you sure you want to reset all settings to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._load_defaults_into_ui()
        QMessageBox.information(self, "Defaults Loaded", "All settings have been reset to their defaults. Click Save to apply.")
