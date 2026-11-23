@echo off
rem Giong lenh build trong .github/workflows/build.yml. Khong dong goi du lieu nguoi dung (secret.key, credentials, history, sessions).
echo Installing requirements...
pip install -r requirements.txt

echo Building MasterDownloader...
pyinstaller --noconfirm --onefile --windowed --name "MasterDownloader" --collect-submodules gallery_dl App.py

echo Build complete!
echo You can find the application in dist\MasterDownloader.exe
pause
