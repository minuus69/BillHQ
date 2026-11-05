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

## Project layout
```
app.py            entry point
appdata/          data layer: bills and CSV files, QR bills, translations, logging
ui/               Textual app, the bill form, dialogs and styles.tcss
ui/screens/       one module per area of the app
userdata/         your bills, templates and settings (bills and templates are not in git)
templates/        example CSV files
tests/            pytest suite
```

In the code, **payee** is who gets the money ("Payable to" on a QR bill) and **payer** is who pays ("Payable by"). In the CSV files they're the `d*` and `c*` columns, stored in `debitorList.csv` and `creditorList.csv`.

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

