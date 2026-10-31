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
