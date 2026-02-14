# gunicorn_config.py
bind = "0.0.0.0:10000"
workers = 2
timeout = 120  # 2 minutes (up from 30s default)
worker_class = "sync"
