import os

IGNORE_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules"}

for root, dirs, files in os.walk(".", topdown=True):

    dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

    for file in files:
        print(os.path.join(root, file))