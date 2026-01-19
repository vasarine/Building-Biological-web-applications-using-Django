# Course Project: "Building Biological Web Applications Using Django"
**Author:** Vasarė Petrulaitytė

This project is a Django-based web application that enables convenient use of three **HMMER** tools (`hmmbuild`, `hmmsearch`, `hmmemit`).

## Contents
- [Main Features](#main-features)
- [Requirements](#requirements)
- [HMMER Installation](#hmmer-installation)
- [Installation and Running](#installation-and-running)

## Main Features
- **HMMBUILD:** generates an HMM profile from a multiple sequence alignment (MSA);
- **HMMSEARCH:** evaluates sequence similarity against a selected HMM profile;
- **HMMEMIT:** generates sequences from an HMM profile.

### Additional Capabilities
- Integration with Pfam and InterPro databases using autocomplete search
- Asynchronous task execution using Celery and Redis
- Project management with three visibility levels (Private / Link / Public)
- Project sharing with other users
- Project history tracking
- Automatic cleanup of temporary data

## Requirements
- **Python 3.10+**
- **Django 5.x**
- **HMMER 3.x**
- **Redis server**

## HMMER Installation

- **macOS (Homebrew):**
```bash
brew install hmmer
```

- **Ubuntu/Debian:**
```bash
sudo apt-get update && sudo apt-get install -y hmmer
```

- **Windows:**
```bash
conda install -c bioconda hmmer
```

## Installation and Running

1. **Clone the repository:**
```bash
git clone https://github.com/vasarine/Building-Biological-web-applications-using-Django.git
cd Building-Biological-web-applications-using-Django
```

2. **Create and activate a virtual environment**

   - **macOS / Linux:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   - **Windows:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install project dependencies:**
```bash
pip install -r requirements.txt
```

4. **Apply database migrations:**
```bash
python manage.py migrate
```

5. **Run the application (requires 4 separate terminals):**

   **Terminal 1 - Django development server:**
   ```bash
   source venv/bin/activate  # macOS/Linux
   # venv\Scripts\activate   # Windows
   python manage.py runserver
   ```

   **Terminal 2 - Celery worker:**
   ```bash
   source venv/bin/activate  # macOS/Linux
   # venv\Scripts\activate   # Windows
   celery -A biologine_aplikacija worker -l info
   ```

   **Terminal 3 - Celery Beat (scheduled tasks):**
   ```bash
   source venv/bin/activate  # macOS/Linux
   # venv\Scripts\activate   # Windows
   celery -A biologine_aplikacija beat -l info
   ```

   **Terminal 4 - Redis server:**
   ```bash
   redis-server
   ```

The application will be available at: http://127.0.0.1:8000
