import json
import asyncio
import pyaudio
import os
from vosk import Model, KaldiRecognizer
from PyQt5.QtCore import QThread, pyqtSignal
from rapidfuzz import process
from plyer import notification
import keyboard as kb
from pynput.keyboard import Key, Controller
from utils import is_russian_layout

keyboard = Controller()


def press_and_release(key):
    keyboard.press(key)
    keyboard.release(key)


async def left():
    press_and_release(Key.left)


async def delete_word():
    with keyboard.pressed(Key.ctrl):
        press_and_release(Key.backspace)


async def right():
    press_and_release(Key.right)


async def write_text(text):
    kb.write(text, delay=0.005)


async def fuzzy_match(text, commands, threshold=75):
    if len(text) <= 2:
        return None
    match, score, _ = process.extractOne(text, commands)
    if score >= threshold:
        return match
    return None


class VoiceThread(QThread):
    update_status_signal = pyqtSignal(str)
    voice_control_state_changed = pyqtSignal(bool)

    def __init__(self, model_path, mode='default'):
        super().__init__()
        self.model_path = model_path
        self.mode = mode
        self.running = True
        self.voice_control_enabled = False
        self.russian_layout = is_russian_layout()
        self.replacements_file = "replacements.json"
        self.replacements = {}
        self.load_replacements()

    def load_replacements(self):
        """Загружает замены из JSON файла. Если файла нет, создает с базовыми настройками."""
        if not os.path.exists(self.replacements_file):
            self.create_default_replacements()
        try:
            with open(self.replacements_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.replacements = {}
                for item in data:
                    patterns = item.get("patterns", "")
                    replacement = item.get("replacement", "")
                    if not patterns or replacement is None:
                        continue
                    for pattern in patterns.split(','):
                        pattern = pattern.strip()
                        if pattern:
                            self.replacements[pattern] = replacement
        except Exception as e:
            print(f"Ошибка загрузки замен: {e}")
            self.replacements = {}

    def create_default_replacements(self):
        """Создает файл replacements.json с базовыми заменами."""
        default_data = [
            {"patterns": "восклицательный знак", "replacement": "!"},
            {"patterns": "собака", "replacement": "@"},
            {"patterns": "двойная кавычках,двойные кавычки", "replacement": "\"\""},
            {"patterns": "кавычках,кавычки", "replacement": "''"},
            {"patterns": "решётка", "replacement": "#"},
            {"patterns": "доллар", "replacement": "$"},
            {"patterns": "точка с запятой", "replacement": ";"},
            {"patterns": "процент", "replacement": "%"},
            {"patterns": "двоеточие", "replacement": ":"},
            {"patterns": "ампер сант,ампер санд,ампер санкт,амбер санд,амбер саунд,амбер санкт,ампир санд,амбер сант,андерсон", "replacement": "&"},
            {"patterns": "вопросительный знак,знак вопроса", "replacement": "?"},
            {"patterns": "звёздочка", "replacement": "*"},
            {"patterns": "квадратные скобки,квадратная скобка", "replacement": "[]"},
            {"patterns": "фигурные скобки,фигурная скобка", "replacement": "{}"},
            {"patterns": "скобки,скобка", "replacement": "()"},
            {"patterns": "тире,минус", "replacement": "-"},
            {"patterns": "плюс", "replacement": "+"},
            {"patterns": "равно", "replacement": "="},
            {"patterns": "слэш", "replacement": "/"},
            {"patterns": "один", "replacement": "1"},
            {"patterns": "два", "replacement": "2"},
            {"patterns": "три", "replacement": "3"},
            {"patterns": "четыре", "replacement": "4"},
            {"patterns": "пять", "replacement": "5"},
            {"patterns": "шесть", "replacement": "6"},
            {"patterns": "семь", "replacement": "7"},
            {"patterns": "восемь", "replacement": "8"},
            {"patterns": "девять", "replacement": "9"},
            {"patterns": "ноль", "replacement": "0"},
            {"patterns": "запятая", "replacement": ", "},
            {"patterns": "нижнее подчёркивание", "replacement": "_"},
            {"patterns": "больше", "replacement": ">"},
            {"patterns": "меньше", "replacement": "<"},
            {"patterns": "ё", "replacement": "е"},
            {"patterns": "дрочка,дочка", "replacement": "."},
            {"patterns": "конец строки", "replacement": ";"}
        ]
        try:
            with open(self.replacements_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Не удалось создать файл замен: {e}")

    def run(self):
        asyncio.run(self.async_run())

    def toggle_voice_control(self):
        self.voice_control_enabled = not self.voice_control_enabled
        self.voice_control_state_changed.emit(self.voice_control_enabled)
        if self.voice_control_enabled:
            self.update_status_signal.emit('Голосовое управление включено!')
            notification.notify(title="Voice1C", message="Программа запущена!", app_icon='open.ico', timeout=2)
        else:
            self.update_status_signal.emit('Голосовое управление остановлено!')
            notification.notify(title="Voice1C", message="Программа остановлена!", app_icon='close.ico', timeout=2)

    async def async_run(self):
        try:
            model = Model(self.model_path)
        except Exception as e:
            self.update_status_signal.emit(f'Ошибка загрузки модели: {str(e)}')
            return

        rec = KaldiRecognizer(model, 16000)
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)

        self.update_status_signal.emit(f'Голосовое управление запущено в режиме: {"1С" if self.mode == "1c" else "Обычный"}')

        try:
            stream.start_stream()
            async for text in self.async_listen(stream, rec):
                if not self.running:
                    break

                zbstxt = self.process_text(text)

                if text in ['старт']:
                    self.voice_control_enabled = True
                    self.voice_control_state_changed.emit(True)
                    self.update_status_signal.emit('Голосовое управление включено!')
                    notification.notify(title="Voice1C", message="Программа запущена!", app_icon='open.ico', timeout=2)

                elif text in ['стоп', 'сто']:
                    self.voice_control_enabled = False
                    self.voice_control_state_changed.emit(False)
                    self.update_status_signal.emit('Голосовое управление остановлено!')
                    notification.notify(title="Voice1C", message="Программа остановлена!", app_icon='close.ico', timeout=2)

                elif self.voice_control_enabled:
                    await self.perform_action_async(text, zbstxt)

        except Exception as e:
            self.update_status_signal.emit(f'Ошибка при работе с аудиопотоком: {str(e)}')
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    async def async_listen(self, stream, rec):
        while self.running:
            data = await asyncio.to_thread(stream.read, 1024, exception_on_overflow=False)
            if rec.AcceptWaveform(data):
                answer = json.loads(rec.Result())
                if answer.get('text'):
                    yield answer['text']
            await asyncio.sleep(0.05)

    def process_text(self, text):
        for pattern, replacement in self.replacements.items():
            text = text.replace(pattern, replacement)

        if self.mode == '1c':
            text = text.title().replace(' ', '')
            text = text.replace('Пробел', ' ')
            text = text.replace('=', ' = ')
            text = text.replace(',', ', ')
            text = text.replace('Нал', "NULL")
            text = text.replace('Ну', "NULL")
        else:
            text = text.replace('пробел', ' ')
            text = text.replace('точка', '.')
        return text

    async def perform_action_async(self, text, zbstxt):
        commands = {
            "интер": ["эндер", "интер"],
            "таб": ["тап", "так", "пап"],
            "удали": ["удали", "доли"],
            "точка": ["точка"],
            "копье": ["копье", "как ее", "как её"],
            "паста": ["паста", "пастор", "просто"],
            "вырезать": ["вырезать", 'вязать'],
            "поиск": ["поиск"],
            "перенос": ["перенос"]
        }

        for action, keywords in commands.items():
            match = await fuzzy_match(text, keywords)
            if match:
                if action == "интер":
                    press_and_release(Key.enter)
                elif action == "таб":
                    press_and_release(Key.tab)
                elif action == "удали":
                    await delete_word()
                elif action == 'точка':
                    self.point()
                elif action == "перенос":
                    press_and_release(";")
                    press_and_release(Key.enter)
                elif action == "копье":
                    self.copy_text()
                elif action == "паста":
                    self.paste_text()
                elif action == "вырезать":
                    self.cut_text()
                elif action == "поиск":
                    self.search_text()

        return await write_text(zbstxt)

    # --- клавиши для действий ---
    def point(self):
        press_and_release('.' if self.russian_layout else '.')

    def copy_text(self):
        with keyboard.pressed(Key.ctrl):
            press_and_release('с' if self.russian_layout else 'c')

    def paste_text(self):
        with keyboard.pressed(Key.ctrl):
            press_and_release('м' if self.russian_layout else 'v')

    def cut_text(self):
        with keyboard.pressed(Key.ctrl):
            press_and_release('ч' if self.russian_layout else 'x')

    def search_text(self):
        with keyboard.pressed(Key.ctrl):
            press_and_release('а' if self.russian_layout else 'f')