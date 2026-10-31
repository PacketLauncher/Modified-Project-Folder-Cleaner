Modified Project Folder Cleaner | Written by Gal Shemesh (PacketLauncher)

This program generates a clean backup of a modified project folder, by comparing it to an original source directory and excluding any leftovers that don't exist in the original source, while preserving all of the original files timestamps.

This comes in handy when you're working on an offline copy of a Visual Studio source project, and then wish to save a clean backup of the ENTIRE PROJECT with your modifications, without all the cache files, dependencies and leftovers that Visual Studio generates when you compile.


How to use:
-----------
1. Set in the "Original path" field the path of the ORIGINAL source project directory (this most likely be an extracted ZIP archive of the project source files that you downloaded from GitHub).

2. Set in the "Modified path" field the path of the MODIFIED source project directory (the one with your changes).

3. Set in the "Save cleaned folder to" field the path where you wish the cleaned folder to be generated.

4. Optioal: set any additional files you created in the modified folder that DON'T exist in the original source in order to include them with the generated backup; you can separate them with either a comma / semicolon / colon and can either wrap or omit them by double-quotes for names that contain a space.

5. Hit "Create Cleaned Modified Folder" and wait for the program to finish. Once done, you'd be prompt with an option to view the folder.


Change log:
===========
v1.0.0.0
October 31, 2026
- Initial release.


Making an EXE from the source Python scripts:

* This is for developers who wish to make adjustments to the source script for generating an EXE.

1. Install Python.

2. From CMD, install:
	py -m pip install tkinterdnd2 <-- drag and drop support for the program (mandatory)
	py -m pip install pyinstaller pillow <-- for making an EXE
	py -m pip install pillow <-- for converting the PNG icon into ICO

3. To make a new icon, update/replace the Icon.png file and run "Python PNG_icon_to_ICO.py" from CMD.

4. To make an EXE, either run "BuildMe.bat" or run from CMD:
	python -m PyInstaller --onefile --windowed --clean --name "Project Modified Folder Cleaner" --icon "Icon.ico" --add-data "Icon.ico;." --collect-all tkinterdnd2 "Project_Modified_Folder_Cleaner.py"
	
5. Run "Build_Leftovers_CleanUp.bat" to clean up this folder after building the EXE.