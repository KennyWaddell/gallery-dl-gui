#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_MENU_DIR="$HOME/.local/share/applications"

mkdir -p "$BIN_DIR" "$APP_MENU_DIR"

cp "$APP_DIR/gallery_dl_gui.py" "$BIN_DIR/gallery-dl-gui"
chmod +x "$BIN_DIR/gallery-dl-gui"

cat > "$APP_MENU_DIR/gallery-dl-gui.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Gallery-DL GUI
Comment=Interfaz ligera en Tkinter para gallery-dl
Exec=$BIN_DIR/gallery-dl-gui
Icon=image-x-generic
Terminal=false
Categories=Network;Graphics;
EOF

echo "Instalado correctamente en $BIN_DIR/gallery-dl-gui"
if ! command -v gallery-dl >/dev/null 2>&1; then
    echo "Aviso: 'gallery-dl' no esta en tu PATH. Instalalo antes de usar la GUI."
fi
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "Nota: agrega '$BIN_DIR' a tu PATH para ejecutar 'gallery-dl-gui' desde la terminal."
fi
