import ctypes
from ctypes import wintypes
import filecmp
import os
from pathlib import Path
import queue
import shutil
import stat
import tempfile
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sys

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

APP_TITLE = 'Modified Project Folder Cleaner'


def same_or_inside(path, root):
    try:
        return os.path.commonpath((os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root)))) == os.path.normcase(os.path.realpath(root))
    except ValueError:
        return False


def set_windows_times(source, destination):
    if os.name != 'nt':
        return
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    CreateFileW.restype = wintypes.HANDLE
    GetFileTime = kernel32.GetFileTime
    GetFileTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    SetFileTime = kernel32.SetFileTime
    SetFileTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    ACCESS_READ = 0x80
    ACCESS_WRITE = 0x100
    SHARE = 0x1 | 0x2 | 0x4
    FLAGS = 0x02000000 if os.path.isdir(source) else 0x80
    invalid = ctypes.c_void_p(-1).value
    src = CreateFileW(str(source), ACCESS_READ, SHARE, None, 3, FLAGS, None)
    if src == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        created, accessed, modified = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        if not GetFileTime(src, ctypes.byref(created), ctypes.byref(accessed), ctypes.byref(modified)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        CloseHandle(src)
    dst = CreateFileW(str(destination), ACCESS_WRITE, SHARE, None, 3, FLAGS, None)
    if dst == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not SetFileTime(dst, ctypes.byref(created), ctypes.byref(accessed), ctypes.byref(modified)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        CloseHandle(dst)


def scan(root):
    found = {}
    directories = {Path('.')}
    for current, subdirs, filenames in os.walk(root, followlinks=False):
        relative_dir = Path(current).relative_to(root)
        directories.add(relative_dir)
        for name in subdirs:
            p = Path(current) / name
            if p.is_symlink():
                raise ValueError(f'Symbolic-link directory is not supported: {p}')
        for name in filenames:
            p = Path(current) / name
            if p.is_symlink():
                raise ValueError(f'Symbolic-link file is not supported: {p}')
            found[str((relative_dir / name)).casefold()] = relative_dir / name
    return found, directories


def copy_selected(source_root, output_root, relative_paths, directories):
    needed = {Path('.')}
    for rel in relative_paths:
        parent = rel.parent
        while parent != Path('.'):
            needed.add(parent)
            parent = parent.parent
    for rel in sorted(needed, key=lambda p: (len(p.parts), str(p))):
        (output_root / rel).mkdir(parents=True, exist_ok=True)
    for rel in relative_paths:
        src, dst = source_root / rel, output_root / rel
        shutil.copy2(src, dst)
        set_windows_times(src, dst)
    for rel in sorted(needed, key=lambda p: (-len(p.parts), str(p))):
        src = source_root / rel
        dst = output_root / rel
        shutil.copystat(src, dst)
        set_windows_times(src, dst)


def parse_preserved_files(value):
    # Quotes are optional. Delimiters inside quotes are literal characters.
    items, current, quoted = [], [], False
    for char in value:
        if char == '"':
            quoted = not quoted
        elif char in ',;:' and not quoted:
            item = ''.join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)
    if quoted:
        raise ValueError('Unclosed quotation mark in additional filenames.')
    item = ''.join(current).strip()
    if item:
        items.append(item)
    return items


def resolve_preserved_files(names, original_files, modified_files, original_dirs, modified_dirs):
    # Match names anywhere in Modified. A directory selection includes its entire tree.
    extras = {key: rel for key, rel in modified_files.items() if key not in original_files}
    original_dir_keys = {str(rel).casefold() for rel in original_dirs}
    selected = {}
    selected_dirs = set()
    missing = []
    for name in names:
        normalized = name.replace('\\', '/').strip().strip('/')
        parts = normalized.split('/')
        if not normalized or any(part in ('', '.', '..') for part in parts):
            raise ValueError(f'Invalid additional file or folder name: {name}')
        target = normalized.casefold()
        # Preserve the existing filename matching behavior.
        matches = [(key, rel) for key, rel in extras.items()
                   if (key == target if '/' in normalized else rel.name.casefold() == target)]
        selected.update(matches)
        # Only additional directories qualify, just as only additional files qualify.
        dir_matches = [rel for rel in modified_dirs if rel != Path('.')
                       and str(rel).casefold() not in original_dir_keys
                       and (str(rel).replace('\\', '/').casefold() == target
                            if '/' in normalized else rel.name.casefold() == target)]
        for directory in dir_matches:
            prefix = str(directory).casefold() + '/'
            for rel in modified_dirs:
                if rel == directory or str(rel).replace('\\', '/').casefold().startswith(prefix):
                    selected_dirs.add(rel)
            for key, rel in modified_files.items():
                if key.replace('\\', '/').startswith(prefix):
                    selected[key] = rel
        if not matches and not dir_matches:
            missing.append(name)
    if missing:
        raise ValueError('These additional files or folders were not found exclusively in the modified folder:\n' + '\n'.join(missing))
    return selected, selected_dirs


def run_cleaning(original, modified, save, report, preserved_names):
    original_files, original_dirs = scan(original)
    modified_files, modified_dirs = scan(modified)
    preserved, preserved_dirs = resolve_preserved_files(preserved_names, original_files, modified_files, original_dirs, modified_dirs)
    if save.exists() or save.is_symlink():
        raise ValueError('The output folder already exists. Choose a new output folder.')
    save.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.project_clean_', dir=save.parent))
    try:
        report(f'Found {len(original_files)} original files. Building cleaned folder...')
        replaced = 0
        for rel in sorted(original_dirs, key=lambda p: (len(p.parts), str(p))):
            (staging / rel).mkdir(parents=True, exist_ok=True)
        for key, rel in sorted(original_files.items()):
            source = original / rel
            other_rel = modified_files.get(key)
            if other_rel is not None:
                other = modified / other_rel
                if not filecmp.cmp(source, other, shallow=False):
                    source = other
                    replaced += 1
            dest = staging / rel
            shutil.copy2(source, dest)
            set_windows_times(source, dest)
        for rel in sorted(preserved_dirs, key=lambda p: (len(p.parts), str(p))):
            (staging / rel).mkdir(parents=True, exist_ok=True)
        for key, rel in sorted(preserved.items()):
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            source = modified / rel
            shutil.copy2(source, dest)
            set_windows_times(source, dest)
        # Restore directory timestamps after copying all files.
        output_dirs = set(original_dirs) | preserved_dirs
        for rel in preserved.values():
            parent = rel.parent
            while parent != Path('.'):
                output_dirs.add(parent)
                parent = parent.parent
        output_dirs.add(Path('.'))
        modified_dir_lookup = {str(rel).casefold(): rel for rel in modified_dirs}
        original_dir_lookup = {str(rel).casefold(): rel for rel in original_dirs}
        for rel in sorted(output_dirs, key=lambda p: (-len(p.parts), str(p))):
            key = str(rel).casefold()
            src = (modified / modified_dir_lookup[key] if key in modified_dir_lookup
                   else original / original_dir_lookup[key])
            dst = staging / rel
            shutil.copystat(src, dst)
            set_windows_times(src, dst)
        excluded = len(modified_files.keys() - original_files.keys() - preserved.keys())
        os.replace(staging, save)
        report(f'Completed: {len(original_files)} original files, {replaced} modified replacements, {len(preserved)} files and {len(preserved_dirs)} folders explicitly preserved, {excluded} extra modified files excluded.')
    finally:
        if staging.exists():
            shutil.rmtree(staging)


class Application(TkinterDnD.Tk if TkinterDnD else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)

        base_dir = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        self.icon_path = os.path.join(base_dir, 'Icon.ico')
        self.png_icon_path = os.path.join(base_dir, 'Project_Modified_Folder_Cleaner_Icon.png')
        self.icon_image = None
        if os.path.isfile(self.png_icon_path):
            self.icon_image = tk.PhotoImage(file=self.png_icon_path)
            self.iconphoto(True, self.icon_image)
        if os.name == 'nt' and os.path.isfile(self.icon_path):
            self.iconbitmap(self.icon_path)

        self.geometry('670x455')
        self.minsize(670, 455)
        self.vars = [tk.StringVar() for _ in range(3)]
        self.preserve_var = tk.StringVar()
        self.events = queue.Queue()
        self.current_save = None
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill='both', expand=True)
        for index, label in enumerate(('Original path:', 'Modified path:', 'Save cleaned folder to:')):
            ttk.Label(frame, text=label).grid(row=index * 2, column=0, sticky='w', pady=(0, 3))
            entry = ttk.Entry(frame, textvariable=self.vars[index])
            entry.grid(row=index * 2 + 1, column=0, sticky='ew', pady=(0, 10))
            if DND_FILES is not None:
                entry.drop_target_register(DND_FILES)
                entry.dnd_bind('<<Drop>>', lambda event, i=index: self.on_drop(event, i))
            ttk.Button(frame, text='Browse...', command=lambda i=index: self.browse(i)).grid(row=index * 2 + 1, column=1, padx=(10, 0), sticky='ew', pady=(0, 10))
        ttk.Label(frame, text='Optional: preserve additional modified files or folders (comman / semicolon / colon separated):').grid(row=6, column=0, sticky='w', pady=(0, 3))
        ttk.Entry(frame, textvariable=self.preserve_var).grid(row=7, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        self.go = ttk.Button(frame, text='Create Cleaned Modified Folder', command=self.start)
        self.go.grid(row=8, column=0, columnspan=2, sticky='ew', pady=(4, 10))
        self.about_button = ttk.Button(frame, text='About', command=self.show_about)
        self.about_button.grid(row=11, column=1, sticky='e', pady=(8, 0))
        self.status = tk.StringVar(value='Ready')
        ttk.Label(frame, textvariable=self.status).grid(row=9, column=0, columnspan=2, sticky='w')
        self.log = tk.Text(frame, height=5, state='disabled', wrap='word')
        self.log.grid(row=10, column=0, columnspan=2, sticky='nsew', pady=(5, 0))
        frame.rowconfigure(10, weight=1)
        self.after(100, self.poll)

    def show_about(self):
        dialog = tk.Toplevel(self)
        if self.icon_image is not None:
            dialog.iconphoto(False, self.icon_image)
        if os.name == 'nt' and os.path.isfile(self.icon_path):
            dialog.iconbitmap(self.icon_path)
        dialog.title('About')
        dialog.resizable(False, False)
        dialog.transient(self)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=APP_TITLE, font=('Segoe UI', 11, 'bold')).pack(pady=(0, 12))
        ttk.Label(body, text='Written by Gal Shemesh (PacketLauncher)').pack()
        url = 'https://github.com/PacketLauncher'
        link = tk.Label(body, text=url, fg='#0066cc', cursor='hand2', font=('Segoe UI', 9, 'underline'))
        link.pack(pady=(7, 16))
        link.bind('<Button-1>', lambda event: webbrowser.open(url))
        ttk.Button(body, text='OK', command=dialog.destroy).pack()
        dialog.bind('<Return>', lambda event: dialog.destroy())
        dialog.bind('<Escape>', lambda event: dialog.destroy())
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f'+{x}+{y}')
        dialog.grab_set()
        dialog.focus_set()

    def on_drop(self, event, index):
        # Tk's splitlist correctly handles Windows paths enclosed in braces,
        # including directory names containing spaces.
        paths = self.tk.splitlist(event.data)
        if len(paths) != 1:
            messagebox.showwarning(APP_TITLE, 'Please drop only one folder at a time.', parent=self)
            return
        path = os.path.normpath(paths[0])
        if not os.path.isdir(path):
            messagebox.showwarning(APP_TITLE, 'Please drop a folder, not a file.', parent=self)
            return
        self.vars[index].set(path)

    def browse(self, i):
        directory = filedialog.askdirectory(parent=self, initialdir=self.vars[i].get() or os.path.expanduser('~'))
        if directory:
            self.vars[i].set(directory)

    def write_log(self, message):
        self.log.configure(state='normal')
        self.log.insert('end', message + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def start(self):
        raw = [v.get().strip().strip('"') for v in self.vars]
        if not all(raw):
            messagebox.showerror(APP_TITLE, 'Please select all three folders.', parent=self)
            return
        original, modified, save = map(lambda s: Path(os.path.realpath(os.path.abspath(os.path.expandvars(s)))), raw)
        if not original.is_dir() or not modified.is_dir():
            messagebox.showerror(APP_TITLE, 'Original and Modified project folders must be existing directories.', parent=self)
            return
        if same_or_inside(original, modified) or same_or_inside(modified, original):
            messagebox.showerror(APP_TITLE, 'Original and Modified project folders must not overlap.', parent=self)
            return
        if (same_or_inside(save, original) or same_or_inside(save, modified) or same_or_inside(original, save) or same_or_inside(modified, save)):
            messagebox.showerror(APP_TITLE, 'Select an output folder that does not overlap either project folder.', parent=self)
            return
        if save.exists() and not save.is_dir():
            messagebox.showerror(APP_TITLE, 'The save path exists but is not a directory.', parent=self)
            return
        if save.exists() or save.is_symlink():
            messagebox.showerror(APP_TITLE, 'The output folder must not already exist. Please choose a new folder path.', parent=self)
            return
        try:
            preserved_names = parse_preserved_files(self.preserve_var.get())
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
            return
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        self.go.configure(state='disabled')
        self.current_save = save
        self.status.set('Cleaning...')
        self.write_log(f'Original: {original}\nModified: {modified}\nOutput: {save}')
        threading.Thread(target=self.worker, args=(original, modified, save, preserved_names), daemon=True).start()

    def worker(self, original, modified, save, preserved_names):
        try:
            run_cleaning(original, modified, save, lambda msg: self.events.put(('log', msg)), preserved_names)
            self.events.put(('done', None))
        except Exception as exc:
            self.events.put(('error', str(exc)))

    def show_completion(self):
        dialog = tk.Toplevel(self)
        dialog.title(APP_TITLE)
        if self.icon_image is not None:
            dialog.iconphoto(False, self.icon_image)
        if os.name == 'nt' and os.path.isfile(self.icon_path):
            dialog.iconbitmap(self.icon_path)
        dialog.resizable(False, False)
        dialog.transient(self)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Cleaned modified folder created successfully.').pack(pady=(0, 18))
        buttons = ttk.Frame(body)
        buttons.pack(fill='x')

        def open_folder():
            dialog.destroy()
            try:
                os.startfile(str(self.current_save))
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f'Could not open output folder:\n{exc}', parent=self)

        ttk.Button(buttons, text='Open Folder', command=open_folder).pack(side='left')
        ttk.Button(buttons, text='OK', command=dialog.destroy).pack(side='right')
        dialog.bind('<Return>', lambda event: dialog.destroy())
        dialog.bind('<Escape>', lambda event: dialog.destroy())
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f'+{x}+{y}')
        dialog.grab_set()
        dialog.focus_set()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'log':
                    self.write_log(value)
                elif kind == 'done':
                    self.status.set('Ready')
                    self.go.configure(state='normal')
                    self.show_completion()
                elif kind == 'error':
                    self.status.set('Ready — error')
                    self.go.configure(state='normal')
                    self.write_log('ERROR: ' + value)
                    messagebox.showerror(APP_TITLE, value, parent=self)
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == '__main__':
    if TkinterDnD is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, 'Folder drag-and-drop requires tkinterdnd2.\n\nInstall it with:\npy -m pip install tkinterdnd2', parent=root)
        root.destroy()
    else:
        Application().mainloop()
