"""
scripts/build_static.py — Compile template files to static files for Vercel deployment.
"""
import os
import shutil

def build():
    # Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_path = os.path.join(base_dir, "dashboard", "templates", "index.html")
    static_js_path = os.path.join(base_dir, "dashboard", "static", "main.js")
    static_css_path = os.path.join(base_dir, "dashboard", "static", "style.css")
    
    public_dir = os.path.join(base_dir, "public")
    public_index_path = os.path.join(public_dir, "index.html")
    public_static_dir = os.path.join(public_dir, "static")
    public_js_path = os.path.join(public_static_dir, "main.js")
    public_css_path = os.path.join(public_static_dir, "style.css")
    
    # Create directories if they don't exist
    os.makedirs(public_static_dir, exist_ok=True)
    
    # 1. Read index.html template and compile
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
        
    # Replace Flask url_for with static relative paths
    html = html.replace("{{ url_for('static', filename='style.css') }}", "static/style.css")
    html = html.replace("{{ url_for('static', filename='main.js') }}", "static/main.js")
    
    with open(public_index_path, "w", encoding="utf-8") as f:
        f.write(html)
        
    print(f"✓ Compiled {template_path} -> {public_index_path}")
    
    # 2. Copy static main.js
    shutil.copy2(static_js_path, public_js_path)
    print(f"✓ Copied {static_js_path} -> {public_js_path}")
    
    # 3. Copy static style.css
    shutil.copy2(static_css_path, public_css_path)
    print(f"✓ Copied {static_css_path} -> {public_css_path}")
    
    print("Static build completed successfully!")

if __name__ == "__main__":
    build()
