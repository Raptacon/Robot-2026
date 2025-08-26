grep -qxF 'cd /raptacon' /config/.bashrc || echo "cd /raptacon" >> /config/.bashrc
echo $(pacman -Syu vscode --noconfirm)
