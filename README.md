# BillHQ

A terminal-based bill management app with Swiss QR-bill support. Built with [Textual](https://github.com/Textualize/textual).

![Python](https://img.shields.io/badge/python-3.11+-blue)

## Features

- Manage bills (create, edit, pay, delete)
- Swiss QR-bill generation and scanning (via webcam or image/PDF)
- Multi-language UI (11 languages)
- Search, filtering, and summary statistics
- Customizable settings (date format, currency, sorting, logging)

## Install

```bash
python -m venv venv
source venv/bin/activate.fish   # or venv/bin/activate for bash/zsh
pip install -r requirements.txt

# needed for QR scanning (optional)
sudo pacman -S zbar             # Arch
sudo apt install libzbar0       # Debian/Ubuntu
```

## Run
```bash
python app.py
```

## Single-file executable
The Linux executable has Python and all libraries inside, so nothing needs to be installed. Put it anywhere, make it executable and start it from a terminal:

```bash
chmod +x BillHQ
./BillHQ
```

To scan bills from a file it uses `zenity` or `kdialog`, and QR bills need fonts on the system. Most desktops already have both.

To build it yourself, start Docker and run this. It writes `dist/BillHQ` and builds on Debian 12, so the file also runs on older distros (glibc 2.36 or newer):

```bash
./packaging/build_linux.sh
```

The version number is in `appdata/version.py`.

## Tests
```bash
pip install -r requirements-dev.txt
pytest
```

## Data Location
| What | Where | Notes |
| ---- | ----- | ----- |
| Bills and templates | `~/Documents/BillHQ/` | Change it under Settings, "Data folder". It can be anywhere. |
| Settings | `~/.config/BillHQ/settings.toml` | Also remembers the data folder. Only your user account can open this folder. |
| Log | `~/.config/BillHQ/log` | Same folder as the settings. |

If `XDG_CONFIG_HOME` is set, the settings and log are in `$XDG_CONFIG_HOME/BillHQ/` instead. If BillHQ can't start because of its data folder, change `data_folder` in `settings.toml` by hand.

BillHQ never creates or copies anything in the data folder on its own. When you create or open bills and files are missing from it, it asks whether to create them there from `templates/`. Files that are already there are kept.

Changing the folder doesn't move your files, so copy them over yourself if you want to keep using them.

## Project layout
```
app.py            entry point
appdata/          data layer: bills and CSV files, QR bills, translations, logging
ui/               Textual app, the bill form, dialogs and styles.tcss
ui/screens/       one module per area of the app
templates/        starter CSV files for a new data folder
packaging/        builds the single-file executable
tests/            pytest suite
```

**Recipient** (`r*` columns, `recipientList.csv`) gets the money, "Payable to" on a QR bill. **Payer** (`p*` columns, `payerList.csv`) pays, "Payable by".

## Usage
| Key     | Action      |
| ------- | ----------- |
| Up/Down | Navigate    |
| mouse wheel | dito |
| Enter  | Select/expand|
| mouse click | dito |
| Esc | Go back |
| Ctrl+Q | Quit |


## Languages
You can choose one of the following languages:

- English
- German
- Swiss German
- Italian
- French
- Romansh
- Serbian
- Russian
- Japanese
- Chinese
- **Fortnite**

**To add a Language:** add a column to `languages.csv`, and then the code to `LANG_CODES` and `LANG_NAMES` in `appdata/languages.py`. Empty cells fall back to English or just the key name.

## Functionality
- **All bills:** lists your bills with unpaid ones on top. Use the search bar to find a bill, then open it to generate its QR bill, mark it as paid, edit it or delete it.
- **New bill:** fill in the form by hand, or use a saved recipient and payer to skip the typing.
- **Scan bill:** reads a Swiss QR bill from your webcam, an image or a PDF, then fills in the form for you to check and save. It only reads Swiss QR bills, not other QR codes.
- **QR generator:** creates a Swiss QR bill as an image and opens it in your image viewer. This only works for bills in CHF or EUR.
- **Summary:** shows your totals and upcoming bills.
- **Manage:** add or delete saved recipients and payers.
- **Settings:** language, date format, default currency and country, sorting, logging and where your data is stored.

