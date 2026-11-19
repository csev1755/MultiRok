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
    """Convert config or INI values into a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in frozenset({"true", "1", "yes", "on"})
    return bool(value)


def _parse_int(value, fallback=0):
    """Safely convert a value to int, returning `fallback` when missing or invalid."""
    if value is None:
        return fallback
    try:
        return int(value)
    except ValueError, TypeError:
        return fallback


class NoScrollSpinBox(QSpinBox):
    """QSpinBox that ignores wheel events so scrolling a tab won't change numbers."""

    def wheelEvent(self, event):
        event.ignore()


class SettingsEditorDialog(QDialog):
    """Modal settings dialog generated from `CONFIG_SCHEMA` and a `settings.ini` file."""

    def __init__(self, config_file="settings.ini", parent=None):
        super().__init__(parent)
        self.config_file = config_file
        self.config = self._load_config_parser(config_file)

        # Maps schema section keys or (section, option) tuples to (kind, widget_or_table)
        self.widgets_map = {}
        # Stores each table section's schema dict so reload/defaults stays schema-driven
        self._table_schemas = {}
        self.restart_requested = False

        self.setWindowTitle("Settings Editor")
        self.resize(780, 550)

        self._init_ui()
        self._populate_navigation()

    @staticmethod
    def _load_config_parser(path):
        """Create a case-preserving ConfigParser and load `path` if it exists."""
        parser = configparser.ConfigParser()
        parser.optionxform = lambda optionstr: optionstr
        if path and os.path.exists(path):
            parser.read(path)
        return parser

    def _init_ui(self):
        """Build the splitter navigation layout and bottom action buttons."""
        main_layout = QVBoxLayout(self)

        self.nav_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.nav_splitter)

        self.nav_tree_widget = QTreeWidget()
        self.nav_tree_widget.setHeaderHidden(True)
        self.nav_tree_widget.setIndentation(14)
        self.nav_tree_widget.currentItemChanged.connect(self._on_tree_item_changed)
        self.nav_splitter.addWidget(self.nav_tree_widget)

        self.page_stack = QStackedWidget()
        self.nav_splitter.addWidget(self.page_stack)

        button_layout = QHBoxLayout()
        self.reload_button = QPushButton("Reload from File")
        self.defaults_button = QPushButton("Load Defaults")
        self.export_button = QPushButton("Export")
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        self.reload_button.clicked.connect(self.on_reload)
        self.defaults_button.clicked.connect(self.on_defaults)
        self.export_button.clicked.connect(self.on_save_as)
        self.save_button.clicked.connect(self.on_save)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.reload_button)
        button_layout.addWidget(self.defaults_button)
        button_layout.addWidget(self.export_button)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        main_layout.addLayout(button_layout)

    def _add_nav_item(self, page_widget, label, parent_tree_item=None):
        """Add `page_widget` to the stacked view and create a matching tree item."""
        page_index = self.page_stack.addWidget(page_widget)
        tree_item = QTreeWidgetItem([label])
        tree_item.setData(0, Qt.ItemDataRole.UserRole, page_index)
        if parent_tree_item is None:
            self.nav_tree_widget.addTopLevelItem(tree_item)
        else:
            parent_tree_item.addChild(tree_item)
        return tree_item

    def _populate_navigation(self):
        """Populate pages and navigation tree items from `CONFIG_SCHEMA`."""
        for section_name, section_def in CONFIG_SCHEMA.items():
            section_type = section_def.get("type", "section")
            label = section_def.get("label", section_name)

            if section_type == "section":
                section_page = self.create_section_tab(section_name, section_def)
                self._add_nav_item(section_page, label)

            elif section_type in ("unified_dynamic_map", "vehicle_dynamic_map"):
                vehicles_page = self.create_unified_vehicles_tab(section_name, section_def)
                parent_tree_item = self._add_nav_item(vehicles_page, label)

                # Each source with options gets a child page under the Vehicles node
                for source_key, source_def in section_def.get("sources", {}).items():
                    if source_def.get("options"):
                        source_label = source_def.get("label", source_key)
                        source_page = self.create_section_tab(source_key, source_def)
                        self._add_nav_item(source_page, source_label, parent_tree_item=parent_tree_item)

                parent_tree_item.setExpanded(True)

            elif section_type == "dynamic_map":
                map_page = self.create_dynamic_map_tab(section_name, section_def)
                self._add_nav_item(map_page, label)

        self.nav_tree_widget.resizeColumnToContents(0)
        tree_width = max(self.nav_tree_widget.sizeHintForColumn(0) + 30, 150)
        self.nav_splitter.setSizes([tree_width, max(self.width() - tree_width, 400)])

        if self.nav_tree_widget.topLevelItemCount() > 0:
            self.nav_tree_widget.setCurrentItem(self.nav_tree_widget.topLevelItem(0))

    def _on_tree_item_changed(self, current_item, _previous_item):
        if current_item is None:
            return
        page_index = current_item.data(0, Qt.ItemDataRole.UserRole)
        if page_index is not None:
            self.page_stack.setCurrentIndex(page_index)

    # ------------------------------------------------------------------
    # Standard Option Tabs
    # ------------------------------------------------------------------

    def create_section_tab(self, section_name, section_def):
        """Create a scrollable form tab for standard key/value schema options."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        content_widget = QWidget()
        form_layout = QVBoxLayout(content_widget)
        form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setSpacing(16)

        for opt_key, opt_def in section_def.get("options", {}).items():
            opt_type = opt_def.get("type", "str")
            current_val = self._get_config_or_default(section_name, opt_key, opt_def)
            option_widget = self._create_widget_for_option(opt_type, opt_def, current_val)
            self.widgets_map[(section_name, opt_key)] = (opt_type, option_widget)

            field_container = QWidget()
            field_layout = QVBoxLayout(field_container)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(4)

            title_label = QLabel(f"<b>{opt_def.get('label', opt_key)}</b>")
            field_layout.addWidget(title_label)

            description = opt_def.get("description", "")
            if description:
                description_label = QLabel(f"<small style='color: gray;'>{description}</small>")
                description_label.setWordWrap(True)
                field_layout.addWidget(description_label)

            if opt_type != "bool":
                option_widget.setMaximumWidth(300)

            input_row_layout = QHBoxLayout()
            input_row_layout.setContentsMargins(0, 0, 0, 0)
            input_row_layout.addWidget(option_widget)
            input_row_layout.addStretch()
            field_layout.addLayout(input_row_layout)

            form_layout.addWidget(field_container)

        form_layout.addStretch()
        scroll_area.setWidget(content_widget)
        return scroll_area

    def _get_config_or_default(self, section_name, opt_key, opt_def):
        if self.config.has_section(section_name) and self.config.has_option(section_name, opt_key):
            return self.config.get(section_name, opt_key)
        return opt_def.get("default")

    def _create_widget_for_option(self, opt_type, opt_def, value):
        if opt_type == "bool":
            option_widget = QCheckBox()
        elif opt_type == "int":
            option_widget = NoScrollSpinBox()
            option_widget.setRange(opt_def.get("min", -999999), opt_def.get("max", 999999))
        elif opt_type == "choice":
            option_widget = QComboBox()
            option_widget.addItems(opt_def.get("choices", []))
        else:
            option_widget = QLineEdit()

        self._set_widget_value(opt_type, opt_def, option_widget, value)
        return option_widget

    @staticmethod
    def _set_widget_value(opt_type, opt_def, option_widget, value):
        default_int = _parse_int(opt_def.get("default"), 0)

        if opt_type == "bool" and isinstance(option_widget, QCheckBox):
            option_widget.setChecked(_parse_bool(value))
        elif opt_type == "int" and isinstance(option_widget, QSpinBox):
            option_widget.setValue(_parse_int(value, fallback=default_int))
        elif opt_type == "choice" and isinstance(option_widget, QComboBox):
            choices = opt_def.get("choices", [])
            str_val = str(value) if value is not None else ""
            if str_val in choices:
                option_widget.setCurrentText(str_val)
        elif isinstance(option_widget, QLineEdit):
            option_widget.setText(str(value) if value is not None else "")

    @staticmethod
    def _get_widget_value(opt_type, option_widget):
        if opt_type == "bool" and isinstance(option_widget, QCheckBox):
            return str(option_widget.isChecked()).lower()
        if opt_type == "int" and isinstance(option_widget, QSpinBox):
            return str(option_widget.value())
        if opt_type == "choice" and isinstance(option_widget, QComboBox):
            return option_widget.currentText()
        if isinstance(option_widget, QLineEdit):
            return option_widget.text()
        return ""

    def _find_option_def(self, section_name, opt_key):
        """Look up an option definition in top-level sections or nested `sources`."""
        for sec_name, sec_def in CONFIG_SCHEMA.items():
            if sec_name == section_name and "options" in sec_def:
                return sec_def["options"].get(opt_key, {})
            for s_key, s_def in sec_def.get("sources", {}).items():
                if s_key == section_name and "options" in s_def:
                    return s_def["options"].get(opt_key, {})
        return {}

    # ------------------------------------------------------------------
    # Table Tabs (Vehicles & Dynamic Maps)
    # ------------------------------------------------------------------

    @staticmethod
    def _hide_vertical_header(table_widget):
        vertical_header = table_widget.verticalHeader()
        if vertical_header:
            vertical_header.setVisible(False)
            vertical_header.hide()
            vertical_header.setDefaultSectionSize(24)

    def _build_table_tab_shell(self, section_name, section_def, headers, on_add, on_remove):
        """Create common scroll container, title/description, add/remove buttons, and table."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        content_widget = QWidget()
        tab_layout = QVBoxLayout(content_widget)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        tab_layout.setContentsMargins(8, 8, 8, 8)
        tab_layout.setSpacing(6)

        label_text = section_def.get("label", section_name)
        heading_label = QLabel(f"<h2 style='margin-top: 0; margin-bottom: 0;'>{label_text}</h2>")
        tab_layout.addWidget(heading_label)

        description = section_def.get("description", "")
        if description:
            description_label = QLabel(f"<small style='color: gray;'>{description}</small>")
            description_label.setWordWrap(True)
            tab_layout.addWidget(description_label)

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

        tab_layout.addLayout(button_bar_layout)
        tab_layout.addWidget(table_widget)
        scroll_area.setWidget(content_widget)
        return scroll_area, table_widget

    @staticmethod
    def _make_readonly_item(text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def create_unified_vehicles_tab(self, section_name, section_def):
        """Create a table editing numbered vehicles across `<source>.vehicles` INI sections."""
        sources = section_def.get("sources", {})
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

        scroll_area, vehicle_table = self._build_table_tab_shell(
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

        refresh_rows = self._populate_unified_vehicles_table(vehicle_table, section_def)
        self._hide_vertical_header(vehicle_table)
        table_state["table_widget"] = vehicle_table
        table_state["refresh_rows"] = refresh_rows

        self._table_schemas[section_name] = section_def
        self.widgets_map[section_name] = ("unified_vehicles", vehicle_table)
        return scroll_area

    def _populate_unified_vehicles_table(self, vehicle_table, section_def):
        """Load numbered vehicle rows from `<source>.vehicles` sections and return `refresh_rows`."""
        sources = section_def.get("sources", {})
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

    def create_dynamic_map_tab(self, section_name, section_def):
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

        scroll_area, map_table = self._build_table_tab_shell(
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
        for key_info, (kind, target_widget) in self.widgets_map.items():
            if kind == "unified_vehicles" and isinstance(target_widget, QTableWidget):
                sec_def = self._table_schemas.get(key_info, {})
                sources = sec_def.get("sources", {})
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

            elif kind == "dynamic_map" and isinstance(target_widget, QTableWidget):
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
                section_name, opt_key = key_info
                if not self.config.has_section(section_name):
                    self.config.add_section(section_name)
                self.config.set(section_name, opt_key, self._get_widget_value(kind, target_widget))

    def _refresh_ui_from_config(self):
        """Reload all widgets from `self.config` (falling back to schema defaults)."""
        for key_info, (kind, target_widget) in self.widgets_map.items():
            if kind == "unified_vehicles" and isinstance(target_widget, QTableWidget):
                self._populate_unified_vehicles_table(target_widget, self._table_schemas.get(key_info, {}))
                self._hide_vertical_header(target_widget)
            elif kind == "dynamic_map" and isinstance(target_widget, QTableWidget):
                self._populate_dynamic_map_table(target_widget, key_info, self._table_schemas.get(key_info, {}))
                self._hide_vertical_header(target_widget)
            else:
                section_name, opt_key = key_info
                opt_def = self._find_option_def(section_name, opt_key)
                value = self._get_config_or_default(section_name, opt_key, opt_def)
                self._set_widget_value(kind, opt_def, target_widget, value)

    def _load_defaults_into_ui(self):
        """Reset all widgets to their schema default values without writing to disk."""
        for key_info, (kind, target_widget) in self.widgets_map.items():
            if kind == "unified_vehicles" and isinstance(target_widget, QTableWidget):
                sources = self._table_schemas.get(key_info, {}).get("sources", {})
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

            elif kind == "dynamic_map" and isinstance(target_widget, QTableWidget):
                sec_def = self._table_schemas.get(key_info, {})
                has_key_range = "key_range" in sec_def
                target_widget.setRowCount(1)
                key_item = self._make_readonly_item("1") if has_key_range else QTableWidgetItem("")
                target_widget.setItem(0, 0, key_item)
                target_widget.setItem(0, 1, QTableWidgetItem(""))
                self._hide_vertical_header(target_widget)

            else:
                section_name, opt_key = key_info
                opt_def = self._find_option_def(section_name, opt_key)
                self._set_widget_value(kind, opt_def, target_widget, opt_def.get("default"))

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

    def on_save_as(self):
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
