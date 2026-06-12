import json
import os
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QMessageBox, QAbstractItemView)
from PyQt5.QtCore import pyqtSignal

class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()  # Сигнал об изменении настроек

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки замен")
        self.setModal(True)
        self.resize(600, 400)
        self.replacements_file = "replacements.json"
        self.load_data()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Таблица
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Слова для замены (через запятую)", "Замена"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.populate_table()
        layout.addWidget(self.table)

        # Кнопки управления таблицей (Добавить/Удалить)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.add_btn = QPushButton("Добавить")
        self.remove_btn = QPushButton("Удалить")
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Кнопки диалога (Сохранить/Отмена)
        dialog_btn_layout = QHBoxLayout()
        dialog_btn_layout.addStretch()
        self.save_btn = QPushButton("Сохранить")
        self.cancel_btn = QPushButton("Отмена")
        dialog_btn_layout.addWidget(self.save_btn)
        dialog_btn_layout.addWidget(self.cancel_btn)
        dialog_btn_layout.addStretch()
        layout.addLayout(dialog_btn_layout)

        # Подключение сигналов
        self.add_btn.clicked.connect(self.add_row)
        self.remove_btn.clicked.connect(self.remove_selected_rows)
        self.save_btn.clicked.connect(self.save_settings)
        self.cancel_btn.clicked.connect(self.reject)

        # Локальный стиль для кнопок в диалоге (чтобы не растягивались)
        self.setStyleSheet("""
            SettingsDialog QPushButton {
                min-width: 80px;
                max-width: 120px;
            }
        """)

    def load_data(self):
        if not os.path.exists(self.replacements_file):
            self.data = []
        else:
            try:
                with open(self.replacements_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл замен:\n{e}")
                self.data = []

    def populate_table(self):
        self.table.setRowCount(len(self.data))
        for row, item in enumerate(self.data):
            patterns = item.get("patterns", "")
            replacement = item.get("replacement", "")
            self.table.setItem(row, 0, QTableWidgetItem(patterns))
            self.table.setItem(row, 1, QTableWidgetItem(replacement))

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(""))

    def remove_selected_rows(self):
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        for row in sorted(selected_rows, reverse=True):
            self.table.removeRow(row)

    def save_settings(self):
        new_data = []
        for row in range(self.table.rowCount()):
            patterns_item = self.table.item(row, 0)
            replacement_item = self.table.item(row, 1)
            if patterns_item and replacement_item:
                raw_patterns = patterns_item.text().strip()
                replacement = replacement_item.text().strip()
                if raw_patterns and replacement:
                    # Приводим паттерны к нижнему регистру и убираем лишние пробелы
                    patterns_list = [p.strip().lower() for p in raw_patterns.split(',') if p.strip()]
                    # Убираем дубликаты (опционально)
                    # patterns_list = list(dict.fromkeys(patterns_list))
                    cleaned_patterns = ', '.join(patterns_list)
                    new_data.append({"patterns": cleaned_patterns, "replacement": replacement})
        try:
            with open(self.replacements_file, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "Успех", "Настройки сохранены.")
            self.settings_changed.emit()  # Сигнал об изменении
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл:\n{e}")