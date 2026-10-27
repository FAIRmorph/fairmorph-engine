# Development Environment Setup Guide

This guide will walk you through setting up your local machine to develop, build, and run this application across **Ubuntu (Linux)**, **macOS**, and **Windows**.

---

## 📋 Prerequisites Overview

Your environment requires four core runtimes:
- **Node.js** (v18+) – Frontend engine (Svelte)
- **Rust** (stable toolchain) – Native OS backend engine (Tauri)
- **Python** (v3.10+) – Data processing / sidecar scripts
- **VS Code** – Recommended IDE with pre-configured extensions

---

## 🐧 1. Ubuntu / Debian Setup

### Step 1: Install System Build Tools & Tauri Dependencies
Tauri requires native C build tools and WebKit libraries on Linux.

```bash
sudo apt update && sudo apt install -y \
  build-essential \
  curl \
  wget \
  file \
  libssl-dev \
  libgtk-3-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev \
  libwebkit2gtk-4.1-dev \
  javascriptcoregtk-4.1-dev
```

### Step 2: Install Node.js & Python
```bash
sudo apt install -y nodejs npm python3 python3-pip python3-venv
```

### Step 3: Install Rust Toolchain
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
```

### Step 4: Install VS Code (Native APT Repository)
*Avoid using Snap or Flatpak for VS Code to prevent permission sandboxing issues with local toolchains.*

```bash
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -D -o root -g root -m 644 packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | sudo tee /etc/apt/sources.list.d/vscode.list > /dev/null

sudo apt update && sudo apt install -y code
```

---

## 🍎 2. macOS Setup

### Step 1: Install Xcode Command Line Tools
Required for native compilation of C and Rust libraries on macOS.

```bash
xcode-select --install
```

### Step 2: Install Homebrew (Package Manager)
If Homebrew is not already installed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Step 3: Install Runtimes & VS Code via Homebrew
```bash
brew install node python rust visual-studio-code
```

*Note: macOS uses native WebKit (Safari), so no extra WebKit libraries are required for Tauri.*

---

## 🪟 3. Windows Setup

### Step 1: Install C++ Build Tools
Tauri requires Microsoft Visual Studio C++ Build Tools on Windows.

1. Download the [Visual Studio Installer](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
2. Run the installer and select **Desktop development with C++**.
3. Ensure **MSVC v143 - VS 2022 C++ x64/x86 build tools** and **Windows 10/11 SDK** are checked in the installation details.
4. Click **Install** and reboot your system when complete.

### Step 2: Install Package Manager & Runtimes (winget)
Open **PowerShell** as Administrator and run:

```powershell
# Install Node.js, Python, and VS Code
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.11
winget install Microsoft.VisualStudioCode
```

### Step 3: Install Rust Toolchain
1. Download `rustup-init.exe` from [rustup.rs](https://rustup.rs/).
2. Run `rustup-init.exe` and select option **1 (Default installation)**.

---

## 🚀 4. Project Initialization (All Platforms)

Once your platform dependencies and VS Code are installed:

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/your-repo.git
cd your-repo
```

### 2. Set Up Python Virtual Environment
```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 3. Install Node (Svelte) Dependencies
```bash
npm install
```

### 4. Launch Project in VS Code
```bash
code .
```
When opened, VS Code will prompt you to install the recommended extensions defined in `.vscode/extensions.json`. Click **Install All**.

---

## 🛠️ Verification & Running Dev Server

To verify that your entire polyglot environment is configured properly, launch the Tauri development server:

```bash
npm run tauri dev
```

This command will:
1. Compile the Svelte frontend via Vite.
2. Build the Rust backend via Cargo.
3. Launch the desktop application window with live-reload enabled.