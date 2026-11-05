# BillHQ
Bill Organizer for Swiss Bills. Either you're broke, autistic or just need a tool to organize bills and plan your payments.

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

## Tests
```bash
pip install -r requirements-dev.txt
pytest
```

## Where your data lives
| What | Where | Notes |
| ---- | ----- | ----- |
| Bills and templates | `~/Documents/BillHQ/` | Change it under Settings, "Data folder". It can be anywhere. |
| Settings and log | `~/.config/BillHQ/` | Only your user account can open this folder. It also remembers the data folder. |

If the data folder is missing or empty, BillHQ creates it and copies in the sample files from `templates/`. A folder with anything in it is left as it is. Changing the folder doesn't move your files: the old folder stays untouched, so copy your CSV files over first if you want to keep using them.

If you used an older version, the first start copies your bills and settings from `userdata/`. You can delete that folder afterwards.

## Project layout
```
app.py            entry point
appdata/          data layer: bills and CSV files, QR bills, translations, logging
ui/               Textual app, the bill form, dialogs and styles.tcss
ui/screens/       one module per area of the app
templates/        starter CSV files copied into a new data folder
tests/            pytest suite
```

**Recipient** (`r*` columns, `recipientList.csv`) gets the money, "Payable to" on a QR bill. **Payer** (`p*` columns, `payerList.csv`) pays, "Payable by". Files from older versions (`d*`/`c*` columns, `debitorList.csv`/`creditorList.csv`) convert automatically at startup, and the originals are kept as `*.pre-rename.bak`.

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
- Fortnite

**To add a Language:** add a column to `languages.csv`, and then the code to `LANG_CODES` and `LANG_NAMES` in `appdata/languages.py`. Empty cells fall back to English or just the key name.

## Functionality
man, find it out yourself, it doesn't have that many funcitons other than a search bar, sumary and qr generator as well as a qr code reader (swiss bill qr code, not some generic shit).

