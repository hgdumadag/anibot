$env:PYTHONPATH = "src"
python -m uvicorn anibot.main:app --host 127.0.0.1 --port 8000
