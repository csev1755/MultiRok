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


class NonScrollingSpinBox(QSpinBox):
    """
    A QSpinBox that ignores mouse wheel events to prevent accidental value changes.
    """

    def wheelEvent(self, event):
        event.ignore()


class SettingsEditorDialog(QDialog):
    """
    Dynamic settings editor dialog generated from CONFIG_SCHEMA and settings.ini.
    """

    def __init__(self, config_file="settings.ini", parent=None):
        super().__init__(parent)
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.config.optionxform = lambda optionstr: optionstr
        self.config.read(self.config_file)

        self.widgets_map = {}  # Maps section/option identifiers to input widgets
        self.restart_requested = False

        self.setWindowTitle("Settings Editor")
        self.resize(780, 550)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Splitter to hold Navigation Tree on the left and Content Stack on the right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setIndentation(14)
        splitter.addWidget(self.tree_widget)

        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)

        # Populate Navigation Tree and Stacked Content
        for section_name, section_def in CONFIG_SCHEMA.items():
            section_type = section_def.get("type", "section")
            label = section_def.get("label", section_name)

            if section_type == "section":
                widget = self.create_section_tab(section_name, section_def)
                index = self.stack.addWidget(widget)
                item = QTreeWidgetItem([label])
                item.setData(0, Qt.ItemDataRole.UserRole, index)
                self.tree_widget.addTopLevelItem(item)

            elif section_type in ("unified_dynamic_map", "vehicle_dynamic_map"):
                widget = self.create_unified_vehicles_tab(section_name, section_def)
                index = self.stack.addWidget(widget)
                parent_item = QTreeWidgetItem([label])
                parent_item.setData(0, Qt.ItemDataRole.UserRole, index)
                self.tree_widget.addTopLevelItem(parent_item)

                # Dynamically branch child configuration items for sources under vehicles
                sources = section_def.get("sources", {})
                for source_key, source_def in sources.items():
                    if source_def.get("options"):
                        source_label = source_def.get("label", source_key)
                        source_widget = self.create_section_tab(source_key, source_def)
                        source_index = self.stack.addWidget(source_widget)
                        child_item = QTreeWidgetItem([source_label])
                        child_item.setData(0, Qt.ItemDataRole.UserRole, source_index)
                        parent_item.addChild(child_item)
                parent_item.setExpanded(True)

            elif section_type == "dynamic_map":
                widget = self.create_dynamic_map_tab(section_name, section_def)
                index = self.stack.addWidget(widget)
                item = QTreeWidgetItem([label])
                item.setData(0, Qt.ItemDataRole.UserRole, index)
                self.tree_widget.addTopLevelItem(item)

        # Auto-fit navigation tree width to its contents and adjust splitter
        self.tree_widget.resizeColumnToContents(0)
        tree_width = self.tree_widget.sizeHintForColumn(0) + 30
        splitter.setSizes([max(tree_width, 150), 780 - max(tree_width, 150)])

        # Connect tree selection to stack index switcher
        self.tree_widget.currentItemChanged.connect(self.on_tree_item_changed)
        if self.tree_widget.topLevelItemCount() > 0:
            self.tree_widget.setCurrentItem(self.tree_widget.topLevelItem(0))

        # Bottom Buttons
        button_layout = QHBoxLayout()

        # Left Utility Buttons (including Export)
        self.reload_btn = QPushButton("Reload from File")
        self.defaults_btn = QPushButton("Load Defaults")
        self.export_btn = QPushButton("Export")

        # Right Action Buttons
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")

        self.reload_btn.clicked.connect(self.on_reload)
        self.defaults_btn.clicked.connect(self.on_defaults)
        self.export_btn.clicked.connect(self.on_save_as)
        self.save_btn.clicked.connect(self.on_save)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.reload_btn)
        button_layout.addWidget(self.defaults_btn)
        button_layout.addWidget(self.export_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(button_layout)

    def _configure_single_row_table(self, table: QTableWidget):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        vert_header = table.verticalHeader()
        if vert_header:
            vert_header.hide()
            vert_header.setDefaultSectionSize(24)

    def on_tree_item_changed(self, current, previous):
        if current:
            index = current.data(0, Qt.ItemDataRole.UserRole)
            if index is not None:
                self.stack.setCurrentIndex(index)

    def create_section_tab(self, section_name, section_def):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form_layout = QVBoxLayout(container)
        form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setSpacing(16)

        options = section_def.get("options", {})
        for opt_key, opt_def in options.items():
            opt_type = opt_def.get("type", "str")
            default_val = opt_def.get("default")
            label_text = opt_def.get("label", opt_key)
            description = opt_def.get("description", "")

            current_val = default_val
            if self.config.has_section(section_name) and self.config.has_option(section_name, opt_key):
                current_val = self.config.get(section_name, opt_key)

            widget = self._create_widget_for_option(opt_type, opt_def, current_val)
            self.widgets_map[(section_name, opt_key)] = (opt_type, widget)

            block_widget = QWidget()
            block_layout = QVBoxLayout(block_widget)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(4)

            title_label = QLabel(f"<b>{label_text}</b>")
            block_layout.addWidget(title_label)

            if description:
                desc_label = QLabel(f"<small style='color: gray;'>{description}</small>")
                desc_label.setWordWrap(True)
                block_layout.addWidget(desc_label)

            input_layout = QHBoxLayout()
            input_layout.setContentsMargins(0, 0, 0, 0)

            if opt_type not in ("bool",):
                widget.setMaximumWidth(300)

            input_layout.addWidget(widget)
            input_layout.addStretch()
            block_layout.addLayout(input_layout)

            form_layout.addWidget(block_widget)

        form_layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _populate_unified_vehicles_table(self, table: QTableWidget, section_def: dict):
        sources = section_def.get("sources", {})
        label_to_key = {s_def.get("label", s_key): s_key for s_key, s_def in sources.items()}
        key_to_label = {s_key: s_def.get("label", s_key) for s_key, s_def in sources.items()}
        all_type_labels = list(label_to_key.keys())
        default_type_label = key_to_label.get(next(iter(sources.keys())), "Smart Port Serial") if sources else ""

        key_to_data = {}
        for s_key in sources:
            ini_sec = f"{s_key}.vehicles"
            expected_label = key_to_label[s_key]
            if self.config.has_section(ini_sec):
                for k, v in self.config.items(ini_sec):
                    try:
                        int_k = int(k)
                        key_to_data[int_k] = (v, expected_label)
                    except ValueError:
                        continue

        max_detected_key = max(key_to_data.keys()) if key_to_data else 0
        total_rows = max(max_detected_key, 1)

        rows_data = []
        for i in range(1, total_rows + 1):
            if i in key_to_data:
                rows_data.append(key_to_data[i])
            else:
                rows_data.append(("", default_type_label))

        table.setRowCount(len(rows_data))

        def update_row_keys_and_validation():
            for r in range(table.rowCount()):
                k_item = QTableWidgetItem(str(r + 1))
                k_item.setFlags(k_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(r, 0, k_item)

                combo = table.cellWidget(r, 2)
                if not isinstance(combo, QComboBox):
                    combo = QComboBox()
                    table.setCellWidget(r, 2, combo)

                current_type = combo.currentText()
                combo.clear()

                allowed_labels = []
                for lbl in all_type_labels:
                    s_key = label_to_key[lbl]
                    max_k = sources[s_key].get("max_key")
                    if max_k is not None and (r + 1) > max_k:
                        continue
                    allowed_labels.append(lbl)

                combo.addItems(allowed_labels)
                if current_type in allowed_labels:
                    combo.setCurrentText(current_type)
                elif allowed_labels:
                    combo.setCurrentIndex(0)

        for row_idx, (name_val, _) in enumerate(rows_data):
            table.setItem(row_idx, 1, QTableWidgetItem(name_val))
            table.setCellWidget(row_idx, 2, QComboBox())

        update_row_keys_and_validation()

        for row_idx, (_, type_val) in enumerate(rows_data):
            combo = table.cellWidget(row_idx, 2)
            if isinstance(combo, QComboBox) and combo.findText(type_val) != -1:
                combo.setCurrentText(type_val)

        return update_row_keys_and_validation

    def create_unified_vehicles_tab(self, section_name, section_def):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        label_text = section_def.get("label", section_name)
        title_label = QLabel(f"<h2 style='margin-top: 0; margin-bottom: 0;'>{label_text}</h2>")
        layout.addWidget(title_label)

        description = section_def.get("description", "")
        if description:
            desc_label = QLabel(f"<small style='color: gray;'>{description}</small>")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Number", "Name", "Type"])

        header = table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)

        table.setColumnWidth(0, 60)
        table.setColumnWidth(2, 160)
        

        update_row_keys_and_validation = self._populate_unified_vehicles_table(table, section_def)

        self._configure_single_row_table(table)

        sources = section_def.get("sources", {})
        finite_max_keys = [s.get("max_key") for s in sources.values() if s.get("max_key") is not None]
        global_max_rows = max(finite_max_keys) if (sources and len(finite_max_keys) == len(sources)) else None

        btn_layout = QHBoxLayout()
        add_row_btn = QPushButton("Add Entry")
        del_row_btn = QPushButton("Remove Selected")

        def add_row():
            r_count = table.rowCount()
            if global_max_rows is not None and r_count >= global_max_rows:
                QMessageBox.information(self, "Limit Reached", f"Maximum of {global_max_rows} entries reached.")
                return
            table.insertRow(r_count)
            table.setItem(r_count, 1, QTableWidgetItem(""))
            table.setCellWidget(r_count, 2, QComboBox())
            update_row_keys_and_validation()
            table.selectRow(r_count)

        def del_row():
            selected = table.currentRow()
            if selected >= 0:
                table.removeRow(selected)
                update_row_keys_and_validation()
                if table.rowCount() > 0:
                    table.selectRow(min(selected, table.rowCount() - 1))

        add_row_btn.clicked.connect(add_row)
        del_row_btn.clicked.connect(del_row)
        btn_layout.addWidget(add_row_btn)
        btn_layout.addWidget(del_row_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addWidget(table)
        scroll.setWidget(container)

        self.widgets_map[section_name] = ("unified_vehicles", table)
        return scroll

    def _populate_dynamic_map_table(self, table: QTableWidget, section_name: str, section_def: dict):
        rows_data = []
        if self.config.has_section(section_name):
            for key, val in self.config.items(section_name):
                rows_data.append((key, val))

        has_key_range = "key_range" in section_def
        table.setRowCount(len(rows_data))
        for row_idx, (k, v) in enumerate(rows_data):
            k_item = QTableWidgetItem(k)
            v_item = QTableWidgetItem(v)
            if has_key_range:
                k_item.setFlags(k_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row_idx, 0, k_item)
            table.setItem(row_idx, 1, v_item)

    def create_dynamic_map_tab(self, section_name, section_def):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        label_text = section_def.get("label", section_name)
        title_label = QLabel(f"<h2 style='margin-top: 0; margin-bottom: 0;'>{label_text}</h2>")
        layout.addWidget(title_label)

        description = section_def.get("description", "")
        if description:
            desc_label = QLabel(f"<small style='color: gray;'>{description}</small>")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Key", "Value"])

        header = table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        table.setColumnWidth(0, 150)
        self._populate_dynamic_map_table(table, section_name, section_def)
        self._configure_single_row_table(table)

        key_range = section_def.get("key_range")

        btn_layout = QHBoxLayout()
        add_row_btn = QPushButton("Add Entry")
        del_row_btn = QPushButton("Remove Selected")

        def add_row():
            r_count = table.rowCount()
            if key_range:
                start_k, end_k = key_range
                max_entries = end_k - start_k + 1
                if r_count >= max_entries:
                    QMessageBox.information(
                        self,
                        "Limit Reached",
                        f"Maximum of {max_entries} entries ({start_k}–{end_k}) reached.",
                    )
                    return

                existing_keys = set()
                for r in range(r_count):
                    item = table.item(r, 0)
                    raw_text = item.text() if item else None
                    if raw_text:
                        existing_keys.add(raw_text.strip())
                next_key = ""
                for candidate in range(start_k, end_k + 1):
                    if str(candidate) not in existing_keys:
                        next_key = str(candidate)
                        break

                k_item = QTableWidgetItem(next_key)
                k_item.setFlags(k_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                k_item = QTableWidgetItem("")

            table.insertRow(r_count)
            table.setItem(r_count, 0, k_item)
            table.setItem(r_count, 1, QTableWidgetItem(""))
            table.selectRow(r_count)

        def del_row():
            selected = table.currentRow()
            if selected >= 0:
                table.removeRow(selected)
                if table.rowCount() > 0:
                    table.selectRow(min(selected, table.rowCount() - 1))

        add_row_btn.clicked.connect(add_row)
        del_row_btn.clicked.connect(del_row)
        btn_layout.addWidget(add_row_btn)
        btn_layout.addWidget(del_row_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addWidget(table)
        scroll.setWidget(container)

        self.widgets_map[section_name] = ("dynamic_map", table)
        return scroll

    def _create_widget_for_option(self, opt_type, opt_def, current_val):
        if opt_type == "bool":
            widget = QCheckBox()
            if isinstance(current_val, str):
                widget.setChecked(current_val.lower() in ("true", "1", "yes", "on"))
            else:
                widget.setChecked(bool(current_val))
            return widget

        elif opt_type == "int":
            widget = NonScrollingSpinBox()
            widget.setRange(opt_def.get("min", -999999), opt_def.get("max", 999999))
            try:
                val_to_cast = current_val if current_val is not None else opt_def.get("default", 0)
                widget.setValue(int(val_to_cast))
            except (ValueError, TypeError):
                default_fallback = opt_def.get("default", 0)
                widget.setValue(int(default_fallback if default_fallback is not None else 0))
            return widget

        elif opt_type == "choice":
            widget = QComboBox()
            choices = opt_def.get("choices", [])
            widget.addItems(choices)
            if str(current_val) in choices:
                widget.setCurrentText(str(current_val))
            return widget

        else:
            widget = QLineEdit()
            widget.setText(str(current_val) if current_val is not None else "")
            return widget

    def _find_option_def(self, section_name: str, opt_key: str) -> dict:
        for sec_name, sec_def in CONFIG_SCHEMA.items():
            if sec_name == section_name and "options" in sec_def:
                return sec_def["options"].get(opt_key, {})
            if "sources" in sec_def:
                for s_key, s_def in sec_def["sources"].items():
                    if s_key == section_name and "options" in s_def:
                        return s_def["options"].get(opt_key, {})
        return {}

    def _populate_config_from_ui(self):
        """Helper to collect current UI field values and update self.config object."""
        for key_info, (opt_type, widget) in self.widgets_map.items():
            if opt_type == "unified_vehicles":
                for s_key in CONFIG_SCHEMA.get("vehicle_types", {}).get("sources", {}):
                    ini_sec = f"{s_key}.vehicles"
                    if self.config.has_section(ini_sec):
                        self.config.remove_section(ini_sec)
                    self.config.add_section(ini_sec)

                sources = CONFIG_SCHEMA.get("vehicle_types", {}).get("sources", {})
                label_to_key = {s_def.get("label", s_key): s_key for s_key, s_def in sources.items()}

                table = widget
                if isinstance(table, QTableWidget):
                    for row in range(table.rowCount()):
                        k_item = table.item(row, 0)
                        name_item = table.item(row, 1)
                        combo = table.cellWidget(row, 2)

                        if k_item and name_item:
                            key_str = k_item.text().strip()
                            name_str = name_item.text().strip()

                            v_label = combo.currentText() if isinstance(combo, QComboBox) else ""
                            s_key = label_to_key.get(v_label)
                            if s_key:
                                ini_sec = f"{s_key}.vehicles"
                                if not self.config.has_section(ini_sec):
                                    self.config.add_section(ini_sec)
                                self.config.set(ini_sec, key_str, name_str)

            elif opt_type == "dynamic_map":
                section_name = key_info
                if self.config.has_section(section_name):
                    self.config.remove_section(section_name)
                self.config.add_section(section_name)

                table = widget
                if isinstance(table, QTableWidget):
                    for row in range(table.rowCount()):
                        k_item = table.item(row, 0)
                        v_item = table.item(row, 1)
                        if k_item and k_item.text().strip():
                            k_text = k_item.text().strip()
                            v_text = v_item.text().strip() if v_item else ""
                            self.config.set(section_name, k_text, v_text)
            else:
                section_name, opt_key = key_info
                if not self.config.has_section(section_name):
                    self.config.add_section(section_name)

                if opt_type == "bool":
                    val_str = str(widget.isChecked()).lower() if isinstance(widget, QCheckBox) else "false"
                elif opt_type == "int":
                    val_str = str(widget.value()) if isinstance(widget, QSpinBox) else "0"
                elif opt_type == "choice":
                    val_str = widget.currentText() if isinstance(widget, QComboBox) else ""
                else:
                    val_str = widget.text() if isinstance(widget, QLineEdit) else ""

                self.config.set(section_name, opt_key, val_str)

    def on_save(self):
        self._populate_config_from_ui()

        try:
            with open(self.config_file, "w") as configfile:
                self.config.write(configfile)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration file:\n{e}")
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
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Settings", self.config_file, "INI Files (*.ini);;All Files (*)")
        if file_path:
            self._populate_config_from_ui()
            try:
                with open(file_path, "w") as configfile:
                    self.config.write(configfile)
                QMessageBox.information(self, "Export Successful", f"Settings successfully exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export configuration file:\n{e}")

    def on_reload(self):
        confirm = QMessageBox.question(
            self,
            "Reload from File",
            "Are you sure you want to discard unsaved changes and reload from file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.config.clear()
        self.config.optionxform = lambda optionstr: optionstr
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)

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

    def _refresh_ui_from_config(self):
        for key_info, (opt_type, widget) in self.widgets_map.items():
            if opt_type == "unified_vehicles":
                if isinstance(widget, QTableWidget):
                    self._populate_unified_vehicles_table(widget, CONFIG_SCHEMA.get("vehicle_types", {}))

            elif opt_type == "dynamic_map":
                section_name = key_info
                if isinstance(widget, QTableWidget):
                    self._populate_dynamic_map_table(widget, section_name, CONFIG_SCHEMA.get(section_name, {}))

            else:
                section_name, opt_key = key_info
                opt_def = self._find_option_def(section_name, opt_key)
                default_val = opt_def.get("default")
                current_val = default_val
                if self.config.has_section(section_name) and self.config.has_option(section_name, opt_key):
                    current_val = self.config.get(section_name, opt_key)

                if opt_type == "bool":
                    if isinstance(widget, QCheckBox):
                        widget.setChecked(str(current_val).lower() in ("true", "1", "yes", "on"))
                elif opt_type == "int":
                    if isinstance(widget, QSpinBox):
                        try:
                            val_to_cast = current_val if current_val is not None else opt_def.get("default", 0)
                            widget.setValue(int(val_to_cast))
                        except (ValueError, TypeError):
                            fallback = opt_def.get("default", 0)
                            widget.setValue(int(fallback if fallback is not None else 0))
                elif opt_type == "choice":
                    if isinstance(widget, QComboBox):
                        choices = opt_def.get("choices", [])
                        if str(current_val) in choices:
                            widget.setCurrentText(str(current_val))
                else:
                    if isinstance(widget, QLineEdit):
                        widget.setText(str(current_val) if current_val is not None else "")

    def _load_defaults_into_ui(self):
        for key_info, (opt_type, widget) in self.widgets_map.items():
            if opt_type == "unified_vehicles":
                if isinstance(widget, QTableWidget):
                    sources = CONFIG_SCHEMA.get("vehicle_types", {}).get("sources", {})
                    key_to_label = {s_key: s_def.get("label", s_key) for s_key, s_def in sources.items()}
                    default_type = key_to_label.get(next(iter(sources.keys())), "") if sources else ""

                    widget.setRowCount(1)
                    k_item = QTableWidgetItem("1")
                    k_item.setFlags(k_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    widget.setItem(0, 0, k_item)
                    widget.setItem(0, 1, QTableWidgetItem(""))

                    combo = QComboBox()
                    combo.addItems(list(key_to_label.values()))
                    if default_type and combo.findText(default_type) != -1:
                        combo.setCurrentText(default_type)
                    widget.setCellWidget(0, 2, combo)

            elif opt_type == "dynamic_map":
                section_name = key_info
                if isinstance(widget, QTableWidget):
                    sec_def = CONFIG_SCHEMA.get(section_name, {})
                    has_key_range = "key_range" in sec_def
                    widget.setRowCount(1)
                    k_item = QTableWidgetItem("1" if has_key_range else "")
                    if has_key_range:
                        k_item.setFlags(k_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    widget.setItem(0, 0, k_item)
                    widget.setItem(0, 1, QTableWidgetItem(""))

            else:
                section_name, opt_key = key_info
                opt_def = self._find_option_def(section_name, opt_key)
                default_val = opt_def.get("default")

                if opt_type == "bool":
                    if isinstance(widget, QCheckBox):
                        widget.setChecked(bool(default_val))
                elif opt_type == "int":
                    if isinstance(widget, QSpinBox):
                        try:
                            def_val = default_val if default_val is not None else 0
                            widget.setValue(int(def_val))
                        except (ValueError, TypeError):
                            widget.setValue(0)
                elif opt_type == "choice":
                    if isinstance(widget, QComboBox):
                        choices = opt_def.get("choices", [])
                        if str(default_val) in choices:
                            widget.setCurrentText(str(default_val))
                else:
                    if isinstance(widget, QLineEdit):
                        widget.setText(str(default_val) if default_val is not None else "")