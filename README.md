# Shift Manager

A Python project for roster and shift management.

## Setup

1. Create a virtual environment:
   ```powershell
   python -m venv venv
   ```
2. Activate the virtual environment:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -e .
   ```

## Streamlit Application

This project includes a Streamlit UI for interactive roster management.

### Running Locally

To run the Streamlit app locally:

1. Ensure your virtual environment is activated.
2. Run the following command from the project root:
   ```powershell
   streamlit run streamlit_app.py
   ```

### Deployment

To deploy to Streamlit Cloud:

1. Push this repository to GitHub.
2. Connect your GitHub account to [Streamlit Cloud](https://share.streamlit.io/).
3. Create a new app, selecting this repository and the `streamlit_app.py` as the main file.
4. Streamlit Cloud will automatically use `requirements.txt` to install dependencies.
