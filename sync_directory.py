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


with open("config.txt", "r", encoding='utf-8') as config_file:
    config = eval(config_file.read())

folder_a = config['folder_a']
folder_b = config['folder_b']
sync_time = config['sync_time']

folder_hashes = {}


def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('sync_log.txt'),
            logging.StreamHandler()
        ]
    )


def get_folder_hash(folder_path):
    """
    Calculate a hash that represents the current state of the folder
    including all files and their modification times
    """
    folder_state = []

    for root, dirs, files in os.walk(folder_path):
        # Sort directories and files for consistent ordering
        dirs.sort()
        files.sort()

        for file in files:
            file_path = os.path.join(root, file)
            try:
                # Get file stats
                stats = os.stat(file_path)
                # Create a string combining file path, size, and modification time
                file_info = f"{file_path}|{stats.st_size}|{stats.st_mtime}"
                folder_state.append(file_info)
            except Exception as e:
                logging.warning(f"Error processing file {file_path}: {str(e)}")
                continue

    # Create a hash of all file information
    hasher = hashlib.md5()
    for item in folder_state:
        hasher.update(item.encode())

    return hasher.hexdigest()


def has_changes(folder1, folder2, previous_hashes):
    """
    Check if either folder has changed since the last sync
    Returns True if changes are detected, False otherwise
    """
    current_hash1 = get_folder_hash(folder1)
    current_hash2 = get_folder_hash(folder2)

    # Get previous hashes or use empty strings if not available
    prev_hash1 = previous_hashes.get(folder1, '')
    prev_hash2 = previous_hashes.get(folder2, '')

    # Update stored hashes
    previous_hashes[folder1] = current_hash1
    previous_hashes[folder2] = current_hash2

    # Return True if either folder has changed
    return current_hash1 != prev_hash1 or current_hash2 != prev_hash2


def compare_files(file1, file2):
    """Compare two files to check if they are identical"""
    return filecmp.cmp(file1, file2, shallow=False)


def get_drive_path_by_label(drive_label):
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


def get_available_drives():
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


def is_flash_drive_name_or_path(config_path):
    drivers = get_available_drives()
    for driver, label in drivers:
        if label == config_path:
            flash_drive_path = get_drive_path_by_label(label)
            return flash_drive_path

    return config_path


def sync_folders(source_dir, target_dir):
    """
    Synchronize two folders recursively
    Args:
        source_dir (str): Path to the source directory
        target_dir (str): Path to the target directory
    """
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        logging.info(f"Created directory: {target_dir}")

    # Get lists of files and directories in both folders
    source_contents = set(os.listdir(source_dir))
    target_contents = set(os.listdir(target_dir))

    # Files/folders to copy from source to target
    to_copy = source_contents - target_contents

    # Files/folders to copy from target to source
    to_copy_back = target_contents - source_contents

    # Items present in both directories
    common_items = source_contents.intersection(target_contents)

    # Process items that need to be copied from source to target
    for item in to_copy:
        source_path = os.path.join(source_dir, item)
        target_path = os.path.join(target_dir, item)

        if os.path.isfile(source_path):
            shutil.copy2(source_path, target_path)
            logging.info(f"Copied file: {item} (source → target)")
        elif os.path.isdir(source_path):
            shutil.copytree(source_path, target_path)
            logging.info(f"Copied directory: {item} (source → target)")

    # Process items that need to be copied from target to source
    for item in to_copy_back:
        source_path = os.path.join(source_dir, item)
        target_path = os.path.join(target_dir, item)

        if os.path.isfile(target_path):
            shutil.copy2(target_path, source_path)
            logging.info(f"Copied file: {item} (target → source)")
        elif os.path.isdir(target_path):
            shutil.copytree(target_path, source_path)
            logging.info(f"Copied directory: {item} (target → source)")

    # Recursively check common directories and update files if needed
    for item in common_items:
        source_path = os.path.join(source_dir, item)
        target_path = os.path.join(target_dir, item)

        if os.path.isfile(source_path) and os.path.isfile(target_path):
            if not compare_files(source_path, target_path):
                # Use the most recently modified file
                source_mtime = os.path.getmtime(source_path)
                target_mtime = os.path.getmtime(target_path)

                if source_mtime > target_mtime:
                    shutil.copy2(source_path, target_path)
                    logging.info(f"Updated file: {item} (source → target)")
                else:
                    shutil.copy2(target_path, source_path)
                    logging.info(f"Updated file: {item} (target → source)")

        elif os.path.isdir(source_path) and os.path.isdir(target_path):
            sync_folders(source_path, target_path)


def sync_job(folder1, folder2):
    checked_folder_a = is_flash_drive_name_or_path(folder1)
    checked_folder_b = is_flash_drive_name_or_path(folder2)
    if not os.path.exists(checked_folder_a) or not os.path.exists(checked_folder_b):
        logging.error("One or both folders do not exist!")
        return

    try:
        logging.info("Checking for changes...")

        # Only sync if changes are detected
        if has_changes(checked_folder_a, checked_folder_b, folder_hashes):
            logging.info("Changes detected, starting synchronization...")
            logging.info(f"Folder 1: {checked_folder_a}")
            logging.info(f"Folder 2: {checked_folder_b}")

            sync_folders(checked_folder_a, checked_folder_b)

            logging.info("Synchronization completed successfully!")
        else:
            logging.info("No changes detected, skipping synchronization")

    except Exception as e:
        logging.error(f"An error occurred during synchronization: {str(e)}")


def main():
    """Main function to run the folder synchronization"""
    setup_logging()

    logging.info("Scheduler started. Will sync folders every 60 minutes.")
    # Keep the script running
    while True:
        logging.info(f"First sync folder: {folder_a}")
        logging.info(f"Second sync folder: {folder_b}")
        sync_job(folder_a, folder_b)
        time.sleep(sync_time)


if __name__ == "__main__":
    main()