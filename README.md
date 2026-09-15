# Nautilus Python 扩展

在 GNOME 文件管理器（Nautilus）右键菜单中，快速用外部程序打开文件夹、查看 Git 仓库或图片，以及复制路径/文件名/文本内容。

扩展脚本位于：

`~/.local/share/nautilus-python/extensions/`

（即本目录。）

---

## 安装与生效

1. 确认 `nautilus-right-menus.py` 已在上述目录中。
2. 安装系统依赖（见下文「依赖」）。
3. **重启 Nautilus** 后菜单才会出现：

```bash
nautilus -q && nautilus &
```

若菜单未出现，可检查是否已安装 `nautilus-python`（或发行版提供的 Nautilus Python 支持包）。

---

## 功能一览

本扩展将所有功能整合在单一 Python 文件中，通过右键菜单提供以下功能：

| 右键菜单文案 | 适用对象 | 调用的程序 |
|-------------|----------|------------|
| **Edit in Cursor** | 文件、文件夹、空白处 | `/usr/bin/cursor`（文件→打开所在目录） |
| **Edit in VSCode** | 同上 | `/usr/bin/code` |
| **Edit in Zed** | 同上 | `/usr/bin/zeditor -n`（文件→打开该文件） |
| **Open in gitg** | 同上 | `/usr/bin/gitg` |
| **Run in Ghostty** | 同上 | `/usr/bin/ghostty --working-directory=<路径>` |
| **Run in Warp** | 同上 | `/usr/bin/warp-terminal warp://action/new_window?path=<路径>` |
| **View in gThumb** | 同上 | `/usr/bin/gthumb` |
| **Copy Full Name / File Name / Dir Path / Content** 等 | 文件、文件夹、空白处（当前目录）；支持多选 | 无（写入剪贴板） |

菜单文案按动作类型分四组：**Edit in**（代码编辑器：Cursor / VSCode / Zed）、**Run in**（终端/shell：Ghostty / Warp）、**Open in**（Git 仓库查看：gitg）、**View in**（图片查看：gThumb）。

---

## 行为规则

**外部程序扩展（Edit in / Run in / Open in / View in）：**

- 一次只能选中 **1 项**；多选时不显示菜单。
- 在文件夹 **空白处** 右键：对 **当前所在目录** 显示与选中文件夹时相同的编辑器菜单（空白处即当前目录）。
- 选中文件夹后右键：Nautilus 会同时调用「文件项」与「背景项」；脚本用 `_file_items_called` 标志避免重复出现两条相同菜单。
- 空白处右键时 Nautilus 会先调用 `get_file_items([])`；扩展对此直接返回空列表，由 `get_background_items` 提供完整菜单。

| 扩展 | 右键选中「文件夹」 | 右键选中「文件」 | 空白处右键 |
|------|------------------|----------------|------------|
| Edit in Cursor / Edit in VSCode / Open in gitg / Run in Ghostty / Run in Warp / View in gThumb | 打开该目录 | 显示；打开**文件所在目录** | 打开当前目录 |
| Edit in Zed | 打开该目录 | 显示；打开**该文件**（cwd 为所在目录） | 打开当前目录 |

**复制路径扩展：**

- 支持多选文件/文件夹。
- 在文件夹空白处右键，复制的是当前目录的信息。

---

## 各功能说明

### 1. 在 Cursor 中编辑（Edit in Cursor）

- 命令：`cursor <目录路径>`
- 对文件右键时传入该文件**所在目录**的路径。

### 2. 在 VSCode 中编辑（Edit in VSCode）

- 命令：`code <目录路径>`
- 对文件右键时传入该文件**所在目录**的路径。

### 3. 在 Zed 中编辑（Edit in Zed）

- 命令：`zeditor -n <路径>`
- `-n` 参数确保以新窗口/标签页打开。
- **文件和文件夹均可**；若为文件，`cwd` 设为该文件所在目录。

### 4. 在 gitg 中打开（Open in gitg）

- 命令：`gitg <目录路径>`
- 用于在图形界面查看 Git 仓库；对文件右键时打开**所在目录**。

### 5. 在 Ghostty 中运行（Run in Ghostty）

- 命令：`ghostty --working-directory=<目录路径>`
- Ghostty 不继承 `cwd`，需通过 `--working-directory` 参数显式指定工作目录。
- 对文件右键时工作目录为**文件所在目录**。

### 6. 在 Warp 中运行（Run in Warp）

- 命令：`warp-terminal warp://action/new_window?path=<目录路径>`
- Warp 终端的 URL scheme 是 `warp`（系统的 MIME `x-scheme-handler/warp` 默认注册到 `dev.warp.Warp.desktop`），Warp 启动器识别 `warp://action/new_window` 路径后**始终开新窗口**，不会复用现有窗口加 tab。
- 如果想要“在现有窗口加 tab”的行为，把 URL 改成 `warp://action/new_tab?path=<dir>` 即可。
- 对文件右键时传 `warp://action/new_window?path=<文件路径>`，Warp 会 fallback 到**文件所在目录**作为新窗口的工作目录。
- `/usr/bin/warp-terminal` 是个 Bash wrapper，实际调用 `/opt/warpdotdev/warp-terminal/warp`。同一个二进制默认进入 Oz CLI 模式，但只要第一个参数是 `warp://` URL，就会被分派到 URL handler（走 GUI）；如果 Warp 以后调整了内部行为，只需修脚本里的 `editors` 列表那一行。
- `warp agent ...` 子命令（`agent run` 等）与本菜单无关，那是另一套 Oz agent 功能。

### 7. 在 gThumb 中查看（View in gThumb）

- 命令：`gthumb <目录路径>`
- 浏览图片目录；对文件右键时打开**所在目录**。

### 8. 复制路径 / 文件名 / 目录 / 内容

不启动外部程序，把信息写入 **剪贴板** 和 **主选择区**（中键粘贴）。

**右键菜单（单选/多选文案不同）：**

| 菜单项 | 作用 |
|--------|------|
| Copy Full Name(s) | 绝对路径 |
| Copy File Name(s) | 文件名（可配置是否去掉扩展名） |
| Copy Dir Path(s) | 所在目录路径 |
| Copy Content(s) | 文件全文（仅 `text/*`、`application/x-shellscript`、`application/json`） |

**快捷键（在 Nautilus 窗口内）：**

| 快捷键 | 作用 |
|--------|------|
| `Ctrl+Shift+C` | 复制路径 |
| `Ctrl+Shift+D` | 复制文件名 |
| `Ctrl+Shift+G` | 复制文本内容 |

多选时，多项之间默认用 `", "` 连接。可在脚本内 `self.config` 中修改分隔符、是否 `shlex.quote`、是否忽略扩展名等。

---

## 依赖

| 类型 | 要求 |
|------|------|
| 文件管理器 | GNOME Nautilus **4.x**（声明 `Nautilus 4.1` API） |
| Python 绑定 | `python-nautilus` / `nautilus-python`（由发行版提供） |
| 外部程序 | 上表中的可执行文件需已安装，且路径与脚本中一致 |

检查命令是否在 PATH 或固定路径：

```bash
which cursor code zeditor gitg ghostty warp-terminal gthumb
ls -l /usr/bin/cursor /usr/bin/code /usr/bin/zeditor /usr/bin/gitg /usr/bin/ghostty /usr/bin/warp-terminal /usr/bin/gthumb
```

若程序安装在其他位置（例如 `~/.local/bin/cursor`），需编辑脚本 `editors` 列表中对应的路径。

---

## 修改可执行文件路径

每个「打开外部程序」的功能都在 `_add_editor_items` 的 `editors` 列表中定义，例如 Cursor：

```python
("Cursor", "/usr/bin/cursor", "Edit in Cursor", True, [], None),
```

把 `"/usr/bin/cursor"` 改成你机器上的实际路径后，保存并重启 Nautilus。

---

## 调试日志

在终端中先导出变量再启动 Nautilus，可在 stderr 看到 `logging.debug` 输出：

```bash
export NAUTILUS_DEBUG=True
nautilus
```

复制路径功能无内置调试开关。

---

## 文件结构

```
extensions/
├── README.md
└── nautilus-right-menus.py       # 整合了所有扩展功能
```

---

## 改进备忘

- [ ] 将硬编码的 `/usr/bin/...` 路径改为 `shutil.which()` 或配置文件，便于不同安装方式。
- [x] 全部外部程序（Cursor / VSCode / Zed / gitg / Ghostty / Warp / gThumb）：支持右键文件，打开所在目录。
