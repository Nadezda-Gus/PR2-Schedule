import os
import shutil
import zipfile
import logging
import argparse
import schedule
import time
import pickle
from datetime import datetime

class Task:
    def __init__(self, task_id, operation, source, destination=None, schedule_time=None, archive_name=None):
        self.task_id = task_id
        self.operation = operation
        self.source = source
        self.destination = destination
        self.schedule_time = schedule_time
        self.archive_name = archive_name

    def __repr__(self):
        return f"<Task id={self.task_id}, operation={self.operation}, source={self.source}, schedule={self.schedule_time}>"

class FileOperations:
    @staticmethod
    def copy(source, destination):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Источник не найден: {source}")
        if os.path.isdir(source):
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
            shutil.copy2(source, destination)

    @staticmethod
    def move(source, destination):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Источник не найден: {source}")
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        shutil.move(source, destination)

    @staticmethod
    def delete(source):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Файл не найден: {source}")
        if os.path.isdir(source):
            shutil.rmtree(source)
        else:
            os.remove(source)

    @staticmethod
    def archive(source, archive_name):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Источник не найден: {source}")
        with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if os.path.isdir(source):
                for root, _, files in os.walk(source):
                    for file in files:
                        full_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_path, os.path.dirname(source))
                        zipf.write(full_path, arcname)
            else:
                zipf.write(source, os.path.basename(source))

class Logger:
    def __init__(self, log_file="file_scheduler.log"):
        logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S", encoding="utf-8")

    @staticmethod
    def log(task, status):
        logging.info(
            f"Task ID {task.task_id}: {task.operation} | source={task.source} | destination={task.destination} | Status: {status}"
        )

class Scheduler:
    def __init__(self, storage_file=None):
        if storage_file is None:
            storage_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.pkl")
        self.storage_file = storage_file
        self.tasks = []
        self.next_id = 1
        self.logger = Logger()
        self._load_tasks(register=False)

    def _load_tasks(self, register=False):
        if not os.path.exists(self.storage_file):
            return
        try:
            with open(self.storage_file, "rb") as f:
                data = pickle.load(f)
            self.tasks = data.get("tasks", [])
            self.next_id = data.get("next_id", 1)
            if register:
                for task in self.tasks:
                    self._schedule_task(task)
        except Exception as e:
            print(f"Не удалось загрузить задачи: {e}")

    def _save_tasks(self):
        try:
            with open(self.storage_file, "wb") as f:
                pickle.dump({"tasks": self.tasks, "next_id": self.next_id}, f)
        except Exception as e:
            print(f"Не удалось сохранить задачи: {e}")

    def add_task(self, operation, source, destination=None,
                 schedule_time=None, archive_name=None):
        task = Task(self.next_id, operation, source, destination, schedule_time, archive_name)
        self.tasks.append(task)
        self.next_id += 1
        self._schedule_task(task)
        self._save_tasks()
        print(f"Добавлена задача: {task}")

    def _schedule_task(self, task):
        if not task.schedule_time:
            return
        parts = task.schedule_time.split(":")
        if parts[0] == "daily" and len(parts) == 3:
            time_str = f"{parts[1]}:{parts[2]}"
            schedule.every().day.at(time_str).do(self.run_task, task)
        elif parts[0] == "weekly" and len(parts) == 4:
            day_map = {
                "mon": schedule.every().monday,
                "tue": schedule.every().tuesday,
                "wed": schedule.every().wednesday,
                "thu": schedule.every().thursday,
                "fri": schedule.every().friday,
                "sat": schedule.every().saturday,
                "sun": schedule.every().sunday,
            }
            day = parts[1].lower()
            time_str = f"{parts[2]}:{parts[3]}"
            if day in day_map:
                day_map[day].at(time_str).do(self.run_task, task)

    def run_task(self, task):
        try:
            if task.operation == "copy":
                FileOperations.copy(task.source, task.destination)
            elif task.operation == "move":
                FileOperations.move(task.source, task.destination)
            elif task.operation == "delete":
                FileOperations.delete(task.source)
            elif task.operation == "archive":
                if not task.archive_name:
                    raise ValueError("Не задано имя архива (--archive_name)")
                FileOperations.archive(task.source, task.archive_name)
            else:
                raise ValueError(f"Неизвестная операция: {task.operation}")
            self.logger.log(task, "Success")
            print(f"[{datetime.now()}] Задача {task.task_id} выполнена успешно.")
        except Exception as e:
            self.logger.log(task, f"Failed - {str(e)}")
            print(f"[{datetime.now()}] Ошибка в задаче {task.task_id}: {e}")

    def view_tasks(self):
        if not self.tasks:
            print("Список задач пуст.")
            return
        print("Запланированные задачи:")
        for task in self.tasks:
            print(task)

    def remove_task(self, task_id):
        for task in self.tasks:
            if task.task_id == task_id:
                self.tasks.remove(task)
                self._save_tasks()
                print(f"Задача {task_id} удалена.")
                return
        print(f"Задача с ID {task_id} не найдена.")

    def start(self):
        schedule.clear()
        self._load_tasks(register=True)
        if not self.tasks:
            print("Нет задач для выполнения. Сначала добавьте задачи командой add.")
            return
        print(f"Шедулер запущен ({len(self.tasks)} задач). Нажмите Ctrl+C для остановки.")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nШедулер остановлен.")

def print_hints():
    print("=" * 65)
    print("ПОДСКАЗКИ ПО ИСПОЛЬЗОВАНИЮ ФАЙЛОВОГО ШЕДУЛЕРА")
    print("=" * 65)
    print()
    print("Напишите \"py FileName.py --help\", чтобы получить информацию о командах.")
    print("Напишите \"py FileName.py --help --(команда)\", чтобы узнать написание конкретной команды.")
    print()
    print("Примеры команд:")
    print("  py FileName.py add --operation copy --source file.txt --destination D:/backup/file.txt")
    print("  py FileName.py add --operation move --source file.txt --destination D:/archive/file.txt")
    print("  py FileName.py add --operation delete --source file.txt")
    print("  py FileName.py add --operation archive --source myfolder --archive_name myfolder.zip")
    print()
    print("С расписанием:")
    print("  py FileName.py add --operation copy --source a.txt --destination b.txt --schedule daily:10:00")
    print("  py FileName.py add --operation copy --source a.txt --destination b.txt --schedule weekly:mon:10:00")
    print()
    print("Просмотр задач:")
    print("  py FileName.py view")
    print()
    print("Удаление задачи по ID:")
    print("  py FileName.py remove --task_id 1")
    print()
    print("Запуск шедулера:")
    print("  py FileName.py start")
    print("=" * 65)
    print()


def main():
    scheduler = Scheduler()

    import sys
    if len(sys.argv) == 1:
        print_hints()
    parser = argparse.ArgumentParser(
        description="Файловый шедулер — планировщик файловых операций (copy, move, delete, archive).",
        epilog=(
            "Примеры использования:\n"
            "  py FileName.py add --operation copy --source a.txt --destination b.txt\n"
            "  py FileName.py add --operation copy --source a.txt --destination b.txt --schedule daily:10:00\n"
            "  py FileName.py view\n"
            "  py FileName.py remove --task_id 1\n"
            "  py FileName.py start\n"
            "\n"
            "Для подробной справки по конкретной команде:\n"
            "  py FileName.py add --help\n"
            "  py FileName.py view --help\n"
            "  py FileName.py remove --help\n"
            "  py FileName.py start --help"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=["add", "view", "remove", "start"],
                        help="Команда: add, view, remove, start")
    parser.add_argument("--operation",
                        choices=["copy", "move", "delete", "archive"],
                        help="Тип операции")
    parser.add_argument("--source", help="Исходный файл или папка")
    parser.add_argument("--destination", help="Целевой путь (для copy/move)")
    parser.add_argument("--archive_name", help="Имя архива (для archive)")
    parser.add_argument("--schedule",
                        help="Расписание: 'daily:10:00' или 'weekly:mon:10:00'")
    parser.add_argument("--task_id", type=int, help="ID задачи для удаления")

    args = parser.parse_args()

    if args.command == "add":
        if args.operation and args.source:
            scheduler.add_task(
                operation=args.operation,
                source=args.source,
                destination=args.destination,
                schedule_time=args.schedule,
                archive_name=args.archive_name
            )
        else:
            print("Укажите --operation и --source")
            print_hints()
    elif args.command == "view":
        scheduler.view_tasks()
    elif args.command == "remove":
        if args.task_id:
            scheduler.remove_task(args.task_id)
        else:
            print("Укажите --task_id")
    elif args.command == "start":
        scheduler.start()

if __name__ == "__main__":
    main()