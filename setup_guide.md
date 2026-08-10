# SYBAU VMS - Setup & Handoff Guide

## 📦 What to Share
To transfer this project to your new RTX 4060 Laptop, you need to copy the entire `sybau_test` folder. 

**IMPORTANT: What NOT to copy (to save space):**
- Delete the `.venv/` folder (Python environment, it must be rebuilt on the new PC).
- Delete the `frontend/node_modules/` folder.
- Delete the `__pycache__` folders.

**CRITICAL: What MUST be included:**
- The custom model: `yolo26l.pt` (Make sure this stays in the root of the folder!)
- The video sources: `Videos/` folder (The `.avi` CCTV footage files).

---

## 🛠️ Prerequisites for the New PC
Before running anything, ensure the new PC has the following installed:
1. **Python 3.10+**: Make sure "Add to PATH" is checked during installation.
2. **Node.js (v18+)**: Required for the frontend.
3. **Docker Desktop**: Must be installed and running (for the database, MediaMTX, etc.).
4. **NVIDIA Drivers**: Ensure the RTX 4060 has the latest Game Ready or Studio drivers.
5. **FFmpeg**: Must be installed and added to the Windows PATH. (You can test this by typing `ffmpeg` in a terminal).

---

## 🚀 Installation Commands (Run on New PC)

Open a **PowerShell** terminal in the root of the project folder (`sybau_test`) and run these commands one by one:

### 1. Create and Activate the Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 2. Install GPU-Accelerated PyTorch
*This step is absolutely critical! If you skip this, it will download the CPU version and the AI will lag heavily.*
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### 3. Install Backend Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Install Frontend Dependencies
```powershell
cd frontend
npm install
cd ..
```

---

## ▶️ How to Start the Project

Once everything is installed and Docker Desktop is running in the background, you can start the entire platform with a single command:

```powershell
.\manage.ps1 start
```

**Wait about 30 seconds** for all services to spin up, and then open your browser to:
[http://localhost:5173](http://localhost:5173)

### How to Stop the Project
```powershell
.\manage.ps1 stop
```
