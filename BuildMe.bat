@echo off

python -m PyInstaller --onefile --windowed --clean --name "Modified Project Folder Cleaner" --icon "Icon.ico" --add-data "Icon.ico;." --collect-all tkinterdnd2 "Modified_Project_Folder_Cleaner.py"

if exist "Modified Project Folder Cleaner.exe" del "Modified Project Folder Cleaner.exe"

move "dist\Modified Project Folder Cleaner.exe"



