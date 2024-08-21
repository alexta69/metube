@echo off

rem Check if Python is installed
where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed. Please install Python and try again.
    pause
    exit /b
)

rem Check if pip is installed
python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo Pip is not installed. Installing Pip...
    powershell Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "get-pip.py"
    python get-pip.py
    del get-pip.py
)

rem Install dependencies
echo Installing dependencies...
pip install pipenv

rem Clone the MeTube repository
echo Cloning the MeTube repository...
git clone https://github.com/alexta69/metube.git
cd metube

rem Install Python dependencies
echo Installing Python dependencies...
pipenv install

rem Build the Angular UI
echo Building the Angular UI...
cd ui
npm install
node_modules\.bin\ng build
cd ..

rem Run the MeTube server
echo Starting the MeTube server...
pipenv run python app\main.py

echo MeTube setup complete!
pause
