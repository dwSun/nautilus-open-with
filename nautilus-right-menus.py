#!/usr/bin/python3
import logging
import os
import shlex
import subprocess
from urllib.parse import unquote, urlparse


def _load_shell_env():
    """加载 Fish shell 的环境变量，使通过 Nautilus 启动的程序能继承这些变量。

    Nautilus 由 GNOME Session 启动，不经过 shell 的初始化流程，
    因此 ~/.config/fish/config.fish 中设置的 PATH、GOPATH、ANDROID_HOME 等
    环境变量不会传递给通过右键菜单启动的程序。
    此函数在模块加载时运行一次，将 Fish login shell 的环境变量合并到当前进程。
    """
    try:
        result = subprocess.run(
            ["fish", "-l", "-c", "env"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logging.debug(
                "fish -l -c env returned %d: %s",
                result.returncode,
                result.stderr.strip(),
            )
            return

        # 需要跳过的 Fish 内部变量
        skip_vars = {
            "SHLVL",
            "_",
            "fish_pid",
            "fish_killring",
            "history",
            "fish_user_paths",
            "fish_function_path",
            "fish_complete_path",
        }

        current_env = dict(os.environ)
        loaded_count = 0
        for line in result.stdout.splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key in skip_vars or key.startswith("fish_"):
                continue
            # 只在当前环境没有该变量，或值不同时更新
            if key not in current_env or current_env[key] != value:
                os.environ[key] = value
                loaded_count += 1
                logging.debug("Loaded env from fish: %s=%s", key, value)

        if loaded_count:
            logging.info(
                "Loaded %d environment variables from Fish shell", loaded_count
            )
    except FileNotFoundError:
        logging.debug("fish not found, skipping shell env loading")
    except subprocess.TimeoutExpired:
        logging.debug("fish -l -c env timed out after 5s")
    except OSError as e:
        logging.debug("Failed to load fish env: %s", e)


# 模块加载时立即加载 Fish shell 环境变量
_load_shell_env()

from gi import require_version

require_version("Nautilus", "4.1")

from gi.repository import Gdk, GLib, GObject, Gtk, Nautilus

if os.environ.get("NAUTILUS_DEBUG", "False") == "True":
    logging.basicConfig(level=logging.DEBUG)


class NautilusMenu(GObject.GObject, Nautilus.MenuProvider):
    """统一的 Nautilus 右键菜单扩展类"""

    # 两个接口的 MenuItem name 分别用 Sel/Bg 前缀区分。
    # Nautilus 每次刷新扩展菜单都会成对调用 get_file_items(当前选区) +
    # get_background_items(当前目录)，不加区分的话两处的 name 会生成同名
    # action（extension_extensions_N_...）互相覆盖，导致菜单项显示重复/错乱。
    _name_tag_selected = "Sel"
    _name_tag_background = "Bg"

    def __init__(self):
        super().__init__()

        self.display = Gdk.Display.get_default()
        self.clipboard = self.display.get_clipboard()
        self.primary_clipboard = self.display.get_primary_clipboard()
        self.selected_files = {}

        self.config = {
            "items": {"path": True, "name": True, "content": True},
            "selections": {"clipboard": True, "primary": True},
            "shortcuts": {
                "path": "<Ctrl><Shift>C",
                "name": "<Ctrl><Shift>D",
                "content": "<Ctrl><Shift>G",
            },
            "separator": ", ",
            "escape_value_items": False,
            "escape_value": False,
            "name_ignore_extension": False,
        }

        self.allow_copy_content = [
            "application/x-shellscript",
            "application/json",
        ]

        app = Gtk.Application.get_default()
        app.connect("window-added", self._window_added)
        app.connect("window-removed", self._window_removed)

    def _window_added(self, application, window):
        for key, shortcut_str in self.config["shortcuts"].items():
            if shortcut_str:
                action = Gtk.CallbackAction.new(self._shortcuts_handler)
                shortcut = Gtk.Shortcut.new(
                    Gtk.ShortcutTrigger.parse_string(shortcut_str), action
                )
                shortcut.set_arguments(GLib.Variant.new_string(key))
                window.add_shortcut(shortcut)

    def _window_removed(self, application, window):
        window_id = window.get_id()
        if window_id in self.selected_files:
            del self.selected_files[window_id]

    def _shortcuts_handler(self, window, key):
        action = GLib.Variant.get_string(key)
        window_id = window.get_id()
        action_function = {
            "path": self._copy_paths,
            "name": self._copy_names,
            "content": self._copy_content,
        }[action]
        if len(self.selected_files[window_id]) > 0 and action_function:
            action_function(None, self.selected_files[window_id])

    def get_file_items(self, *args):
        files = args[-1]
        # Nautilus 每次刷新扩展菜单都会调用本接口（带当前选区），
        # 即使这次弹的是背景菜单；空选区时直接返回空列表。
        if not files:
            return []

        app = Gtk.Application.get_default()
        window = app.get_active_window()
        self.selected_files[window.get_id()] = files

        return self._build_menu_items(files, NautilusMenu._name_tag_selected)

    def get_background_items(self, *args):
        # 总是为当前目录构建菜单（选区是否非空与此无关）。
        file = args[-1]

        app = Gtk.Application.get_default()
        window = app.get_active_window()
        if window:
            self.selected_files[window.get_id()] = [file]

        return self._build_menu_items([file], NautilusMenu._name_tag_background)

    def _build_menu_items(self, files, name_tag):
        def mkname(key):
            return f"NautilusMenu::{name_tag}::{key}"

        items = []

        # ---------- Open in... 子菜单 ----------
        edit_menu = Nautilus.Menu()
        edit_parent = Nautilus.MenuItem(
            name=mkname("OpenIn"),
            label="Open in...",
        )
        edit_parent.set_submenu(edit_menu)

        self._add_editor_items(edit_menu, files, mkname)
        items.append(edit_parent)

        # ---------- Copy 子菜单 ----------
        copy_parent = Nautilus.MenuItem(
            name=mkname("Copy"),
            label="Copy ...",
        )
        copy_menu = Nautilus.Menu()
        copy_parent.set_submenu(copy_menu)

        plural = len(files) > 1
        filtered_files = [
            f
            for f in files
            if f.get_mime_type() in self.allow_copy_content
            or f.get_mime_type().startswith("text/")
        ]

        if plural:
            if self.config["items"]["path"]:
                p = Nautilus.MenuItem(
                    name=mkname("CopyFullName"), label="Copy Full Names"
                )
                p.connect("activate", self._copy_paths, files)
                copy_menu.append_item(p)

            if self.config["items"]["name"]:
                n = Nautilus.MenuItem(
                    name=mkname("CopyFileName"), label="Copy File Names"
                )
                n.connect("activate", self._copy_names, files)
                copy_menu.append_item(n)

            if self.config["items"]["path"]:
                d = Nautilus.MenuItem(
                    name=mkname("CopyDirPath"), label="Copy Dir Paths"
                )
                d.connect("activate", self._copy_dirpaths, files)
                copy_menu.append_item(d)

            if self.config["items"]["content"] and filtered_files:
                c = Nautilus.MenuItem(
                    name=mkname("CopyContents"), label="Copy Contents"
                )
                c.connect("activate", self._copy_content, filtered_files)
                copy_menu.append_item(c)
        else:
            if len(files) == 0:
                return items

            if self.config["items"]["path"]:
                p = Nautilus.MenuItem(
                    name=mkname("CopyFullName"), label="Copy Full Name"
                )
                p.connect("activate", self._copy_paths, files)
                copy_menu.append_item(p)

            if self.config["items"]["name"]:
                n = Nautilus.MenuItem(
                    name=mkname("CopyFileName"), label="Copy File Name"
                )
                n.connect("activate", self._copy_names, files)
                copy_menu.append_item(n)

            if self.config["items"]["path"]:
                d = Nautilus.MenuItem(
                    name=mkname("CopyDirPath"), label="Copy Dir Path"
                )
                d.connect("activate", self._copy_dirpaths, files)
                copy_menu.append_item(d)

            if self.config["items"]["content"] and filtered_files:
                c = Nautilus.MenuItem(
                    name=mkname("CopyContent"), label="Copy Content"
                )
                c.connect("activate", self._copy_content, filtered_files)
                copy_menu.append_item(c)

        items.append(copy_parent)
        return items

    def _add_editor_items(self, menu, files, mkname):
        if len(files) != 1:
            return

        fileinfo = files[0]
        path = fileinfo.get_location().get_path()

        # open_directory=True：右键文件时以所在目录为目标（Cursor/VSCode/gitg/Ghostty/Kitty/Warp/gThumb）
        # extra_args：额外命令行参数
        # cwd_flag：通过命令行参数指定工作目录的标志/前缀；为 None 时把 target 作为位置参数传入。
        #           - Ghostty 使用 --working-directory= 显式传入工作目录
        #           - Warp 通过 warp://action/new_window?path=<dir> URL 触发其内置 URL handler
        #             （系统 MIME x-scheme-handler/warp 已注册到 dev.warp.Warp.desktop），强制开**新窗口**；
        #             如果改用 /new_tab，则会复用现有窗口加 tab。
        # 注：Cursor / VSCode 在 extra_args 里加 "-n"（--new-window）以避开其"恢复上次窗口"行为，
        #     否则会忽略命令行路径，继续恢复上次的 workspace（实测现象：不管右键哪个目录都打开同一个项目）。
        editors = [
            ("Cursor", "/usr/bin/cursor", "Edit in Cursor", True, ["-n"], None),
            ("VSCode", "/usr/bin/code", "Edit in VSCode", True, ["-n"], None),
            ("Zed", "/usr/bin/zeditor", "Edit in Zed", False, ["-n"], None),
            ("gitg", "/usr/bin/gitg", "Open in gitg", True, [], None),
            #(
            #    "Ghostty",
            #    "/usr/bin/ghostty",
            #    "Run in Ghostty",
            #    True,
            #    [],
            #    "--working-directory=",
            #),
            (
                "Kitty",
                "/usr/bin/kitty",
                "Run in Kitty",
                True,
                [],
                "--working-directory=",
            ),

            #(
            #    "Warp",
            #    "/usr/bin/warp-terminal",
            #    "Run in Warp",
            #    True,
            #    [],
            #    "warp://action/new_window?path=",
            #),
            ("gThumb", "/usr/bin/gthumb", "View in gThumb", True, [], None),
        ]

        for name, cmd, label, open_directory, extra_args, cwd_flag in editors:
            item = Nautilus.MenuItem(name=mkname(f"edit_{name}"), label=label)
            item.connect(
                "activate",
                self._run_editor,
                cmd,
                path,
                open_directory,
                extra_args,
                cwd_flag,
            )
            menu.append_item(item)

    def _run_editor(
        self, menu, cmd, path, open_directory, extra_args=None, cwd_flag=None
    ):
        extra_args = extra_args or []
        if open_directory:
            target = path if os.path.isdir(path) else os.path.dirname(path)
        else:
            target = path

        cwd = target if os.path.isdir(target) else os.path.dirname(target)

        if cwd_flag:
            # 通过命令行参数指定工作目录（如 Ghostty 的 --working-directory=/path）
            subprocess.Popen([cmd] + extra_args + [f"{cwd_flag}{cwd}"], cwd=cwd)
        else:
            subprocess.Popen([cmd] + extra_args + [target], cwd=cwd)

    def _get_file_abs_path(self, fileinfo):
        return fileinfo.get_location().get_path()

    def _copy_paths(self, menu, files):
        paths = [
            os.path.abspath(
                os.path.join(
                    urlparse(f.get_activation_uri()).netloc,
                    unquote(urlparse(f.get_activation_uri()).path),
                )
            )
            for f in files
        ]
        self._copy_value(paths)

    def _copy_names(self, menu, files):
        names = [
            unquote(os.path.basename(urlparse(f.get_activation_uri()).path))
            for f in files
        ]
        if self.config["name_ignore_extension"]:
            names = [os.path.splitext(n)[0] for n in names]
        self._copy_value(names)

    def _copy_content(self, menu, files):
        content = []
        for f in files:
            p = urlparse(f.get_activation_uri())
            p = os.path.abspath(os.path.join(p.netloc, unquote(p.path)))
            with open(p, "r") as fh:
                content.append(fh.read())
        self._copy_value(content)

    def _copy_dirpaths(self, menu, files):
        dirs = [
            os.path.dirname(
                os.path.abspath(
                    os.path.join(
                        urlparse(f.get_activation_uri()).netloc,
                        unquote(urlparse(f.get_activation_uri()).path),
                    )
                )
            )
            for f in files
        ]
        self._copy_value(dirs)

    def _copy_value(self, value):
        if not value:
            return
        if self.config["escape_value_items"]:
            value = [shlex.quote(v) for v in value]
        text = self.config["separator"].join(value)
        if self.config["escape_value"]:
            text = shlex.quote(text)
        if self.config["selections"]["clipboard"]:
            self.clipboard.set(text)
        if self.config["selections"]["primary"]:
            self.primary_clipboard.set(text)
