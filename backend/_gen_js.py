import os

JS = None  # Will be loaded from frontend/js/app.js

if __name__ == '__main__':
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'js', 'app.js')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Read {len(content)} chars from app.js')
