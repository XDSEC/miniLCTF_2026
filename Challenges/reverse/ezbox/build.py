"""Build script for ezbox CTF challenge.
Usage: uv run python build.py
Output: dist/ezbox (Linux) or dist/ezbox.exe (Windows)
"""
import subprocess
import sys
import platform

NAME = 'ezbox'
ENTRY = 'main.py'
DATA = 'levels:levels'


def main():
    print(f'Building {NAME} on {platform.system()}...')
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile', ENTRY,
        '--add-data', DATA,
        '--name', NAME,
        '--distpath', 'dist',
        '--clean',
    ]
    subprocess.run(cmd, check=True)
    print(f'Done: dist/{NAME}{".exe" if platform.system() == "Windows" else ""}')


if __name__ == '__main__':
    main()
