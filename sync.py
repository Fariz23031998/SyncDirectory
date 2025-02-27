import os
import shutil
import filecmp
from datetime import datetime
import logging
import time
import hashlib
import string
import win32api
import win32file
import functools

# pyinstaller --onefile --name=SyncDirectory sync.py


today = datetime.now().strftime("%d-%m-%Y")
log_file = f"{today}-sync_log.txt"
with open("config.txt", "r", encoding='utf-8') as config_file:
    config = eval(config_file.read())

folders = config["folders"]
sync_time = config["sync_time"]
check_size = config["check_size"]
check_modified_time = config["check_modified_time"]
excepted_folders_or_files = config["excepted_folders_or_files"]

def write_logs(log):
    with open(log_file, "a", encoding="utf-8") as log_f:
        log_f.write(f"{datetime.now()} - {log}\n")


def is_path_excepted(excepted_list, file_path):
    if "System Volume Information" in file_path:
        return True
    split_path = file_path.split("\\")
    for e in excepted_list:
        if e in split_path:
            return True

    return False


class SyncFolders:
    def get_files_info(self, folder_path):
        files_infos = {}
        for root, dirs, files in os.walk(folder_path):
            # Sort directories and files for consistent ordering
            dirs.sort()
            files.sort()

            for file in files:
                file_path = os.path.join(root, file)
                if is_path_excepted(excepted_list=excepted_folders_or_files, file_path=file_path):
                    continue

                try:
                    stats = os.stat(file_path)
                    files_infos[file_path] = [file_path, stats.st_size, stats.st_mtime]

                except Exception as e:
                    print(f"Error processing file {file_path}: {str(e)}")
                    write_logs(f"Error processing file {file_path}: {str(e)}")
                    continue

        return files_infos

    def get_drive_path_by_label(self, drive_label):
        """
        Find drive path by its label
        Returns the drive path or None if not found
        """
        drives = []
        # Get list of drives
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            try:
                if win32file.GetDriveType(drive) == win32file.DRIVE_REMOVABLE:
                    try:
                        volume_name = win32api.GetVolumeInformation(drive)[0]
                        if volume_name.lower() == drive_label.lower():
                            return drive
                    except:
                        continue
            except:
                continue
        return None

    def get_available_drives(self):
        """Get list of available removable drives and their labels"""
        drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            try:
                if win32file.GetDriveType(drive) == win32file.DRIVE_REMOVABLE:
                    try:
                        volume_name = win32api.GetVolumeInformation(drive)[0]
                        drives.append((drive, volume_name))

                    except:
                        continue
            except:
                continue
        return drives

    def is_drive_name_or_path(self, config_path):
        drives = self.get_available_drives()
        for driver, label in drives:
            if label == config_path:
                drive_path = self.get_drive_path_by_label(label)
                return drive_path

        if config_path[-1] != "\\":
            config_path += "\\"
        return config_path

    def copy_file(self, source, destination):
        try:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(source, destination)
            # print(f"File copied successfully from {source} to {destination}")
            # write_logs(f"File copied successfully from {source} to {destination}")
        except FileNotFoundError:
            print(f"Source file {source} not found")
            write_logs(f"Source file {source} not found")
        except PermissionError:
            print("Permission denied")
            write_logs("Permission denied")
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            write_logs(f"An error occurred: {str(e)}")

    def compare_and_copy_files_claude_version(self, folders_dict):
        # Read all folder files once and store them
        folder_files = {}
        for key, folder_info in folders_dict.items():
            folder_path = self.is_drive_name_or_path(folder_info["path"])
            folder_files[key] = {
                "path": folder_path,
                "files": self.get_files_info(folder_path)
            }

        # Perform one-way sync between each pair of folders
        for main_key, main_data in folder_files.items():
            main_path = main_data["path"]
            main_files = main_data["files"]

            for dest_key, dest_data in folder_files.items():
                if main_key != dest_key:
                    dest_path = dest_data["path"]
                    dest_files = dest_data["files"]

                    # Sync files from main to destination
                    self.sync_folders(
                        main_files=main_files,
                        destination_files=dest_files,
                        main_path=main_path,
                        destination_path=dest_path
                    )

    def sync_all_folders(self, folders_dict):
        folders_list = self.create_list_from_dict(folders_dict)
        for folder_info in folders_list:
            checked_main_path = self.is_drive_name_or_path(folder_info["path"])
            main_folder_files = self.get_files_info(checked_main_path)
            for path in folder_info["dep_folders_path"]:
                checked_dest_path = self.is_drive_name_or_path(path)
                dest_folder_files = self.get_files_info(checked_dest_path)
                self.sync_folders(
                    main_files=main_folder_files,
                    destination_files=dest_folder_files,
                    main_path=checked_main_path,
                    destination_path=checked_dest_path
                )

    def sync_folders(self, main_files, destination_files, main_path, destination_path):
        if not os.path.exists(main_path):
            print(f"Main folder ({main_path}) does not exists")
            write_logs(f"Main folder ({main_path}) does not exists")
            return False

        if not os.path.exists(destination_path):
            print(f"Destination folder ({destination_path}) does not exists!")
            write_logs(f"Destination folder ({destination_path}) does not exists!")
            return False
        start_time = time.time()
        print(f"Copying was started, from: {main_path}, to: {destination_path}")
        write_logs(f"Copying was started, from: {main_path}, to: {destination_path}")
        print(f"Number of files in main folder ({main_path}): {len(main_files)}")
        write_logs(f"Number of files in main folder ({main_path}): {len(main_files)}")
        print(f"Number of files in destination folder ({destination_path}): {len(main_files)}")
        write_logs(f"Number of files in destination folder ({destination_path}): {len(main_files)}")
        count = 0
        main_path_slice_point = len(main_path)

        for key, info in main_files.items():
            converted_destination_path = f"{destination_path}{info[0][main_path_slice_point:]}"
            if converted_destination_path not in destination_files:
                count += 1
                self.copy_file(
                    source=info[0],
                    destination=converted_destination_path,
                )
                # print(f"{count}. Copied, path doesn't exists: {converted_destination_path}")
                # write_logs(f"{count}. Copied, path doesn't exists: {converted_destination_path}")

            elif check_size and info[1] != destination_files[converted_destination_path][1]:
                count += 1
                os.remove(converted_destination_path)
                self.copy_file(
                    source=info[0],
                    destination=converted_destination_path,
                )
                # print(f"{count}. Copied, file size has been changed: {info[1]}")
                # write_logs(f"{count}. Copied, file size has been changed: {info[1]}")

            elif check_modified_time and info[2] > destination_files[converted_destination_path][2]:
                count += 1
                os.remove(converted_destination_path)
                self.copy_file(
                    source=info[0],
                    destination=converted_destination_path,
                )
                # print(f"{count}. Copied, file has been modified: {info[0]}")
                # write_logs(f"{count}. Copied, file has been modified: {info[0]}")

        end_time = time.time()
        execution_time = end_time - start_time

        print(f"Total of {count} files was copied and it took {execution_time:.6f} seconds")
        write_logs(f"Total of {count} files was copied and it took {execution_time:.6f} seconds\n_______________________________")

    def create_list_from_dict(self, source_dict):
        main_folders = {k: v for k, v in source_dict.items() if v.get('is_main', False)}

        result_list = []

        for folder_name, folder_data in main_folders.items():
            dep_paths = [
                v['path'] for k, v in source_dict.items()
                if k != folder_name
            ]

            entry = {
                "name": folder_name,
                "path": folder_data['path'],
                "dep_folders_path": dep_paths
            }

            result_list.append(entry)

        return result_list


sync_folders = SyncFolders()


def main():
    while True:
        sync_folders.sync_all_folders(folders_dict=folders)
        time.sleep(sync_time)


if __name__ == "__main__":
    main()
